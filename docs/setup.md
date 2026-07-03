# AzurePilot — Setup Guide

> **New here?** See the [Run Against a Real Azure Subscription](../README.md#run-against-a-real-azure-subscription)
> section in the README for the condensed quick-start before diving into the full detail below.

## Quick Start (Demo Mode — no Azure account required)

Everything works out of the box in demo mode using synthetic data.

### Prerequisites

- Python 3.11+
- pip

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/vinoth-kanagaraj-14883/azurepilot.git
cd azurepilot

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure for demo mode (default — no changes needed)
cp .env.example .env
# The default AZUREPILOT_MODE=demo is already set in .env.example

# 5. Start the API server
python -m uvicorn api.main:app --reload --port 8000

# 6. Open the UI
# Either open ui/index.html in your browser directly,
# or serve it with:
python -m http.server 3000 --directory ui
# Then visit: http://localhost:3000
```

The API auto-docs are available at: **http://localhost:8000/docs**

---

## Docker Compose (API + UI in one command)

```bash
docker-compose up --build
```

- API: http://localhost:8000
- UI:  http://localhost:3000
- API docs: http://localhost:8000/docs

---

## Live Azure Mode Setup

### Required Azure Permissions

Your service principal or managed identity needs the following RBAC roles:

| Scope | Role | Purpose |
|---|---|---|
| Subscription | `Reader` | List resources, read metrics |
| Subscription | `Monitoring Reader` | Read Azure Monitor metrics |
| Subscription | `Resource Health Reader` | Read availability statuses |

### Option 1: Service Principal (local dev / CI)

```bash
# Create a service principal
az ad sp create-for-rbac \
  --name azurepilot-sp \
  --role Reader \
  --scopes /subscriptions/<your-subscription-id>

# Assign additional roles
az role assignment create \
  --assignee <sp-client-id> \
  --role "Monitoring Reader" \
  --scope /subscriptions/<your-subscription-id>
```

Set in `.env`:
```
AZUREPILOT_MODE=live
AZURE_TENANT_ID=<your-tenant-id>
AZURE_CLIENT_ID=<sp-client-id>
AZURE_CLIENT_SECRET=<sp-client-secret>
AZURE_SUBSCRIPTION_ID=<your-subscription-id>
AZURE_RESOURCE_GROUP=<optional-resource-group>
```

### Option 2: Azure CLI (local dev)

```bash
az login
az account set --subscription <your-subscription-id>
```

Set in `.env`:
```
AZUREPILOT_MODE=live
AZURE_SUBSCRIPTION_ID=<your-subscription-id>
```

`DefaultAzureCredential` will automatically pick up your CLI login.

### Option 3: Managed Identity (Azure VM / App Service / Container)

No configuration needed — `DefaultAzureCredential` picks up the managed identity automatically. Just ensure the identity has the required roles above.

---

### Validate your setup

Before running the full app in live mode, run the included verification script.
It checks auth, resource discovery, resource health reads, and metrics reads in
sequence and prints a clear pass/fail summary with actionable hints:

```bash
python scripts/verify_azure_connection.py
```

The script exits with code `0` if all steps pass, `1` if any step fails — making
it suitable for use in CI or scripting as well.

---

### Subscription scope

AzurePilot currently targets a **single Azure subscription**, identified by
`AZURE_SUBSCRIPTION_ID`.  You can optionally narrow the scope to a single resource
group via `AZURE_RESOURCE_GROUP` (leave it blank to monitor the whole subscription).

Multi-subscription aggregation is a roadmap item (tracked in the README) and is
not yet implemented.

---

## LLM Configuration (optional)

Without LLM credentials, the mock summarizer generates realistic
template-based summaries automatically.

### Azure OpenAI (preferred)

```
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your-key>
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-15-preview
```

### OpenAI (fallback)

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `AZUREPILOT_MODE` | `demo` | `demo` = offline mock data; `live` = real Azure |
| `AZURE_TENANT_ID` | — | Azure AD tenant ID |
| `AZURE_CLIENT_ID` | — | Service principal client ID |
| `AZURE_CLIENT_SECRET` | — | Service principal client secret |
| `AZURE_SUBSCRIPTION_ID` | — | Target subscription |
| `AZURE_RESOURCE_GROUP` | — | Scope to specific RG (optional) |
| `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | — | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o` | Deployment name |
| `OPENAI_API_KEY` | — | OpenAI API key (fallback) |
| `METRICS_LOOKBACK_HOURS` | `24` | History window for metric analysis |
| `API_HOST` | `0.0.0.0` | API bind host |
| `API_PORT` | `8000` | API bind port |

---

## Troubleshooting

**"Could not connect to API"** in the UI
→ Ensure the API server is running: `python -m uvicorn api.main:app --port 8000`

**"No incidents detected"**
→ In demo mode this shouldn't happen. In live mode, check that your subscription has
  VMs, App Services, or Storage Accounts and that your credentials have the required roles.

**Azure OpenAI errors**
→ The system automatically falls back to the mock summarizer. Check logs for details.

**Dependency install fails**
→ Ensure you are using Python 3.11+: `python --version`
→ Try: `pip install --upgrade pip` then re-run `pip install -r requirements.txt`
