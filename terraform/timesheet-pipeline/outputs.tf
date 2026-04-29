output "upload_bucket_name" {
  description = "S3 bucket where staff upload timesheet PDFs"
  value       = aws_s3_bucket.upload.bucket
}

output "raw_json_bucket_name" {
  description = "S3 bucket for raw Claude JSON output"
  value       = aws_s3_bucket.raw_json.bucket
}

output "sqs_queue_url" {
  description = "SQS processing queue URL"
  value       = aws_sqs_queue.process.url
}

output "sqs_dlq_url" {
  description = "SQS dead-letter queue URL"
  value       = aws_sqs_queue.dlq.url
}

output "ecr_repository_url" {
  description = "ECR repository URL for the Lambda image"
  value       = aws_ecr_repository.lambda.repository_url
}

output "lambda_function_name" {
  description = "Lambda function name"
  value       = aws_lambda_function.etl.function_name
}
