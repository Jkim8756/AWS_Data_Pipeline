# -----------------------------------------------------------
# IAM Role: ocr-pipeline-lambda-role
# Used by: ocr-trigger, ocr-processor, db-init
# -----------------------------------------------------------
resource "aws_iam_role" "ocr_pipeline_lambda_role" {
  name        = "ocr-pipeline-lambda-role"
  description = "Allows Lambda functions to call AWS services on your behalf."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "ocr_pipeline_lambda_policy" {
  name = "ocr-pipeline-lambda-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "TextractAccess"
        Effect = "Allow"
        Action = [
          "textract:StartDocumentTextDetection",
          "textract:GetDocumentTextDetection",
          "textract:StartDocumentAnalysis",
          "textract:GetDocumentAnalysis",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3Access"
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::ocr-input-*",
          "arn:aws:s3:::ocr-input-*/*"
        ]
      },
      {
        Sid    = "SecretsAccess"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:us-east-1:*:secret:ocr-pipeline/*"
      },
      {
        Sid      = "IAMPassRole"
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = "arn:aws:iam::*:role/textract-sns-role"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_custom_policy" {
  role       = aws_iam_role.ocr_pipeline_lambda_role.name
  policy_arn = aws_iam_policy.ocr_pipeline_lambda_policy.arn
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_execution" {
  role       = aws_iam_role.ocr_pipeline_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# -----------------------------------------------------------
# IAM Role: textract-sns-role
# Used by: Textract service to publish to SNS
# -----------------------------------------------------------
resource "aws_iam_role" "textract_sns_role" {
  name        = "textract-sns-role"
  description = "Allows AWS Textract to call other AWS services on your behalf."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = ""
      Effect    = "Allow"
      Principal = { Service = "textract.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "textract_service_role" {
  role       = aws_iam_role.textract_sns_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonTextractServiceRole"
}

# -----------------------------------------------------------
# IAM Role: rds-monitoring-role
# Used by: RDS enhanced monitoring
# -----------------------------------------------------------
resource "aws_iam_role" "rds_monitoring_role" {
  name = "rds-monitoring-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "monitoring.rds.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "rds_enhanced_monitoring" {
  role       = aws_iam_role.rds_monitoring_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
