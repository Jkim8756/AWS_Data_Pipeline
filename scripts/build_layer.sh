#!/usr/bin/env bash
# build_layer.sh — builds the psycopg2-binary Lambda layer using a Docker image
# that matches the Lambda Python 3.12 execution environment (Amazon Linux 2023).
#
# Usage:
#   cd /path/to/Project03_AWS\ OCR
#   bash scripts/build_layer.sh
#
# Output: layers/psycopg2/python/lib/python3.12/site-packages/

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAYER_DIR="${REPO_ROOT}/layers/psycopg2"
PYTHON_VERSION="3.12"

echo "==> Building psycopg2-binary layer for Python ${PYTHON_VERSION}"
echo "    Target: ${LAYER_DIR}/python/lib/python${PYTHON_VERSION}/site-packages/"

# Clean any previous build artefacts so the CDK asset hash stays stable
rm -rf "${LAYER_DIR}/python"
mkdir -p "${LAYER_DIR}/python/lib/python${PYTHON_VERSION}/site-packages"

# Use the public ECR Lambda Python image — identical to the actual Lambda runtime
docker run --rm \
  -v "${LAYER_DIR}/python:/output" \
  "public.ecr.aws/lambda/python:${PYTHON_VERSION}" \
  /bin/bash -c "
    pip install psycopg2-binary \
        --target /output/lib/python${PYTHON_VERSION}/site-packages \
        --platform manylinux2014_x86_64 \
        --only-binary=:all: \
        --upgrade
  "

echo "==> Layer build complete."
echo "    Contents:"
ls "${LAYER_DIR}/python/lib/python${PYTHON_VERSION}/site-packages/" | head -20
