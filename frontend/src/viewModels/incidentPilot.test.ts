import { describe, expect, it } from 'vitest';
import type {
  AgentRunState,
  BackendAttempt,
  BackendVerification,
  SafetyAssessment,
} from '../types/incidentPilot';
import {
  buildIncidentView,
  FALLBACK_CONFIG,
  mapAttempt,
  mapSafetyAssessment,
  mapVerification,
} from './incidentPilot';

const agent: AgentRunState = {
  run_id: 'inc-demo',
  goal: 'Restore service',
  started_at: '2026-09-13T12:00:00Z',
  running: false,
  status: 'resolved',
  phase: 'complete',
  attempt: 1,
  max_attempts: 3,
  reason: null,
};

describe('IncidentPilot view models', () => {
  it('renders no-incident as a successful no-op without invented attempts', () => {
    const view = buildIncidentView(
      [],
      'no_incident',
      'Live telemetry is within incident thresholds.',
      'healthy',
      { ...agent, status: 'no_incident', attempt: 0 },
      FALLBACK_CONFIG,
    );

    expect(view.attempts).toEqual([]);
    expect(view.summary.finalOutcome).toBe('NO INCIDENT');
    expect(view.summary.finalVerification).toBe('Not required');
    expect(view.resolutionBanner.text).toContain('NO INCIDENT');
  });

  it('shows the backend policy rule and proves a safety challenge did not execute', () => {
    const assessment: SafetyAssessment = {
      assessment_id: 'safe-demo',
      executed: false,
      decision: {
        checked: true,
        allowed: false,
        rule_id: 'replica_upper_bound',
        reason: 'Requested 20 replicas; configured maximum is 3.',
        action: 'scale_service',
        target: 20,
        namespace: 'incidentpilot',
        bounds: { min_replicas: 1, max_replicas: 3 },
        budget: { attempt: 1, maximum: 3, remaining_after_this_attempt: 2 },
      },
      events: [],
    };

    const safety = mapSafetyAssessment(assessment, FALLBACK_CONFIG);
    expect(safety.verdict).toBe('BLOCKED');
    expect(safety.ruleId).toBe('replica_upper_bound');
    expect(safety.reason).toContain('maximum is 3');
    expect(safety.executed).toBe('No');
  });

  it('keeps partial verification and named checks visible', () => {
    const verification: BackendVerification = {
      status: 'partial',
      recovered: false,
      reason: 'Latency improved, but error rate remains above the recovery SLO.',
      checks: [
        { name: 'error_rate_slo', passed: false, observed: 0.12, expected: { maximum: 0.05 }, message: 'Error rate is too high.' },
        { name: 'latency_slo', passed: true, observed: 180, expected: { maximum_ms: 200 }, message: 'Latency recovered.' },
      ],
      samples: [
        { error_rate: 0.12, latency_ms: 180, status: 'down' },
        { error_rate: 0.11, latency_ms: 170, status: 'down' },
      ],
      metrics_before: { error_rate: 0.7, latency_ms: 1000, status: 'down' },
      metrics_after: { error_rate: 0.11, latency_ms: 170, status: 'down' },
      deltas: { error_rate: -0.59, latency_ms: -830 },
    };

    const view = mapVerification(verification);
    expect(view.status).toBe('PARTIAL');
    expect(view.samples).toBe('2 fresh samples');
    expect(view.checks).toHaveLength(2);
    expect(view.checks.find((check) => check.id === 'error_rate_slo')?.passed).toBe(false);
  });

  it('keeps diagnosis separate from the action rationale', () => {
    const attempt: BackendAttempt = {
      attempt: 1,
      diagnosis: {
        probable_cause: 'bad_deployment',
        summary: 'The current version correlates with the error spike.',
        confidence: 0.94,
      },
      proposal: {
        action: 'rollback_deployment',
        target: 'v41',
        reason: 'Deployment history contains a known-good predecessor.',
        confidence: 0.92,
      },
      safety: {
        checked: true,
        allowed: true,
        rule_id: 'rollback_target_allowed',
        reason: 'v41 is a known previous version.',
        action: 'rollback_deployment',
        target: 'v41',
      },
      action_result: {
        action: 'rollback_deployment',
        success: true,
        status: 'success',
        message: 'Rollback completed.',
        executed: true,
      },
      evidence: [{ id: 'deploy-1', source: 'history', signal: 'version_change', detail: 'v42 followed v41.' }],
    };

    const view = mapAttempt(attempt, 1, 'bad_deployment', FALLBACK_CONFIG);
    expect(view.inspector.summary.diagnosisCause).toBe('Bad Deployment');
    expect(view.inspector.summary.diagnosisSummary).toContain('correlates');
    expect(view.inspector.decision.reason).toContain('known-good predecessor');
    expect(view.inspector.safety.reason).toContain('known previous version');
  });
});
