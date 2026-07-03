"""
Shared authentication helper for AzurePilot ingestion layer.

Provides a single function to acquire a bearer token via DefaultAzureCredential,
used by IngestionService and the verify_azure_connection diagnostic script.
"""
from __future__ import annotations

from azure.identity import DefaultAzureCredential  # type: ignore[import]

MANAGEMENT_SCOPE = "https://management.azure.com/.default"


def get_credential_token(scope: str = MANAGEMENT_SCOPE) -> str:
    """
    Obtain a bearer token via DefaultAzureCredential.

    Supports: Managed Identity, Service Principal env vars (AZURE_CLIENT_ID /
    AZURE_CLIENT_SECRET / AZURE_TENANT_ID), az CLI login, and other credential
    sources supported by the azure-identity SDK.

    Args:
        scope: OAuth2 scope to request.  Defaults to the Azure Resource Manager
               management plane scope.

    Returns:
        A raw bearer token string.

    Raises:
        azure.core.exceptions.ClientAuthenticationError: if no valid credential
            could be found.
    """
    credential = DefaultAzureCredential()
    token = credential.get_token(scope)
    return token.token
