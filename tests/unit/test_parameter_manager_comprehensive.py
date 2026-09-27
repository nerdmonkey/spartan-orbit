"""
Comprehensive tests for ParameterManager service with proper GCP SDK mocking.
Focuses on credential detection, pagination, and utility methods to improve coverage.
"""

from unittest.mock import MagicMock, patch


class TestParameterManagerProjectDetection:
    """Test project ID detection from various sources."""

    @patch("app.services.parameter_manager.env")
    def test_framework_env_project_id_success(self, mock_env):
        """Test successful project ID detection from GOOGLE_CLOUD_PROJECT."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project-123"
        }.get(key, default)

        service = ParameterManagerService()
        assert service.project_id == "test-project-123"

    @patch("app.services.parameter_manager.env")
    def test_framework_env_project_id_exception(self, mock_env, monkeypatch):
        """Test project ID detection handles exceptions from env."""
        from app.services.parameter_manager import ParameterManagerService

        def env_side_effect(key, default=None):
            if key == "GOOGLE_CLOUD_PROJECT":
                raise RuntimeError("Environment access error")
            return default

        mock_env.side_effect = env_side_effect

        # Framework env raises, should fall back to standard env vars
        monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "fallback-project")
        service = ParameterManagerService()
        assert service.project_id == "fallback-project"

    @patch("app.services.parameter_manager.default_credentials")
    @patch("app.services.parameter_manager.env")
    def test_standard_env_vars_project_id(self, mock_env, mock_creds, monkeypatch):
        """Test project ID detection from standard GCP env vars."""
        from app.services.parameter_manager import ParameterManagerService

        # Framework env has nothing, forcing fallback to standard env vars
        mock_env.return_value = None
        mock_creds.return_value = (MagicMock(), "env-var-project")
        monkeypatch.setenv("GCP_PROJECT", "env-var-project")

        service = ParameterManagerService()
        assert service.project_id == "env-var-project"


class TestParameterManagerCredentialLoading:
    """Test credential loading from various sources."""

    @patch("os.path.exists")
    @patch("app.services.parameter_manager.service_account")
    @patch("app.services.parameter_manager.env")
    def test_framework_env_credentials_success(self, mock_env, mock_sa, mock_exists):
        """Test loading credentials from GOOGLE_APPLICATION_CREDENTIALS."""
        from app.services.parameter_manager import ParameterManagerService

        creds_path = "/path/to/service-account.json"
        mock_exists.return_value = True
        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_APPLICATION_CREDENTIALS": creds_path,
            "GOOGLE_CLOUD_PROJECT": "test-project",
        }.get(key, default)

        mock_creds = MagicMock()
        mock_creds.service_account_email = "test@example.iam.gserviceaccount.com"
        mock_sa.Credentials.from_service_account_file.return_value = mock_creds

        ParameterManagerService()
        # Should successfully initialize with credentials configured

    @patch("app.services.parameter_manager.get_logger")
    @patch("os.path.exists")
    @patch("app.services.parameter_manager.service_account")
    @patch("app.services.parameter_manager.env")
    def test_framework_env_credentials_file_not_exists(
        self, mock_env, mock_sa, mock_exists, mock_logger
    ):
        """Test when credentials file doesn't exist."""
        from app.services.parameter_manager import ParameterManagerService

        mock_logger.return_value = MagicMock()
        creds_path = "/nonexistent/path.json"
        mock_exists.return_value = False
        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_APPLICATION_CREDENTIALS": creds_path,
            "GOOGLE_CLOUD_PROJECT": "test-project",
        }.get(key, default)

        ParameterManagerService()
        # Should not attempt to load from non-existent file
        mock_sa.Credentials.from_service_account_file.assert_not_called()

    @patch("os.path.exists")
    @patch("app.services.parameter_manager.service_account")
    @patch("app.services.parameter_manager.env")
    def test_framework_env_credentials_load_error(self, mock_env, mock_sa, mock_exists):
        """Test handling of credential loading errors."""
        from app.services.parameter_manager import ParameterManagerService

        creds_path = "/path/to/invalid.json"
        mock_exists.return_value = True
        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_APPLICATION_CREDENTIALS": creds_path,
            "GOOGLE_CLOUD_PROJECT": "test-project",
        }.get(key, default)

        mock_sa.Credentials.from_service_account_file.side_effect = ValueError(
            "Invalid JSON"
        )

        # Should log warning but continue
        ParameterManagerService()
        # Service should still initialize

    @patch("app.services.parameter_manager.default_credentials")
    @patch("app.services.parameter_manager.env")
    def test_default_credentials_fallback(self, mock_env, mock_default_creds):
        """Test fallback to default credentials."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.return_value = None
        mock_creds = MagicMock()
        mock_default_creds.return_value = (mock_creds, "default-project")

        ParameterManagerService(project_id="test-project")
        # Should use default credentials
        mock_default_creds.assert_called()


class TestParameterManagerCacheBehavior:
    """Test caching mechanisms."""

    @patch("app.services.parameter_manager.env")
    def test_cache_enabled(self, mock_env):
        """Test cache initialization when enabled."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService(enable_cache=True, cache_ttl_seconds=300)

        assert service.enable_cache is True
        assert service.cache_ttl_seconds == 300

    @patch("app.services.parameter_manager.env")
    def test_cache_clear(self, mock_env):
        """Test cache clearing."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService(enable_cache=True)

        # Clear cache should not raise
        service.clear_cache()


class TestParameterManagerPathUtilities:
    """Test path formatting utilities."""

    @patch("app.services.parameter_manager.env")
    def test_get_parent_path(self, mock_env):
        """Test parent path generation."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService(location="us-central1")
        parent_path = service._get_parent_path()

        assert "test-project" in parent_path
        assert "us-central1" in parent_path

    @patch("app.services.parameter_manager.env")
    def test_get_parameter_path(self, mock_env):
        """Test parameter path generation."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService()
        param_path = service._get_parameter_path("my-parameter")

        assert "my-parameter" in param_path

    @patch("app.services.parameter_manager.env")
    def test_get_parameter_version_path(self, mock_env):
        """Test parameter version path generation."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService()
        version_path = service._get_parameter_version_path("my-parameter", "v1")

        assert "my-parameter" in version_path
        assert "v1" in version_path


class TestParameterManagerLogging:
    """Test logging operations."""

    @patch("app.services.parameter_manager.env")
    def test_log_operation_start(self, mock_env):
        """Test operation start logging."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService()
        start_time = service._log_operation_start("test_operation", param="value")

        assert isinstance(start_time, float)
        assert start_time > 0

    @patch("app.services.parameter_manager.env")
    def test_log_operation_success(self, mock_env):
        """Test operation success logging."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService()
        start_time = service._log_operation_start("test_operation")
        # Should not raise
        service._log_operation_success("test_operation", start_time, result="success")

    @patch("app.services.parameter_manager.env")
    def test_log_operation_error(self, mock_env):
        """Test operation error logging."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService()
        start_time = service._log_operation_start("test_operation")
        error = ValueError("test error")

        # Should not raise
        service._log_operation_error("test_operation", start_time, error)


class TestParameterManagerConnectionPooling:
    """Test connection pooling configuration."""

    @patch("app.services.parameter_manager.env")
    def test_connection_pooling_enabled(self, mock_env):
        """Test connection pooling initialization."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService(
            enable_connection_pooling=True, max_pool_size=50
        )

        assert service.enable_connection_pooling is True
        assert service.max_pool_size == 50

    @patch("app.services.parameter_manager.env")
    def test_connection_pooling_disabled(self, mock_env):
        """Test default connection pooling settings."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService()

        # Should have default pooling settings
        assert hasattr(service, "enable_connection_pooling")


class TestParameterManagerLocationHandling:
    """Test location (region) configuration."""

    @patch("app.services.parameter_manager.env")
    def test_regional_location(self, mock_env):
        """Test service with regional location."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService(location="us-east1")
        assert service.location == "us-east1"

    @patch("app.services.parameter_manager.env")
    def test_global_location(self, mock_env):
        """Test service with global location."""
        from app.services.parameter_manager import ParameterManagerService

        mock_env.side_effect = lambda key, default=None: {
            "GOOGLE_CLOUD_PROJECT": "test-project"
        }.get(key, default)

        service = ParameterManagerService(location="global")
        assert service.location == "global"
