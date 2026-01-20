# Azure Waste Hunter — Cloud FinOps Automation Bot

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Azure](https://img.shields.io/badge/Azure-Functions%20%7C%20Resource%20Graph-blue)

## Overview
Azure Waste Hunter is a serverless FinOps automation framework that reduces cloud spend and operational toil. It detects wasted Azure resources, estimates monthly cost, enforces tagging compliance, and delivers optimization reports on a schedule.

## Key Capabilities
- **Waste Detection**
  - Unattached managed disks
  - Idle VMs (avg CPU < threshold over 7 days)
  - Unused Load Balancers (no backends, low availability)
  - Stopped PostgreSQL Flexible Servers
- **Financial Estimation** — static defaults or live Azure Retail Prices
- **Governance** — required tags: `owner`, `env`, `cost-center`
- **Reporting** — Markdown report (Jinja2) delivered via Logic App webhook; archived to Azure Blob
- **Serverless Automation** — Azure Functions timer trigger

## Architecture

```
Azure Functions (timer)
        ↓
Resource Graph (discovery)
        ↓
Azure Monitor (metrics)
        ↓
Cost Engine (cost_engine/estimator.py)
        ↓
Compliance (compliance/tag_checker.py)
        ↓
Reporting (reporting/report_builder.py)
        ↓
Delivery (Logic App + Blob Storage)
```

**Data Flow:**
1. **Trigger:** Azure Functions timer starts the weekly run.
2. **Scan:** Resource Graph queries find candidate resources.
3. **Enrich:** Azure Monitor metrics mark idle resources.
4. **Analyze:** Cost estimates + tag compliance.
5. **Report:** Jinja2 Markdown summary is generated.
6. **Deliver:** Send to Logic App webhook and archive to Blob Storage.

### Project Structure
```text
azure-waste-hunter/
├── scanner/              # Resource discovery (Azure Resource Graph)
├── enrichment/           # Azure Monitor metrics enrichment
├── cost_engine/          # Pricing and estimation
├── compliance/           # Tagging checks
├── reporting/            # Jinja2 report template
├── delivery/             # Logic App + Blob Storage delivery
├── function_app.py       # Azure Functions entrypoint
├── infra/                # Terraform (Azure resources)
├── requirements.txt      # Dependencies
├── .env.example          # Environment variable template
└── runbook.md            # Operational playbook
```

## Setup & Deployment

### Prerequisites
- Python 3.9+
- Azure CLI logged in
- Terraform 1.5+

### 1. Infrastructure (Terraform)
Configure variables in `infra/variables.tf` and apply:
```bash
cd infra
terraform init
terraform apply -var="subscription_id=<sub-id>" -var="logic_app_webhook=<url>" -var="alert_email=<email>"
```

### 2. Deploy Function
Package and deploy the Function App (zip deploy or CI). Ensure the Function uses Python 3.10+.

### 3. Configure App Settings
Set the values from `.env.example` in the Function App configuration:
- `AZURE_SUBSCRIPTIONS`
- `LOGIC_APP_WEBHOOK`
- `AZURE_STORAGE_CONNECTION_STRING`
- `REPORT_CONTAINER`
- `CPU_THRESHOLD`
- `PRICING_MODE`, `PRICING_JSON` or `PRICING_FILE`
- `PRICING_CACHE_TTL_SECONDS`
- `RETRY_MAX_ATTEMPTS`, `RETRY_BASE_DELAY_MS`

## Example Output
**Subject:** Azure Waste Hunter — Weekly Cost Optimization Report

> **Total Monthly Waste:** $42.30  
> **Wasted Resources:**  
> - `vm-123` (VM): $32.30/mo  
> - `disk-456` (Disk): $10.00/mo  
> **Tagging Violations:**  
> - `vm-123` missing: `owner`, `cost-center`

## Operations
See [runbook.md](runbook.md) for on-call playbooks, alerts, and remediation workflows.