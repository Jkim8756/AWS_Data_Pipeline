"""Full CDK stack for the OCR pipeline.

Resources provisioned:
  - VPC (2 AZs, 1 NAT GW)
  - Security groups for Lambda and Aurora
  - Secrets Manager secret for DB credentials
  - Aurora PostgreSQL Serverless v2 (engine 15.4)
  - S3 input bucket with PDF event notification
  - SNS topic for Textract completion callbacks
  - IAM roles for Textract, ocr-trigger Lambda, and ocr-processor Lambda
  - Lambda Layer (psycopg2-binary, Python 3.12)
  - ocr-trigger Lambda  → invoked by S3 OBJECT_CREATED events on *.pdf
  - ocr-processor Lambda → invoked by SNS Textract completion notifications
"""
from constructs import Construct

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_rds as rds
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions


class OcrPipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── 1. VPC ─────────────────────────────────────────────────────────────
        vpc = ec2.Vpc(
            self,
            "OcrVpc",
            max_azs=2,
            nat_gateways=1,  # single NAT GW keeps costs low for a pipeline workload
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
        )

        # ── 2. Security Groups ─────────────────────────────────────────────────
        lambda_sg = ec2.SecurityGroup(
            self,
            "LambdaSg",
            vpc=vpc,
            description="Security group for OCR Lambda functions",
            allow_all_outbound=True,  # Lambdas need HTTPS to AWS APIs + Textract
        )

        rds_sg = ec2.SecurityGroup(
            self,
            "RdsSg",
            vpc=vpc,
            description="Security group for Aurora PostgreSQL cluster",
            allow_all_outbound=False,
        )
        # Only allow inbound Postgres traffic from the Lambda security group
        rds_sg.add_ingress_rule(
            peer=lambda_sg,
            connection=ec2.Port.tcp(5432),
            description="Allow Postgres from Lambda SG",
        )

        # ── 3. Secrets Manager – DB credentials ────────────────────────────────
        db_secret = secretsmanager.Secret(
            self,
            "DbCredentials",
            secret_name="ocr-pipeline/db-credentials",
            description="Master credentials for the OCR pipeline Aurora cluster",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"username": "ocrpipelineadmin"}',
                generate_string_key="password",
                exclude_punctuation=True,  # keeps connection strings unambiguous
                password_length=32,
            ),
        )

        # ── 4. Aurora PostgreSQL Serverless v2 ─────────────────────────────────
        db_cluster = rds.DatabaseCluster(
            self,
            "AuroraCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            ),
            credentials=rds.Credentials.from_secret(db_secret),
            writer=rds.ClusterInstance.serverless_v2("writer"),
            serverless_v2_min_capacity=0.5,
            serverless_v2_max_capacity=4.0,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[rds_sg],
            default_database_name="ocrdb",
            removal_policy=RemovalPolicy.DESTROY,  # safe to destroy in dev; change for prod
        )

        # ── 5. S3 Input Bucket ─────────────────────────────────────────────────
        input_bucket = s3.Bucket(
            self,
            "OcrInputBucket",
            # Globally unique name derived from account + region
            bucket_name=f"ocr-input-{self.account}-{self.region}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,  # empties the bucket on stack teardown
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        # ── 6. SNS Topic – Textract completion ────────────────────────────────
        textract_topic = sns.Topic(
            self,
            "TextractCompletionTopic",
            topic_name="textract-completion",
            display_name="Textract Async Job Completion",
        )

        # ── 7. IAM Role for Textract (service-to-SNS trust) ────────────────────
        textract_role = iam.Role(
            self,
            "TextractRole",
            assumed_by=iam.ServicePrincipal("textract.amazonaws.com"),
            description="Allows Textract to publish job completion events to SNS",
        )
        textract_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sns:Publish"],
                resources=[textract_topic.topic_arn],
            )
        )

        # ── 8. Lambda Layer – psycopg2-binary ─────────────────────────────────
        # Build the layer first with scripts/build_layer.sh, which populates
        # layers/psycopg2/python/lib/python3.12/site-packages/
        psycopg2_layer = lambda_.LayerVersion(
            self,
            "Psycopg2Layer",
            layer_version_name="psycopg2-binary",
            code=lambda_.Code.from_asset("../layers/psycopg2"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            compatible_architectures=[lambda_.Architecture.X86_64],
            description="psycopg2-binary compiled for Amazon Linux 2023 / Python 3.12",
        )

        # ── 9. Common environment variables shared by both Lambdas ─────────────
        common_env = {
            "DB_SECRET_ARN": db_secret.secret_arn,
            "DB_HOST": db_cluster.cluster_endpoint.hostname,
            "DB_PORT": "5432",
            "DB_NAME": "ocrdb",
            "TEXTRACT_SNS_TOPIC_ARN": textract_topic.topic_arn,
            "TEXTRACT_ROLE_ARN": textract_role.role_arn,
        }

        # ── 10. ocr-trigger Lambda ─────────────────────────────────────────────
        trigger_role = iam.Role(
            self,
            "OcrTriggerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )
        # Read objects from input bucket
        input_bucket.grant_read(trigger_role)
        # Start Textract async document analysis jobs
        trigger_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "textract:StartDocumentTextDetection",
                    "textract:StartDocumentAnalysis",
                ],
                resources=["*"],  # Textract does not support resource-level restrictions
            )
        )
        # Allow passing the Textract SNS role so Textract can publish completions
        trigger_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[textract_role.role_arn],
            )
        )
        db_secret.grant_read(trigger_role)

        ocr_trigger_fn = lambda_.Function(
            self,
            "OcrTriggerFn",
            function_name="ocr-trigger",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../lambdas/ocr_trigger"),
            layers=[psycopg2_layer],
            role=trigger_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.minutes(5),
            memory_size=512,
            environment=common_env,
        )

        # Wire S3 → Lambda for every .pdf object created in the input bucket
        input_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(ocr_trigger_fn),
            s3.NotificationKeyFilter(suffix=".pdf"),
        )

        # ── 11. ocr-processor Lambda ───────────────────────────────────────────
        processor_role = iam.Role(
            self,
            "OcrProcessorRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaVPCAccessExecutionRole"
                )
            ],
        )
        # Retrieve Textract job results
        processor_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "textract:GetDocumentTextDetection",
                    "textract:GetDocumentAnalysis",
                ],
                resources=["*"],
            )
        )
        # Write extracted text back to the input bucket (prefix: extracted/)
        input_bucket.grant_write(processor_role)
        db_secret.grant_read(processor_role)

        ocr_processor_fn = lambda_.Function(
            self,
            "OcrProcessorFn",
            function_name="ocr-processor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../lambdas/ocr_processor"),
            layers=[psycopg2_layer],
            role=processor_role,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            security_groups=[lambda_sg],
            timeout=Duration.minutes(10),
            memory_size=1024,
            environment=common_env,
        )

        # Subscribe processor to Textract completion notifications
        textract_topic.add_subscription(
            subscriptions.LambdaSubscription(ocr_processor_fn)
        )

        # ── 12. Stack output ───────────────────────────────────────────────────
        CfnOutput(
            self,
            "InputBucketName",
            value=input_bucket.bucket_name,
            description="S3 bucket name — upload PDFs here to trigger OCR",
            export_name="OcrPipelineInputBucketName",
        )
        CfnOutput(
            self,
            "TextractTopicArn",
            value=textract_topic.topic_arn,
            description="SNS topic ARN for Textract async job completion",
        )
        CfnOutput(
            self,
            "DbSecretArn",
            value=db_secret.secret_arn,
            description="Secrets Manager ARN for Aurora DB credentials",
        )
