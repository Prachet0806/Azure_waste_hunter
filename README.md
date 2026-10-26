# Azure Waste Hunter

Azure Waste Hunter performs scheduled, read-only discovery and publishes review signals for four Azure resource categories. It does not stop, resize, or delete resources. A report estimate is not a bill amount, guaranteed saving, or authorization to remediate.

## Evidence and support matrix

| Resource | Discovery evidence | Assessment | Price evidence and limits |
|---|---|---|---|
| Virtual machines | Resource Graph inventory across configured subscriptions | Seven-day average CPU; zero samples are preserved. At least `MIN_METRIC_SAMPLES` non-null daily observations are required. Below-threshold resources are `validated_idle`; others are `active`; insufficient coverage is `unassessed`. | Live price is accepted only for one exact USD consumption meter with a supported hourly unit. Explicit SKU overrides are monthly USD. Retail price is not an invoice or realized savings. |
| Managed disks | Resource Graph reports `managedBy` null | `candidate`; verify recovery, retention, and lifecycle requirements. | Live price is accepted only for one exact supported USD per-GB/month meter. Disk overrides are USD/GB/month and multiplied by size. |
| Load balancers | Empty backend-pool list | `candidate`; availability is not used as an idle signal. Confirm routing, frontend, and traffic dependencies before action. | Live single-meter price is not inferred from load-balancer type. Configure a reviewed SKU override or the price remains unknown. |
| PostgreSQL Flexible Servers | Resource Graph inventory and server state | CPU coverage is required. Stopped state or low CPU produces a review candidate, not a deletion recommendation. | Compute, storage, backup, and retention charges need a valid SKU-specific model. Otherwise price remains unknown. |

Unknown metrics and unknown prices remain visible in reports. The inventory table reports attempted/successful query counts and resource counts; it is not a claim about resources the identity cannot read. Resource Graph pagination is followed until its continuation token is absent. Runs exceeding configured limits are marked incomplete.

## Run flow

The weekly timer creates a unique run ID, writes append-only JSON manifest snapshots, records discovery and assessment outcomes, archives an immutable Markdown report, then attempts notification once. Notification carries the run ID as an idempotency key; the Logic App must enforce that key if it is to deduplicate deliveries. A timeout is recorded as `unknown` and is not retried automatically. The final manifest records report and delivery outcomes when Blob Storage is available.

## Runtime and dependencies

- Azure Functions v4, Linux, Python 3.12.
- Direct Python dependencies are pinned in `requirements.txt`; test and audit tools are pinned in `requirements-dev.txt`.
- `python -m pytest --cov --cov-branch --cov-fail-under=80` is the core logic gate.
- GitHub Actions runs lint, syntax compilation, regression tests, dependency audit, Terraform formatting, initialization, and validation.

The runtime targets Python 3.12 because Python 3.10 reaches its Azure Functions support end in October 2026. Confirm the hosting plan and region support before deployment.

## Configuration

Copy `.env.example` to a local secret-managed environment. Do not commit `.env`, access keys, connection strings, or webhook values. Locally, `DefaultAzureCredential` can use Azure CLI authentication. In Azure, the Function's system-assigned identity reads Resource Graph/Monitor and writes report blobs. Terraform retains run artifacts for 365 days by default (configurable from 30 to 3650 days), then applies the storage lifecycle deletion policy.

Pricing is fail-closed. `PRICING_MODE=live` uses only a unique exact meter with a recognized unit; unsupported, ambiguous, or failed lookups produce an unknown price. `PRICING_MODE=static` uses only explicit overrides. `PRICING_JSON` maps resource category to exact SKU keys. VM amounts are USD/month; disk amounts are USD/GB/month. Load balancer and database overrides are monthly USD by SKU. Overrides must be reviewed and updated by the operator.

## Local checks

```bash
python -m pip install -r requirements-dev.txt
ruff check .
python -m compileall -q function_app.py scanner enrichment cost_engine shared delivery compliance reporting observability
python -m pytest --cov --cov-branch --cov-fail-under=80
pip-audit -r requirements.txt
```

Terraform configuration lives in `infra/`. Use a protected remote Terraform state backend before applying: the webhook is a sensitive Terraform variable, and sensitive Terraform values can still be stored in state. The subscription IDs listed for discovery require role assignments at each selected subscription.

## Smoke checks

`scripts/live_test.sh` performs a local package/config check by default. Set `AZURE_SMOKE_LIVE=1` to permit a read-only Resource Graph query. Set `AZURE_SMOKE_ARCHIVE=1` or `AZURE_SMOKE_DELIVERY=1` separately to authorize those external side effects.

## Operations

See [runbook.md](runbook.md) for partial-run triage, dashboard queries, permissions, smoke testing, and human-reviewed remediation guidance. Staging identity, delivery, alerting, and runtime behavior require validation in an Azure subscription; repository checks do not prove a live deployment works.
