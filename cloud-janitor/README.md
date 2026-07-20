# Cloud Janitor

Cloud Janitor is a Phase 1 FinOps tool for Azure that scans subscriptions, identifies likely waste, scores resources, and produces a dry-run report plus a lightweight dashboard.

## Phase 1 Limitations

**Phase 1 is dry-run only.** The tool does not stop, delete, resize, deallocate, or mutate Azure resources in any way. It only reads Azure Resource Graph, Azure Monitor metrics, and Cost Management data to generate reports.

## Prerequisites

- Azure permissions:
  - **Reader** on target subscriptions/resource groups
  - **Cost Management Reader** for cost queries
- Go **1.21+**
- Node.js **18+**

## Authentication

Cloud Janitor uses `azidentity.NewDefaultAzureCredential()`.

Use either:

- Service Principal environment variables:
  - `AZURE_CLIENT_ID`
  - `AZURE_CLIENT_SECRET`
  - `AZURE_TENANT_ID`
- Or Managed Identity / other supported Azure Identity flows (no environment variables required)

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

AKS pod-level and container-level utilization is not fully available from the Azure Monitor Metrics API alone. Accurate pod insights generally require **Container Insights** and/or **Log Analytics**. In Phase 1, Cloud Janitor is best-effort only for AKS-adjacent telemetry and does not attempt deep pod-level waste detection.

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

## Road Map

- **Phase 2**: stop/deallocate VMs and delete orphaned resources with explicit safeguards
- **Phase 3**: AI-assisted recommendations, triage, and remediation planning
