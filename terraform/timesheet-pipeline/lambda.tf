# IMPORTANT: The Lambda resource requires a Docker image to already exist in ECR.
# Apply order:
#   1. terraform apply -target=aws_ecr_repository.lambda   (creates ECR repo)
#   2. Build and push the Docker image to ECR (see README.md)
#   3. terraform apply                                       (creates everything else)

resource "aws_lambda_function" "etl" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:latest"

  memory_size = 1024
  timeout     = 300 # matches SQS visibility timeout

  architectures = ["x86_64"]

  environment {
    variables = {
      ANTHROPIC_API_KEY = var.anthropic_api_key
      RAW_JSON_BUCKET   = var.raw_json_bucket_name
      DB_HOST           = var.db_host
      DB_NAME           = var.db_name
      DB_USER           = var.db_user
      DB_PASSWORD       = var.db_password
      DB_PORT           = var.db_port
    }
  }
}

resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn = aws_sqs_queue.process.arn
  function_name    = aws_lambda_function.etl.arn
  batch_size       = 1
  enabled          = true
}
