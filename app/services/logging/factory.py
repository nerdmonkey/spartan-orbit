from typing import Dict, List, Optional, Type

from app.helpers.environment import env
from app.services.logging.both import BothLogger
from app.services.logging.file import FileLogger
from app.services.logging.stream import StreamLogger

from .base import BaseLogger


class LoggerFactory:
    """
    Factory class for creating different types of loggers with lazy
    loading support.
    """

    # Cache for lazy-loaded logger classes
    _lazy_logger_cache: Dict[str, Type[BaseLogger]] = {}

    # Registry of available logger types
    _logger_registry = {
        "stream": StreamLogger,
        "file": FileLogger,
        "both": BothLogger,
        # azure is handled separately due to lazy loading
    }

    @classmethod
    def _get_azure_logger(cls) -> Type[BaseLogger]:
        """Lazy loader for Azure Monitor Logger to avoid dependency conflicts."""
        if "azure" not in cls._lazy_logger_cache:
            from app.services.logging.azure_monitor import AzureMonitorLogger

            cls._lazy_logger_cache["azure"] = AzureMonitorLogger
        return cls._lazy_logger_cache["azure"]

    @classmethod
    def _is_azure_environment(cls) -> bool:
        """Detect if running in Azure environment."""
        # Check for Azure environment indicators
        return any(
            [
                env("FUNCTIONS_WORKER_RUNTIME"),
                env("AZURE_FUNCTIONS_ENVIRONMENT"),
                env("WEBSITE_INSTANCE_ID"),
                env("WEBSITE_SITE_NAME"),
                env("APPSETTING_WEBSITE_SITE_NAME"),
                env("WEBSITE_HOSTNAME"),
            ]
        )

    @classmethod
    def _resolve_logger_type(cls, logger_type: Optional[str]) -> str:
        """
        Resolve the logger type from parameters or environment variables
        with smart fallback.
        """
        resolved_type = (
            logger_type or env("LOGGER_TYPE", env("LOG_CHANNEL", "file"))
        ).lower()

        # Smart fallback: if azure is requested in truly local
        # environment, fall back to 'both' for local development
        # Only fallback if APP_ENVIRONMENT explicitly says local/dev
        # AND no Azure indicators
        app_env = env("APP_ENVIRONMENT", "").lower()
        if resolved_type == "azure" and app_env in ["local", "development"]:
            is_azure = cls._is_azure_environment()
            if not is_azure:
                print(
                    "⚠️  Warning: azure logger requested in local "
                    "environment. Falling back to 'both' logger."
                )
                return "both"

        return resolved_type

    @classmethod
    def _get_logger_params(
        cls, service_name: str, level: str, logger_type: str
    ) -> Dict:
        """Get common parameters for logger initialization."""
        base_params = {"service_name": service_name, "level": level}

        # Add sample_rate for loggers that support it
        if logger_type in ["file", "azure", "both"]:
            base_params["sample_rate"] = float(env("LOG_SAMPLE_RATE", "1.0"))

        return base_params

    @classmethod
    def get_supported_types(cls) -> List[str]:
        """Get list of all supported logger types."""
        return list(cls._logger_registry.keys()) + ["azure"]

    @classmethod
    def create_logger(
        cls,
        service_name: str,
        level: str = "INFO",
        logger_type: Optional[str] = None,
    ) -> BaseLogger:
        """
        Create a logger instance based on the specified type.

        Args:
            service_name: Name of the service for logging identification
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            logger_type: Type of logger to create (stream, file, azure, both)

        Returns:
            BaseLogger: Configured logger instance

        Raises:
            ValueError: If logger_type is not supported
            ImportError: If required dependencies for the logger type are not available
        """
        resolved_type = cls._resolve_logger_type(logger_type)
        params = cls._get_logger_params(service_name, level, resolved_type)

        # Handle regular logger types
        if resolved_type in cls._logger_registry:
            logger_class = cls._logger_registry[resolved_type]
            return logger_class(**params)

        # Handle lazy-loaded logger types
        elif resolved_type == "azure":
            logger_class = cls._get_azure_logger()
            return logger_class(**params)

        # Unknown logger type
        else:
            supported_types = ", ".join([f"'{t}'" for t in cls.get_supported_types()])
            raise ValueError(
                f"Unknown logger_type: '{resolved_type}'. "
                f"Must be one of: {supported_types}."
            )
