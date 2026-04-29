# Infrastructure (AWS CDK)

CDK stack for AskMom Recipes. Provisions everything the app needs in a single
stack and region.

## What it provisions

- **S3 bucket (uploads)** — private, SSE-S3, 7-day lifecycle, CORS rule for
  browser PUT.
- **S3 bucket (web)** — private, served through CloudFront via Origin Access
  Control.
- **CloudFront distribution** — HTTPS, SPA-style 403/404 fallback to
  `index.html`, compression on.
- **DynamoDB table (sessions)** — partition key `session_id`, TTL on
  `expires_at`, on-demand billing.
- **Lambda function** — Python 3.12 on arm64, 1GB memory, 60s timeout,
  one-week log retention. Runs the Strands agent.
- **API Gateway HTTP API** — CORS preflight + three POST routes:
  `/upload-url`, `/ingredients`, `/refine`.
- **IAM** — Lambda role scoped to `bedrock:InvokeModel` on Claude 3 Haiku,
  DynamoDB r/w on the sessions table, and S3 read + put on the uploads bucket.

## Layout

```
infra/
├── app.py                  # CDK app entry point
├── stacks/
│   ├── __init__.py
│   └── askmom_stack.py     # The main stack
├── Makefile                # Shortcut commands (synth, deploy, destroy)
├── cdk.json
├── requirements.txt
└── README.md
```

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| AWS account | — | With Bedrock model access enabled for Claude 3 Haiku in `us-east-1` |
| AWS credentials | — | Configured locally (env vars, `~/.aws/credentials`, or SSO) |
| Python | 3.12 | Other 3.x versions may work; 3.12 is pinned because that's the Lambda runtime |
| Node.js | 20.x, 22.x, or 24.x | Required by the CDK CLI (jsii) |
| AWS CDK CLI | 2.140+ | `npm install -g aws-cdk` |

Docker is **not** required. Lambda bundling runs locally via `pip`.

## One-time setup

```bash
cd ask_moms_recipe/infra

python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# First time bootstrapping this account/region:
cdk bootstrap aws://<account-id>/us-east-1
```

## Deploy

With the venv activated:

```bash
cdk deploy
```

Or without activating the venv (uses the bundled helper script):

```bash
make deploy
```

First deploy takes **5-15 minutes**, almost entirely for the CloudFront
distribution to propagate globally. Subsequent deploys are usually 1-2 minutes
unless CloudFront itself changed.

After deploy, capture the outputs. You'll need them to wire up the frontend:

```
AskMomStack.ApiUrl              = https://abc123.execute-api.us-east-1.amazonaws.com
AskMomStack.DistributionUrl     = https://d111abc.cloudfront.net
AskMomStack.DistributionId      = E1AB2CD34EF5GH
AskMomStack.WebBucketName       = askmomstack-webbucket...
AskMomStack.UploadsBucketName   = askmomstack-uploadsbucket...
AskMomStack.SessionsTableName   = AskMomStack-SessionsTable...
```

## Development tip: skip CloudFront during iteration

CloudFront is slow to update. For tight iteration on the frontend, use the
S3 website URL pattern directly against the **web** bucket, or point your
local `web/` server at the deployed API. Only verify on the `DistributionUrl`
before you ship.

After frontend changes, invalidate CloudFront so visitors see them:

```bash
aws cloudfront create-invalidation \
  --distribution-id "$(aws cloudformation describe-stacks \
      --stack-name AskMomStack \
      --query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' \
      --output text)" \
  --paths "/*"
```

Or simply:

```bash
make invalidate
```

## Destroy

To tear everything down:

```bash
cdk destroy
# or
make destroy
```

This removes the Lambda, API, DynamoDB table, both S3 buckets (including any
objects, because `auto_delete_objects` is on), and the CloudFront distribution.

## Gotchas worth knowing

**Node version warnings.** If you're on Node 25+, jsii prints a big banner
saying it's untested. CDK still works fine. The Makefile silences this with
`JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1`.

**Bedrock access.** The Lambda IAM role is scoped specifically to the Haiku
model ARN. If you change `_DEFAULT_MODEL_ID` in `askmom_stack.py`, update the
IAM statement to match, and make sure that model is enabled in your Bedrock
model access page in `us-east-1`.

**CORS is wide open by default.** The HTTP API allows all origins so the
blog's deploy-and-go story works out of the box. For a production deploy,
tighten `allow_origins` to just your CloudFront domain.

**DynamoDB TTL is soft.** DynamoDB deletes expired items within ~48 hours of
the TTL, not instantly. Fine for session cleanup; not a substitute for real
authorization if you ever store sensitive data.

**Auto-delete on destroy.** Both S3 buckets are configured with
`auto_delete_objects=True` and `RemovalPolicy.DESTROY` so `cdk destroy` wipes
them cleanly. Remove those two flags if you want buckets to stick around after
destroy.
