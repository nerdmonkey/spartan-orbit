"""
Azure Monitor / Application Insights logging implementation.

Key features:
1. Structured logging with JSON output
2. Application Insights integration via OpenTelemetry
3. Automatic correlation with distributed traces
4. Proper severity levels
5. PII sanitization
6. Source location for debugging
"""

import inspect
import json
import os
import sys
from typing import Any, Dict, Optional

from app.helpers.environment import env

from .base import BaseLogger


class AzureMonitorLogger(BaseLogger):
    """
    Azure Monitor / Application Insights logging implementation.

    Features:
    - Structured logging with JSON output
    - Application Insights correlation
    - Proper severity levels (Verbose, Information, Warning, Error, Critical)
    - Resource labels for service identification
    - Source location for debugging
    - PII sanitization
    - Azure Functions integration
    """

    # Azure Monitor severity levels
    SEVERITY_MAPPING = {
        "debug": "Verbose",
        "info": "Information",
        "warning": "Warning",
        "error": "Error",
        "critical": "Critical",
        "exception": "Error",
    }

    def __init__(
        self,
        service_name: str,
        level: str = "INFO",
        sample_rate: float = None,
    ):
        self.service_name = service_name
        self.sample_rate = (
            sample_rate
            if sample_rate is not None
            else float(env("LOG_SAMPLE_RATE", "1.0"))
        )
        self.level = level.upper()

        # Sensitive fields for PII sanitization (optimized as frozenset)
        self._sensitive_fields = frozenset(
            {
                "password",
                "token",
                "secret",
                "key",
                "auth",
                "credentials",
                "api_key",
                "access_token",
                "refresh_token",
                "private_key",
                "authorization",
                "cookie",
                "session",
            }
        )

        # Get project root for source location (cached)
        self.project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "../../..")
        )

        # Cache environment info
        self._app_environment = env("APP_ENVIRONMENT", "production")
        self._app_version = env("APP_VERSION", "unknown")
        self._function_name = env("AZURE_FUNCTIONS_FUNCTION_NAME")

        # Use JSON stdout for Azure Functions
        # Application Insights automatically parses structured logs
        self.use_json_stdout = True

    def _is_azure_functions(self) -> bool:
        """Check if running in Azure Functions environment."""
        return bool(
            env("FUNCTIONS_WORKER_RUNTIME")
            or env("AZURE_FUNCTIONS_ENVIRONMENT")
            or env("WEBSITE_INSTANCE_ID")
        )

    def _get_operation_context(self) -> Optional[Dict[str, str]]:
        """
        Extract operation context for Application Insights correlation.

        Returns correlation ID and parent ID if available.
        """
        context = {}

        # Check for Azure Functions invocation ID
        invocation_id = env("AZURE_FUNCTIONS_INVOCATION_ID")
        if invocation_id:
            context["operation_Id"] = invocation_id

        # Check for parent operation ID (for distributed tracing)
        parent_id = env("REQUEST_ID") or env("TRACEPARENT")
        if parent_id:
            context["operation_ParentId"] = parent_id

        return context if context else None

    def _get_source_location(self) -> Optional[Dict[str, Any]]:
        """
        Get source location for debugging.

        Returns:
            Dict with file, line, and function, or None
        """
        # Skip in production for performance
        if self._app_environment == "production":
            return None

        try:
            stack = inspect.stack()
            # Skip frames: [0]=this method, [1]=_create_log_entry,
            # [2]=_write_log, [3]=log method. Start from frame 4.
            for frame_info in stack[4:]:
                filename = frame_info.filename

                # Skip logging framework and stdlib
                if any(
                    skip in filename
                    for skip in [
                        "/services/logging/",
                        "/helpers/logger.py",
                        "site-packages/",
                        "/lib/python",
                    ]
                ):
                    continue

                # Make path relative to project root
                if filename.startswith(self.project_root):
                    filename = filename[len(self.project_root) + 1 :]

                return {
                    "file": filename,
                    "line": frame_info.lineno,
                    "function": frame_info.function,
                }
        except Exception:  # nosec
            # Silently fail on source location errors
            pass

        return None

    def _sanitize_data(self, data: Any) -> Any:
        """
        Recursively sanitize sensitive data (PII) from logs.
        """
        if isinstance(data, dict):
            return {
                k: (
                    "[REDACTED]"
                    if any(
                        sensitive in k.lower() for sensitive in self._sensitive_fields
                    )
                    else self._sanitize_data(v)
                )
                for k, v in data.items()
            }
        elif isinstance(data, (list, tuple)):
            return [self._sanitize_data(item) for item in data]
        return data

    def _create_log_entry(
        self, severity: str, message: str, extra: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Create structured log entry for Azure Monitor.

        Format follows Application Insights custom dimensions pattern.
        """
        log_entry = {
            "timestamp": self._get_iso_timestamp(),
            "severity": self.SEVERITY_MAPPING.get(severity.lower(), "Information"),
            "message": message,
            "service": self.service_name,
            "environment": self._app_environment,
        }

        # Add operation context for correlation
        operation_context = self._get_operation_context()
        if operation_context:
            log_entry.update(operation_context)

        # Add function name if available
        if self._function_name:
            log_entry["function"] = self._function_name

        # Add custom dimensions (sanitized)
        if extra:
            sanitized_extra = self._sanitize_data(extra)
            log_entry["customDimensions"] = sanitized_extra

        # Add source location in non-production
        source_location = self._get_source_location()
        if source_location:
            log_entry["sourceLocation"] = source_location

        return log_entry

    def _get_iso_timestamp(self) -> str:
        """Get current timestamp in ISO 8601 format."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()

    def _write_log(self, log_entry: Dict[str, Any]) -> None:
        """
        Write log entry to stdout as JSON.

        Azure Functions and Application Insights automatically
        capture and parse JSON logs from stdout.
        """
        try:
            json_log = json.dumps(log_entry, default=str)
            print(json_log, file=sys.stdout, flush=True)
        except Exception as e:
            # Fallback to plain text if JSON serialization fails
            print(
                f"[{log_entry.get('severity', 'ERROR')}] "
                f"{log_entry.get('message', 'Log serialization error')}: {e}",
                file=sys.stderr,
            )

    def _should_log(self, severity: str) -> bool:
        """Determine if log should be written based on level."""
        level_priority = {
            "DEBUG": 0,
            "VERBOSE": 0,
            "INFO": 1,
            "INFORMATION": 1,
            "WARNING": 2,
            "ERROR": 3,
            "CRITICAL": 4,
        }

        current_priority = level_priority.get(self.level.upper(), 1)
        log_priority = level_priority.get(
            self.SEVERITY_MAPPING.get(severity.lower(), "Information").upper(), 1
        )

        return log_priority >= current_priority

    def info(self, message: str, extra: Optional[Dict] = None, **kwargs):
        """Log info level message."""
        if self._should_log("info"):
            merged_extra = {**(extra or {}), **kwargs}
            log_entry = self._create_log_entry("info", message, merged_extra)
            self._write_log(log_entry)

    def error(self, message: str, extra: Optional[Dict] = None, **kwargs):
        """Log error level message."""
        if self._should_log("error"):
            merged_extra = {**(extra or {}), **kwargs}
            log_entry = self._create_log_entry("error", message, merged_extra)
            self._write_log(log_entry)

    def warning(self, message: str, extra: Optional[Dict] = None, **kwargs):
        """Log warning level message."""
        if self._should_log("warning"):
            merged_extra = {**(extra or {}), **kwargs}
            log_entry = self._create_log_entry("warning", message, merged_extra)
            self._write_log(log_entry)

    def debug(self, message: str, extra: Optional[Dict] = None, **kwargs):
        """Log debug level message."""
        if self._should_log("debug"):
            merged_extra = {**(extra or {}), **kwargs}
            log_entry = self._create_log_entry("debug", message, merged_extra)
            self._write_log(log_entry)

    def critical(self, message: str, extra: Optional[Dict] = None, **kwargs):
        """Log critical level message."""
        if self._should_log("critical"):
            merged_extra = {**(extra or {}), **kwargs}
            log_entry = self._create_log_entry("critical", message, merged_extra)
            self._write_log(log_entry)

    def exception(self, message: str, extra: Optional[Dict] = None, **kwargs):
        """Log exception with traceback."""
        import traceback

        merged_extra = {**(extra or {}), **kwargs}
        merged_extra["traceback"] = traceback.format_exc()

        log_entry = self._create_log_entry("exception", message, merged_extra)
        self._write_log(log_entry)
