variable "location" {
  default = "westeurope"
}

variable "resource_group" {
  default = "rg-azure-waste-hunter"
}

variable "subscription_id" {}

variable "discovery_subscription_ids" {
  description = "Subscription UUIDs scanned by Resource Graph. Empty uses subscription_id."
  type        = list(string)
  default     = []
  validation {
    condition     = alltrue([for id in var.discovery_subscription_ids : can(regex("^[0-9a-fA-F-]{36}$", id))])
    error_message = "Every discovery_subscription_ids item must be a subscription UUID."
  }
}

variable "logic_app_webhook" {
  type      = string
  sensitive = true
}

variable "alert_email" {}

variable "report_retention_days" {
  description = "Days to retain immutable run report and manifest blobs before lifecycle deletion."
  type        = number
  default     = 365
  validation {
    condition     = var.report_retention_days >= 30 && var.report_retention_days <= 3650
    error_message = "report_retention_days must be between 30 and 3650."
  }
}
