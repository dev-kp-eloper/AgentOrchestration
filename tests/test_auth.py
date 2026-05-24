import time
import pytest
from fastapi.testclient import TestClient
from src.api.server import create_app

class TestAuthMiddleware:
    def setup_method(self):
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_anonymous_request_denied(self):
        response = self.client.get("/api/v2/agents")
        assert response.status_code == 401
        assert response.text == "Unauthorized"

    def test_invalid_bearer_prefix_denied(self):
        response = self.client.get("/api/v2/agents", headers={"Authorization": "InvalidPrefix xyz"})
        assert response.status_code == 401
        assert response.text == "Unauthorized"

    def test_invalid_token_prefix_denied(self):
        response = self.client.get("/api/v2/agents", headers={"Authorization": "Bearer invalid_prefix_xyz"})
        assert response.status_code == 403
        assert "Invalid token prefix" in response.text

    def test_valid_user_token_allowed(self):
        response = self.client.get("/api/v2/agents", headers={"Authorization": "Bearer ao_user_valid"})
        assert response.status_code == 200

    def test_valid_machine_token_allowed(self):
        response = self.client.get("/api/v2/agents", headers={"Authorization": "Bearer ao_machine_valid"})
        assert response.status_code == 200

    def test_machine_token_destructive_action_forbidden(self):
        response = self.client.delete("/api/v2/agents/some-id", headers={"Authorization": "Bearer ao_machine_valid"})
        assert response.status_code == 403
        assert "Action not allowed for machine tokens" in response.text

    def test_valid_worker_token_allowed(self):
        now = time.time()
        # Format: ao_worker_<nbf>_<exp>_<jti>
        token = f"ao_worker_{now - 10}_{now + 10}_token123"
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

    def test_stale_future_nbf_worker_token_denied(self):
        now = time.time()
        # Token active in future
        token = f"ao_worker_{now + 10}_{now + 20}_token123"
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "Token not active yet" in response.text

    def test_expired_worker_token_denied(self):
        now = time.time()
        # Token expired in past
        token = f"ao_worker_{now - 20}_{now - 10}_token123"
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "Token expired" in response.text

    def test_malformed_worker_token_denied(self):
        token = "ao_worker_notfloat_notfloat_token123"
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "Invalid token format" in response.text

        token_short = "ao_worker_123"
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token_short}"})
        assert response.status_code == 401
        assert "Invalid token format" in response.text

    def test_revoked_worker_token_denied(self):
        now = time.time()
        token = f"ao_worker_{now - 10}_{now + 10}_revoked123"
        
        # Trigger lazy middleware stack compilation in FastAPI by making a dummy call
        self.client.get("/health")
        
        # Traverse middleware stack to find AuthMiddleware and add JTI to revoked_tokens
        curr = self.app.middleware_stack
        auth_inst = None
        while curr:
            if curr.__class__.__name__ == "AuthMiddleware":
                auth_inst = curr
                break
            curr = getattr(curr, "app", None)
            
        if auth_inst:
            auth_inst.revoked_tokens.add("revoked123")
            
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401
        assert "Token revoked" in response.text

    def test_worker_token_destructive_action_forbidden(self):
        now = time.time()
        token = f"ao_worker_{now - 10}_{now + 10}_token123"
        response = self.client.delete("/api/v2/agents/some-id", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403
        assert "Action not allowed for worker tokens" in response.text

    def test_valid_browser_token_allowed(self):
        now = time.time()
        token = f"ao_browser_{now - 10}_{now + 10}_token123"
        response = self.client.get("/api/v2/agents", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
