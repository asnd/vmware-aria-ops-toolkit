"""Integration tests for API endpoints."""


class TestAuthEndpoints:
    """Test authentication endpoints."""

    def test_login_success(self, test_client, auth_test_password):
        """Test successful login."""
        response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": auth_test_password},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

    def test_login_invalid_credentials(self, test_client):
        """Test login with invalid credentials."""
        response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "admin", "password": "wrong-password"},
        )

        assert response.status_code == 401

    def test_get_current_user(self, test_client, auth_test_password):
        """Test getting current user info."""
        # First login
        login_response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "operator", "password": auth_test_password},
        )
        token = login_response.json()["access_token"]

        # Get user info
        response = test_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "operator"
        assert "operator" in data["roles"]


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check(self, test_client):
        """Test basic health check (unauthenticated)."""
        response = test_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_root_endpoint(self, test_client):
        """Test root endpoint."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


class TestJobEndpoints:
    """Test job tracking endpoints."""

    def test_list_jobs_requires_auth(self, test_client):
        """Test that listing jobs requires authentication."""
        response = test_client.get("/api/v1/jobs")

        assert response.status_code == 401

    def test_list_jobs_authenticated(self, test_client, auth_test_password):
        """Test listing jobs with authentication."""
        # Login
        login_response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "operator", "password": auth_test_password},
        )
        token = login_response.json()["access_token"]

        # List jobs
        response = test_client.get(
            "/api/v1/jobs",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "total" in data

    def test_get_job_not_found(self, test_client, auth_test_password):
        """Test getting non-existent job."""
        # Login
        login_response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "operator", "password": auth_test_password},
        )
        token = login_response.json()["access_token"]

        # Get non-existent job
        response = test_client.get(
            "/api/v1/jobs/job_nonexistent",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


class TestSiteEndpoints:
    """Test site inventory endpoints."""

    def test_list_sites_requires_auth(self, test_client):
        """Test that listing sites requires authentication."""
        response = test_client.get("/api/v1/sites")

        assert response.status_code == 401

    def test_get_site_not_found(self, test_client, auth_test_password):
        """Test getting non-existent site."""
        # Login
        login_response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "operator", "password": auth_test_password},
        )
        token = login_response.json()["access_token"]

        # Get non-existent site
        response = test_client.get(
            "/api/v1/sites/non-existent",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404


class TestNSXTEndpoints:
    """Test NSX-T operation endpoints."""

    def test_create_segment_requires_auth(self, test_client):
        """Test that creating segment requires authentication."""
        response = test_client.post(
            "/api/v1/nsxt/test-site/segments",
            json={
                "name": "test-segment",
                "tier1_gateway": "/infra/tier-1s/T1",
                "subnets": ["10.1.1.0/24"],
            },
        )

        assert response.status_code == 401

    def test_create_segment_validation(self, test_client, auth_test_password):
        """Test segment creation request validation."""
        # Login
        login_response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "operator", "password": auth_test_password},
        )
        token = login_response.json()["access_token"]

        # Try to create segment with invalid data (missing required fields)
        response = test_client.post(
            "/api/v1/nsxt/test-site/segments",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "test-segment"},  # Missing tier1_gateway and subnets
        )

        assert response.status_code == 422  # Validation error
        data = response.json()
        assert data["error"] == "ValidationError"


class TestErrorHandling:
    """Test error handling."""

    def test_validation_error_format(self, test_client, auth_test_password):
        """Test validation error response format."""
        # Login
        login_response = test_client.post(
            "/api/v1/auth/token",
            data={"username": "operator", "password": auth_test_password},
        )
        token = login_response.json()["access_token"]

        # Send invalid request
        response = test_client.post(
            "/api/v1/nsxt/test-site/segments",
            headers={"Authorization": f"Bearer {token}"},
            json={},  # Empty body
        )

        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert "detail" in data
        assert "request_id" in data
        assert "timestamp" in data

    def test_request_id_in_response(self, test_client):
        """Test that request ID is included in response headers."""
        response = test_client.get("/health")

        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req_")
