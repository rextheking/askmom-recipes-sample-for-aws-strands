"""The main AskMom Recipes CDK stack.

Provisions:
- S3 bucket for photo uploads (private, short lifecycle, CORS for browser PUT)
- S3 bucket for the static web frontend (served via CloudFront)
- DynamoDB table for session state (with TTL)
- Lambda running the Strands agent
- API Gateway HTTP API with three routes
- CloudFront distribution in front of the web bucket
"""

import subprocess
import sys
from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    BundlingOutput,
    CfnOutput,
    DockerImage,
    Duration,
    ILocalBundling,
    RemovalPolicy,
    Stack,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_logs as logs,
    aws_s3 as s3,
    aws_ssm as ssm,
)
import jsii
from constructs import Construct


# Path to the agent code, relative to the infra directory where cdk runs.
_AGENT_CODE_PATH = "../agent"

# Claude 3 Haiku in us-east-1.
_DEFAULT_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"


@jsii.implements(ILocalBundling)
class _LocalPipBundling:
    """Bundle the Lambda locally with pip instead of Docker.

    Keeps deploys fast and removes the Docker prerequisite for readers.
    """

    def try_bundle(self, output_dir: str, options) -> bool:
        src = Path(_AGENT_CODE_PATH).resolve()
        pip_cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--quiet",
            "--no-cache-dir",
            "-r",
            str(src / "requirements.txt"),
            "-t",
            output_dir,
            "--platform",
            "manylinux2014_aarch64",
            "--implementation",
            "cp",
            "--python-version",
            "3.12",
            "--only-binary=:all:",
            "--upgrade",
        ]
        try:
            subprocess.check_call(pip_cmd)
            subprocess.check_call(["cp", "-r", str(src / "askmom"), output_dir])
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Local bundling failed: {e}")
            return False
        return True


class AskMomStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Context flag to skip CloudFront for fast iteration. Default is to
        # deploy everything. Override with: cdk deploy -c with_cloudfront=false
        raw = self.node.try_get_context("with_cloudfront")
        with_cloudfront = str(raw).lower() != "false" if raw is not None else True

        # --- Storage ---
        uploads_bucket = s3.Bucket(
            self,
            "UploadsBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    expiration=Duration.days(7),
                    abort_incomplete_multipart_upload_after=Duration.days(1),
                )
            ],
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.PUT],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    exposed_headers=["ETag"],
                    max_age=3000,
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        web_bucket = s3.Bucket(
            self,
            "WebBucket",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        sessions_table = dynamodb.Table(
            self,
            "SessionsTable",
            partition_key=dynamodb.Attribute(
                name="session_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # --- Lambda ---
        usda_key_param = ssm.StringParameter.from_secure_string_parameter_attributes(
            self,
            "UsdaApiKeyParam",
            parameter_name="/askmom/usda-api-key",
        )

        agent_lambda = _lambda.Function(
            self,
            "AgentLambda",
            runtime=_lambda.Runtime.PYTHON_3_12,
            architecture=_lambda.Architecture.ARM_64,
            handler="askmom.handler.lambda_handler",
            code=_lambda.Code.from_asset(
                _AGENT_CODE_PATH,
                bundling=BundlingOptions(
                    image=DockerImage.from_registry(
                        "public.ecr.aws/sam/build-python3.12"
                    ),
                    local=_LocalPipBundling(),
                    command=[
                        "bash",
                        "-c",
                        "pip install --no-cache-dir -r requirements.txt -t /asset-output "
                        "&& cp -r askmom /asset-output/",
                    ],
                    platform="linux/arm64",
                    output_type=BundlingOutput.AUTO_DISCOVER,
                ),
            ),
            memory_size=1024,
            timeout=Duration.seconds(120),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "SESSIONS_TABLE_NAME": sessions_table.table_name,
                "UPLOADS_BUCKET_NAME": uploads_bucket.bucket_name,
                "BEDROCK_MODEL_ID": _DEFAULT_MODEL_ID,
                "USDA_API_KEY_PARAM": usda_key_param.parameter_name,
            },
        )

        # Permissions: Bedrock, DynamoDB, S3 (read + put on uploads).
        agent_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/{_DEFAULT_MODEL_ID}",
                ],
            )
        )
        sessions_table.grant_read_write_data(agent_lambda)
        uploads_bucket.grant_read(agent_lambda)
        uploads_bucket.grant_put(agent_lambda)
        usda_key_param.grant_read(agent_lambda)

        # --- HTTP API ---
        http_api = apigwv2.HttpApi(
            self,
            "HttpApi",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_headers=["Content-Type"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_origins=["*"],
                max_age=Duration.days(1),
            ),
        )

        lambda_integration = apigwv2_integrations.HttpLambdaIntegration(
            "LambdaIntegration", agent_lambda
        )

        for route_path in ["/upload-url", "/ingredients", "/refine"]:
            http_api.add_routes(
                path=route_path,
                methods=[apigwv2.HttpMethod.POST],
                integration=lambda_integration,
            )

        # --- CloudFront + web bucket (optional) ---
        distribution = None
        if with_cloudfront:
            distribution = cloudfront.Distribution(
                self,
                "WebDistribution",
                default_behavior=cloudfront.BehaviorOptions(
                    origin=cloudfront_origins.S3BucketOrigin.with_origin_access_control(
                        web_bucket
                    ),
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                    compress=True,
                ),
                default_root_object="index.html",
                error_responses=[
                    cloudfront.ErrorResponse(
                        http_status=403,
                        response_http_status=200,
                        response_page_path="/index.html",
                        ttl=Duration.seconds(10),
                    ),
                    cloudfront.ErrorResponse(
                        http_status=404,
                        response_http_status=200,
                        response_page_path="/index.html",
                        ttl=Duration.seconds(10),
                    ),
                ],
                comment="AskMom Recipes web distribution",
            )

        # --- Outputs ---
        CfnOutput(self, "ApiUrl", value=http_api.api_endpoint)
        if distribution is not None:
            CfnOutput(
                self,
                "DistributionUrl",
                value=f"https://{distribution.distribution_domain_name}",
            )
            CfnOutput(self, "DistributionId", value=distribution.distribution_id)
        CfnOutput(self, "WebBucketName", value=web_bucket.bucket_name)
        CfnOutput(self, "UploadsBucketName", value=uploads_bucket.bucket_name)
        CfnOutput(self, "SessionsTableName", value=sessions_table.table_name)
