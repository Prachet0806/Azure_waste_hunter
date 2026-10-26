# Azure Waste Hunter Operations Runbook

## Service boundary

The timer-triggered Function performs read-only discovery. It does not stop, resize, or delete Azure resources. Findings are candidates for human review; estimates are not measured savings. Every report is archived under `runs/<run_id>/report.md`, with append-only manifest snapshots under `runs/<run_id>/manifests/`.

## Run status and triage

| Status / symptom | Meaning | First checks |
|---|---|---|
| `complete` | All configured queries and assessments completed, candidate prices were known, report was archived, and webhook accepted the notification. | Review the manifest and evidence in the report. |
| `partial` | Inventory, evidence, pricing, delivery, or finalization has a gap. | Open the newest manifest; inspect `errors`, per-resource query counts, assessment counts, unpriced count, and delivery state. |
| Delivery `unknown` | Request timed out or returned a server error; receiver acceptance cannot be proven. | Check the Logic App run history using the run ID/idempotency key. Do not replay until receiver state is known. |
| No final completion event | The process may have crashed, exceeded the run budget, or lost storage access. | Find the `run_start` event and latest manifest revision; alert rule detects a start without completion after ten minutes. |

`unknown` delivery is not retried automatically. A new run receives a new ID. The receiving Logic App must persist and enforce the `Idempotency-Key` header if duplicate suppression is required.

## Permissions and configuration

- Assign `Reader` and `Monitoring Reader` to the Function identity at each configured discovery subscription.
- Assign `Storage Blob Data Contributor` at the report storage account scope.
- Keep the webhook URL in a secret store / Function App setting. Protect Terraform state: sensitive Terraform variables are still present in state.
- Run artifacts are retained for 365 days by default; review `report_retention_days` against audit and incident-response needs before applying Terraform.
- The report account now uses GRS, seven-day SAS-expiry logging, Queue service request logs, and Blob service diagnostic logs in Log Analytics. GRS and diagnostic ingestion add storage and monitoring costs; review those against the deployment budget.
- The Function App has public ingress disabled because it is timer-triggered. This also prevents external access to its SCM/Kudu deployment endpoint; deploy from an approved private path or managed build agent. The report container is private and application Blob access uses the Function identity. The Storage account still has a public network endpoint because the Y1 Consumption plan has no VNet integration; shared-key authorization remains enabled for platform storage/content compatibility. Checkov skips for private networking, shared-key disablement, and customer-managed keys document these limits. Move to a VNet-capable plan and migrate host/content storage to identity-based access before requiring private-only storage or disabling account keys.
- SAS expiration is configured for seven days with the AzureRM 3.x supported `Log` action. Treat the policy as monitoring, not enforcement; the application does not issue SAS tokens.
- Confirm `AZURE_SUBSCRIPTIONS`, `AZURE_STORAGE_ACCOUNT_URL`, `REPORT_CONTAINER`, `LOGIC_APP_WEBHOOK`, and the runtime settings before deployment.
- `MIN_METRIC_SAMPLES` defaults to five daily samples in a seven-day window. A missing or sparse series is `unassessed`.
- Live pricing can return unknown when a meter is ambiguous, unsupported, unavailable, or in a non-USD currency. Explicit overrides are monthly review estimates and must be reviewed.

## Queries for Application Insights / Log Analytics

Run event counts and partial outcomes:

```kusto
AppTraces
| where TimeGenerated > ago(30d)
| extend Payload = parse_json(Message)
| summarize Events=count() by Event=tostring(Payload.event), Status=tostring(Payload.status)
```

Find incomplete runs and unpriced candidates:

```kusto
AppTraces
| where TimeGenerated > ago(30d)
| extend Payload = parse_json(Message)
| where tostring(Payload.event) == "run_complete"
| where tostring(Payload.status) != "complete"
| project TimeGenerated, RunId=tostring(Payload.run_id), Status=tostring(Payload.status)
| order by TimeGenerated desc
```

The Terraform alert rule pages on partial completion events and starts without a completion event. Confirm query results and alert delivery in the staging workspace before relying on it operationally.

## Staging smoke checks

Run `scripts/live_test.sh` for the package and environment check. To permit a read-only Resource Graph query, set `AZURE_SMOKE_LIVE=1`. Archive and webhook delivery each require their own opt-in (`AZURE_SMOKE_ARCHIVE=1`, `AZURE_SMOKE_DELIVERY=1`). Use a dedicated staging subscription and webhook. Never use production report destinations for a smoke check.

Before release, validate:

1. Function package imports on the configured Linux/Python runtime.
2. Each subscription is visible and Resource Graph continuation tokens are followed.
3. Metrics include zero samples and sparse windows become `unassessed`.
4. Storage writes immutable run artifacts using the Function identity.
5. An induced partial scan and ambiguous delivery produce visible manifest states and alerts.
6. The Logic App deduplicates a repeated `Idempotency-Key` if duplicate suppression is part of the service contract.

## Human-reviewed candidate workflows

- **Unattached disk:** verify backup, retention, restore, and owner requirements before any deletion.
- **Low-CPU VM:** review CPU coverage, network and application telemetry, ownership, and workload schedules before resizing or deallocation.
- **Load balancer without backends:** verify frontend use, private links, DNS, health probes, and traffic history before removal.
- **Stopped PostgreSQL server:** verify expected maintenance state, backups, storage/backup charges, and owner intent before any change.

The report does not run any remediation. Obtain the service owner's approval and follow the organization's change process for every action.

## Incident record

- Run ID and UTC time:
- Inventory/query outcomes:
- Assessment and price gaps:
- Delivery state and receiver run history:
- Root cause and mitigation:
- Follow-up prevention work:
