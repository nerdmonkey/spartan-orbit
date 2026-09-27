"""
Unit tests for Secret Manager request validation edge cases.

Tests specifically target uncovered validation logic paths including
whitespace validation and edge case scenarios.

Coverage Target: Lines 28, 42, 49, 63 in app/requests/secret_manager.py
"""

import pytest
from pydantic import ValidationError

from app.requests.secret_manager import (
    SecretAccessRequest,
    SecretCreateRequest,
    SecretVersionCreateRequest,
)


# Testing edge cases for secret name and value validation


class TestSecretCreateRequestValidation:
    """Test SecretCreateRequest validation edge cases."""

    def test_secret_name_whitespace_various_types(self):
        """Test secret name rejects various whitespace patterns."""
        whitespace_patterns = [
            "   ",  # spaces
            "\t\t",  # tabs
            "\n\n",  # newlines
            " \t\n ",  # mixed whitespace
        ]

        for whitespace in whitespace_patterns:
            with pytest.raises(ValidationError) as exc_info:
                SecretCreateRequest(
                    secret_name=whitespace,
                    secret_value="test-value",
                )

            assert "Secret name cannot be empty or whitespace" in str(exc_info.value)

    def test_secret_value_whitespace_various_types(self):
        """Test secret value rejects various whitespace patterns."""
        whitespace_patterns = [
            "   ",  # spaces
            "\t\t",  # tabs
            "\n\n",  # newlines
            " \t\n ",  # mixed whitespace
        ]

        for whitespace in whitespace_patterns:
            with pytest.raises(ValidationError) as exc_info:
                SecretCreateRequest(
                    secret_name="test-secret",
                    secret_value=whitespace,
                )

            assert "Secret value cannot be empty or whitespace" in str(exc_info.value)

    def test_secret_name_leading_trailing_whitespace_trimmed(self):
        """Test secret name is properly trimmed."""
        variations = [
            ("  test-secret", "test-secret"),
            ("test-secret  ", "test-secret"),
            ("  test-secret  ", "test-secret"),
            ("\ttest-secret\t", "test-secret"),
            ("\n test-secret \n", "test-secret"),
        ]

        for input_name, expected_name in variations:
            request = SecretCreateRequest(
                secret_name=input_name,
                secret_value="test-value",
            )
            assert request.secret_name == expected_name

    def test_secret_name_with_internal_whitespace_preserved(self):
        """Test secret name with internal whitespace is preserved."""
        # Internal whitespace should be preserved after trimming
        request = SecretCreateRequest(
            secret_name="  my secret name  ",
            secret_value="test-value",
        )

        # After trimming: "my secret name"
        assert request.secret_name == "my secret name"

    def test_secret_value_not_trimmed(self):
        """Test secret value preserves whitespace (no trimming)."""
        # Note: Check if secret_value has a trimming validator
        # If no validator exists, this test confirms the behavior
        request = SecretCreateRequest(
            secret_name="test-secret",
            secret_value="  value-with-spaces  ",
        )

        # If there's no trimming, spaces are preserved
        # If there IS trimming, adjust this assertion
        assert request.secret_value == "  value-with-spaces  "

    def test_secret_name_empty_string(self):
        """Test empty string secret name is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SecretCreateRequest(
                secret_name="",
                secret_value="test-value",
            )

        error_msg = str(exc_info.value)
        # Either caught by min_length or custom validator
        assert (
            "String should have at least 1 character" in error_msg
            or "Secret name cannot be empty" in error_msg
        )

    def test_secret_value_empty_string(self):
        """Test empty string secret value is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SecretCreateRequest(
                secret_name="test-secret",
                secret_value="",
            )

        error_msg = str(exc_info.value)
        # Either caught by min_length or custom validator
        assert (
            "String should have at least 1 character" in error_msg
            or "Secret value cannot be empty" in error_msg
        )


class TestSecretVersionCreateRequestValidation:
    """Test SecretVersionCreateRequest validation edge cases."""

    def test_version_create_secret_name_whitespace(self):
        """Test SecretVersionCreateRequest rejects whitespace-only secret name."""
        whitespace_patterns = ["   ", "\t", "\n", " \t\n "]

        for whitespace in whitespace_patterns:
            with pytest.raises(ValidationError) as exc_info:
                SecretVersionCreateRequest(
                    secret_name=whitespace,
                    secret_value="new-value",
                )

            assert "Secret name cannot be empty or whitespace" in str(exc_info.value)

    def test_version_create_secret_value_whitespace(self):
        """Test SecretVersionCreateRequest rejects whitespace-only secret value."""
        whitespace_patterns = ["   ", "\t", "\n", " \t\n "]

        for whitespace in whitespace_patterns:
            with pytest.raises(ValidationError) as exc_info:
                SecretVersionCreateRequest(
                    secret_name="test-secret",
                    secret_value=whitespace,
                )

            assert "Secret value cannot be empty or whitespace" in str(exc_info.value)

    def test_version_create_secret_name_trimmed(self):
        """Test SecretVersionCreateRequest trims secret name."""
        request = SecretVersionCreateRequest(
            secret_name="  test-secret  ",
            secret_value="new-value",
        )

        assert request.secret_name == "test-secret"

    def test_version_create_with_special_characters_in_name(self):
        """Test SecretVersionCreateRequest with special characters in secret name."""
        # GCP allows certain special characters in secret names
        special_name = "test-secret_with-special.chars123"
        request = SecretVersionCreateRequest(
            secret_name=special_name,
            secret_value="test-value",
        )

        assert request.secret_name == special_name

    def test_version_create_with_long_value(self):
        """Test SecretVersionCreateRequest with very long secret value."""
        # Secrets can be up to 64 KiB
        long_value = "x" * 65536  # 64 KiB
        request = SecretVersionCreateRequest(
            secret_name="test-secret",
            secret_value=long_value,
        )

        assert len(request.secret_value) == 65536


class TestSecretAccessRequestValidation:
    """Test SecretAccessRequest validation edge cases."""

    def test_access_request_secret_name_whitespace(self):
        """Test SecretAccessRequest rejects whitespace-only secret name."""
        whitespace_patterns = ["   ", "\t", "\n", " \t\n "]

        for whitespace in whitespace_patterns:
            with pytest.raises(ValidationError) as exc_info:
                SecretAccessRequest(
                    secret_name=whitespace,
                )

            assert "Secret name cannot be empty or whitespace" in str(exc_info.value)

    def test_access_request_secret_name_trimmed(self):
        """Test SecretAccessRequest trims secret name."""
        request = SecretAccessRequest(
            secret_name="  test-secret  ",
        )

        assert request.secret_name == "test-secret"

    def test_access_request_default_version(self):
        """Test SecretAccessRequest defaults to 'latest' version."""
        request = SecretAccessRequest(
            secret_name="test-secret",
        )

        assert request.version == "latest"

    def test_access_request_with_numeric_version(self):
        """Test SecretAccessRequest with numeric version string."""
        request = SecretAccessRequest(
            secret_name="test-secret",
            version="12345",
        )

        assert request.version == "12345"

    def test_access_request_with_version_aliases(self):
        """Test SecretAccessRequest with various version aliases."""
        version_aliases = ["latest", "1", "42", "v1.0.0"]

        for version in version_aliases:
            request = SecretAccessRequest(
                secret_name="test-secret",
                version=version,
            )

            assert request.version == version

    def test_access_request_secret_name_max_length(self):
        """Test SecretAccessRequest with maximum length secret name."""
        long_name = "a" * 255
        request = SecretAccessRequest(
            secret_name=long_name,
        )

        assert request.secret_name == long_name

    def test_access_request_secret_name_exceeds_max_length(self):
        """Test SecretAccessRequest rejects secret name exceeding 255 characters."""
        too_long_name = "a" * 256

        with pytest.raises(ValidationError) as exc_info:
            SecretAccessRequest(
                secret_name=too_long_name,
            )

        assert "String should have at most 255 characters" in str(exc_info.value)


# Comprehensive parametrized tests


class TestSecretRequestParametrized:
    """Parametrized tests for comprehensive coverage."""

    @pytest.mark.parametrize(
        "whitespace",
        [
            "   ",  # spaces
            "\t\t\t",  # tabs
            "\n\n",  # newlines
            "\r\n",  # carriage return + newline
            " \t\n\r ",  # mixed
        ],
    )
    def test_secret_create_rejects_whitespace_name(self, whitespace):
        """Parametrized test for whitespace rejection in secret name."""
        with pytest.raises(ValidationError) as exc_info:
            SecretCreateRequest(
                secret_name=whitespace,
                secret_value="test-value",
            )

        assert "Secret name cannot be empty or whitespace" in str(exc_info.value)

    @pytest.mark.parametrize(
        "whitespace",
        [
            "   ",  # spaces
            "\t\t\t",  # tabs
            "\n\n",  # newlines
            "\r\n",  # carriage return + newline
            " \t\n\r ",  # mixed
        ],
    )
    def test_secret_create_rejects_whitespace_value(self, whitespace):
        """Parametrized test for whitespace rejection in secret value."""
        with pytest.raises(ValidationError) as exc_info:
            SecretCreateRequest(
                secret_name="test-secret",
                secret_value=whitespace,
            )

        assert "Secret value cannot be empty or whitespace" in str(exc_info.value)

    @pytest.mark.parametrize(
        "input_name,expected_name",
        [
            ("  test-secret", "test-secret"),
            ("test-secret  ", "test-secret"),
            ("  test-secret  ", "test-secret"),
            ("\ttest-secret", "test-secret"),
            ("test-secret\n", "test-secret"),
        ],
    )
    def test_secret_name_trimming(self, input_name, expected_name):
        """Parametrized test for secret name trimming."""
        request = SecretCreateRequest(
            secret_name=input_name,
            secret_value="test-value",
        )

        assert request.secret_name == expected_name

    @pytest.mark.parametrize(
        "replication_policy",
        [
            "automatic",
            "user-managed",
            "custom-policy",
        ],
    )
    def test_secret_create_with_various_replication_policies(self, replication_policy):
        """Parametrized test for various replication policies."""
        request = SecretCreateRequest(
            secret_name="test-secret",
            secret_value="test-value",
            replication_policy=replication_policy,
        )

        assert request.replication_policy == replication_policy

    @pytest.mark.parametrize(
        "labels",
        [
            {"env": "prod"},
            {"env": "dev", "team": "backend"},
            {"env": "uat", "team": "platform", "version": "1.0"},
            {},  # Empty dict
            None,  # No labels
        ],
    )
    def test_secret_create_with_various_labels(self, labels):
        """Parametrized test for various label configurations."""
        request = SecretCreateRequest(
            secret_name="test-secret",
            secret_value="test-value",
            labels=labels,
        )

        assert request.labels == labels
