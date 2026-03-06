output "api_url" {
  description = "Public URL for the CivicProof API"
  value       = google_cloud_run_v2_service.api.uri
}

output "worker_url" {
  description = "Internal URL for the Worker service"
  value       = google_cloud_run_v2_service.worker.uri
}

output "gateway_url" {
  description = "Internal URL for the LLM Gateway service"
  value       = google_cloud_run_v2_service.gateway.uri
}

output "db_connection_name" {
  description = "Cloud SQL connection name for proxy"
  value       = google_sql_database_instance.main.connection_name
}

output "artifacts_bucket" {
  description = "Cloud Storage bucket for evidence artifacts"
  value       = google_storage_bucket.artifacts.name
}

output "redis_host" {
  description = "Memorystore Redis host"
  value       = google_redis_instance.main.host
}

output "redis_port" {
  description = "Memorystore Redis port"
  value       = google_redis_instance.main.port
}
