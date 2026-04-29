resource "aws_s3_bucket" "upload" {
  bucket = var.upload_bucket_name
}

resource "aws_s3_bucket_public_access_block" "upload" {
  bucket                  = aws_s3_bucket.upload.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "upload" {
  bucket = aws_s3_bucket.upload.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_notification" "upload_to_sqs" {
  bucket = aws_s3_bucket.upload.id

  queue {
    queue_arn     = aws_sqs_queue.process.arn
    events        = ["s3:ObjectCreated:*"]
    filter_suffix = ".pdf"
  }

  depends_on = [aws_sqs_queue_policy.allow_s3]
}

resource "aws_s3_bucket" "raw_json" {
  bucket = var.raw_json_bucket_name
}

resource "aws_s3_bucket_public_access_block" "raw_json" {
  bucket                  = aws_s3_bucket.raw_json.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "raw_json" {
  bucket = aws_s3_bucket.raw_json.id
  versioning_configuration {
    status = "Enabled"
  }
}
