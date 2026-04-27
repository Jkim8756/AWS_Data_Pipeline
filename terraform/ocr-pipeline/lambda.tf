# -----------------------------------------------------------
# Lambda Layer: psycopg2-python313 (version 1)
# Used by all three Lambda functions
# NOTE: The layer zip must exist locally to re-deploy.
#       Reference the existing ARN directly for import-only setups.
# -----------------------------------------------------------
resource "aws_lambda_layer_version" "psycopg2_python313" {
  layer_name          = "psycopg2-python313"
  description         = "psycopg2-binary for Python 3.13"
  compatible_runtimes = ["python3.13"]
  skip_destroy        = true

  # filename only needed when deploying a new version
  # existing version 1 is tracked via import — do not set filename here
  # to deploy a new version: add filename and run terraform apply

  lifecycle {
    ignore_changes = [filename, source_code_hash]
  }
}

locals {
  lambda_layer_arn = "arn:aws:lambda:${var.aws_region}:${var.account_id}:layer:psycopg2-python313:1"

  # Shared VPC config for all Lambdas
  lambda_vpc_config_subnets = var.subnet_ids

  # Shared env vars present in multiple functions
  common_env = {
    DB_PORT       = "5432"
    DB_NAME       = "ocrdb"
    DB_HOST       = "ocrdb.cluster-cg50w40uytey.us-east-1.rds.amazonaws.com"
    DB_SECRET_ARN = "arn:aws:secretsmanager:${var.aws_region}:${var.account_id}:secret:ocr-pipeline/db-credentials-7dbJsg"
  }
}

# -----------------------------------------------------------
# Lambda: ocr-trigger
# Trigger: S3 ObjectCreated *.pdf → starts Textract job
# Runtime: Python 3.13 | Timeout: 63s | Memory: 128MB
# VPC: yes | SG: default (sg-006065c5ca0e2dade)
# -----------------------------------------------------------
resource "aws_lambda_function" "ocr_trigger" {
  function_name = "ocr-trigger"
  role          = aws_iam_role.ocr_pipeline_lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.13"
  timeout       = 63
  memory_size   = 128
  architectures = ["x86_64"]

  # Set filename to your deployment zip before apply
  filename = "${path.module}/ocr-trigger.zip"

  layers = [local.lambda_layer_arn]

  environment {
    variables = merge(local.common_env, {
      TEXTRACT_ROLE_ARN     = aws_iam_role.textract_sns_role.arn
      TEXTRACT_SNS_TOPIC_ARN = aws_sns_topic.textract_completion.arn
    })
  }

  vpc_config {
    subnet_ids         = local.lambda_vpc_config_subnets
    security_group_ids = [aws_security_group.ocr_lambda_default_sg.id]
  }

  tracing_config {
    mode = "PassThrough"
  }

  ephemeral_storage {
    size = 512
  }

  logging_config {
    log_format = "Text"
    log_group  = "/aws/lambda/ocr-trigger"
  }
}

resource "aws_lambda_permission" "allow_s3_invoke_trigger" {
  statement_id  = "lambda-277ac3e1-54fc-4f03-b9af-c9fdcf4f0d1c"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ocr_trigger.function_name
  principal     = "s3.amazonaws.com"

  source_account = var.account_id
  source_arn     = aws_s3_bucket.ocr_input.arn
}

# -----------------------------------------------------------
# Lambda: ocr-processor
# Trigger: SNS textract-completion → processes Textract results
# Runtime: Python 3.13 | Timeout: 63s | Memory: 128MB
# VPC: yes | SG: default (sg-006065c5ca0e2dade)
# -----------------------------------------------------------
resource "aws_lambda_function" "ocr_processor" {
  function_name = "ocr-processor"
  role          = aws_iam_role.ocr_pipeline_lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.13"
  timeout       = 63
  memory_size   = 128
  architectures = ["x86_64"]

  filename = "${path.module}/ocr-processor.zip"

  layers = [local.lambda_layer_arn]

  environment {
    variables = merge(local.common_env, {
      TEXTRACT_ROLE_ARN      = aws_iam_role.textract_sns_role.arn
      TEXTRACT_SNS_TOPIC_ARN = aws_sns_topic.textract_completion.arn
    })
  }

  vpc_config {
    subnet_ids         = local.lambda_vpc_config_subnets
    security_group_ids = [aws_security_group.ocr_lambda_default_sg.id]
  }

  tracing_config {
    mode = "PassThrough"
  }

  ephemeral_storage {
    size = 512
  }

  logging_config {
    log_format = "Text"
    log_group  = "/aws/lambda/ocr-processor"
  }
}

resource "aws_lambda_permission" "allow_sns_invoke_processor" {
  statement_id  = "lambda-4200e3db-eb24-4ee1-81f2-1233c327a9bf"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ocr_processor.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.textract_completion.arn
}

# -----------------------------------------------------------
# Lambda: db-init
# Trigger: manual invocation (schema init / migrations)
# Runtime: Python 3.13 | Timeout: 30s | Memory: 128MB
# VPC: yes | SG: ocr-rds-sg (sg-01dd61603e1931ecd)
# NOTE: DB_PASSWORD env var is set directly — consider moving
#       to Secrets Manager and using DB_SECRET_ARN instead.
# -----------------------------------------------------------
resource "aws_lambda_function" "db_init" {
  function_name = "db-init"
  role          = aws_iam_role.ocr_pipeline_lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.13"
  timeout       = 30
  memory_size   = 128
  architectures = ["x86_64"]

  filename = "${path.module}/db-init.zip"

  layers = [local.lambda_layer_arn]

  environment {
    variables = merge(local.common_env, {
      DB_USER     = "ocruser"
      # WARNING: plaintext password detected in live config.
      # Rotate this credential and switch to DB_SECRET_ARN.
      DB_PASSWORD = "REPLACE_WITH_SECRET_OR_REMOVE"
    })
  }

  vpc_config {
    subnet_ids         = local.lambda_vpc_config_subnets
    security_group_ids = [aws_security_group.ocr_rds_sg.id]
  }

  tracing_config {
    mode = "PassThrough"
  }

  ephemeral_storage {
    size = 512
  }

  logging_config {
    log_format = "Text"
    log_group  = "/aws/lambda/db-init"
  }
}
