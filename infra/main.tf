resource "azurerm_resource_group" "rg" {
  name     = var.resource_group
  location = var.location
}

locals {
  discovery_subscription_ids = length(var.discovery_subscription_ids) > 0 ? var.discovery_subscription_ids : [var.subscription_id]
}

# Storage for reports
resource "azurerm_storage_account" "storage" {
  # The Y1 Consumption plan has no VNet integration, so this workload cannot
  # use storage private endpoints or disable storage public-network access yet.
  # Reports remain in a private container; report SDK access uses TLS and the
  # Function's managed identity. The platform host/content path still uses key auth.
  #checkov:skip=CKV_AZURE_59: Y1 Consumption has no VNet integration; blobs are private and app data access uses managed identity.
  #checkov:skip=CKV2_AZURE_33: Y1 Consumption has no VNet integration to route storage traffic through a private endpoint.
  #checkov:skip=CKV2_AZURE_40: Azure Functions Consumption content storage still uses its platform storage key; report SDK access uses managed identity.
  #checkov:skip=CKV2_AZURE_1: This pilot stores operational inventory reports; customer-managed keys require a separately operated Key Vault and key lifecycle.
  name                            = "wastehunter${random_integer.rand.result}"
  resource_group_name             = azurerm_resource_group.rg.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "GRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  shared_access_key_enabled       = true
  sas_policy {
    expiration_period = "7.00:00:00"
    expiration_action = "Log"
  }
  queue_properties {
    logging {
      delete                = true
      read                  = true
      write                 = true
      version               = "1.0"
      retention_policy_days = 7
    }
  }
  blob_properties {
    delete_retention_policy {
      days = 30
    }
    container_delete_retention_policy {
      days = 7
    }
  }
}

resource "azurerm_storage_management_policy" "report_retention" {
  storage_account_id = azurerm_storage_account.storage.id
  rule {
    name    = "expire-run-artifacts"
    enabled = true
    filters {
      prefix_match = ["waste-reports/runs/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_modification_greater_than = var.report_retention_days
      }
    }
  }
}

resource "random_integer" "rand" {
  min = 10000
  max = 99999
}

resource "azurerm_storage_container" "reports" {
  # Blob read/write/delete logging is sent to Log Analytics by the diagnostic
  # setting below. Checkov's graph rule only recognizes the legacy storage
  # insights resource, not this current diagnostic-settings configuration.
  #checkov:skip=CKV2_AZURE_21: Blob service categories are enabled with azurerm_monitor_diagnostic_setting below; Checkov only recognizes the legacy insights resource.
  name                  = "waste-reports"
  storage_account_name  = azurerm_storage_account.storage.name
  container_access_type = "private"
}

resource "azurerm_monitor_diagnostic_setting" "report_blob" {
  name                       = "report-blob-logs"
  target_resource_id         = "${azurerm_storage_account.storage.id}/blobServices/default"
  log_analytics_workspace_id = azurerm_log_analytics_workspace.law.id

  enabled_log {
    category = "StorageRead"
  }
  enabled_log {
    category = "StorageWrite"
  }
  enabled_log {
    category = "StorageDelete"
  }
}

# Log Analytics + App Insights
resource "azurerm_log_analytics_workspace" "law" {
  name                = "law-waste-hunter"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "ai" {
  name                = "ai-waste-hunter"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  application_type    = "web"
  workspace_id        = azurerm_log_analytics_workspace.law.id
}

# Function App
resource "azurerm_linux_function_app" "func" {
  name                          = "azure-waste-hunter-fn"
  location                      = var.location
  resource_group_name           = azurerm_resource_group.rg.name
  service_plan_id               = azurerm_service_plan.plan.id
  https_only                    = true
  public_network_access_enabled = false

  identity {
    type = "SystemAssigned"
  }

  storage_account_name       = azurerm_storage_account.storage.name
  storage_account_access_key = azurerm_storage_account.storage.primary_access_key

  site_config {
    application_stack {
      python_version = "3.12"
    }
  }

  app_settings = {
    FUNCTIONS_EXTENSION_VERSION           = "~4"
    FUNCTIONS_WORKER_RUNTIME              = "python"
    AZURE_SUBSCRIPTIONS                   = join(",", local.discovery_subscription_ids)
    AZURE_STORAGE_ACCOUNT_URL             = azurerm_storage_account.storage.primary_blob_endpoint
    REPORT_CONTAINER                      = azurerm_storage_container.reports.name
    LOGIC_APP_WEBHOOK                     = var.logic_app_webhook
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.ai.connection_string
  }
}

resource "azurerm_role_assignment" "resource_reader" {
  for_each             = toset(local.discovery_subscription_ids)
  scope                = "/subscriptions/${each.value}"
  role_definition_name = "Reader"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

resource "azurerm_role_assignment" "monitor_reader" {
  for_each             = toset(local.discovery_subscription_ids)
  scope                = "/subscriptions/${each.value}"
  role_definition_name = "Monitoring Reader"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

resource "azurerm_role_assignment" "report_blob_writer" {
  scope                = azurerm_storage_account.storage.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_linux_function_app.func.identity[0].principal_id
}

resource "azurerm_service_plan" "plan" {
  # Zone redundancy and a minimum always-ready instance are not available on
  # the Y1 serverless Consumption SKU; retain the low-cost scale-to-zero plan.
  #checkov:skip=CKV_AZURE_225: Y1 Consumption does not support zone-redundant App Service plans.
  #checkov:skip=CKV_AZURE_212: Y1 Consumption scales to zero and does not expose a minimum instance count.
  name                = "waste-hunter-plan"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = "Y1"
}

resource "azurerm_monitor_action_group" "alerts" {
  name                = "ag-waste-hunter"
  resource_group_name = azurerm_resource_group.rg.name
  short_name          = "wastehunt"

  email_receiver {
    name          = "primary"
    email_address = var.alert_email
  }
}

resource "azurerm_monitor_metric_alert" "function_errors" {
  name                = "waste-hunter-function-errors"
  resource_group_name = azurerm_resource_group.rg.name
  scopes              = [azurerm_linux_function_app.func.id]
  description         = "Alert on Azure Function execution errors."
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.Web/sites"
    metric_name      = "FunctionExecutionErrors"
    aggregation      = "Total"
    operator         = "GreaterThan"
    threshold        = 0
  }

  action {
    action_group_id = azurerm_monitor_action_group.alerts.id
  }
}

resource "azurerm_monitor_scheduled_query_rules_alert_v2" "run_health" {
  name                 = "waste-hunter-run-health"
  resource_group_name  = azurerm_resource_group.rg.name
  location             = azurerm_resource_group.rg.location
  evaluation_frequency = "PT5M"
  window_duration      = "PT1H"
  scopes               = [azurerm_log_analytics_workspace.law.id]
  severity             = 2
  description          = "Alert when a run is partial or does not reach a completion event."
  display_name         = "Waste Hunter incomplete run"
  enabled              = true

  criteria {
    query                   = <<-QUERY
      let Events = AppTraces
        | where TimeGenerated > ago(1h)
        | extend Payload = parse_json(Message)
        | extend Event = tostring(Payload.event), RunId = tostring(Payload.run_id), RunStatus = tostring(Payload.status);
      let Started = Events | where Event == "run_start" | project RunId, StartedAt = TimeGenerated;
      let Completed = Events | where Event == "run_complete" | project RunId;
      let Stalled = Started | join kind=leftanti Completed on RunId | where StartedAt < ago(10m) | project AlertCount = 1;
      let Partial = Events | where Event == "run_complete" and RunStatus != "complete" | project AlertCount = 1;
      union Stalled, Partial | summarize AlertCount = count()
    QUERY
    time_aggregation_method = "Maximum"
    metric_measure_column   = "AlertCount"
    operator                = "GreaterThan"
    threshold               = 0
    failing_periods {
      minimum_failing_periods_to_trigger_alert = 1
      number_of_evaluation_periods             = 1
    }
  }

  action {
    action_groups = [azurerm_monitor_action_group.alerts.id]
  }
}
