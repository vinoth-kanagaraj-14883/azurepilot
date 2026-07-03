#!/usr/bin/env python
"""
AzurePilot — Azure Connection Verification Script

Run this BEFORE starting the full app to confirm that your credentials and
RBAC permissions are wired up correctly for live mode.

Usage:
    python scripts/verify_azure_connection.py

Prerequisites:
    - AZUREPILOT_MODE=live must be set (in .env or the environment)
    - AZURE_SUBSCRIPTION_ID must be set
    - Valid credentials must be available (az login, service principal env vars,
      or managed identity — see docs/setup.md)

Exit codes:
    0  — All checks passed
    1  — One or more checks failed (details printed to stdout)
"""
from __future__ import annotations

import sys
import os

# ---------------------------------------------------------------------------
# Allow running as  python scripts/verify_azure_connection.py  from the repo
# root without installing the package.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


PASS = "✓"
FAIL = "✗"


def _print_step(label: str, ok: bool, hint: str = "") -> None:
    symbol = PASS if ok else FAIL
    print(f"  [{symbol}] {label}")
    if not ok and hint:
        print(f"       → {hint}")


def main() -> int:
    """Run all verification checks and return an exit code (0=pass, 1=fail)."""
    print("=" * 60)
    print("AzurePilot — Live Azure Connection Verifier")
    print("=" * 60)

    all_passed = True

    # ------------------------------------------------------------------
    # Step 0: Load settings and validate required config
    # ------------------------------------------------------------------
    print("\n[Step 0] Loading configuration …")
    try:
        from ingestion.config import get_settings

        settings = get_settings()
    except Exception as exc:
        print(f"  [{FAIL}] Failed to load settings: {exc}")
        return 1

    if settings.is_demo:
        print(
            f"  [{FAIL}] AZUREPILOT_MODE is set to 'demo' (or not set).\n"
            "       → Set AZUREPILOT_MODE=live in your .env file and re-run."
        )
        return 1

    if not settings.azure_subscription_id:
        print(
            f"  [{FAIL}] AZURE_SUBSCRIPTION_ID is not set.\n"
            "       → Add AZURE_SUBSCRIPTION_ID=<your-subscription-id> to your .env file."
        )
        return 1

    scope_desc = settings.azure_subscription_id
    if settings.azure_resource_group:
        scope_desc += f" / resource group: {settings.azure_resource_group}"
    print(f"  [{PASS}] Mode: live | Subscription: {scope_desc}")

    # ------------------------------------------------------------------
    # Step 1: Acquire a bearer token via DefaultAzureCredential
    # ------------------------------------------------------------------
    print("\n[Step 1] Acquiring Azure credential token …")
    token: str | None = None
    try:
        from ingestion.auth import get_credential_token

        token = get_credential_token()
        _print_step("Auth — DefaultAzureCredential succeeded", ok=True)
    except Exception as exc:
        _print_step(
            "Auth — DefaultAzureCredential failed",
            ok=False,
            hint=(
                f"Error: {exc}\n"
                "       Run `az login` for CLI auth, or set AZURE_CLIENT_ID / "
                "AZURE_CLIENT_SECRET / AZURE_TENANT_ID for a service principal."
            ),
        )
        all_passed = False
        # Cannot continue without a token
        _print_summary(all_passed)
        return 1

    # ------------------------------------------------------------------
    # Step 2: Resource discovery — list VMs, App Services, Storage Accounts
    # ------------------------------------------------------------------
    print("\n[Step 2] Discovering resources …")
    resources: list = []
    try:
        from ingestion.resource_discovery import ResourceDiscovery
        from ingestion.models import ResourceType

        discovery = ResourceDiscovery(
            credential_token=token,
            subscription_id=settings.azure_subscription_id,
            resource_group=settings.azure_resource_group,
        )
        resources = discovery.list_resources()

        counts = {rt: 0 for rt in ResourceType}
        for r in resources:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1

        total = len(resources)
        ok = total > 0
        detail = ", ".join(
            f"{rt.value.split('/')[-1]}={n}" for rt, n in counts.items() if n > 0
        ) or "none"
        _print_step(
            f"Resource discovery — found {total} resource(s) ({detail})",
            ok=ok,
            hint=(
                "Zero resources found.\n"
                "       Check that AZURE_SUBSCRIPTION_ID is correct and that the "
                "identity has the 'Reader' role at subscription or resource-group scope.\n"
                "       Also confirm there are VMs, App Services, or Storage Accounts "
                "in the target scope."
            ) if not ok else "",
        )
        if not ok:
            all_passed = False
    except Exception as exc:
        _print_step(
            "Resource discovery — error",
            ok=False,
            hint=(
                f"Error: {exc}\n"
                "       Check AZURE_SUBSCRIPTION_ID and that the identity has the 'Reader' role."
            ),
        )
        all_passed = False

    # ------------------------------------------------------------------
    # Step 3 & 4: Health + Metrics for the first discovered resource
    # ------------------------------------------------------------------
    if resources:
        first = resources[0]
        print(f"\n[Step 3] Fetching Resource Health for: {first.name} …")
        try:
            from ingestion.health_client import ResourceHealthClient

            health_client = ResourceHealthClient(
                credential_token=token,
                subscription_id=settings.azure_subscription_id,
            )
            event = health_client.get_availability_status(first.id)
            _print_step(
                f"Resource Health read — status: {event.status.value}",
                ok=True,
            )
        except Exception as exc:
            _print_step(
                "Resource Health read — failed",
                ok=False,
                hint=(
                    f"Error: {exc}\n"
                    "       Check that the identity has the 'Resource Health Reader' role."
                ),
            )
            all_passed = False

        print(f"\n[Step 4] Fetching Monitor Metrics for: {first.name} …")
        try:
            from ingestion.metrics_client import MonitorMetricsClient

            metrics_client = MonitorMetricsClient(credential_token=token)
            series = metrics_client.get_metrics_for_resource_type(
                resource_id=first.id,
                resource_type=first.resource_type.value,
                lookback_hours=1,
            )
            _print_step(
                f"Monitor Metrics read — retrieved {len(series)} metric series",
                ok=True,
            )
        except Exception as exc:
            _print_step(
                "Monitor Metrics read — failed",
                ok=False,
                hint=(
                    f"Error: {exc}\n"
                    "       Check that the identity has the 'Monitoring Reader' role."
                ),
            )
            all_passed = False
    else:
        print("\n[Step 3] Skipping Resource Health check (no resources found).")
        print("[Step 4] Skipping Monitor Metrics check (no resources found).")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    _print_summary(all_passed)
    return 0 if all_passed else 1


def _print_summary(all_passed: bool) -> None:
    print("\n" + "=" * 60)
    if all_passed:
        print("All checks passed — AzurePilot is ready to run in live mode!")
        print("  python -m uvicorn api.main:app --port 8000")
    else:
        print("One or more checks FAILED — see hints above.")
        print("See docs/setup.md for detailed RBAC and auth setup instructions.")
    print("=" * 60)


if __name__ == "__main__":
    sys.exit(main())
