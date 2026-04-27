#!/usr/bin/env bash
# upload_test.sh — uploads a test PDF to the OCR input bucket to trigger the pipeline.
#
# Usage:
#   bash scripts/upload_test.sh [path/to/file.pdf]
#
# If no argument is given, defaults to src/input/AIRFILTER DEC.pdf.
# Reads the bucket name from the OcrPipelineStack CloudFormation output.
#
# Prerequisites:
#   - AWS CLI configured with a profile that has s3:PutObject on the input bucket
#   - Stack must be deployed (cdk deploy run from infra/)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_NAME="OcrPipelineStack"
CF_OUTPUT_KEY="InputBucketName"
DEFAULT_PDF="${REPO_ROOT}/src/input/AIRFILTER DEC.pdf"

# ── Resolve the PDF to upload ─────────────────────────────────────────────────
PDF_PATH="${1:-${DEFAULT_PDF}}"

if [[ ! -f "${PDF_PATH}" ]]; then
  echo "ERROR: PDF not found at '${PDF_PATH}'" >&2
  echo "Usage: $0 [path/to/file.pdf]" >&2
  exit 1
fi

# ── Fetch the bucket name from CloudFormation ─────────────────────────────────
echo "==> Looking up CloudFormation output '${CF_OUTPUT_KEY}' from stack '${STACK_NAME}'..."
BUCKET_NAME=$(
  aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --query "Stacks[0].Outputs[?OutputKey=='${CF_OUTPUT_KEY}'].OutputValue" \
    --output text
)

if [[ -z "${BUCKET_NAME}" ]]; then
  echo "ERROR: Could not retrieve bucket name from CloudFormation." >&2
  echo "       Make sure the stack is deployed and your AWS credentials are active." >&2
  exit 1
fi

echo "    Bucket: ${BUCKET_NAME}"

# ── Upload ─────────────────────────────────────────────────────────────────────
FILENAME="$(basename "${PDF_PATH}")"
S3_KEY="uploads/${FILENAME}"

echo "==> Uploading '${FILENAME}' to s3://${BUCKET_NAME}/${S3_KEY} ..."
aws s3 cp "${PDF_PATH}" "s3://${BUCKET_NAME}/${S3_KEY}"

echo "==> Upload complete. The ocr-trigger Lambda should fire within seconds."
echo "    Monitor CloudWatch Logs for /aws/lambda/ocr-trigger to track progress."
