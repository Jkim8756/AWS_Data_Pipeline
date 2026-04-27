# -----------------------------------------------------------
# S3 Bucket: ocr-input (PDF upload landing zone)
# Triggers: ocr-trigger Lambda on s3:ObjectCreated:* for *.pdf
# -----------------------------------------------------------
resource "aws_s3_bucket" "ocr_input" {
  bucket = "ocr-input-${var.account_id}-${var.aws_region}"
}

resource "aws_s3_bucket_notification" "ocr_input_trigger" {
  bucket = aws_s3_bucket.ocr_input.id

  lambda_function {
    id                  = "7c9fb1f8-e5e4-467d-bc23-3dcc9f49ed29"
    lambda_function_arn = aws_lambda_function.ocr_trigger.arn
    events              = ["s3:ObjectCreated:*"]

    filter_suffix = ".pdf"
  }

  depends_on = [aws_lambda_permission.allow_s3_invoke_trigger]
}

# -----------------------------------------------------------
# S3 Bucket: timesheets-pdf-uploads-01
# (Separate bucket — not connected to OCR pipeline triggers)
# -----------------------------------------------------------