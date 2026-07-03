"""
Unit tests for ingestion/auth.py — the shared DefaultAzureCredential token helper.

These tests mock azure.identity so they never require real Azure credentials.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGetCredentialToken:
    """Tests for ingestion.auth.get_credential_token."""

    def test_returns_token_string(self):
        """get_credential_token returns the raw token string from the credential."""
        mock_token = MagicMock()
        mock_token.token = "fake-bearer-token-abc123"

        mock_credential = MagicMock()
        mock_credential.get_token.return_value = mock_token

        with patch("ingestion.auth.DefaultAzureCredential", return_value=mock_credential):
            from ingestion.auth import get_credential_token

            result = get_credential_token()

        assert result == "fake-bearer-token-abc123"

    def test_requests_management_scope_by_default(self):
        """get_credential_token requests the ARM management scope by default."""
        mock_token = MagicMock()
        mock_token.token = "token"
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = mock_token

        with patch("ingestion.auth.DefaultAzureCredential", return_value=mock_credential):
            from ingestion.auth import get_credential_token, MANAGEMENT_SCOPE

            get_credential_token()

        mock_credential.get_token.assert_called_once_with(MANAGEMENT_SCOPE)

    def test_custom_scope_is_forwarded(self):
        """get_credential_token forwards a custom scope to DefaultAzureCredential."""
        custom_scope = "https://storage.azure.com/.default"
        mock_token = MagicMock()
        mock_token.token = "storage-token"
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = mock_token

        with patch("ingestion.auth.DefaultAzureCredential", return_value=mock_credential):
            from ingestion.auth import get_credential_token

            result = get_credential_token(scope=custom_scope)

        mock_credential.get_token.assert_called_once_with(custom_scope)
        assert result == "storage-token"

    def test_credential_error_propagates(self):
        """get_credential_token lets credential exceptions bubble up."""
        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = Exception("No credential found")

        with patch("ingestion.auth.DefaultAzureCredential", return_value=mock_credential):
            from ingestion.auth import get_credential_token

            with pytest.raises(Exception, match="No credential found"):
                get_credential_token()

    def test_instantiates_default_azure_credential(self):
        """get_credential_token instantiates DefaultAzureCredential (not a subclass)."""
        mock_token = MagicMock()
        mock_token.token = "t"
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = mock_token

        with patch(
            "ingestion.auth.DefaultAzureCredential", return_value=mock_credential
        ) as mock_cls:
            from ingestion.auth import get_credential_token

            get_credential_token()

        mock_cls.assert_called_once_with()


class TestIngestionServiceUsesSharedAuth:
    """Verify that IngestionService._get_credential_token delegates to ingestion.auth."""

    def test_service_delegates_to_auth_module(self):
        """IngestionService._get_credential_token calls ingestion.auth.get_credential_token."""
        import os

        os.environ["AZUREPILOT_MODE"] = "live"
        os.environ["AZURE_SUBSCRIPTION_ID"] = "sub-test-123"

        # Reset cached settings so the env change is picked up
        import ingestion.config as cfg_module

        cfg_module._settings = None

        try:
            with patch("ingestion.auth.get_credential_token", return_value="svc-token") as mock_fn:
                from ingestion.service import IngestionService

                svc = IngestionService()
                token = svc._get_credential_token()

            mock_fn.assert_called_once()
            assert token == "svc-token"
        finally:
            os.environ["AZUREPILOT_MODE"] = "demo"
            cfg_module._settings = None
