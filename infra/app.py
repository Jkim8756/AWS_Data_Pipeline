#!/usr/bin/env python3
"""CDK app entrypoint for the OCR pipeline."""
import aws_cdk as cdk
from stacks.ocr_pipeline_stack import OcrPipelineStack

app = cdk.App()

OcrPipelineStack(
    app,
    "OcrPipelineStack",
    env=cdk.Environment(
        # account is resolved at synth time from the active AWS CLI profile
        account=app.account,
        region="us-east-1",
    ),
)

app.synth()
