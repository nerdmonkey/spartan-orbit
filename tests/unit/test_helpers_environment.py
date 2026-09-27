"""
Tests for environment helper to improve coverage.

Focuses on edge cases for environment variable validation,
particularly the empty string to None conversion.

Coverage Target: app/helpers/environment.py Line 60
"""

import os

from app.helpers.environment import EnvironmentVariables


class TestEnvironmentVariablesEdgeCases:
    """Test edge cases for environment variable validation."""

    def test_storage_bucket_empty_string_converts_to_none(self, monkeypatch):
        """Test that empty STORAGE_BUCKET string is converted to None (Line 60)."""
        # Clear all environment variables first
        for key in list(os.environ.keys()):
            if key.startswith(("APP_", "LOG_", "STORAGE_", "ALLOWED_")):
                monkeypatch.delenv(key, raising=False)

        # Set all required environment variables
        monkeypatch.setenv("APP_NAME", "test-app")
        monkeypatch.setenv("APP_ENVIRONMENT", "test")
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("ALLOWED_ORIGINS", "*")
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_CHANNEL", "console")
        monkeypatch.setenv("LOG_DIR", "/tmp/logs")
        monkeypatch.setenv("STORAGE_BUCKET", "")  # Empty string

        # Reload settings
        env_vars = EnvironmentVariables()

        # Empty string should be converted to None
        assert env_vars.STORAGE_BUCKET is None

    def test_storage_bucket_with_value_not_converted(self, monkeypatch):
        """Test that STORAGE_BUCKET with actual value is not converted."""
        # Clear all environment variables first
        for key in list(os.environ.keys()):
            if key.startswith(("APP_", "LOG_", "STORAGE_", "ALLOWED_")):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("APP_NAME", "test-app")
        monkeypatch.setenv("APP_ENVIRONMENT", "test")
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("ALLOWED_ORIGINS", "*")
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_CHANNEL", "console")
        monkeypatch.setenv("LOG_DIR", "/tmp/logs")
        monkeypatch.setenv("STORAGE_BUCKET", "my-bucket")

        env_vars = EnvironmentVariables()

        assert env_vars.STORAGE_BUCKET == "my-bucket"

    def test_storage_bucket_none_when_not_set(self, monkeypatch):
        """Test that STORAGE_BUCKET defaults to None when not set."""
        # Clear all environment variables first
        for key in list(os.environ.keys()):
            if key.startswith(("APP_", "LOG_", "STORAGE_", "ALLOWED_")):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("APP_NAME", "test-app")
        monkeypatch.setenv("APP_ENVIRONMENT", "test")
        monkeypatch.setenv("APP_DEBUG", "true")
        monkeypatch.setenv("ALLOWED_ORIGINS", "*")
        monkeypatch.setenv("LOG_LEVEL", "INFO")
        monkeypatch.setenv("LOG_CHANNEL", "console")
        monkeypatch.setenv("LOG_DIR", "/tmp/logs")
        monkeypatch.setenv("STORAGE_BUCKET", "")  # Set to empty to trigger conversion

        env_vars = EnvironmentVariables()

        # Empty string should be converted to None
        assert env_vars.STORAGE_BUCKET is None

    def test_app_environment_validation_valid_options(self, monkeypatch):
        """Test all valid APP_ENVIRONMENT options."""
        valid_envs = ["local", "dev", "uat", "prod", "test"]

        for env_value in valid_envs:
            # Clear all environment variables first
            for key in list(os.environ.keys()):
                if key.startswith(("APP_", "LOG_", "STORAGE_", "ALLOWED_")):
                    monkeypatch.delenv(key, raising=False)

            monkeypatch.setenv("APP_NAME", "test-app")
            monkeypatch.setenv("APP_ENVIRONMENT", env_value)
            monkeypatch.setenv("APP_DEBUG", "true")
            monkeypatch.setenv("ALLOWED_ORIGINS", "*")
            monkeypatch.setenv("LOG_LEVEL", "INFO")
            monkeypatch.setenv("LOG_CHANNEL", "console")
            monkeypatch.setenv("LOG_DIR", "/tmp/logs")

            env_vars = EnvironmentVariables()
            assert env_vars.APP_ENVIRONMENT == env_value
