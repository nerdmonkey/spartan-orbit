import importlib
from types import SimpleNamespace

import pytest


def make_env(mapping):
    """Return an env(...) replacement that supports var_name or no-arg calls."""

    def _env(var_name=None, default=None):
        if var_name is None:
            # Return an object with attributes for no-arg usage
            return SimpleNamespace(**{k: v for k, v in mapping.items()})
        return mapping.get(var_name, default)

    return _env


def test_appsettings_dot_access_and_defaults(monkeypatch):
    mapping = {
        "APP_NAME": "myapp",
        "APP_ENVIRONMENT": "dev",
        "APP_DEBUG": True,
        "ALLOWED_ORIGINS": "a,b",
        "LOG_LEVEL": "INFO",
        "LOG_DIR": "logs",
    }

    monkeypatch.setattr("app.helpers.environment.env", make_env(mapping))

    # Reload the module so class-level env() calls pick up the patched env
    cfg_mod = importlib.reload(importlib.import_module("config.app"))
    cfg = cfg_mod.config

    assert cfg.app_name == "myapp"
    assert cfg.environment == "dev"
    assert cfg.debug is True
    assert cfg.allowed_origins == ["a", "b"]

    # Dot access into nested settings
    assert cfg("log.level") == "INFO"
    # Missing key returns default
    assert cfg("no.such.key", default=123) == 123


def test_storage_settings_defaults(monkeypatch):
    """Test storage settings with defaults."""
    mapping = {
        "APP_NAME": "myapp",
        "APP_ENVIRONMENT": "dev",
        "APP_DEBUG": False,
        "ALLOWED_ORIGINS": "a,b",
        "LOG_LEVEL": "INFO",
        "LOG_DIR": "logs",
        "STORAGE_TYPE": "s3",
        "STORAGE_BUCKET": "my-bucket",
    }

    # Set environment variables directly
    for key, value in mapping.items():
        monkeypatch.setenv(key, str(value))

    # Clear the cache to force reload
    from app.helpers.environment import env

    env.cache_clear()

    # Get fresh settings
    settings = env()

    assert settings.STORAGE_TYPE == "s3"
    assert settings.STORAGE_BUCKET == "my-bucket"


def test_handlers_singleton_and_handler_configs(monkeypatch):
    mapping = {
        "APP_NAME": "appx",
        "LOG_LEVEL": "WARN",
        "LOG_FILE": "/tmp/appx.log",
    }
    monkeypatch.setattr("app.helpers.environment.env", make_env(mapping))

    # Reload logging config module to re-create singleton with
    # patched env
    log_mod = importlib.reload(importlib.import_module("config.logging"))

    # handler() convenience should return the pydantic config models
    file_handler = log_mod.handler("file")
    assert file_handler is not None
    assert file_handler.class_ == "logging.FileHandler"
    assert file_handler.path == "/tmp/appx.log"

    console_handler = log_mod.handler("console")
    assert console_handler.name == "appx"

    # TcpHandlerConfig port validation: invalid port should raise
    from config.logging import TcpHandlerConfig

    with pytest.raises(Exception):
        TcpHandlerConfig(
            class_="x",
            formatter="json",
            name="n",
            level="INFO",
            host="h",
            port=70000,
        )


def test_filehandler_pydantic_serialization_and_validation(monkeypatch):
    """
    Ensure json_deserializer attribute exists but is excluded from model
    dumps and invalid values raise.
    """

    mapping = {"APP_NAME": "appx", "LOG_LEVEL": "WARN", "LOG_FILE": "/tmp/appx.log"}
    monkeypatch.setattr("app.helpers.environment.env", make_env(mapping))

    log_mod = importlib.reload(importlib.import_module("config.logging"))

    # Default FileHandlerConfig should have a callable json_deserializer attribute
    fh = log_mod.FileHandlerConfig(
        class_="logging.FileHandler",
        formatter="json",
        name="appx",
        level="WARN",
        path="/tmp/a",
    )
    assert callable(getattr(fh, "json_deserializer"))

    # model dump should not contain json_deserializer (field has exclude=True)
    dump = fh.model_dump() if hasattr(fh, "model_dump") else fh.dict()
    assert "json_deserializer" not in dump

    # Passing a non-callable json_deserializer should raise
    with pytest.raises(Exception):
        log_mod.FileHandlerConfig(
            class_="x",
            formatter="json",
            name="n",
            level="INFO",
            path="/tmp/a",
            json_deserializer=123,
        )


def test_handlers_singleton_behavior(monkeypatch):
    mapping = {"APP_NAME": "appx", "LOG_LEVEL": "WARN", "LOG_FILE": "/tmp/appx.log"}
    monkeypatch.setattr("app.helpers.environment.env", make_env(mapping))

    log_mod = importlib.reload(importlib.import_module("config.logging"))
    h1 = log_mod.Handlers()
    h2 = log_mod.Handlers()
    assert h1 is h2
    # get_handler should return None for unknown types
    assert h1.get_handler("unknown") is None


def test_storage_settings_class(monkeypatch):
    """Test StorageSettings class from config.storage."""
    mapping = {
        "STORAGE_TYPE": "gcs",
        "STORAGE_BUCKET": "test-bucket",
        "STORAGE_PATH": "test/path",
    }
    monkeypatch.setattr("app.helpers.environment.env", make_env(mapping))

    # Import and instantiate StorageSettings
    storage_mod = importlib.reload(importlib.import_module("config.storage"))
    settings = storage_mod.StorageSettings()

    assert settings.storage_type == "gcs"
    assert settings.storage_bucket == "test-bucket"
    assert settings.storage_path == "test/path"


def test_storage_settings_class_defaults(monkeypatch):
    """Test StorageSettings with default values."""
    mapping = {}
    monkeypatch.setattr("app.helpers.environment.env", make_env(mapping))

    storage_mod = importlib.reload(importlib.import_module("config.storage"))
    settings = storage_mod.StorageSettings()

    assert settings.storage_type == "local"
    assert settings.storage_bucket == "spartan-bucket"
    assert settings.storage_path == "storage/core"
