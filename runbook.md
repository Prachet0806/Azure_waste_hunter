# SRE Runbook: Azure Waste Hunter Bot

**Service Name:** `azure-waste-hunter-fn`  
**Service Owner:** Platform Engineering / SRE  
**Severity:** SEV-4 (Internal Tooling / Cost Optimization)

## Purpose
This playbook outlines troubleshooting steps, alert responses, and remediation workflows for the Azure Waste Hunter automation bot.

## Alerts & Troubleshooting

### Alert 1: Function Failure / No Report Received
**Symptom:** Weekly report not delivered to Logic App or Function execution errors > 0.  
**Severity:** Medium (Degraded Cost Visibility)

**Diagnosis Workflow:**
1. **Check Application Insights:**
   - Navigate to App Insights for the Function App.
   - Filter logs for `ERROR`, `CRITICAL`, or `Traceback`.
2. **Verify Timer Trigger:**
   - Check Function App logs for timer trigger invocation.
3. **Validate Permissions:**
   - Ensure managed identity has access to Resource Graph, Monitor, and Storage.

**Common Failures Matrix:**
| Error Message | Probable Cause | Remediation |
| :--- | :--- | :--- |
| `AccessDenied` | Missing RBAC role | Assign Reader/Monitoring Reader at subscription scope. |
| `Task timed out` | Long scan or throttling | Increase Function timeout, add retries/backoff. |
| `ValueError: AZURE_SUBSCRIPTIONS` | Missing env var | Set `AZURE_SUBSCRIPTIONS` in App Settings. |

### Alert 2: Blob Storage Access Denied
**Symptom:** Report delivered via Logic App but failed to archive.  
**Fix:**
1. Check `AZURE_STORAGE_CONNECTION_STRING` and container name.
2. Verify the Storage account key or managed identity permissions.

## Remediation Playbooks (Waste Cleanup)
*Note: The bot reports waste. Humans (or future automation) must resolve it.*

### 1. Unattached Managed Disks
- **Check:** `managedBy` is null.
- **Action:**
  1. Create a final snapshot (tag: `waste-hunter-backup`).
  2. Delete the disk.

### 2. Idle VMs
- **Check:** CPU < threshold for 7 days.
- **Verification:** Review Network In/Out to avoid deleting relays or proxies.
- **Action:**
  1. Stop the VM.
  2. Notify the `owner` tag.
  3. Deallocate after 7 days if no response.

### 3. Stopped PostgreSQL Flexible Servers
- **Check:** `state == Stopped`.
- **Action:**
  1. Take a manual backup.
  2. Delete the server if unused.

## Postmortem Template
If the bot fails to run for > 2 weeks, perform a mini-postmortem.

- **Summary:** (e.g., Bot failed due to API throttling on large account)
- **Root Cause:** (e.g., Default retry limit reached)
- **Resolution:** (e.g., Added exponential backoff for Azure Monitor calls)
- **Prevention:** (e.g., Add alert on Function duration)

## Ownership & Escalation
- **Primary On-Call:** SRE Intern / Junior SRE
- **Escalation:** Platform Team Lead
- **Repository:** `github.com/org/azure-waste-hunter`