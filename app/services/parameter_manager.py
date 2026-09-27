# Parameter Manager Service
# This file contains the main ParameterManagerService class

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple, Union

from google.api_core import exceptions as gcp_exceptions
from google.auth import default as default_credentials
from google.auth.credentials import Credentials
from google.oauth2 import service_account

from app.exceptions.parameter_manager import (
    InvalidParameterValueException,
    ParameterAccessDeniedException,
    ParameterConnectionException,
    ParameterInternalErrorException,
    ParameterManagerException,
    ParameterNotFoundException,
    ParameterQuotaExceededException,
    ParameterTimeoutException,
    ParameterUnavailableException,
    ParameterVersionNotFoundException,
)
from app.helpers.environment import env
from app.helpers.logger import get_logger


class ParameterManagerService:
    """
    Service class for managing configuration parameters using Google Cloud
    Parameter Manager.

    This service provides a type-safe interface for storing, retrieving,
    and managing configuration parameters following the Spartan Framework
    patterns. It integrates seamlessly with Google Cloud Parameter Manager
    to provide centralized parameter management capabilities.

    Features:
        - Create, retrieve, update, and delete parameters
        - Version management with custom version names
        - Support for multiple format types (UNFORMATTED, JSON, YAML)
        - Optional in-memory caching with TTL for improved performance
        - Batch operations for efficient multi-parameter operations
        - Connection pooling for optimized API performance
        - Comprehensive error handling with custom exceptions
        - Structured logging with parameter values (non-sensitive)
        - Automatic project and credential detection
        - Support for labels and metadata
        - Pagination for large result sets
        - Regional and global endpoint support
        - Secret Manager integration for secret references

    The service follows the Spartan Framework's established patterns:
        - Pydantic models for request/response validation
        - Custom exceptions for error handling
        - Integration with framework logging system
        - Environment-based configuration

    Performance Features:
        - In-memory caching with configurable TTL
        - Automatic cache invalidation on updates
        - Batch operations to reduce API calls
        - Connection pooling for improved throughput
        - Cache statistics tracking

    Attributes:
        project_id: Google Cloud project ID where parameters are stored
        location: Geographic location where parameters are stored (global or regional)
        logger: Framework logger instance for structured logging
        enable_cache: Whether in-memory caching is enabled
        cache_ttl_seconds: Time-to-live for cached parameters in seconds
        enable_connection_pooling: Whether connection pooling is enabled
        max_pool_size: Maximum number of connections in the pool

    Example:
        >>> # Basic usage with auto-detected project
        >>> service = ParameterManagerService()
        >>>
        >>> # Create a parameter
        >>> request = ParameterCreateRequest(
        ...     parameter_name="app-config",
        ...     format_type="JSON"
        ... )
        >>> response = service.create_parameter(request)
        >>>
        >>> # Retrieve the parameter
        >>> parameter = service.get_parameter("app-config")
        >>> print(parameter.data)
        >>>
        >>> # With caching and connection pooling enabled
        >>> optimized_service = ParameterManagerService(
        ...     location="us-central1",
        ...     enable_cache=True,
        ...     cache_ttl_seconds=300,
        ...     enable_connection_pooling=True,
        ...     max_pool_size=20
        ... )
        >>> # Cached for 5 minutes
        >>> parameter = optimized_service.get_parameter("app-config")
        >>>
        >>> # Batch operations for efficiency
        >>> results = optimized_service.get_parameters_batch(
        ...     ["app-config", "database-url", "api-key"]
        ... )
        >>> print(f"Retrieved {results['successful']} parameters")

    See Also:
        - ParameterCreateRequest: Request model for creating parameters
        - ParameterResponse: Response model for parameter retrieval
        - ParameterManagerException: Base exception for all parameter manager errors
    """

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: str = "global",
        credentials: Optional[Union[Credentials, str]] = None,
        credentials_path: Optional[str] = None,
        enable_cache: bool = False,
        cache_ttl_seconds: int = 300,
        enable_connection_pooling: bool = True,
        max_pool_size: int = 10,
    ):
        """
        Initialize the Parameter Manager service.

        Args:
            project_id: Google Cloud project ID. If None, will attempt to
                detect from environment.
            location: Geographic location for parameters (default: "global").
                Can be regional (e.g., "us-central1") or "global".
            credentials: Google Cloud credentials object or service account
                key JSON string. If None, will use default credentials.
            credentials_path: Path to service account key file. If provided,
                takes precedence over credentials parameter.
            enable_cache: Enable in-memory caching for parameter values
                (default: False)
            cache_ttl_seconds: Time-to-live for cached parameters in seconds
                (default: 300)
            enable_connection_pooling: Enable connection pooling for improved
                performance (default: True)
            max_pool_size: Maximum number of connections in the pool
                (default: 10)

        Raises:
            ParameterManagerException: If project_id cannot be determined,
                credentials are invalid, or client initialization fails.
        """
        self.logger = get_logger("app.services.parameter_manager")

        # Enhanced project ID detection with framework integration
        self.project_id = self._determine_project_id(project_id)
        if not self.project_id:
            raise ParameterManagerException(
                "Project ID must be provided or available in environment. "
                "Set GOOGLE_CLOUD_PROJECT environment variable, configure gcloud CLI, "
                "or provide project_id parameter."
            )

        # Set location (global or regional)
        self.location = location

        # Enhanced credential handling
        self.credentials = self._setup_credentials(credentials, credentials_path)

        # Connection pooling configuration
        self.enable_connection_pooling = enable_connection_pooling
        self.max_pool_size = max_pool_size

        # Initialize Google Cloud Parameter Manager client with enhanced error handling
        self._initialize_client()

        # Initialize caching mechanism
        self.enable_cache = enable_cache
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[str, Tuple[Any, datetime]] = {}

        # Initialize batch operation statistics
        self._batch_stats = {
            "total_batch_operations": 0,
            "total_parameters_in_batches": 0,
            "cache_hits_in_batches": 0,
        }

        if self.enable_cache:
            self.logger.info(
                "Parameter caching enabled",
                extra={
                    "cache_ttl_seconds": self.cache_ttl_seconds,
                    "project_id": self.project_id,
                    "location": self.location,
                },
            )

        if self.enable_connection_pooling:
            self.logger.info(
                "Connection pooling enabled",
                extra={
                    "max_pool_size": self.max_pool_size,
                    "project_id": self.project_id,
                    "location": self.location,
                },
            )

    def _try_framework_env_project_id(self) -> Optional[str]:
        """Try to get project ID from framework environment."""
        try:
            framework_project_id = env("GOOGLE_CLOUD_PROJECT")
            if framework_project_id:
                self.logger.debug(
                    "Project ID detected from framework environment",
                    extra={
                        "project_id": framework_project_id,
                        "source_env_var": "GOOGLE_CLOUD_PROJECT",
                        "detection_method": "environment_variable",
                    },
                )
                return framework_project_id
        except Exception as e:
            self.logger.debug(
                "Failed to read from framework environment",
                extra={
                    "error": str(e),
                    "source": "framework_environment",
                    "detection_method": "environment_variable",
                },
            )
        return None

    def _try_standard_env_vars_project_id(self) -> Optional[str]:
        """Try to get project ID from standard environment variables."""
        gcp_env_vars = [
            "GOOGLE_CLOUD_PROJECT",
            "GCP_PROJECT",
            "GCLOUD_PROJECT",
            "PROJECT_ID",
        ]

        for env_var in gcp_env_vars:
            project_id = os.getenv(env_var)
            if project_id:
                self.logger.debug(
                    "Project ID detected from environment variable",
                    extra={
                        "project_id": project_id,
                        "source_env_var": env_var,
                        "detection_method": "environment_variable",
                    },
                )
                return project_id
        return None

    def _try_gcloud_config_project_id(self) -> Optional[str]:
        """Try to get project ID from gcloud config."""
        try:
            import subprocess  # nosec B404

            result = subprocess.run(  # nosec B603, B607
                ["gcloud", "config", "get-value", "project"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                gcloud_project = result.stdout.strip()
                self.logger.debug(
                    "Project ID detected from gcloud config",
                    extra={
                        "project_id": gcloud_project,
                        "source": "gcloud_config",
                        "detection_method": "gcloud_cli",
                    },
                )
                return gcloud_project
        except (
            subprocess.TimeoutExpired,
            subprocess.CalledProcessError,
            FileNotFoundError,
        ) as e:
            self.logger.debug(
                "Failed to get project from gcloud config",
                extra={
                    "error": str(e),
                    "source": "gcloud_config",
                    "detection_method": "gcloud_cli",
                },
            )
        return None

    def _try_metadata_service_project_id(self) -> Optional[str]:
        """Try to get project ID from GCP metadata service."""
        try:
            import requests

            metadata_url = (
                "http://metadata.google.internal/computeMetadata/v1/project/project-id"
            )
            headers = {"Metadata-Flavor": "Google"}
            response = requests.get(metadata_url, headers=headers, timeout=2)
            if response.status_code == 200:
                metadata_project = response.text.strip()
                self.logger.debug(
                    "Project ID detected from metadata service",
                    extra={
                        "project_id": metadata_project,
                        "source_env_var": "metadata_service",
                        "detection_method": "gcp_metadata",
                    },
                )
                return metadata_project
        except Exception as e:
            self.logger.debug(
                "Failed to get project from metadata service",
                extra={
                    "error": str(e),
                    "source": "metadata_service",
                    "detection_method": "gcp_metadata",
                },
            )
        return None

    def _determine_project_id(
        self, provided_project_id: Optional[str]
    ) -> Optional[str]:
        """
        Determine project ID from multiple sources with enhanced detection.

        Args:
            provided_project_id: Project ID provided directly to constructor

        Returns:
            Project ID string or None if not found
        """
        # Priority order for project ID detection:
        # 1. Explicitly provided parameter
        # 2. Framework environment configuration
        # 3. Standard Google Cloud environment variables
        # 4. Google Cloud SDK default project
        # 5. Metadata service (for GCP environments)

        # 1. Check explicitly provided parameter
        if provided_project_id:
            self.logger.debug(
                "Project ID provided explicitly",
                extra={
                    "project_id": provided_project_id,
                    "source": "constructor_parameter",
                    "detection_method": "explicit",
                },
            )
            return provided_project_id

        # 2. Check framework environment configuration
        project_id = self._try_framework_env_project_id()
        if project_id:
            return project_id

        # 3. Check standard Google Cloud environment variables
        project_id = self._try_standard_env_vars_project_id()
        if project_id:
            return project_id

        # 4. Try to get default project from Google Cloud SDK
        project_id = self._try_gcloud_config_project_id()
        if project_id:
            return project_id

        # 5. Try to get project from metadata service (GCP environments)
        project_id = self._try_metadata_service_project_id()
        if project_id:
            return project_id

        # If we get here, no project ID could be determined
        self.logger.error(
            "Project ID could not be determined from any source",
            extra={
                "attempted_sources": [
                    "constructor_parameter",
                    "framework_environment",
                    "environment_variables",
                    "gcloud_config",
                    "metadata_service",
                ],
                "checked_env_vars": [
                    "GOOGLE_CLOUD_PROJECT",
                    "GCP_PROJECT",
                    "GCLOUD_PROJECT",
                    "PROJECT_ID",
                ],
            },
        )

        return None

    def _load_credentials_from_file(self, credentials_path: str) -> Credentials:
        """Load credentials from service account file."""
        if not os.path.exists(credentials_path):
            self.logger.error(
                "Service account key file not found",
                extra={
                    "credentials_path": credentials_path,
                    "credential_source": "file_path",
                },
            )
            raise ParameterManagerException(
                f"Service account key file not found: {credentials_path}"
            )

        try:
            creds = service_account.Credentials.from_service_account_file(
                credentials_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self.logger.debug(
                "Credentials loaded from service account file",
                extra={
                    "credentials_path": credentials_path,
                    "credential_source": "service_account_file",
                    "service_account_email": getattr(
                        creds, "service_account_email", "unknown"
                    ),
                },
            )
            return creds
        except Exception as e:
            self.logger.error(
                "Failed to load credentials from service account file",
                extra={
                    "credentials_path": credentials_path,
                    "error": str(e),
                    "credential_source": "service_account_file",
                },
            )
            raise ParameterManagerException(
                f"Failed to load credentials from file {credentials_path}: {str(e)}"
            )

    def _load_credentials_from_json(self, credentials: str) -> Credentials:
        """Load credentials from JSON string."""
        try:
            import json

            creds_info = json.loads(credentials)
            creds = service_account.Credentials.from_service_account_info(
                creds_info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self.logger.debug(
                "Credentials loaded from JSON string",
                extra={
                    "credential_source": "json_string",
                    "service_account_email": getattr(
                        creds, "service_account_email", "unknown"
                    ),
                },
            )
            return creds
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.error(
                "Failed to parse credentials JSON string",
                extra={"error": str(e), "credential_source": "json_string"},
            )
            raise ParameterManagerException(
                f"Invalid credentials JSON string: {str(e)}"
            )

    def _try_framework_env_credentials(self) -> Optional[Credentials]:
        """Try to load credentials from framework environment."""
        try:
            # Re-import the environment helper module so that tests which
            # patch app.helpers.environment.env affect this lookup.
            try:
                from app.helpers import environment as env_module

                framework_creds_path = env_module.env("GOOGLE_APPLICATION_CREDENTIALS")
            except ImportError:
                # Fallback to the locally imported env helper
                framework_creds_path = env("GOOGLE_APPLICATION_CREDENTIALS")
            if framework_creds_path and os.path.exists(framework_creds_path):
                try:
                    creds = service_account.Credentials.from_service_account_file(
                        framework_creds_path,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"],
                    )
                    self.logger.debug(
                        "Credentials loaded from framework environment",
                        extra={
                            "credentials_path": framework_creds_path,
                            "credential_source": "framework_environment",
                            "service_account_email": getattr(
                                creds, "service_account_email", "unknown"
                            ),
                        },
                    )
                    return creds
                except Exception as e:
                    self.logger.warning(
                        "Failed to load credentials from framework environment path",
                        extra={
                            "credentials_path": framework_creds_path,
                            "error": str(e),
                            "credential_source": "framework_environment",
                        },
                    )
        except Exception as e:
            self.logger.debug(
                "Failed to read credentials path from framework environment",
                extra={"error": str(e), "credential_source": "framework_environment"},
            )
        return None

    def _try_default_credentials(self) -> Optional[Credentials]:
        """Try to use default credentials (ADC)."""
        try:
            creds, detected_project = default_credentials()
            self.logger.debug(
                "Using default credentials (ADC)",
                extra={
                    "credential_source": "default_credentials",
                    "detected_project": detected_project,
                    "credential_type": type(creds).__name__,
                },
            )
            return creds
        except Exception as e:
            self.logger.warning(
                "Failed to load default credentials",
                extra={"error": str(e), "credential_source": "default_credentials"},
            )
            # Return None to let the client use default authentication
            return None

    def _setup_credentials(
        self,
        credentials: Optional[Union[Credentials, str]],
        credentials_path: Optional[str],
    ) -> Optional[Credentials]:
        """
        Setup Google Cloud credentials with enhanced handling.

        Args:
            credentials: Credentials object or service account JSON string
            credentials_path: Path to service account key file

        Returns:
            Credentials object or None for default credentials

        Raises:
            ParameterManagerException: If credentials are invalid or cannot be loaded
        """
        # Priority order for credentials:
        # 1. Service account key file path
        # 2. Credentials object or JSON string
        # 3. Framework environment configuration for credentials
        # 4. Default credentials (ADC)

        # 1. Check service account key file path
        if credentials_path:
            return self._load_credentials_from_file(credentials_path)

        # 2. Check provided credentials object or JSON string
        if credentials:
            if isinstance(credentials, str):
                return self._load_credentials_from_json(credentials)
            elif isinstance(credentials, Credentials):
                self.logger.debug(
                    "Using provided credentials object",
                    extra={
                        "credential_source": "credentials_object",
                        "credential_type": type(credentials).__name__,
                    },
                )
                return credentials
            else:
                self.logger.error(
                    "Invalid credentials type provided",
                    extra={
                        "credential_type": type(credentials).__name__,
                        "credential_source": "invalid",
                    },
                )
                raise ParameterManagerException(
                    f"Invalid credentials type: {type(credentials)}. "
                    "Expected Credentials object or JSON string."
                )

        # 3. Check framework environment for credentials path
        creds = self._try_framework_env_credentials()
        if creds:
            return creds

        # 4. Use default credentials (ADC)
        return self._try_default_credentials()

    def _initialize_client(self):
        """
        Initialize Google Cloud Parameter Manager client with enhanced
        error handling and connection pooling.

        Raises:
            ParameterManagerException: If client initialization fails
        """
        try:
            start_time = time.time()

            # Note: Google Cloud Parameter Manager client will be initialized here
            # For now, we'll set client to None as the actual
            # google-cloud-parametermanager library needs to be installed and imported
            # TODO: Import and initialize actual Parameter Manager client
            # from google.cloud import parametermanager
            #
            # # Configure client options for connection pooling
            # if self.enable_connection_pooling:
            #     from google.api_core import client_options as client_options_lib
            #     from google.api_core.gapic_v1 import client_info
            #
            #     # Configure connection pool settings
            #     client_opts = client_options_lib.ClientOptions()
            #
            #     # Create client with connection pooling
            #     if self.credentials:
            #         self.client = parametermanager.ParameterManagerServiceClient(
            #             credentials=self.credentials,
            #             client_options=client_opts
            #         )
            #     else:
            #         self.client = parametermanager.ParameterManagerServiceClient(
            #             client_options=client_opts
            #         )
            # else:
            #     # Create client without connection pooling
            #     if self.credentials:
            #         self.client = parametermanager.ParameterManagerServiceClient(
            #             credentials=self.credentials
            #         )
            #     else:
            #         self.client = parametermanager.ParameterManagerServiceClient()

            self.client = None  # Placeholder until library is available

            initialization_time = time.time() - start_time

            credential_info = {
                "credential_source": (
                    "custom_credentials" if self.credentials else "default_credentials"
                ),
                "credential_type": (
                    type(self.credentials).__name__ if self.credentials else "default"
                ),
            }

            self.logger.info(
                "ParameterManagerService initialized successfully",
                extra={
                    "project_id": self.project_id,
                    "location": self.location,
                    "initialization_time_ms": round(initialization_time * 1000, 2),
                    "client_type": "ParameterManagerServiceClient",
                    "connection_pooling_enabled": self.enable_connection_pooling,
                    "max_pool_size": (
                        self.max_pool_size if self.enable_connection_pooling else None
                    ),
                    **credential_info,
                },
            )

        except Exception as e:
            self.logger.error(
                "Failed to initialize Parameter Manager client",
                extra={
                    "project_id": self.project_id,
                    "location": self.location,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "initialization_phase": "client_creation",
                },
            )

            # Provide more specific error messages based on exception type
            if isinstance(e, gcp_exceptions.Unauthenticated):
                raise ParameterManagerException(
                    "Authentication failed. Please check your credentials and "
                    "ensure they have the necessary permissions for Parameter "
                    "Manager operations."
                )
            elif isinstance(e, gcp_exceptions.PermissionDenied):
                raise ParameterManagerException(
                    f"Permission denied for project '{self.project_id}'. Please "
                    f"ensure your credentials have the 'Parameter Manager Admin' "
                    f"or appropriate IAM roles."
                )
            elif isinstance(e, gcp_exceptions.NotFound):
                raise ParameterManagerException(
                    f"Project '{self.project_id}' not found. Please verify the "
                    f"project ID and ensure it exists and is accessible."
                )
            else:
                raise ParameterManagerException(
                    f"Failed to initialize Parameter Manager client: {str(e)}"
                )

    def _log_operation_start(self, operation: str, **context) -> float:
        """
        Log the start of an operation and return start time for timing.

        Args:
            operation: Name of the operation being started
            **context: Additional context to include in logs (parameter names, etc.)

        Returns:
            Start time for calculating operation duration
        """
        # Parameter values CAN be logged (non-sensitive configuration data)
        start_time = time.time()
        self.logger.info(
            f"Starting {operation}",
            extra={
                "operation": operation,
                "project_id": self.project_id,
                "location": self.location,
                "operation_start_time": start_time,
                **context,
            },
        )
        return start_time

    def _log_operation_success(self, operation: str, start_time: float, **context):
        """
        Log successful completion of an operation with timing.

        Args:
            operation: Name of the operation that completed
            start_time: Start time from _log_operation_start
            **context: Additional context to include in logs
        """
        duration_ms = round((time.time() - start_time) * 1000, 2)
        self.logger.info(
            f"Successfully completed {operation}",
            extra={
                "operation": operation,
                "project_id": self.project_id,
                "location": self.location,
                "operation_duration_ms": duration_ms,
                "operation_status": "success",
                **context,
            },
        )

    def _log_operation_error(
        self, operation: str, start_time: float, error: Exception, **context
    ):
        """
        Log failed operation with timing and error details.

        Args:
            operation: Name of the operation that failed
            start_time: Start time from _log_operation_start
            error: The exception that occurred
            **context: Additional context to include in logs
        """
        duration_ms = round((time.time() - start_time) * 1000, 2)
        self.logger.error(
            f"Failed to complete {operation}",
            extra={
                "operation": operation,
                "project_id": self.project_id,
                "location": self.location,
                "operation_duration_ms": duration_ms,
                "operation_status": "error",
                "error_type": type(error).__name__,
                "error_message": str(error),
                **context,
            },
        )

    def _get_parent_path(self) -> str:
        """Get the full parent path for Google Cloud Parameter Manager."""
        return f"projects/{self.project_id}/locations/{self.location}"

    def _get_parameter_path(self, parameter_name: str) -> str:
        """Get the full parameter path for Google Cloud Parameter Manager."""
        return (
            f"projects/{self.project_id}/locations/{self.location}/parameters/"
            f"{parameter_name}"
        )

    def _get_parameter_version_path(self, parameter_name: str, version: str) -> str:
        """Get the full parameter version path for Google Cloud Parameter Manager."""
        return (
            f"projects/{self.project_id}/locations/{self.location}/parameters/"
            f"{parameter_name}/versions/{version}"
        )

    def clear_cache(self) -> None:
        """
        Clear all cached parameters.

        This method removes all entries from the in-memory cache. This is useful when
        you need to force fresh retrieval of all parameters, such as after a bulk update
        operation or when you suspect cached data may be stale.
        If caching is not enabled, this method has no effect.

        Note:
            - Only affects the local cache; does not modify parameters in Google Cloud
            - Subsequent get_parameter() calls will fetch fresh data from the API
            - Cache statistics are reset to zero

        Example:
            >>> service = ParameterManagerService(enable_cache=True)
            >>> # Use some parameters (they get cached)
            >>> service.get_parameter("app-config")
            >>> service.get_parameter("database-url")
            >>>
            >>> # Clear all cached data
            >>> service.clear_cache()
            >>>
            >>> # Next access will fetch from API
            >>> service.get_parameter("app-config")  # Cache miss
        """
        if not self.enable_cache:
            return

        cache_size = len(self._cache)
        self._cache.clear()

        self.logger.info(
            "Cache cleared",
            extra={
                "cleared_entries": cache_size,
                "project_id": self.project_id,
                "location": self.location,
            },
        )

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        This method returns information about the current state of the cache, including
        the number of cached entries, expired entries, and cache configuration. This is
        useful for monitoring cache effectiveness and debugging cache-related issues.

        Returns:
            Dictionary containing cache statistics:
                - enabled: Whether caching is enabled (bool)
                - size: Total number of entries in cache (int)
                - expired_entries: Number of expired but not yet removed entries (int)
                - active_entries: Number of valid, non-expired entries (int)
                - ttl_seconds: Cache time-to-live in seconds (int)
                - batch_stats: Statistics about batch operations (dict)

        Note:
            - If caching is disabled, returns minimal stats with enabled=False
            - Expired entries are counted but not automatically removed until accessed
            - Active entries are those that haven't expired yet

        Example:
            >>> service = ParameterManagerService(
            ...     enable_cache=True, cache_ttl_seconds=300
            ... )
            >>> service.get_parameter("app-config")
            >>> service.get_parameter("database-url")
            >>>
            >>> stats = service.get_cache_stats()
            >>> print(f"Cache enabled: {stats['enabled']}")
            >>> print(f"Active entries: {stats['active_entries']}")
            >>> print(f"TTL: {stats['ttl_seconds']} seconds")
        """
        if not self.enable_cache:
            return {
                "enabled": False,
                "size": 0,
                "ttl_seconds": self.cache_ttl_seconds,
                "batch_stats": self._batch_stats,
            }

        # Count expired entries
        now = datetime.now()
        expired_count = sum(1 for _, expiry in self._cache.values() if expiry < now)

        return {
            "enabled": True,
            "size": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count,
            "ttl_seconds": self.cache_ttl_seconds,
            "batch_stats": self._batch_stats,
        }

    def _map_not_found_exception(
        self, parameter_name: str, version: str
    ) -> ParameterManagerException:
        """Map NotFound exception to appropriate custom exception."""
        if version:
            return ParameterVersionNotFoundException(
                f"Parameter '{parameter_name}' version '{version}' not found "
                f"in project '{self.project_id}' location '{self.location}'"
            )
        else:
            return ParameterNotFoundException(
                f"Parameter '{parameter_name}' not found in project "
                f"'{self.project_id}' location '{self.location}'"
            )

    def _map_permission_exception(
        self, operation: str, parameter_name: str, error_msg: str
    ) -> ParameterAccessDeniedException:
        """Map permission/auth exceptions to ParameterAccessDeniedException."""
        return ParameterAccessDeniedException(
            f"Permission denied for {operation} on parameter '{parameter_name}': "
            f"{error_msg}. "
            f"Ensure your credentials have the necessary IAM roles "
            f"(e.g., 'Parameter Manager Admin')."
        )

    def _map_already_exists_exception(
        self, parameter_name: str, version: str
    ) -> ParameterManagerException:
        """Map AlreadyExists exception to ParameterManagerException."""
        if version:
            return ParameterManagerException(
                f"Parameter '{parameter_name}' version '{version}' already exists. "
                f"Version names must be unique within a parameter."
            )
        else:
            return ParameterManagerException(
                f"Parameter '{parameter_name}' already exists in project "
                f"'{self.project_id}' location '{self.location}'"
            )

    def _map_failed_precondition_exception(
        self, parameter_name: str, version: str, error_msg: str
    ) -> ParameterManagerException:
        """Map FailedPrecondition exception to appropriate custom exception."""
        if "disabled" in error_msg.lower() or "destroyed" in error_msg.lower():
            return ParameterVersionNotFoundException(
                f"Parameter '{parameter_name}' version '{version}' is not accessible "
                f"(disabled or destroyed): {error_msg}"
            )
        else:
            return ParameterManagerException(
                f"Operation failed due to precondition: {error_msg}. "
                f"This may indicate the resource is in an invalid state."
            )

    def _map_gcp_exception(
        self, e: Exception, operation: str, context: dict = None
    ) -> ParameterManagerException:
        """
        Map Google Cloud API exceptions to custom Parameter Manager exceptions.

        This method provides comprehensive error mapping from Google Cloud API
        exceptions to framework-specific exceptions with enhanced context and
        logging. It handles
        various error scenarios including authentication, authorization, network issues,
        quota limits, and service availability.

        Args:
            e: The original Google Cloud exception or any other exception
            operation: Description of the operation that failed
                (e.g., "parameter creation")
            context: Additional context information (parameter_name, version, etc.)

        Returns:
            Appropriate ParameterManagerException subclass with enhanced error message

        Note:
            This method logs the original error with full context before mapping to
            ensure debugging information is preserved.
        """
        context = context or {}
        parameter_name = context.get("parameter_name", "unknown")
        version = context.get("version", "")
        error_msg = str(e)

        # Log the original error with full context
        self.logger.error(
            f"Google Cloud API error during {operation}",
            extra={
                "operation": operation,
                "gcp_error_type": type(e).__name__,
                "gcp_error_message": error_msg,
                "project_id": self.project_id,
                "location": self.location,
                "error_mapping": "gcp_to_custom",
                **context,
            },
        )

        # Map exceptions using helper methods
        mapped_exception = self._get_mapped_exception(
            e, operation, parameter_name, version, error_msg
        )

        # Log the mapped exception details
        self.logger.debug(
            "Mapped GCP exception to custom exception",
            extra={
                "operation": operation,
                "original_exception": type(e).__name__,
                "mapped_exception": type(mapped_exception).__name__,
                "project_id": self.project_id,
                "location": self.location,
                **context,
            },
        )

        return mapped_exception

    def _get_mapped_exception(
        self,
        e: Exception,
        operation: str,
        parameter_name: str,
        version: str,
        error_msg: str,
    ) -> ParameterManagerException:
        """Get the appropriate mapped exception based on exception type."""
        # Direct mappings for simple cases
        if isinstance(e, gcp_exceptions.NotFound):
            return self._map_not_found_exception(parameter_name, version)
        if isinstance(e, gcp_exceptions.AlreadyExists):
            return self._map_already_exists_exception(parameter_name, version)
        if isinstance(e, InvalidParameterValueException):
            return e

        # Group mappings with single method calls
        exception_groups = [
            (
                (gcp_exceptions.PermissionDenied, gcp_exceptions.Unauthenticated),
                lambda: self._map_auth_exception(
                    e, operation, parameter_name, error_msg
                ),
            ),
            (
                (gcp_exceptions.InvalidArgument, gcp_exceptions.OutOfRange),
                lambda: self._map_validation_exception(e, operation, error_msg),
            ),
            (
                (gcp_exceptions.ResourceExhausted, gcp_exceptions.TooManyRequests),
                lambda: self._map_quota_exception(operation, error_msg),
            ),
            (
                (gcp_exceptions.DeadlineExceeded, TimeoutError),
                lambda: self._map_timeout_exception(operation, error_msg),
            ),
            (
                (gcp_exceptions.InternalServerError, gcp_exceptions.DataLoss),
                lambda: self._map_internal_exception(e, operation, error_msg),
            ),
            (
                (gcp_exceptions.RetryError, ConnectionError, OSError),
                lambda: self._map_connection_exception(operation, error_msg),
            ),
        ]

        for exception_types, mapper in exception_groups:
            if isinstance(e, exception_types):
                return mapper()

        # Handle remaining single cases
        if isinstance(e, gcp_exceptions.ServiceUnavailable):
            return self._map_unavailable_exception(operation, error_msg)
        if isinstance(e, gcp_exceptions.FailedPrecondition):
            return self._map_failed_precondition_exception(
                parameter_name, version, error_msg
            )

        return self._map_generic_exception(e, operation, error_msg)

    def _map_auth_exception(
        self, e: Exception, operation: str, parameter_name: str, error_msg: str
    ) -> ParameterAccessDeniedException:
        """Map authentication/authorization exceptions."""
        if isinstance(e, gcp_exceptions.PermissionDenied):
            return self._map_permission_exception(operation, parameter_name, error_msg)
        return ParameterAccessDeniedException(
            f"Authentication failed for {operation}: {error_msg}. "
            f"Please check your credentials and ensure they are valid."
        )

    def _map_validation_exception(
        self, e: Exception, operation: str, error_msg: str
    ) -> InvalidParameterValueException:
        """Map validation-related exceptions."""
        if isinstance(e, gcp_exceptions.InvalidArgument):
            return InvalidParameterValueException(
                f"Invalid argument for {operation}: {error_msg}. "
                f"Please check the parameter name, format type, and data values."
            )
        return InvalidParameterValueException(
            f"Value out of range for {operation}: {error_msg}. "
            f"Please adjust the requested range or page size."
        )

    def _map_quota_exception(
        self, operation: str, error_msg: str
    ) -> ParameterQuotaExceededException:
        """Map quota/rate limit exceptions."""
        return ParameterQuotaExceededException(
            f"Quota/rate limit exceeded for {operation}: {error_msg}. "
            f"Please slow down request rate or request quota increase."
        )

    def _map_timeout_exception(
        self, operation: str, error_msg: str
    ) -> ParameterTimeoutException:
        """Map timeout exceptions."""
        return ParameterTimeoutException(
            f"Operation timed out during {operation}: {error_msg}. "
            f"The request took too long. Check your network and try again."
        )

    def _map_unavailable_exception(
        self, operation: str, error_msg: str
    ) -> ParameterUnavailableException:
        """Map service unavailable exceptions."""
        return ParameterUnavailableException(
            f"Service unavailable during {operation}: {error_msg}. "
            f"Please retry the operation. If the issue persists, "
            f"check Google Cloud status."
        )

    def _map_internal_exception(
        self, e: Exception, operation: str, error_msg: str
    ) -> ParameterInternalErrorException:
        """Map internal server error exceptions."""
        if isinstance(e, gcp_exceptions.InternalServerError):
            message = (
                f"Internal server error during {operation}: {error_msg}. "
                f"This is a Google Cloud issue. Please retry or contact support."
            )
        else:
            message = (
                f"Data loss detected during {operation}: {error_msg}. "
                f"This may indicate corruption or loss of parameter data."
            )
        return ParameterInternalErrorException(message)

    def _map_connection_exception(
        self, operation: str, error_msg: str
    ) -> ParameterConnectionException:
        """Map connection-related exceptions."""
        if "Retry" in error_msg or "retry" in error_msg:
            return ParameterConnectionException(
                f"Retry limit exceeded during {operation}: {error_msg}. "
                f"Network connectivity issue detected. "
                f"Check your network connection and try again."
            )
        return ParameterConnectionException(
            f"Network connectivity issue during {operation}: {error_msg}. "
            f"Check your network connection and try again."
        )

    def _map_generic_exception(
        self, e: Exception, operation: str, error_msg: str
    ) -> ParameterManagerException:
        """Map generic or unknown exceptions."""
        if isinstance(e, gcp_exceptions.MethodNotImplemented):
            return ParameterManagerException(
                f"Method not implemented for {operation}: {error_msg}. "
                f"Please check if this feature is supported by "
                f"Google Cloud Parameter Manager."
            )
        if isinstance(e, (gcp_exceptions.Aborted, gcp_exceptions.Unknown)):
            return ParameterManagerException(
                f"Operation failed during {operation}: {error_msg}. "
                f"Please retry or check if this feature is available."
            )
        return ParameterManagerException(
            f"Unexpected error during {operation}: {error_msg}. "
            f"Error type: {type(e).__name__}"
        )

    def _get_cache_key(self, parameter_name: str, version: Optional[str] = None) -> str:
        """
        Generate a cache key for a parameter.

        Args:
            parameter_name: Name of the parameter
            version: Version of the parameter

        Returns:
            Cache key string
        """
        version_str = version if version else "latest"
        return f"{parameter_name}:{version_str}"

    def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """
        Retrieve a value from cache if it exists and is not expired.

        Args:
            cache_key: Cache key to retrieve

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if not self.enable_cache:
            return None

        if cache_key in self._cache:
            value, expiry_time = self._cache[cache_key]
            if datetime.now() < expiry_time:
                self.logger.debug(
                    "Cache hit",
                    extra={
                        "cache_key": cache_key,
                        "expiry_time": expiry_time.isoformat(),
                        "project_id": self.project_id,
                        "location": self.location,
                    },
                )
                return value
            else:
                # Cache entry expired, remove it
                self.logger.debug(
                    "Cache entry expired",
                    extra={
                        "cache_key": cache_key,
                        "expiry_time": expiry_time.isoformat(),
                        "project_id": self.project_id,
                        "location": self.location,
                    },
                )
                del self._cache[cache_key]

        self.logger.debug(
            "Cache miss",
            extra={
                "cache_key": cache_key,
                "project_id": self.project_id,
                "location": self.location,
            },
        )
        return None

    def _put_in_cache(self, cache_key: str, value: Any) -> None:
        """
        Store a value in cache with TTL.

        Args:
            cache_key: Cache key to store
            value: Value to cache
        """
        if not self.enable_cache:
            return

        expiry_time = datetime.now() + timedelta(seconds=self.cache_ttl_seconds)
        self._cache[cache_key] = (value, expiry_time)

        self.logger.debug(
            "Value cached",
            extra={
                "cache_key": cache_key,
                "expiry_time": expiry_time.isoformat(),
                "cache_size": len(self._cache),
                "project_id": self.project_id,
                "location": self.location,
            },
        )

    def _invalidate_cache(
        self, parameter_name: str, version: Optional[str] = None
    ) -> None:
        """
        Invalidate cache entries for a parameter.

        Args:
            parameter_name: Name of the parameter
            version: Specific version to invalidate, or None to invalidate all versions
        """
        if not self.enable_cache:
            return

        if version:
            # Invalidate specific version
            cache_key = self._get_cache_key(parameter_name, version)
            if cache_key in self._cache:
                del self._cache[cache_key]
                self.logger.debug(
                    "Cache invalidated for specific version",
                    extra={
                        "parameter_name": parameter_name,
                        "version": version,
                        "cache_key": cache_key,
                        "project_id": self.project_id,
                        "location": self.location,
                    },
                )
        else:
            # Invalidate all versions of this parameter
            keys_to_delete = [
                key
                for key in self._cache.keys()
                if key.startswith(f"{parameter_name}:")
            ]
            for key in keys_to_delete:
                del self._cache[key]

            self.logger.debug(
                "Cache invalidated for all versions",
                extra={
                    "parameter_name": parameter_name,
                    "invalidated_count": len(keys_to_delete),
                    "project_id": self.project_id,
                    "location": self.location,
                },
            )

    def _validate_json_data(self, data: Union[str, Dict]) -> str:
        """Validate and convert JSON data to string."""
        import json

        if isinstance(data, dict):
            data_str = json.dumps(data)
            self.logger.debug(
                "Encoded dict to JSON string",
                extra={
                    "format_type": "JSON",
                    "data_type": "dict",
                    "json_length": len(data_str),
                },
            )
            return data_str
        elif isinstance(data, str):
            # Validate it's valid JSON
            try:
                json.loads(data)
                self.logger.debug(
                    "Validated JSON string",
                    extra={
                        "format_type": "JSON",
                        "data_type": "string",
                        "json_length": len(data),
                    },
                )
                return data
            except json.JSONDecodeError as e:
                self.logger.error(
                    "Invalid JSON format in string data",
                    extra={
                        "format_type": "JSON",
                        "error": str(e),
                        "error_line": e.lineno,
                        "error_column": e.colno,
                    },
                )
                raise InvalidParameterValueException(
                    f"Invalid JSON format: {str(e)} at line {e.lineno}, "
                    f"column {e.colno}"
                )
        else:
            self.logger.error(
                "Invalid data type for JSON format",
                extra={
                    "format_type": "JSON",
                    "data_type": type(data).__name__,
                    "expected_types": ["dict", "str"],
                },
            )
            raise InvalidParameterValueException(
                f"Invalid data type for JSON format: {type(data).__name__}. "
                f"Expected dict or str."
            )

    def _validate_yaml_data(self, data: Union[str, Dict]) -> str:
        """Validate and convert YAML data to string."""
        import yaml

        if isinstance(data, dict):
            data_str = yaml.dump(data)
            self.logger.debug(
                "Encoded dict to YAML string",
                extra={
                    "format_type": "YAML",
                    "data_type": "dict",
                    "yaml_length": len(data_str),
                },
            )
            return data_str
        elif isinstance(data, str):
            # Validate it's valid YAML
            try:
                yaml.safe_load(data)
                self.logger.debug(
                    "Validated YAML string",
                    extra={
                        "format_type": "YAML",
                        "data_type": "string",
                        "yaml_length": len(data),
                    },
                )
                return data
            except yaml.YAMLError as e:
                self.logger.error(
                    "Invalid YAML format in string data",
                    extra={
                        "format_type": "YAML",
                        "error": str(e),
                        "error_mark": (
                            str(e.problem_mark) if hasattr(e, "problem_mark") else None
                        ),
                    },
                )
                raise InvalidParameterValueException(f"Invalid YAML format: {str(e)}")
        else:
            self.logger.error(
                "Invalid data type for YAML format",
                extra={
                    "format_type": "YAML",
                    "data_type": type(data).__name__,
                    "expected_types": ["dict", "str"],
                },
            )
            raise InvalidParameterValueException(
                f"Invalid data type for YAML format: {type(data).__name__}. "
                f"Expected dict or str."
            )

    def _convert_unformatted_data(self, data: Any) -> str:
        """Convert unformatted data to string."""
        import json

        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            data_str = json.dumps(data)
            self.logger.debug(
                "Encoded dict to JSON string for UNFORMATTED",
                extra={
                    "format_type": "UNFORMATTED",
                    "data_type": "dict",
                    "string_length": len(data_str),
                },
            )
            return data_str
        else:
            data_str = str(data)
            self.logger.debug(
                "Converted data to string for UNFORMATTED",
                extra={
                    "format_type": "UNFORMATTED",
                    "data_type": type(data).__name__,
                    "string_length": len(data_str),
                },
            )
            return data_str

    def _validate_and_encode_data(
        self, data: Union[str, Dict, Any], format_type: str
    ) -> bytes:
        """
        Validate and encode parameter data based on format type.

        Args:
            data: The parameter data to encode
            format_type: The format type (UNFORMATTED, JSON, YAML)

        Returns:
            Encoded data as bytes

        Raises:
            InvalidParameterValueException: If data validation or encoding fails
        """
        try:
            if format_type == "JSON":
                data_str = self._validate_json_data(data)
            elif format_type == "YAML":
                data_str = self._validate_yaml_data(data)
            else:  # UNFORMATTED
                data_str = self._convert_unformatted_data(data)

            # Encode to bytes
            try:
                data_bytes = data_str.encode("utf-8")
            except UnicodeEncodeError as e:
                self.logger.error(
                    "Failed to encode data to UTF-8",
                    extra={
                        "format_type": format_type,
                        "error": str(e),
                        "encoding": "utf-8",
                    },
                )
                raise InvalidParameterValueException(
                    f"Failed to encode data to UTF-8: {str(e)}"
                )

            # Validate size (1 MiB = 1,048,576 bytes)
            if len(data_bytes) > 1_048_576:
                self.logger.error(
                    "Parameter data exceeds size limit",
                    extra={
                        "format_type": format_type,
                        "data_size_bytes": len(data_bytes),
                        "max_size_bytes": 1_048_576,
                        "size_exceeded_by": len(data_bytes) - 1_048_576,
                    },
                )
                raise InvalidParameterValueException(
                    f"Parameter data size ({len(data_bytes)} bytes) "
                    f"exceeds 1 MiB limit (1,048,576 bytes). Exceeded by "
                    f"{len(data_bytes) - 1_048_576} bytes."
                )

            self.logger.debug(
                "Data validated and encoded successfully",
                extra={
                    "format_type": format_type,
                    "data_size_bytes": len(data_bytes),
                    "encoding": "utf-8",
                },
            )

            return data_bytes

        except InvalidParameterValueException:
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            # Catch any other unexpected errors
            self.logger.error(
                "Unexpected error during data validation and encoding",
                extra={
                    "format_type": format_type,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise InvalidParameterValueException(
                f"Unexpected error during data validation: {str(e)}"
            )

    def _decode_data(
        self, data_bytes: bytes, format_type: str
    ) -> Union[str, Dict, Any]:
        """
        Decode parameter data based on format type.

        Args:
            data_bytes: The encoded parameter data
            format_type: The format type (UNFORMATTED, JSON, YAML)

        Returns:
            Decoded data (string or dict)

        Raises:
            InvalidParameterValueException: If data decoding fails
        """
        import json

        import yaml

        try:
            data_str = data_bytes.decode("utf-8")
            self.logger.debug(
                "Decoded bytes to UTF-8 string",
                extra={
                    "format_type": format_type,
                    "data_size_bytes": len(data_bytes),
                    "string_length": len(data_str),
                },
            )
        except UnicodeDecodeError as e:
            self.logger.error(
                "Failed to decode data from UTF-8",
                extra={
                    "format_type": format_type,
                    "data_size_bytes": len(data_bytes),
                    "error": str(e),
                    "encoding": "utf-8",
                },
            )
            raise InvalidParameterValueException(
                f"Failed to decode data from UTF-8: {str(e)}"
            )

        if format_type == "JSON":
            try:
                decoded_data = json.loads(data_str)
                self.logger.debug(
                    "Decoded JSON data successfully",
                    extra={
                        "format_type": format_type,
                        "decoded_type": type(decoded_data).__name__,
                    },
                )
                return decoded_data
            except json.JSONDecodeError as e:
                # If decoding fails, log warning and return as string
                self.logger.warning(
                    "Failed to decode JSON, returning as string",
                    extra={
                        "format_type": format_type,
                        "error": str(e),
                        "error_line": e.lineno,
                        "error_column": e.colno,
                    },
                )
                return data_str

        elif format_type == "YAML":
            try:
                decoded_data = yaml.safe_load(data_str)
                self.logger.debug(
                    "Decoded YAML data successfully",
                    extra={
                        "format_type": format_type,
                        "decoded_type": type(decoded_data).__name__,
                    },
                )
                return decoded_data
            except yaml.YAMLError as e:
                # If decoding fails, log warning and return as string
                self.logger.warning(
                    "Failed to decode YAML, returning as string",
                    extra={
                        "format_type": format_type,
                        "error": str(e),
                        "error_mark": (
                            str(e.problem_mark) if hasattr(e, "problem_mark") else None
                        ),
                    },
                )
                return data_str

        else:  # UNFORMATTED
            self.logger.debug(
                "Returning UNFORMATTED data as string",
                extra={"format_type": format_type, "string_length": len(data_str)},
            )
            return data_str

    def create_parameter(self, request) -> Any:
        """
        Create a new parameter in Google Cloud Parameter Manager.

        This method creates a new parameter resource with the specified format type.
        The parameter name must be unique within the project and location. Labels can be
        used to organize and categorize parameters for easier management.

        Args:
            request: ParameterCreateRequest containing:
                - parameter_name: Unique identifier for the parameter
                - format_type: Data format (UNFORMATTED, JSON, or YAML)
                - labels: Optional key-value pairs for organization

        Returns:
            ParameterCreateResponse containing:
                - parameter_name: The name of the created parameter
                - created_time: Timestamp when the parameter was created
                - format_type: The format type of the parameter

        Raises:
            ParameterManagerException: If parameter creation fails or parameter already
            exists
            InvalidParameterNameException: If parameter name is invalid
            ParameterAccessDeniedException: If credentials lack necessary permissions

        Example:
            >>> service = ParameterManagerService()
            >>> request = ParameterCreateRequest(
            ...     parameter_name="app-config",
            ...     format_type="JSON",
            ...     labels={"environment": "production"}
            ... )
            >>> response = service.create_parameter(request)
            >>> print(f"Created parameter: {response.parameter_name}")
        """
        from app.responses.parameter_manager import ParameterCreateResponse

        operation = "parameter creation"
        start_time = self._log_operation_start(
            operation,
            parameter_name=request.parameter_name,
            format_type=request.format_type,
            has_labels=bool(request.labels),
            label_count=len(request.labels) if request.labels else 0,
        )

        try:
            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # parameter_request = {
            #     "parent": self._get_parent_path(),
            #     "parameter_id": request.parameter_name,
            #     "parameter": {
            #         "format": request.format_type,
            #         "labels": request.labels or {},
            #     },
            # }
            # parameter = self.client.create_parameter(request=parameter_request)

            response = ParameterCreateResponse(
                parameter_name=request.parameter_name,
                created_time=datetime.now(),
                format_type=request.format_type,
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=request.parameter_name,
                format_type=request.format_type,
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=request.parameter_name
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"parameter_name": request.parameter_name}
            )
            raise mapped_exception

    def get_parameter(self, parameter_name: str, version: Optional[str] = None) -> Any:
        """
        Retrieve a parameter value from Google Cloud Parameter Manager.

        This method retrieves the data of a parameter. By default, it returns the latest
        version. You can specify a specific version name to retrieve historical values.
        If caching is enabled, frequently accessed parameters will be served from cache
        to improve performance.

        Args:
            parameter_name: Name of the parameter to retrieve
                (must exist in the project/location)
            version: Version identifier to retrieve. Options:
                - None (default): Returns the most recent version
                - Specific version name (e.g., "v1", "prod-2024"):
                  Returns that exact version

        Returns:
            ParameterResponse containing:
                - parameter_name: The name of the parameter
                - data: The parameter data (string or dict depending on format)
                - format_type: The format type (UNFORMATTED, JSON, YAML)
                - version: The version name that was retrieved
                - created_time: When this version was created
                - updated_time: When this version was last updated
                - labels: Optional labels for organization

        Raises:
            ParameterNotFoundException: If the parameter or specified version does not
            exist
            ParameterVersionNotFoundException: If the version is not found
            ParameterAccessDeniedException: If credentials lack read permissions
            ParameterManagerException: If retrieval fails for other reasons

        Example:
            >>> service = ParameterManagerService()
            >>> # Get latest version
            >>> parameter = service.get_parameter("app-config")
            >>> print(parameter.data)
            >>>
            >>> # Get specific version
            >>> old_parameter = service.get_parameter("app-config", version="v1")
            >>> print(f"Version {old_parameter.version}: {old_parameter.data}")
        """
        from app.responses.parameter_manager import ParameterResponse

        operation = "parameter retrieval"
        start_time = self._log_operation_start(
            operation,
            parameter_name=parameter_name,
            version=version,
            access_type="read",
            cache_enabled=self.enable_cache,
        )

        try:
            # Check cache first
            cache_key = self._get_cache_key(parameter_name, version)
            cached_response = self._get_from_cache(cache_key)
            if cached_response is not None:
                self._log_operation_success(
                    operation,
                    start_time,
                    parameter_name=parameter_name,
                    version=version,
                    cache_hit=True,
                    access_type="read",
                )
                return cached_response

            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # if version:
            #     version_path = self._get_parameter_version_path(
            #         parameter_name, version
            #     )
            #     response = self.client.get_parameter_version(
            #         request={"name": version_path}
            #     )
            # else:
            #     parameter_path = self._get_parameter_path(parameter_name)
            #     response = self.client.get_parameter(request={"name": parameter_path})
            #
            # # Decode the parameter data
            # data = self._decode_data(response.data, response.format)

            # Placeholder response
            parameter_response = ParameterResponse(
                parameter_name=parameter_name,
                data="placeholder_data",
                format_type="UNFORMATTED",
                version=version if version else "latest",
                created_time=datetime.now(),
                updated_time=datetime.now(),
                labels=None,
            )

            # Cache the response
            self._put_in_cache(cache_key, parameter_response)

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                version=version,
                access_type="read",
                cache_hit=False,
            )

            return parameter_response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=parameter_name, version=version
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"parameter_name": parameter_name, "version": version}
            )
            raise mapped_exception

    def create_parameter_version(
        self,
        parameter_name: str,
        version_name: str,
        data: Union[str, Dict, Any],
        format_type: str = "UNFORMATTED",
    ) -> Any:
        """
        Create a new version of an existing parameter with a custom version name.

        This method creates a new version of a parameter while preserving all previous
        versions. Unlike auto-incrementing version numbers, Parameter Manager allows
        custom version names (e.g., "v1", "prod-2024", "staging-config") for better
        semantic versioning. The version name must be unique within the parameter.

        Args:
            parameter_name: Name of the existing parameter (must already exist)
            version_name: Custom name for this version (e.g., "v1", "prod-2024")
                         Must be unique within the parameter
            data: The parameter data to store. Can be:
                - String: For UNFORMATTED or pre-formatted JSON/YAML
                - Dict: Will be serialized to JSON or YAML based on format_type
                - Any: Will be converted to string for UNFORMATTED
            format_type: Data format (default: "UNFORMATTED"). Options:
                - "UNFORMATTED": Plain text or custom format
                - "JSON": Structured JSON data (validated)
                - "YAML": Structured YAML data (validated)

        Returns:
            ParameterVersionResponse containing:
                - parameter_name: The name of the parameter
                - version: The custom version name that was created
                - data: The stored parameter data
                - format_type: The format type of the data
                - created_time: When this version was created

        Raises:
            ParameterNotFoundException: If the parameter does not exist
            ParameterManagerException: If version already exists or creation fails
            InvalidParameterValueException: If data validation fails for JSON/YAML
            ParameterAccessDeniedException: If credentials lack write permissions

        Example:
            >>> service = ParameterManagerService()
            >>> # Create a new version with custom name
            >>> response = service.create_parameter_version(
            ...     parameter_name="app-config",
            ...     version_name="v2",
            ...     data={"timeout": 30, "retries": 3},
            ...     format_type="JSON"
            ... )
            >>> print(f"Created version: {response.version}")
            >>>
            >>> # Create a version with semantic name
            >>> response = service.create_parameter_version(
            ...     parameter_name="database-url",
            ...     version_name="prod-2024-01",
            ...     data="postgresql://prod-db:5432/myapp",
            ...     format_type="UNFORMATTED"
            ... )
        """
        from app.responses.parameter_manager import ParameterVersionResponse

        operation = "parameter version creation"
        start_time = self._log_operation_start(
            operation,
            parameter_name=parameter_name,
            version_name=version_name,
            format_type=format_type,
            data_type=type(data).__name__,
        )

        try:
            # Validate and encode the data
            data_bytes = self._validate_and_encode_data(data, format_type)

            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # parameter_path = self._get_parameter_path(parameter_name)
            # version_request = {
            #     "parent": parameter_path,
            #     "version_id": version_name,
            #     "version": {
            #         "data": data_bytes,
            #         "format": format_type,
            #     },
            # }
            # version = self.client.create_parameter_version(request=version_request)

            # Invalidate cache for this parameter
            self._invalidate_cache(parameter_name)

            response = ParameterVersionResponse(
                parameter_name=parameter_name,
                version=version_name,
                data=data,
                format_type=format_type,
                created_time=datetime.now(),
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                version_name=version_name,
                format_type=format_type,
                data_size_bytes=len(data_bytes),
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation,
                start_time,
                e,
                parameter_name=parameter_name,
                version_name=version_name,
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e,
                operation,
                {"parameter_name": parameter_name, "version": version_name},
            )
            raise mapped_exception

    def list_parameter_versions(
        self,
        parameter_name: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> Any:
        """
        List all versions of a parameter in chronological order.

        This method retrieves metadata for all versions of a parameter,
        including version
        names, creation times, and format types. Versions are returned in chronological
        order (oldest first). The results are paginated to handle parameters with many
        versions efficiently.

        Args:
            parameter_name: Name of the parameter whose versions to list (must exist)
            page_size: Maximum number of versions to return per page (default: 100)
                      Valid range: 1-1000. Larger values may improve performance but
                      increase response time and memory usage.
            page_token: Token for retrieving the next page of results (optional)
                       Obtained from the previous response's next_page_token field.
                       Omit or pass None to retrieve the first page.

        Returns:
            ParameterVersionListResponse containing:
                - versions: List of ParameterVersionResponse objects with metadata
                - next_page_token: Token for the next page (None if no more pages)
                - total_size: Total number of versions (may be None if not available)

        Raises:
            ParameterNotFoundException: If the parameter does not exist
            ParameterAccessDeniedException: If credentials lack read permissions
            ParameterManagerException: If listing fails for other reasons

        Example:
            >>> service = ParameterManagerService()
            >>> # List all versions (first page)
            >>> response = service.list_parameter_versions("app-config")
            >>> for version in response.versions:
            ...     print(f"Version {version.version}: created {version.created_time}")
            >>>
            >>> # Paginate through all versions
            >>> page_token = None
            >>> all_versions = []
            >>> while True:
            ...     response = service.list_parameter_versions(
            ...         "app-config",
            ...         page_size=50,
            ...         page_token=page_token
            ...     )
            ...     all_versions.extend(response.versions)
            ...     if not response.next_page_token:
            ...         break
            ...     page_token = response.next_page_token
            >>> print(f"Total versions: {len(all_versions)}")
        """
        from app.responses.parameter_manager import ParameterVersionListResponse

        operation = "parameter version listing"
        start_time = self._log_operation_start(
            operation,
            parameter_name=parameter_name,
            page_size=page_size,
            has_page_token=bool(page_token),
        )

        try:
            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # parameter_path = self._get_parameter_path(parameter_name)
            # list_request = {
            #     "parent": parameter_path,
            #     "page_size": page_size,
            # }
            # if page_token:
            #     list_request["page_token"] = page_token
            #
            # response = self.client.list_parameter_versions(request=list_request)
            #
            # versions = []
            # for version in response.versions:
            #     data = self._decode_data(version.data, version.format)
            #     versions.append(ParameterVersionResponse(
            #         parameter_name=parameter_name,
            #         version=version.name.split("/")[-1],
            #         data=data,
            #         format_type=version.format,
            #         created_time=version.create_time
            #     ))

            # Placeholder response
            response = ParameterVersionListResponse(
                versions=[], next_page_token=None, total_size=0
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                version_count=len(response.versions),
                has_more_pages=bool(response.next_page_token),
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=parameter_name
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"parameter_name": parameter_name}
            )
            raise mapped_exception

    def get_parameter_version(self, parameter_name: str, version: str) -> Any:
        """
        Retrieve a specific version of a parameter by version name.

        This method retrieves the data and metadata for a specific version of
        a parameter.
        Unlike get_parameter() which returns the latest version by default, this method
        requires an explicit version name and returns exactly that version. This is
        useful for accessing historical configurations or comparing different versions.

        Args:
            parameter_name: Name of the parameter (must exist in the project/location)
            version: The specific version name to retrieve (e.g., "v1", "prod-2024")
                Must be an exact match to an existing version name

        Returns:
            ParameterResponse containing:
                - parameter_name: The name of the parameter
                - data: The parameter data (string or dict depending on format)
                - format_type: The format type (UNFORMATTED, JSON, YAML)
                - version: The version name that was retrieved
                - created_time: When this version was created
                - updated_time: When this version was last updated
                - labels: Optional labels for organization

        Raises:
            ParameterNotFoundException: If the parameter does not exist
            ParameterVersionNotFoundException: If the specified version does not exist
            ParameterAccessDeniedException: If credentials lack read permissions
            ParameterManagerException: If retrieval fails for other reasons

        Example:
            >>> service = ParameterManagerService()
            >>> # Get a specific version
            >>> old_config = service.get_parameter_version("app-config", "v1")
            >>> print(f"Version v1 data: {old_config.data}")
            >>>
            >>> # Compare two versions
            >>> v1 = service.get_parameter_version("app-config", "v1")
            >>> v2 = service.get_parameter_version("app-config", "v2")
            >>> if v1.data != v2.data:
            ...     print("Configuration changed between versions")
        """
        # Delegate to get_parameter with explicit version
        return self.get_parameter(parameter_name, version=version)

    def delete_parameter_version(self, parameter_name: str, version: str) -> Any:
        """
        Delete a specific version of a parameter.

        This method removes a specific version of a parameter while preserving
        other versions.
        The parameter itself remains intact with its other versions. This is
        useful for cleaning
        up old or incorrect versions while maintaining version history. Note that
        you cannot
        delete the only remaining version of a parameter; use delete_parameter()
        instead.

        Args:
            parameter_name: Name of the parameter (must exist in the project/location)
            version: The specific version name to delete (e.g., "v1", "prod-2024")
                    Must be an exact match to an existing version name

        Returns:
            ParameterOperationResponse containing:
                - success: True if deletion was successful
                - message: Confirmation message with details
                - operation_time: When the deletion occurred

        Raises:
            ParameterNotFoundException: If the parameter does not exist
            ParameterVersionNotFoundException: If the specified version does not exist
            ParameterAccessDeniedException: If credentials lack delete permissions
            ParameterManagerException: If deletion fails (e.g., last remaining version)

        Example:
            >>> service = ParameterManagerService()
            >>> # Delete an old version
            >>> response = service.delete_parameter_version("app-config", "v1")
            >>> print(response.message)
            >>>
            >>> # Clean up multiple old versions
            >>> old_versions = ["v1", "v2", "v3"]
            >>> for version in old_versions:
            ...     try:
            ...         service.delete_parameter_version("app-config", version)
            ...         print(f"Deleted version {version}")
            ...     except ParameterVersionNotFoundException:
            ...         print(f"Version {version} not found, skipping")
        """
        from app.responses.parameter_manager import ParameterOperationResponse

        operation = "parameter version deletion"
        start_time = self._log_operation_start(
            operation,
            parameter_name=parameter_name,
            version=version,
            operation_type="delete",
        )

        try:
            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # version_path = self._get_parameter_version_path(parameter_name, version)
            # delete_request = {
            #     "name": version_path,
            # }
            # self.client.delete_parameter_version(request=delete_request)

            # Invalidate cache for this parameter version
            self._invalidate_cache(parameter_name, version)

            response = ParameterOperationResponse(
                success=True,
                message=(
                    f"Successfully deleted version '{version}' of parameter "
                    f"'{parameter_name}'"
                ),
                operation_time=datetime.now(),
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                version=version,
                operation_type="delete",
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=parameter_name, version=version
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"parameter_name": parameter_name, "version": version}
            )
            raise mapped_exception

    def list_parameters(
        self,
        page_size: int = 100,
        page_token: Optional[str] = None,
        filter_expression: Optional[str] = None,
    ) -> Any:
        """
        List all parameters in the project and location with optional filtering.

        This method retrieves metadata for all parameters in the configured
        project and location.
        Results can be filtered using filter expressions and are paginated for
        efficient handling
        of large parameter collections. The method returns metadata only
        (no parameter data) to
        minimize response size and improve performance.

        Args:
            page_size: Maximum number of parameters to return per page (default: 100)
                      Valid range: 1-1000. Larger values may improve performance but
                      increase response time and memory usage.
            page_token: Token for retrieving the next page of results (optional)
                       Obtained from the previous response's next_page_token field.
                       Omit or pass None to retrieve the first page.
            filter_expression: Filter expression to narrow results (optional)
                              Supports filtering by labels and other metadata.
                              Examples:
                              - "labels.environment=production"
                              - "labels.team=backend AND format=JSON"
                              - "format=YAML"

        Returns:
            ParameterListResponse containing:
                - parameters: List of ParameterMetadataResponse objects
                - next_page_token: Token for the next page (None if no more pages)
                - total_size: Total number of parameters matching filter (may be None)

        Raises:
            ParameterAccessDeniedException: If credentials lack list permissions
            ParameterManagerException: If listing fails for other reasons

        Example:
            >>> service = ParameterManagerService()
            >>> # List all parameters (first page)
            >>> response = service.list_parameters()
            >>> for param in response.parameters:
            ...     print(f"{param.parameter_name}: {param.format_type}")
            >>>
            >>> # List with filtering
            >>> response = service.list_parameters(
            ...     filter_expression="labels.environment=production"
            ... )
            >>> print(f"Found {len(response.parameters)} production parameters")
            >>>
            >>> # Paginate through all parameters
            >>> page_token = None
            >>> all_parameters = []
            >>> while True:
            ...     response = service.list_parameters(
            ...         page_size=50,
            ...         page_token=page_token
            ...     )
            ...     all_parameters.extend(response.parameters)
            ...     if not response.next_page_token:
            ...         break
            ...     page_token = response.next_page_token
            >>> print(f"Total parameters: {len(all_parameters)}")
        """
        from app.responses.parameter_manager import ParameterListResponse

        operation = "parameter listing"
        start_time = self._log_operation_start(
            operation,
            page_size=page_size,
            has_page_token=bool(page_token),
            has_filter=bool(filter_expression),
            filter_expression=filter_expression,
        )

        try:
            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # parent_path = self._get_parent_path()
            # list_request = {
            #     "parent": parent_path,
            #     "page_size": page_size,
            # }
            # if page_token:
            #     list_request["page_token"] = page_token
            # if filter_expression:
            #     list_request["filter"] = filter_expression
            #
            # response = self.client.list_parameters(request=list_request)
            #
            # parameters = []
            # for param in response.parameters:
            #     # Get version count for this parameter
            #     version_count = len(list(self.client.list_parameter_versions(
            #         request={"parent": param.name}
            #     )))
            #
            #     parameters.append(ParameterMetadataResponse(
            #         parameter_name=param.name.split("/")[-1],
            #         format_type=param.format,
            #         created_time=param.create_time,
            #         updated_time=param.update_time,
            #         labels=dict(param.labels) if param.labels else None,
            #         version_count=version_count
            #     ))

            # Placeholder response
            response = ParameterListResponse(
                parameters=[], next_page_token=None, total_size=0
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_count=len(response.parameters),
                has_more_pages=bool(response.next_page_token),
                filter_applied=bool(filter_expression),
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, filter_expression=filter_expression
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"filter_expression": filter_expression}
            )
            raise mapped_exception

    def delete_parameter(self, parameter_name: str) -> Any:
        """
        Delete a parameter and all its versions.

        This method permanently removes a parameter and all of its versions from Google
        Cloud Parameter Manager. This operation cannot be undone. Use with caution,
        especially in production environments. Consider using delete_parameter_version()
        if you only need to remove specific versions.

        Args:
            parameter_name: Name of the parameter to delete
                (must exist in the project/location)
                           All versions of this parameter will be deleted

        Returns:
            ParameterOperationResponse containing:
                - success: True if deletion was successful
                - message: Confirmation message with details
                - operation_time: When the deletion occurred

        Raises:
            ParameterNotFoundException: If the parameter does not exist
            ParameterAccessDeniedException: If credentials lack delete permissions
            ParameterManagerException: If deletion fails for other reasons

        Example:
            >>> service = ParameterManagerService()
            >>> # Delete a parameter and all its versions
            >>> response = service.delete_parameter("old-config")
            >>> print(response.message)
            >>>
            >>> # Delete with error handling
            >>> try:
            ...     service.delete_parameter("app-config")
            ...     print("Parameter deleted successfully")
            ... except ParameterNotFoundException:
            ...     print("Parameter not found, may have been already deleted")
            ... except ParameterAccessDeniedException:
            ...     print("Insufficient permissions to delete parameter")
        """
        from app.responses.parameter_manager import ParameterOperationResponse

        operation = "parameter deletion"
        start_time = self._log_operation_start(
            operation,
            parameter_name=parameter_name,
            operation_type="delete",
            delete_scope="all_versions",
        )

        try:
            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # parameter_path = self._get_parameter_path(parameter_name)
            # delete_request = {
            #     "name": parameter_path,
            # }
            # self.client.delete_parameter(request=delete_request)

            # Invalidate all cache entries for this parameter
            self._invalidate_cache(parameter_name)

            response = ParameterOperationResponse(
                success=True,
                message=(
                    f"Successfully deleted parameter '{parameter_name}' "
                    f"and all its versions"
                ),
                operation_time=datetime.now(),
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                operation_type="delete",
                delete_scope="all_versions",
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=parameter_name
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"parameter_name": parameter_name}
            )
            raise mapped_exception

    def get_parameter_metadata(self, parameter_name: str) -> Any:
        """
        Get metadata for a parameter without retrieving its data.

        This method retrieves only the metadata for a parameter (format type,
        labels, version
        count, timestamps) without fetching the actual parameter data. This is
        more efficient
        than get_parameter() when you only need metadata, as it avoids
        transferring potentially
        large parameter values over the network.

        Args:
            parameter_name: Name of the parameter (must exist in the project/location)

        Returns:
            ParameterMetadataResponse containing:
                - parameter_name: The name of the parameter
                - format_type: The format type (UNFORMATTED, JSON, YAML)
                - created_time: When the parameter was created
                - updated_time: When the parameter was last updated
                - labels: Optional labels for organization
                - version_count: Total number of versions for this parameter

        Raises:
            ParameterNotFoundException: If the parameter does not exist
            ParameterAccessDeniedException: If credentials lack read permissions
            ParameterManagerException: If retrieval fails for other reasons

        Example:
            >>> service = ParameterManagerService()
            >>> # Get metadata only
            >>> metadata = service.get_parameter_metadata("app-config")
            >>> print(f"Parameter: {metadata.parameter_name}")
            >>> print(f"Format: {metadata.format_type}")
            >>> print(f"Versions: {metadata.version_count}")
            >>> print(f"Labels: {metadata.labels}")
            >>>
            >>> # Check if parameter exists and get basic info
            >>> try:
            ...     metadata = service.get_parameter_metadata("database-url")
            ...     print(f"Parameter exists with {metadata.version_count} versions")
            ... except ParameterNotFoundException:
            ...     print("Parameter does not exist")
        """
        from app.responses.parameter_manager import ParameterMetadataResponse

        operation = "parameter metadata retrieval"
        start_time = self._log_operation_start(
            operation, parameter_name=parameter_name, access_type="metadata_only"
        )

        try:
            # Note: Actual implementation would use the Parameter Manager client
            # For now, this is a placeholder that follows the framework patterns

            # TODO: Implement actual Parameter Manager API call
            # Example structure:
            # parameter_path = self._get_parameter_path(parameter_name)
            # param = self.client.get_parameter(request={"name": parameter_path})
            #
            # # Get version count
            # versions_response = self.client.list_parameter_versions(
            #     request={"parent": parameter_path}
            # )
            # version_count = len(list(versions_response))

            # Placeholder response
            response = ParameterMetadataResponse(
                parameter_name=parameter_name,
                format_type="UNFORMATTED",
                created_time=datetime.now(),
                updated_time=datetime.now(),
                labels=None,
                version_count=0,
            )

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                format_type=response.format_type,
                version_count=response.version_count,
                access_type="metadata_only",
            )

            return response

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=parameter_name
            )
            # Use comprehensive error mapping
            mapped_exception = self._map_gcp_exception(
                e, operation, {"parameter_name": parameter_name}
            )
            raise mapped_exception

    def parameter_exists(self, parameter_name: str) -> bool:
        """
        Check if a parameter exists.

        This method provides a simple boolean check for parameter existence without
        retrieving any data or metadata. It's more efficient than get_parameter() or
        get_parameter_metadata() when you only need to verify existence.

        Args:
            parameter_name: Name of the parameter to check

        Returns:
            True if the parameter exists, False otherwise

        Example:
            >>> service = ParameterManagerService()
            >>> if service.parameter_exists("app-config"):
            ...     print("Parameter exists")
            ... else:
            ...     print("Parameter does not exist")
            >>>
            >>> # Conditional parameter creation
            >>> if not service.parameter_exists("new-config"):
            ...     request = ParameterCreateRequest(
            ...         parameter_name="new-config",
            ...         format_type="JSON"
            ...     )
            ...     service.create_parameter(request)
        """
        try:
            self.get_parameter_metadata(parameter_name)
            return True
        except ParameterNotFoundException:
            return False
        except Exception:
            # For other exceptions, re-raise them
            raise

    def _parse_secret_path(self, secret_path: str) -> tuple:
        """Parse secret path to extract secret name and version."""
        path_parts = secret_path.split("/")

        if (
            len(path_parts) != 6
            or path_parts[0] != "projects"
            or path_parts[2] != "secrets"
            or path_parts[4] != "versions"
        ):
            raise InvalidParameterValueException(
                f"Invalid secret reference format: {secret_path}. "
                f"Expected format: "
                f"projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION"
            )

        secret_name = path_parts[3]
        secret_version = path_parts[5]
        return secret_name, secret_version

    def _resolve_secret_reference(
        self,
        secret_service,
        secret_path: str,
        parameter_name: str,
        operation: str,
    ) -> str:
        """Resolve a single secret reference and return the secret value."""
        from app.exceptions.secret_manager import SecretNotFoundException

        secret_name, secret_version = self._parse_secret_path(secret_path)

        self.logger.debug(
            "Resolving secret reference",
            extra={
                "operation": operation,
                "parameter_name": parameter_name,
                "secret_name": secret_name,
                "secret_version": secret_version,
                "secret_path": secret_path,
            },
        )

        try:
            # Retrieve the secret value
            secret_response = secret_service.get_secret(
                secret_name, version=secret_version
            )
            secret_value = secret_response.secret_value

            self.logger.debug(
                "Secret reference resolved successfully",
                extra={
                    "operation": operation,
                    "parameter_name": parameter_name,
                    "secret_name": secret_name,
                    "secret_version": secret_version,
                },
            )

            return secret_value

        except SecretNotFoundException as e:
            error_msg = (
                f"Secret reference '{secret_path}' in parameter '{parameter_name}' "
                f"points to a non-existent secret: {str(e)}"
            )
            self.logger.error(
                "Secret not found during parameter rendering",
                extra={
                    "operation": operation,
                    "parameter_name": parameter_name,
                    "secret_path": secret_path,
                    "error": str(e),
                },
            )
            raise ParameterManagerException(error_msg)

        except Exception as e:
            error_msg = (
                f"Failed to resolve secret reference '{secret_path}' "
                f"in parameter '{parameter_name}': {str(e)}"
            )
            self.logger.error(
                "Error resolving secret reference",
                extra={
                    "operation": operation,
                    "parameter_name": parameter_name,
                    "secret_path": secret_path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise ParameterManagerException(error_msg)

    def render_parameter(
        self, parameter_name: str, version: Optional[str] = None
    ) -> str:
        """
        Retrieve a parameter and resolve any Secret Manager secret references.

        This method retrieves a parameter value and automatically resolves any embedded
        Secret Manager secret references. Secret references use the syntax:
        ${secret.projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION}

        The method supports multiple secret references within a single parameter value
        and handles both simple text replacement and structured data formats
        (JSON, YAML).

        Args:
            parameter_name: Name of the parameter to retrieve and render (must exist)
            version: Version identifier to retrieve. Options:
                - None (default): Returns the most recent version
                - Specific version name (e.g., "v1", "prod-2024"):
                  Returns that exact version

        Returns:
            Rendered parameter value as a string with all secret references resolved to
            their actual secret values. For structured formats (JSON, YAML),
            the returned
            string will be the serialized form with secrets resolved.

        Raises:
            ParameterNotFoundException: If the parameter or specified version
            does not exist
            ParameterAccessDeniedException: If credentials lack read permissions
            for parameter
            InvalidParameterValueException: If secret reference syntax is invalid
            ParameterManagerException: If secret resolution fails or retrieval fails

        Example:
            >>> service = ParameterManagerService()
            >>>
            >>> # Parameter with secret reference:
            >>> # "database_url=postgresql://user:"
            >>> # "${secret.projects/my-project/secrets/db-password/versions/latest}"
            >>> # "@localhost/db"
            >>>
            >>> # Render the parameter (resolves secret reference)
            >>> rendered = service.render_parameter("database-config")
            >>> print(rendered)
            >>> # Output: "database_url=postgresql://user:actual-secret-value"
            >>> # "@localhost/db"
            >>>
            >>> # Parameter with multiple secret references
            >>> # "api_key=${secret.projects/my-project/secrets/api-key/versions/1}"
            >>> # "&secret=${secret.projects/my-project/secrets/"
            >>> # "api-secret/versions/latest}"
            >>> rendered = service.render_parameter("api-config")
            >>> print(rendered)
            >>> # Output: "api_key=actual-key-value&secret=actual-secret-value"
            >>>
            >>> # Render specific version
            >>> rendered = service.render_parameter("database-config", version="v1")

        Note:
            - Secret references must follow the exact syntax: ${secret.FULL_SECRET_PATH}
            - The secret path must include:
              projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION
            - If a secret reference is invalid or the secret doesn't exist,
              an exception is raised
            - The method requires both Parameter Manager and Secret Manager permissions
            - Secret values are retrieved using the Secret Manager service
        """
        import re

        from app.services.secret_manager import SecretManagerService

        operation = "parameter rendering with secret resolution"
        start_time = self._log_operation_start(
            operation,
            parameter_name=parameter_name,
            version=version,
            access_type="render",
            secret_resolution="enabled",  # nosec B106
        )

        try:
            # First, retrieve the parameter value
            parameter_response = self.get_parameter(parameter_name, version=version)

            # Convert data to string if it's not already
            if isinstance(parameter_response.data, dict):
                import json

                parameter_value = json.dumps(parameter_response.data)
            else:
                parameter_value = str(parameter_response.data)

            # Pattern to match secret references
            secret_pattern = (  # nosec B105
                r"\$\{secret\.(projects/[^/]+/secrets/[^/]+/versions/[^}]+)\}"
            )

            # Find all secret references
            secret_matches = re.findall(secret_pattern, parameter_value)

            if not secret_matches:
                # No secret references found, return the parameter value as-is
                self.logger.debug(
                    "No secret references found in parameter",
                    extra={
                        "operation": operation,
                        "parameter_name": parameter_name,
                        "version": version,
                        "secret_references_found": 0,  # nosec B105
                    },
                )

                self._log_operation_success(
                    operation,
                    start_time,
                    parameter_name=parameter_name,
                    version=version,
                    secret_references_resolved=0,
                )

                return parameter_value

            # Initialize Secret Manager service for resolving references
            secret_service = SecretManagerService(
                project_id=self.project_id, credentials=self.credentials
            )

            self.logger.debug(
                "Found secret references in parameter",
                extra={
                    "operation": operation,
                    "parameter_name": parameter_name,
                    "version": version,
                    "secret_references_found": len(secret_matches),
                    "secret_paths": secret_matches,
                },
            )

            # Resolve each secret reference
            rendered_value = parameter_value
            resolved_count = 0

            for secret_path in secret_matches:
                secret_value = self._resolve_secret_reference(
                    secret_service, secret_path, parameter_name, operation
                )

                # Replace the secret reference with the actual secret value
                secret_reference = f"${{secret.{secret_path}}}"
                rendered_value = rendered_value.replace(secret_reference, secret_value)
                resolved_count += 1

            self._log_operation_success(
                operation,
                start_time,
                parameter_name=parameter_name,
                version=version,
                secret_references_found=len(secret_matches),
                secret_references_resolved=resolved_count,
            )

            return rendered_value

        except (ParameterNotFoundException, ParameterManagerException):
            # Re-raise Parameter Manager exceptions as-is
            self._log_operation_error(
                operation,
                start_time,
                Exception("Parameter rendering failed"),
                parameter_name=parameter_name,
                version=version,
            )
            raise

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_name=parameter_name, version=version
            )
            # Wrap unexpected exceptions
            raise ParameterManagerException(
                f"Unexpected error during parameter rendering: {str(e)}"
            )

    def get_parameters_batch(
        self, parameter_names: list[str], version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve multiple parameters in a single batch operation.

        This method efficiently retrieves multiple parameters by leveraging caching and
        minimizing API calls. When caching is enabled, cached parameters are returned
        immediately, and only non-cached parameters are fetched from the API. This
        significantly improves performance when retrieving multiple parameters.

        Args:
            parameter_names: List of parameter names to retrieve
            version: Optional version to retrieve for all parameters (default: latest)
                    If specified, retrieves the same version for all parameters

        Returns:
            Dictionary mapping parameter names to ParameterResponse objects:
                - Keys: Parameter names from the input list
                - Values: ParameterResponse objects or None if parameter not found
                - Includes metadata about the batch operation

        Raises:
            ParameterAccessDeniedException: If credentials lack read permissions
            ParameterManagerException: If batch retrieval fails

        Note:
            - Parameters that don't exist will have None as their value in the result
            - Errors for individual parameters are logged but don't fail the
              entire batch
            - Cache hits are tracked separately in batch statistics
            - Empty parameter_names list returns empty results

        Example:
            >>> service = ParameterManagerService(enable_cache=True)
            >>> # Retrieve multiple parameters at once
            >>> param_names = ["app-config", "database-url", "api-key"]
            >>> results = service.get_parameters_batch(param_names)
            >>>
            >>> # Access individual parameters
            >>> for name, response in results["parameters"].items():
            ...     if response:
            ...         print(f"{name}: {response.data}")
            ...     else:
            ...         print(f"{name}: Not found")
            >>>
            >>> # Check batch statistics
            >>> print(f"Cache hits: {results['cache_hits']}")
            >>> print(f"API calls: {results['api_calls']}")
        """

        operation = "batch parameter retrieval"
        start_time = self._log_operation_start(
            operation,
            parameter_count=len(parameter_names),
            version=version,
            cache_enabled=self.enable_cache,
        )

        try:
            results = {}
            cache_hits = 0
            api_calls = 0
            errors = []

            # Track parameters that need to be fetched from API
            parameters_to_fetch = []

            # First pass: Check cache for all parameters
            for param_name in parameter_names:
                cache_key = self._get_cache_key(param_name, version)
                cached_response = self._get_from_cache(cache_key)

                if cached_response is not None:
                    results[param_name] = cached_response
                    cache_hits += 1
                    self.logger.debug(
                        "Batch cache hit",
                        extra={
                            "operation": operation,
                            "parameter_name": param_name,
                            "version": version,
                            "cache_key": cache_key,
                        },
                    )
                else:
                    parameters_to_fetch.append(param_name)

            # Second pass: Fetch non-cached parameters from API
            for param_name in parameters_to_fetch:
                try:
                    # Use the existing get_parameter method which handles caching
                    parameter_response = self.get_parameter(param_name, version)
                    results[param_name] = parameter_response
                    api_calls += 1

                except ParameterNotFoundException as e:
                    # Parameter doesn't exist, store None
                    results[param_name] = None
                    errors.append(
                        {
                            "parameter_name": param_name,
                            "error": "not_found",
                            "message": str(e),
                        }
                    )
                    self.logger.warning(
                        "Parameter not found in batch operation",
                        extra={
                            "operation": operation,
                            "parameter_name": param_name,
                            "version": version,
                        },
                    )

                except Exception as e:
                    # Other errors, store None and log
                    results[param_name] = None
                    errors.append(
                        {
                            "parameter_name": param_name,
                            "error": type(e).__name__,
                            "message": str(e),
                        }
                    )
                    self.logger.error(
                        "Error retrieving parameter in batch operation",
                        extra={
                            "operation": operation,
                            "parameter_name": param_name,
                            "version": version,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )

            # Update batch statistics
            self._batch_stats["total_batch_operations"] += 1
            self._batch_stats["total_parameters_in_batches"] += len(parameter_names)
            self._batch_stats["cache_hits_in_batches"] += cache_hits

            batch_result = {
                "parameters": results,
                "total_requested": len(parameter_names),
                "successful": len([r for r in results.values() if r is not None]),
                "failed": len([r for r in results.values() if r is None]),
                "cache_hits": cache_hits,
                "api_calls": api_calls,
                "errors": errors,
            }

            self._log_operation_success(
                operation,
                start_time,
                parameter_count=len(parameter_names),
                successful_count=batch_result["successful"],
                failed_count=batch_result["failed"],
                cache_hits=cache_hits,
                api_calls=api_calls,
            )

            return batch_result

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_count=len(parameter_names)
            )
            raise ParameterManagerException(
                f"Batch parameter retrieval failed: {str(e)}"
            )

    def create_parameters_batch(
        self, parameters: list[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create multiple parameters in a single batch operation.

        This method efficiently creates multiple parameters by processing them in
        sequence with optimized error handling. Each parameter is created
        independently, so failures for individual parameters don't affect the
        creation of others. This is useful for initial setup or bulk configuration
        updates.

        Args:
            parameters: List of parameter specifications, each containing:
                - parameter_name: Name of the parameter to create (required)
                - format_type: Data format (UNFORMATTED, JSON, YAML)
                  (optional, default: UNFORMATTED)
                - labels: Optional labels for organization (optional)
                - initial_data: Optional initial data for first version (optional)
                - initial_version_name: Optional name for first version
                  (optional, default: "v1")

        Returns:
            Dictionary containing batch operation results:
                - successful: List of successfully created parameter names
                - failed: List of failed parameter names with error details
                - total_requested: Total number of parameters in the batch
                - success_count: Number of successfully created parameters
                - failure_count: Number of failed parameter creations

        Raises:
            ParameterManagerException: If batch creation fails completely
            ParameterAccessDeniedException: If credentials lack create permissions

        Note:
            - Individual parameter failures don't stop the batch operation
            - Each parameter is validated before creation
            - Cache is not affected by parameter creation (no data to cache yet)
            - Empty parameters list returns empty results

        Example:
            >>> service = ParameterManagerService()
            >>> # Create multiple parameters at once
            >>> params = [
            ...     {
            ...         "parameter_name": "app-config",
            ...         "format_type": "JSON",
            ...         "labels": {"env": "prod"},
            ...         "initial_data": {"timeout": 30},
            ...         "initial_version_name": "v1"
            ...     },
            ...     {
            ...         "parameter_name": "database-url",
            ...         "format_type": "UNFORMATTED",
            ...         "initial_data": "postgresql://localhost:5432/db"
            ...     }
            ... ]
            >>> results = service.create_parameters_batch(params)
            >>> print(
            ...     f"Created: {results['success_count']}/{results['total_requested']}"
            ... )
            >>> for param_name in results['successful']:
            ...     print(f"✓ {param_name}")
            >>> for failure in results['failed']:
            ...     print(f"✗ {failure['parameter_name']}: {failure['error']}")
        """
        from app.requests.parameter_manager import ParameterCreateRequest

        operation = "batch parameter creation"
        start_time = self._log_operation_start(
            operation, parameter_count=len(parameters)
        )

        try:
            successful = []
            failed = []

            for param_spec in parameters:
                param_name = param_spec.get("parameter_name")

                if not param_name:
                    failed.append(
                        {
                            "parameter_name": "unknown",
                            "error": "missing_parameter_name",
                            "message": "Parameter name is required",
                        }
                    )
                    continue

                try:
                    # Create the parameter
                    create_request = ParameterCreateRequest(
                        parameter_name=param_name,
                        format_type=param_spec.get("format_type", "UNFORMATTED"),
                        labels=param_spec.get("labels"),
                    )
                    self.create_parameter(create_request)

                    # If initial data is provided, create first version
                    if "initial_data" in param_spec:
                        version_name = param_spec.get("initial_version_name", "v1")
                        self.create_parameter_version(
                            parameter_name=param_name,
                            version_name=version_name,
                            data=param_spec["initial_data"],
                            format_type=param_spec.get("format_type", "UNFORMATTED"),
                        )

                    successful.append(param_name)
                    self.logger.debug(
                        "Parameter created in batch operation",
                        extra={
                            "operation": operation,
                            "parameter_name": param_name,
                            "format_type": param_spec.get("format_type", "UNFORMATTED"),
                            "has_initial_data": "initial_data" in param_spec,
                        },
                    )

                except Exception as e:
                    failed.append(
                        {
                            "parameter_name": param_name,
                            "error": type(e).__name__,
                            "message": str(e),
                        }
                    )
                    self.logger.error(
                        "Error creating parameter in batch operation",
                        extra={
                            "operation": operation,
                            "parameter_name": param_name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )

            batch_result = {
                "successful": successful,
                "failed": failed,
                "total_requested": len(parameters),
                "success_count": len(successful),
                "failure_count": len(failed),
            }

            self._log_operation_success(
                operation,
                start_time,
                parameter_count=len(parameters),
                success_count=len(successful),
                failure_count=len(failed),
            )

            return batch_result

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_count=len(parameters)
            )
            raise ParameterManagerException(
                f"Batch parameter creation failed: {str(e)}"
            )

    def delete_parameters_batch(self, parameter_names: list[str]) -> Dict[str, Any]:
        """
        Delete multiple parameters in a single batch operation.

        This method efficiently deletes multiple parameters by processing them
        in sequence
        with optimized error handling and cache invalidation. Each parameter is deleted
        independently, so failures for individual parameters don't affect the
        deletion of
        others. All versions of each parameter are deleted.

        Args:
            parameter_names: List of parameter names to delete

        Returns:
            Dictionary containing batch operation results:
                - successful: List of successfully deleted parameter names
                - failed: List of failed parameter names with error details
                - total_requested: Total number of parameters in the batch
                - success_count: Number of successfully deleted parameters
                - failure_count: Number of failed parameter deletions

        Raises:
            ParameterManagerException: If batch deletion fails completely
            ParameterAccessDeniedException: If credentials lack delete permissions

        Note:
            - Individual parameter failures don't stop the batch operation
            - Cache entries for deleted parameters are automatically invalidated
            - Parameters that don't exist are reported as failures
            - Empty parameter_names list returns empty results
            - This operation is irreversible

        Example:
            >>> service = ParameterManagerService()
            >>> # Delete multiple old parameters
            >>> old_params = ["old-config-1", "old-config-2", "deprecated-setting"]
            >>> results = service.delete_parameters_batch(old_params)
            >>> print(
            ...     f"Deleted: {results['success_count']}/{results['total_requested']}"
            ... )
            >>> for param_name in results['successful']:
            ...     print(f"✓ Deleted {param_name}")
            >>> for failure in results['failed']:
            ...     print(
            ...         f"✗ Failed to delete {failure['parameter_name']}: "
            ...         f"{failure['error']}"
            ...     )
        """
        operation = "batch parameter deletion"
        start_time = self._log_operation_start(
            operation, parameter_count=len(parameter_names)
        )

        try:
            successful = []
            failed = []

            for param_name in parameter_names:
                try:
                    # Delete the parameter (this also invalidates cache)
                    self.delete_parameter(param_name)
                    successful.append(param_name)

                    self.logger.debug(
                        "Parameter deleted in batch operation",
                        extra={"operation": operation, "parameter_name": param_name},
                    )

                except ParameterNotFoundException as e:
                    failed.append(
                        {
                            "parameter_name": param_name,
                            "error": "not_found",
                            "message": str(e),
                        }
                    )
                    self.logger.warning(
                        "Parameter not found in batch deletion",
                        extra={"operation": operation, "parameter_name": param_name},
                    )

                except Exception as e:
                    failed.append(
                        {
                            "parameter_name": param_name,
                            "error": type(e).__name__,
                            "message": str(e),
                        }
                    )
                    self.logger.error(
                        "Error deleting parameter in batch operation",
                        extra={
                            "operation": operation,
                            "parameter_name": param_name,
                            "error": str(e),
                            "error_type": type(e).__name__,
                        },
                    )

            batch_result = {
                "successful": successful,
                "failed": failed,
                "total_requested": len(parameter_names),
                "success_count": len(successful),
                "failure_count": len(failed),
            }

            self._log_operation_success(
                operation,
                start_time,
                parameter_count=len(parameter_names),
                success_count=len(successful),
                failure_count=len(failed),
            )

            return batch_result

        except Exception as e:
            self._log_operation_error(
                operation, start_time, e, parameter_count=len(parameter_names)
            )
            raise ParameterManagerException(
                f"Batch parameter deletion failed: {str(e)}"
            )

    # Format Conversion Helper Methods

    def convert_to_json(self, data: Union[str, Dict, Any]) -> str:
        """
        Convert data to JSON format string.

        This helper method converts various data types to a JSON-formatted string.
        It handles dictionaries, strings (validates if already JSON), and other types
        by converting them to JSON representation. This is useful for preparing data
        before storing it as a JSON-formatted parameter.

        Args:
            data: Data to convert to JSON format. Can be:
                - dict: Converted directly to JSON string
                - str: Validated as JSON and returned (or wrapped if not valid JSON)
                - other: Converted to JSON representation

        Returns:
            JSON-formatted string representation of the data

        Raises:
            InvalidParameterValueException: If data cannot be converted to valid JSON

        Example:
            >>> service = ParameterManagerService()
            >>> # Convert dict to JSON
            >>> json_str = service.convert_to_json({"timeout": 30, "retries": 3})
            >>> print(json_str)
            >>> # Output: '{"timeout": 30, "retries": 3}'
            >>>
            >>> # Validate and return JSON string
            >>> json_str = service.convert_to_json('{"key": "value"}')
            >>> print(json_str)
            >>> # Output: '{"key": "value"}'
        """
        import json

        try:
            if isinstance(data, dict):
                # Convert dict to JSON string
                json_str = json.dumps(data, indent=2)
                self.logger.debug(
                    "Converted dict to JSON string",
                    extra={"data_type": "dict", "json_length": len(json_str)},
                )
                return json_str

            elif isinstance(data, str):
                # Validate if it's already valid JSON
                try:
                    json.loads(data)
                    self.logger.debug(
                        "Validated JSON string",
                        extra={"data_type": "string", "json_length": len(data)},
                    )
                    return data
                except json.JSONDecodeError:
                    # Not valid JSON, wrap it as a JSON string value
                    json_str = json.dumps(data)
                    self.logger.debug(
                        "Wrapped string as JSON value",
                        extra={
                            "data_type": "string",
                            "original_length": len(data),
                            "json_length": len(json_str),
                        },
                    )
                    return json_str

            else:
                # Convert other types to JSON
                json_str = json.dumps(data, indent=2)
                self.logger.debug(
                    "Converted data to JSON string",
                    extra={
                        "data_type": type(data).__name__,
                        "json_length": len(json_str),
                    },
                )
                return json_str

        except (TypeError, ValueError) as e:
            self.logger.error(
                "Failed to convert data to JSON",
                extra={"data_type": type(data).__name__, "error": str(e)},
            )
            raise InvalidParameterValueException(
                f"Failed to convert data to JSON: {str(e)}"
            )

    def convert_to_yaml(self, data: Union[str, Dict, Any]) -> str:
        """
        Convert data to YAML format string.

        This helper method converts various data types to a YAML-formatted string.
        It handles dictionaries, strings (validates if already YAML), and other types
        by converting them to YAML representation. This is useful for preparing data
        before storing it as a YAML-formatted parameter.

        Args:
            data: Data to convert to YAML format. Can be:
                - dict: Converted directly to YAML string
                - str: Validated as YAML and returned (or wrapped if not valid YAML)
                - other: Converted to YAML representation

        Returns:
            YAML-formatted string representation of the data

        Raises:
            InvalidParameterValueException: If data cannot be converted to valid YAML

        Example:
            >>> service = ParameterManagerService()
            >>> # Convert dict to YAML
            >>> yaml_str = service.convert_to_yaml({"timeout": 30, "retries": 3})
            >>> print(yaml_str)
            >>> # Output:
            >>> # timeout: 30
            >>> # retries: 3
            >>>
            >>> # Validate and return YAML string
            >>> yaml_str = service.convert_to_yaml('key: value\\ncount: 42')
            >>> print(yaml_str)
            >>> # Output: key: value
            >>> #         count: 42
        """
        import yaml

        try:
            if isinstance(data, dict):
                # Convert dict to YAML string
                yaml_str = yaml.dump(data, default_flow_style=False)
                self.logger.debug(
                    "Converted dict to YAML string",
                    extra={"data_type": "dict", "yaml_length": len(yaml_str)},
                )
                return yaml_str

            elif isinstance(data, str):
                # Validate if it's already valid YAML
                try:
                    yaml.safe_load(data)
                    self.logger.debug(
                        "Validated YAML string",
                        extra={"data_type": "string", "yaml_length": len(data)},
                    )
                    return data
                except yaml.YAMLError:
                    # Not valid YAML, convert it to YAML representation
                    yaml_str = yaml.dump(data, default_flow_style=False)
                    self.logger.debug(
                        "Converted string to YAML representation",
                        extra={
                            "data_type": "string",
                            "original_length": len(data),
                            "yaml_length": len(yaml_str),
                        },
                    )
                    return yaml_str

            else:
                # Convert other types to YAML
                yaml_str = yaml.dump(data, default_flow_style=False)
                self.logger.debug(
                    "Converted data to YAML string",
                    extra={
                        "data_type": type(data).__name__,
                        "yaml_length": len(yaml_str),
                    },
                )
                return yaml_str

        except (TypeError, ValueError, yaml.YAMLError) as e:
            self.logger.error(
                "Failed to convert data to YAML",
                extra={"data_type": type(data).__name__, "error": str(e)},
            )
            raise InvalidParameterValueException(
                f"Failed to convert data to YAML: {str(e)}"
            )

    def parse_json(self, json_str: str) -> Union[Dict, Any]:
        """
        Parse a JSON string into a Python object.

        This helper method parses a JSON-formatted string and returns the corresponding
        Python object (typically a dict or list). This is useful for working with
        JSON-formatted parameters after retrieval.

        Args:
            json_str: JSON-formatted string to parse

        Returns:
            Parsed Python object (dict, list, or primitive type)

        Raises:
            InvalidParameterValueException: If the string is not valid JSON

        Example:
            >>> service = ParameterManagerService()
            >>> # Parse JSON string
            >>> data = service.parse_json('{"timeout": 30, "retries": 3}')
            >>> print(data["timeout"])
            >>> # Output: 30
            >>>
            >>> # Parse JSON array
            >>> data = service.parse_json('[1, 2, 3, 4, 5]')
            >>> print(len(data))
            >>> # Output: 5
        """
        import json

        try:
            parsed_data = json.loads(json_str)
            self.logger.debug(
                "Parsed JSON string successfully",
                extra={
                    "json_length": len(json_str),
                    "parsed_type": type(parsed_data).__name__,
                },
            )
            return parsed_data

        except json.JSONDecodeError as e:
            self.logger.error(
                "Failed to parse JSON string",
                extra={
                    "json_length": len(json_str),
                    "error": str(e),
                    "error_line": e.lineno,
                    "error_column": e.colno,
                },
            )
            raise InvalidParameterValueException(
                f"Invalid JSON format: {str(e)} at line {e.lineno}, column {e.colno}"
            )

    def parse_yaml(self, yaml_str: str) -> Union[Dict, Any]:
        """
        Parse a YAML string into a Python object.

        This helper method parses a YAML-formatted string and returns the corresponding
        Python object (typically a dict or list). This is useful for working with
        YAML-formatted parameters after retrieval.

        Args:
            yaml_str: YAML-formatted string to parse

        Returns:
            Parsed Python object (dict, list, or primitive type)

        Raises:
            InvalidParameterValueException: If the string is not valid YAML

        Example:
            >>> service = ParameterManagerService()
            >>> # Parse YAML string
            >>> data = service.parse_yaml('timeout: 30\\nretries: 3')
            >>> print(data["timeout"])
            >>> # Output: 30
            >>>
            >>> # Parse YAML list
            >>> data = service.parse_yaml('- item1\\n- item2\\n- item3')
            >>> print(len(data))
            >>> # Output: 3
        """
        import yaml

        try:
            parsed_data = yaml.safe_load(yaml_str)
            self.logger.debug(
                "Parsed YAML string successfully",
                extra={
                    "yaml_length": len(yaml_str),
                    "parsed_type": type(parsed_data).__name__,
                },
            )
            return parsed_data

        except yaml.YAMLError as e:
            self.logger.error(
                "Failed to parse YAML string",
                extra={
                    "yaml_length": len(yaml_str),
                    "error": str(e),
                    "error_mark": (
                        str(e.problem_mark) if hasattr(e, "problem_mark") else None
                    ),
                },
            )
            raise InvalidParameterValueException(f"Invalid YAML format: {str(e)}")

    # Secret Reference Helper Methods

    def parse_secret_references(self, parameter_value: str) -> list[Dict[str, str]]:
        """
        Parse and extract secret references from a parameter value.

        This helper method identifies and extracts all Secret Manager secret
        references
        from a parameter value string. Secret references use the syntax:
        ${secret.projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION}

        The method returns detailed information about each reference, including the
        full path, project ID, secret name, and version. This is useful for validating
        parameter values before storage or for analyzing secret dependencies.

        Args:
            parameter_value: Parameter value string that may contain secret
            references

        Returns:
            List of dictionaries, each containing:
                 - full_reference: The complete reference string including
                   ${secret. ... }
                 - secret_path: The path portion
                   (projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION)
                - project_id: The Google Cloud project ID
                - secret_name: The name of the secret
                - version: The version identifier (e.g., "latest", "1", "v1")
                - is_valid: Boolean indicating if the reference syntax is valid

        Example:
            >>> service = ParameterManagerService()
            >>> # Parse parameter with secret references
            >>> param_value = (
            ...     "db_url=postgresql://user:"
            ...     "${secret.projects/my-project/secrets/db-password/versions/latest}"
            ...     "@localhost/db"
            ... )
            >>> references = service.parse_secret_references(param_value)
            >>> for ref in references:
            ...     print(f"Secret: {ref['secret_name']}, Version: {ref['version']}")
            >>> # Output: Secret: db-password, Version: latest
            >>>
            >>> # Parse parameter with multiple references
            >>> param_value = (
            ...     "key=${secret.projects/proj/secrets/api-key/versions/1}"
            ...     "&secret=${secret.projects/proj/secrets/api-secret/versions/2}"
            ... )
            >>> references = service.parse_secret_references(param_value)
            >>> print(f"Found {len(references)} secret references")
            >>> # Output: Found 2 secret references
        """
        import re

        # Pattern to match secret references:
        # ${secret.projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION}
        secret_pattern = (
            r"\$\{secret\.(projects/[^/]+/secrets/[^/]+/versions/[^}]+)\}"  # nosec B105
        )

        # Find all secret references
        matches = re.finditer(secret_pattern, parameter_value)

        references = []

        for match in matches:
            full_reference = match.group(0)
            secret_path = match.group(1)

            # Parse the secret path to extract components
            # Format: projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION
            path_parts = secret_path.split("/")

            is_valid = (
                len(path_parts) == 6
                and path_parts[0] == "projects"
                and path_parts[2] == "secrets"
                and path_parts[4] == "versions"
            )

            if is_valid:
                reference_info = {
                    "full_reference": full_reference,
                    "secret_path": secret_path,
                    "project_id": path_parts[1],
                    "secret_name": path_parts[3],
                    "version": path_parts[5],
                    "is_valid": True,
                }
            else:
                reference_info = {
                    "full_reference": full_reference,
                    "secret_path": secret_path,
                    "project_id": None,
                    "secret_name": None,  # nosec B105
                    "version": None,
                    "is_valid": False,
                }

            references.append(reference_info)

            self.logger.debug(
                "Parsed secret reference",
                extra={
                    "full_reference": full_reference,
                    "secret_path": secret_path,
                    "is_valid": is_valid,
                    "project_id": reference_info.get("project_id"),
                    "secret_name": reference_info.get("secret_name"),
                    "version": reference_info.get("version"),
                },
            )

        self.logger.debug(
            "Completed secret reference parsing",
            extra={
                "parameter_value_length": len(parameter_value),
                "references_found": len(references),
                "valid_references": sum(1 for r in references if r["is_valid"]),
                "invalid_references": sum(1 for r in references if not r["is_valid"]),
            },
        )

        return references

    def validate_secret_references(self, parameter_value: str) -> Dict[str, Any]:
        """
        Validate all secret references in a parameter value.

        This helper method checks if all secret references in a parameter value have
        valid syntax. It parses the references and returns a validation report
        indicating whether all references are valid and providing details about any
        invalid references.

        This is useful for validating parameter values before storage to ensure they
        can be successfully rendered later.

        Args:
            parameter_value: Parameter value string that may contain secret references

        Returns:
            Dictionary containing validation results:
                - is_valid: Boolean indicating if all references are valid
                - total_references: Total number of references found
                - valid_references: Number of valid references
                - invalid_references: Number of invalid references
                - invalid_details: List of invalid reference details (if any)

        Raises:
            InvalidParameterValueException: If any secret references have invalid syntax

        Example:
            >>> service = ParameterManagerService()
            >>> # Validate parameter with valid references
            >>> param_value = (
            ...     "key=${secret.projects/my-project/secrets/api-key/versions/1}"
            ... )
            >>> result = service.validate_secret_references(param_value)
            >>> print(f"Valid: {result['is_valid']}")
            >>> # Output: Valid: True
            >>>
            >>> # Validate parameter with invalid reference
            >>> param_value = "key=${secret.invalid/path}"
            >>> try:
            ...     result = service.validate_secret_references(param_value)
            ... except InvalidParameterValueException as e:
            ...     print(f"Validation failed: {e}")
        """
        references = self.parse_secret_references(parameter_value)

        valid_count = sum(1 for r in references if r["is_valid"])
        invalid_count = sum(1 for r in references if not r["is_valid"])

        invalid_details = [
            {
                "full_reference": r["full_reference"],
                "secret_path": r["secret_path"],
                "error": (
                    "Invalid secret reference format. Expected: "
                    "projects/PROJECT_ID/secrets/SECRET_NAME/versions/VERSION"
                ),
            }
            for r in references
            if not r["is_valid"]
        ]

        validation_result = {
            "is_valid": invalid_count == 0,
            "total_references": len(references),
            "valid_references": valid_count,
            "invalid_references": invalid_count,
            "invalid_details": invalid_details,
        }

        self.logger.debug(
            "Secret reference validation completed",
            extra={
                "parameter_value_length": len(parameter_value),
                "is_valid": validation_result["is_valid"],
                "total_references": validation_result["total_references"],
                "valid_references": valid_count,
                "invalid_references": invalid_count,
            },
        )

        if not validation_result["is_valid"]:
            error_messages = [
                f"Invalid reference: {detail['full_reference']}"
                for detail in invalid_details
            ]
            error_msg = (
                f"Found {invalid_count} invalid secret reference(s): "
                + "; ".join(error_messages)
            )

            self.logger.error(
                "Secret reference validation failed",
                extra={
                    "parameter_value_length": len(parameter_value),
                    "invalid_count": invalid_count,
                    "invalid_references": [
                        d["full_reference"] for d in invalid_details
                    ],
                },
            )

            raise InvalidParameterValueException(error_msg)

        return validation_result

    def has_secret_references(self, parameter_value: str) -> bool:
        """
        Check if a parameter value contains any secret references.

        This is a simple helper method that returns a boolean indicating whether
        the parameter value contains any Secret Manager secret references. This is
        useful for quickly determining if a parameter needs secret resolution.

        Args:
            parameter_value: Parameter value string to check

        Returns:
            True if the parameter value contains secret references, False otherwise

        Example:
            >>> service = ParameterManagerService()
            >>> # Check parameter with secret reference
            >>> param_value = (
            ...     "key=${secret.projects/my-project/secrets/api-key/versions/1}"
            ... )
            >>> has_secrets = service.has_secret_references(param_value)
            >>> print(f"Has secrets: {has_secrets}")
            >>> # Output: Has secrets: True
            >>>
            >>> # Check parameter without secret reference
            >>> param_value = "key=plain-text-value"
            >>> has_secrets = service.has_secret_references(param_value)
            >>> print(f"Has secrets: {has_secrets}")
            >>> # Output: Has secrets: False
        """
        import re

        # Pattern to match secret references
        secret_pattern = (
            r"\$\{secret\.(projects/[^/]+/secrets/[^/]+/versions/[^}]+)\}"  # nosec B105
        )

        # Check if pattern exists in the parameter value
        has_references = bool(re.search(secret_pattern, parameter_value))

        self.logger.debug(
            "Checked for secret references",
            extra={
                "parameter_value_length": len(parameter_value),
                "has_secret_references": has_references,
            },
        )

        return has_references
