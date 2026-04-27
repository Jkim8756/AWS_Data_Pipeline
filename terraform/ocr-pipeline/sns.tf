# -----------------------------------------------------------
# SNS Topic: textract-completion
# Published to by: Textract (via textract-sns-role)
# Subscribed by: ocr-processor Lambda
# -----------------------------------------------------------
resource "aws_sns_topic" "textract_completion" {
  name         = "textract-completion"
  display_name = "textract Job Completion"
}

resource "aws_sns_topic_policy" "textract_completion_policy" {
  arn = aws_sns_topic.textract_completion.arn

  policy = jsonencode({
    Version = "2008-10-17"
    Id      = "__default_policy_ID"
    Statement = [{
      Sid    = "__default_statement_ID"
      Effect = "Allow"
      Principal = { AWS = "*" }
      Action = [
        "SNS:Publish",
        "SNS:RemovePermission",
        "SNS:SetTopicAttributes",
        "SNS:DeleteTopic",
        "SNS:ListSubscriptionsByTopic",
        "SNS:GetTopicAttributes",
        "SNS:AddPermission",
        "SNS:Subscribe"
      ]
      Resource = aws_sns_topic.textract_completion.arn
      Condition = {
        StringEquals = {
          "AWS:SourceAccount" = var.account_id
        }
      }
    }]
  })
}

resource "aws_sns_topic_subscription" "textract_to_ocr_processor" {
  topic_arn = aws_sns_topic.textract_completion.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.ocr_processor.arn
}
