output "ocr_input_bucket" {
  value = aws_s3_bucket.ocr_input.bucket
}

output "rds_cluster_endpoint" {
  value = aws_rds_cluster.ocrdb.endpoint
}

output "rds_cluster_reader_endpoint" {
  value = aws_rds_cluster.ocrdb.reader_endpoint
}

output "sns_topic_arn" {
  value = aws_sns_topic.textract_completion.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.ocr_pipeline_lambda_role.arn
}

output "textract_role_arn" {
  value = aws_iam_role.textract_sns_role.arn
}
