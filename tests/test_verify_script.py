"""
Tests for scripts/verify_azure_connection.py — validation and config-check logic.

These tests exercise only the parts of the script that don't require live Azure
connectivity (mode/config validation, summary printing).  The actual Azure API
calls are inherently untestable in CI without credentials and are not covered here.
"""
from __future__ import annotations

import importlib
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper — import the script as a module
# ---------------------------------------------------------------------------

def _import_verify():
    """Import the verify script, reloading to pick up env changes."""
    script_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "scripts"
    )
    if script_path not in sys.path:
        sys.path.insert(0, script_path)

    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "verify_azure_connection",
        os.path.join(script_path, "verify_azure_connection.py"),
    )
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------


class TestConfigValidation:
    """Test early-exit behaviour when config is missing/wrong."""

    def _run_main(self, env_overrides: dict) -> tuple[int, str]:
        """Run main() with patched env vars and capture stdout."""
        base_env = {
            "AZUREPILOT_MODE": "live",
            "AZURE_SUBSCRIPTION_ID": "sub-123",
        }
        base_env.update(env_overrides)

        # Reset cached settings before each run
        import ingestion.config as cfg

        cfg._settings = None

        captured = StringIO()
        with patch.dict(os.environ, base_env, clear=False):
            # Also reset settings inside the patched env
            cfg._settings = None
            module = _import_verify()
            with patch("sys.stdout", captured):
                exit_code = module.main()

        cfg._settings = None
        return exit_code, captured.getvalue()

    def test_exits_nonzero_when_mode_is_demo(self):
        """main() exits with code 1 when AZUREPILOT_MODE=demo."""
        import ingestion.config as cfg

        cfg._settings = None
        captured = StringIO()

        with patch.dict(os.environ, {"AZUREPILOT_MODE": "demo"}, clear=False):
            cfg._settings = None
            module = _import_verify()
            with patch("sys.stdout", captured):
                exit_code = module.main()

        cfg._settings = None
        assert exit_code == 1
        assert "demo" in captured.getvalue().lower()

    def test_exits_nonzero_when_subscription_id_missing(self):
        """main() exits with code 1 when AZURE_SUBSCRIPTION_ID is not set."""
        import ingestion.config as cfg

        cfg._settings = None

        env = {"AZUREPILOT_MODE": "live"}
        # Remove AZURE_SUBSCRIPTION_ID from environment if present
        clean_env = {k: v for k, v in os.environ.items() if k != "AZURE_SUBSCRIPTION_ID"}
        clean_env.update(env)

        captured = StringIO()
        with patch.dict(os.environ, clean_env, clear=True):
            cfg._settings = None
            module = _import_verify()
            with patch("sys.stdout", captured):
                exit_code = module.main()

        cfg._settings = None
        assert exit_code == 1
        assert "AZURE_SUBSCRIPTION_ID" in captured.getvalue()

    def test_exits_nonzero_on_auth_failure(self):
        """main() exits with code 1 when DefaultAzureCredential raises."""
        import ingestion.config as cfg

        cfg._settings = None

        captured = StringIO()
        env = {"AZUREPILOT_MODE": "live", "AZURE_SUBSCRIPTION_ID": "sub-456"}
        with patch.dict(os.environ, env, clear=False):
            cfg._settings = None
            module = _import_verify()

            with patch(
                "ingestion.auth.DefaultAzureCredential",
                side_effect=Exception("No credential"),
            ):
                with patch("sys.stdout", captured):
                    exit_code = module.main()

        cfg._settings = None
        assert exit_code == 1
        output = captured.getvalue()
        assert "✗" in output or "FAIL" in output.upper() or "failed" in output.lower()

    def test_passes_when_resources_found_and_clients_succeed(self):
        """main() returns 0 when auth, discovery, health, and metrics all succeed."""
        import ingestion.config as cfg

        cfg._settings = None

        # Build a fake AzureResource
        from ingestion.models import AzureResource, HealthEvent, HealthStatus, MetricSeries, ResourceType
        from datetime import datetime, timezone

        fake_resource = AzureResource(
            id="/subscriptions/sub-123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm1",
            name="vm1",
            resource_type=ResourceType.VIRTUAL_MACHINE,
            resource_group="rg",
            location="eastus",
            subscription_id="sub-123",
        )
        fake_health = HealthEvent(
            resource_id=fake_resource.id,
            status=HealthStatus.AVAILABLE,
            reason="",
            occurred_time=datetime.now(tz=timezone.utc),
            reported_time=datetime.now(tz=timezone.utc),
        )
        fake_series: list[MetricSeries] = []

        captured = StringIO()
        env = {"AZUREPILOT_MODE": "live", "AZURE_SUBSCRIPTION_ID": "sub-123"}

        mock_token = MagicMock()
        mock_token.token = "fake-token"
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = mock_token

        mock_discovery = MagicMock()
        mock_discovery.list_resources.return_value = [fake_resource]

        mock_health_client = MagicMock()
        mock_health_client.get_availability_status.return_value = fake_health

        mock_metrics_client = MagicMock()
        mock_metrics_client.get_metrics_for_resource_type.return_value = fake_series

        with patch.dict(os.environ, env, clear=False):
            cfg._settings = None
            module = _import_verify()

            with (
                patch("ingestion.auth.DefaultAzureCredential", return_value=mock_credential),
                patch("ingestion.resource_discovery.ResourceDiscovery", return_value=mock_discovery),
                patch("ingestion.health_client.ResourceHealthClient", return_value=mock_health_client),
                patch("ingestion.metrics_client.MonitorMetricsClient", return_value=mock_metrics_client),
                patch("sys.stdout", captured),
            ):
                exit_code = module.main()

        cfg._settings = None
        assert exit_code == 0
        output = captured.getvalue()
        assert "✓" in output


class TestPrintStep:
    """Unit tests for the _print_step helper."""

    def test_pass_shows_checkmark(self):
        captured = StringIO()
        module = _import_verify()
        with patch("sys.stdout", captured):
            module._print_step("Auth OK", ok=True)
        assert "✓" in captured.getvalue()
        assert "Auth OK" in captured.getvalue()

    def test_fail_shows_cross(self):
        captured = StringIO()
        module = _import_verify()
        with patch("sys.stdout", captured):
            module._print_step("Auth failed", ok=False, hint="run az login")
        assert "✗" in captured.getvalue()
        assert "run az login" in captured.getvalue()

    def test_no_hint_on_pass(self):
        captured = StringIO()
        module = _import_verify()
        with patch("sys.stdout", captured):
            module._print_step("OK", ok=True, hint="should not appear")
        assert "should not appear" not in captured.getvalue()
