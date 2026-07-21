# Cloud Janitor

Cloud Janitor is a Phase 1 FinOps tool for Azure that scans subscriptions, identifies likely waste, scores resources, and produces a dry-run report plus a lightweight dashboard.

## Phase 1 Limitations

**Phase 1 is dry-run only.** The tool does not stop, delete, resize, deallocate, or mutate Azure resources in any way. It only reads Azure Resource Graph, Azure Monitor metrics, and Cost Management data, then produces a report.

## Prerequisites

- Azure permissions:
  - **Reader** on target subscriptions/resource groups
  - **Cost Management Reader** for cost queries
- Go **1.21+**
- Node.js **18+**
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) (recommended for local auth and subscription discovery)

## Authentication

Cloud Janitor uses `azidentity.NewDefaultAzureCredential()`.

Use either:

- Service Principal environment variables:
  - `AZURE_CLIENT_ID`
  - `AZURE_CLIENT_SECRET`
  - `AZURE_TENANT_ID`
- Or Managed Identity / other supported Azure Identity flows (no environment variables required)
- Or an interactive `az login` session (picked up automatically as a fallback by `DefaultAzureCredential`)

## How to Run a Scan

```bash
cd cloud-janitor
go build ./cmd/janitor
./janitor scan --config config/rules.json --subscriptions <sub-id> --output output/
```

The generated report is written to `output/report-YYYY-MM-DD.json`.

## How to View the Dashboard

```bash
cd dashboard && npm install && npm run build
cd ..
./janitor serve --report output/report-2026-07-20.json --port 8080
# Open http://localhost:8080
```

## AKS Metrics Note

AKS pod-level and container-level utilization is not fully available from the Azure Monitor Metrics API alone. Accurate pod insights generally require **Container Insights** and/or **Log Analytics** integration, which is out of scope for Phase 1.

## Report Format

The JSON report includes:

- Dry-run flag and generation timestamp
- Subscription IDs scanned
- Total resource count
- Score band summary
- Estimated monthly savings
- Top waste by owner
- Full per-resource records with score, band, cost, and reasons
- Human-readable summary text

## Scoring Rules

| Rule | Default Score |
| --- | ---: |
| Expired (`ExpiryDate` tag in the past) | 40 |
| Idle resource | 30 |
| Missing owner tag | 20 |
| No tags at all | 10 |
| Premium SKU keyword match | 15 |
| Over per-resource budget threshold | 25 |

Band thresholds:

- **0-19**: Healthy
- **20-39**: Warning
- **40-69**: Cleanup Candidate
- **70+**: Delete Candidate

## Configuration

- `config/rules.json` contains scoring and threshold settings.
- `config/config.yaml.example` shows example runtime configuration values.

---

## Run on Your Own Azure Subscription — Step by Step

This walks through everything needed to point Cloud Janitor at a **real** Azure subscription, from zero.

### Step 1: Identify your subscription(s)

```bash
az login
az account list --output table
```

Note the `SubscriptionId` column for every subscription you want scanned. You can pass multiple, comma-separated, to the CLI later.

If you only want to scan one subscription and it's not your default:

```bash
az account set --subscription "<subscription-id>"
```

### Step 2: Grant the required RBAC roles

Cloud Janitor is **read-only**, so it only needs two roles. Assign them to whichever identity will run the tool (your own user for local testing, or a service principal / managed identity for scheduled runs).

**For local testing as yourself** (using `az login`), just confirm you already have at least Reader access — most users do by default on subscriptions they own.

**For a Service Principal** (recommended for scheduled/automated runs):

```bash
# Create the service principal (no built-in role yet)
az ad sp create-for-rbac --name "cloud-janitor-sp" --skip-assignment

# Note the appId, password, and tenant from the output, then:
az role assignment create \
  --assignee "<appId>" \
  --role "Reader" \
  --scope "/subscriptions/<subscription-id>"

az role assignment create \
  --assignee "<appId>" \
  --role "Cost Management Reader" \
  --scope "/subscriptions/<subscription-id>"
```

Repeat the two `az role assignment create` commands for each additional subscription you want scanned.

**For a Managed Identity** (if running the tool from an Azure VM, Container App, or Function):

```bash
az role assignment create \
  --assignee-object-id "<managed-identity-principal-id>" \
  --assignee-principal-type ServicePrincipal \
  --role "Reader" \
  --scope "/subscriptions/<subscription-id>"

az role assignment create \
  --assignee-object-id "<managed-identity-principal-id>" \
  --assignee-principal-type ServicePrincipal \
  --role "Cost Management Reader" \
  --scope "/subscriptions/<subscription-id>"
```

> Role assignments can take a few minutes to propagate. If you see `AuthorizationFailed` errors immediately after assigning roles, wait and retry.

### Step 3: Set credentials for Cloud Janitor

Pick **one** of the following, matching what you set up in Step 2.

**Option A — Service Principal:**

```bash
export AZURE_CLIENT_ID="<appId>"
export AZURE_CLIENT_SECRET="<password>"
export AZURE_TENANT_ID="<tenant>"
```

**Option B — Managed Identity:**
No environment variables needed. Just run the tool from inside the Azure resource that has the managed identity attached.

**Option C — Your own `az login` session (quickest for a first test):**
Nothing extra to set — `DefaultAzureCredential` automatically falls back to your Azure CLI session if no service principal variables are present.

### Step 4: Review/adjust scoring thresholds (optional)

Open `cloud-janitor/config/rules.json` and adjust as needed:
- Idle lookback windows (default 7 days for VM/App Service, 30 days for Storage)
- CPU/requests/transactions thresholds
- Budget thresholds used for the "Over Budget" rule
- Premium SKU keyword list

Defaults are usable as-is for a first run.

### Step 5: Build the CLI

```bash
cd cloud-janitor
go build -o janitor ./cmd/janitor
```

### Step 6: Run the scan against your subscription(s)

```bash
./janitor scan \
  --config config/rules.json \
  --subscriptions "<sub-id-1>,<sub-id-2>" \
  --output output/
```

This performs, in order:
1. Resource Graph discovery across the given subscriptions
2. Azure Monitor metric collection per resource for idle detection
3. Cost Management queries for actual cost per resource
4. Rule engine scoring and banding
5. Report generation to `output/report-<date>.json`

You'll see a console summary like:

```
Scanned 142 resources across 2 subscription(s).
Healthy: 88  Warning: 25  Cleanup Candidate: 21  Delete Candidate: 8
Estimated potential monthly savings: ₹43,000
```

**Nothing is stopped, deleted, resized, or modified** — this is strictly a read/report operation.

### Step 7: View the results in the dashboard

```bash
cd dashboard && npm install && npm run build && cd ..
./janitor serve --report output/report-<date>.json --port 8080
```

Open `http://localhost:8080` in a browser to see:
- Summary cards (totals, band counts, estimated savings)
- A sortable/filterable table of every scanned resource with score, band, cost, owner, and the specific reasons it was flagged

### Step 8: Validate before trusting the output

Before relying on this for cleanup decisions:
- Spot-check a handful of flagged "Delete Candidate" resources against what you already know is idle/orphaned.
- Run the scan daily/weekly for 1–2 weeks to confirm consistency (per the original dry-run recommendation).
- Tune `config/rules.json` thresholds based on what you observe (e.g., raise idle CPU threshold if too many false positives).

### Step 9: (Optional) Automate the scan

Run it on a schedule via cron, a GitHub Actions workflow, or an Azure Function/Container App timer trigger — using a Service Principal or Managed Identity for credentials (Step 3, Options A or B) rather than an interactive login.

### Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| `AuthorizationFailed` | Role assignment hasn't propagated yet, or wrong scope | Wait a few minutes; confirm scope is the subscription, not a resource group |
| `no subscriptions found` | Wrong/no `--subscriptions` value, or account has no access | Re-run `az account list` and confirm the subscription ID |
| Empty/zero cost figures | Cost Management Reader role missing | Re-check Step 2 role assignment |
| `Invalid query definition: Invalid dataset grouping: 'Currency'` | Running an older janitor build | Pull latest code and rebuild `janitor` — currency is returned automatically and is no longer sent as a grouping |
| `DefaultAzureCredential: failed to acquire token` | No valid credential source available | Run `az login`, or set the Service Principal env vars from Step 3 |
| AKS pods/containers show no idle signal | Expected — Monitor Metrics alone can't see pod-level data | See "AKS Metrics Note" above; Container Insights integration is a future enhancement |

## Road Map

- **Phase 2**: stop/deallocate VMs and delete orphaned resources with explicit safeguards
- **Phase 3**: AI-assisted recommendations, triage, and remediation planning
