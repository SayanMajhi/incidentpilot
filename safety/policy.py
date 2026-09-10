class SafetyPolicy:
    MAX_REPLICAS = 10

    def allows(self, action, **kwargs):
        if action == "restart_service":
            return True

        if action == "scale_service":
            replicas = kwargs.get("replicas")
            return replicas is not None and 1 <= replicas <= self.MAX_REPLICAS

        if action == "delete_database":
            return False

        return False


policy = SafetyPolicy()