resource "aws_sqs_queue" "dlq" {
  name                      = var.sqs_dlq_name
  message_retention_seconds = 1209600 # 14 days
}

resource "aws_sqs_queue" "process" {
  name                       = var.sqs_queue_name
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400 # 1 day; raw JSON in S3 is the durable record
  receive_wait_time_seconds  = 20    # long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3
  })
}

data "aws_iam_policy_document" "sqs_allow_s3" {
  statement {
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.process.arn]

    principals {
      type        = "Service"
      identifiers = ["s3.amazonaws.com"]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = [aws_s3_bucket.upload.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "allow_s3" {
  queue_url = aws_sqs_queue.process.id
  policy    = data.aws_iam_policy_document.sqs_allow_s3.json
}
