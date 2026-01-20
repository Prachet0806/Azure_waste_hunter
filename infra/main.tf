resource "azurerm_resource_group" "rg" {
  name     = var.resource_group
  location = var.location
}

# Storage for reports
resource "azurerm_storage_account" "storage" {
  name                     = "wastehunter${random_integer.rand.result}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "random_integer" "rand" {
  min = 10000
  max = 99999
}

resource "azurerm_storage_container" "reports" {
  name                  = "waste-reports"
  storage_account_name  = azurerm_storage_account.storage.name
  container_access_type = "private"
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
  name                = "azure-waste-hunter-fn"
  location            = var.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.plan.id

  identity {
    type = "SystemAssigned"
  }

  storage_account_name       = azurerm_storage_account.storage.name
  storage_account_access_key = azurerm_storage_account.storage.primary_access_key

  site_config {
    application_stack {
      python_version = "3.10"
    }
  }

  app_settings = {
    AZURE_SUBSCRIPTIONS           = var.subscription_id
    AZURE_STORAGE_CONNECTION_STRING = azurerm_storage_account.storage.primary_connection_string
    LOGIC_APP_WEBHOOK            = var.logic_app_webhook
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.ai.connection_string
  }
}

resource "azurerm_service_plan" "plan" {
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