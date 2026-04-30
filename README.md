# 💖 AskMom Recipes

> A Mother's Day project: tell it what's in your kitchen and get 3 healthy recipes, grounded in real USDA nutrition data and a bit of food history.

Snap a photo of your groceries (or type what you have), pick a dietary preference and AskMom suggests 3 recipes with honest nutrition notes and a one-line origin story for each dish.

Built on AWS with Strands, Amazon Bedrock (Claude 3 Haiku), Lambda, API Gateway, S3, DynamoDB, CloudFront and the USDA FoodData Central API. Infrastructure is CDK (Python). Frontend is plain HTML / CSS / JS.

---

## Table of contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [How a request flows](#how-a-request-flows)
- [Project layout](#project-layout)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick start: deploy your own](#quick-start-deploy-your-own)
- [Updating after deploy](#updating-after-deploy)
- [Security notes](#security-notes)
- [Costs](#costs)
- [Tear down](#tear-down)
- [Troubleshooting](#troubleshooting)

---

## What it does

- Accepts a photo of groceries, typed ingredient text, or both.
- Applies a dietary preference... no restriction, vegetarian, low sodium, diabetic-friendly, or gluten-free.
- Returns 3 recipe cards, each with:
  - Name, a one-line hook, estimated time
  - Ingredients you already have vs. what you'd need to grab
  - Simple step-by-step instructions
  - A grounded **"why it's good for you"** note pulled from USDA FoodData Central
  - A one-line **origin note** from a small curated dataset (no hallucinated country-of-origin facts)
- Supports follow-up instructions... "make it healthier," "something quicker," "fewer ingredients."

The separation between **LLM planning** (extract ingredients + suggest recipes) and **deterministic enrichment** (nutrition + origin + formatting) is a core design choice. It keeps the system fast (2 Bedrock round-trips instead of 10+), cheap and prevents the model from inventing numbers or history.

---

## Architecture

```
┌─────────────────┐
│  Browser        │  https://<distribution>.cloudfront.net
│  HTML / CSS / JS│
└────────┬────────┘
         │  (1) GET site
         │  (2) POST /upload-url (if photo)
         │  (3) PUT photo directly to S3 via pre-signed URL
         │  (4) POST /ingredients  or  POST /refine
         ▼
┌─────────────────────────────────────────────────────────┐
│              Amazon CloudFront (HTTPS)                  │
└────────┬────────────────────────┬───────────────────────┘
         │ static site            │ API calls go directly
         ▼                        ▼
┌─────────────────┐      ┌─────────────────────┐
│  S3 Web Bucket  │      │ API Gateway         │
│  (private, OAC) │      │ (HTTP API, CORS)    │
└─────────────────┘      └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │  Lambda (Python)    │
                         │  askmom.handler     │
                         └─────────┬───────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
┌──────────────┐         ┌─────────────────────┐       ┌───────────────┐
│   Bedrock    │         │  S3 Uploads Bucket  │       │   DynamoDB    │
│   Claude 3   │         │  (pre-signed PUT,   │       │   Sessions    │
│   Haiku      │         │   7-day lifecycle)  │       │   (TTL)       │
└──────────────┘         └─────────────────────┘       └───────────────┘
       │                           ▲
       │                           │
       │                 ┌─────────┴─────────┐
       │                 │ Strands Agent     │
       │                 │ tools:            │
       │                 │ - extract (image) │
       │                 │ - extract (text)  │
       │                 │ - suggest recipes │
       │                 └───────────────────┘
       │
       │ deterministic enrichment (no LLM):
       ▼
┌──────────────────────────────────────────────┐
│ lookup_food_origin (curated dict)            │
│ lookup_food_facts (USDA FoodData Central)    │
│ format_recipe_card (pure Python)             │
└──────────────────────────────────────────────┘
```

---

## How a request flows

### Typed ingredients, no photo

1. Browser sends `POST /ingredients` with `{text, preferences}`.
2. Lambda builds a Strands agent with 3 tools: text extractor, image extractor, recipe suggester.
3. The agent calls `extract_ingredients_from_text` to normalize the user's input.
4. The agent calls `suggest_recipes` once with the clean ingredient list and preference. Returns 3 raw recipes.
5. Lambda enriches each recipe **in pure Python**:
   - `lookup_food_origin(main_ingredient)` → curated dict
   - `lookup_food_facts(main_ingredient)` → USDA API (key fetched from SSM once per cold start)
   - `format_recipe_card(recipe, facts, origin)` → final card
6. Result saved to DynamoDB with a 24-hour TTL.
7. Browser renders 3 pink recipe cards.

Typical latency: **~15-20 seconds**.

### With a photo

1. Browser calls `POST /upload-url` and gets back a pre-signed S3 PUT URL and object key.
2. Browser uploads the photo directly to S3 (Lambda never sees the bytes).
3. Browser calls `POST /ingredients` with `{photo_key, text?, preferences}`.
4. Agent calls `extract_ingredients_from_image(photo_key)`, which fetches the photo from S3 and sends it to Bedrock Claude Haiku with a vision prompt.
5. If text is also provided, agent calls `extract_ingredients_from_text` and combines results.
6. Same `suggest_recipes` → enrich → respond flow as above.

### Refine

1. Browser sends `POST /refine` with `{session_id, instruction}`.
2. Lambda loads the prior session from DynamoDB.
3. Agent re-runs `suggest_recipes` with the original ingredients + the refinement instruction in the prompt.
4. Fresh 3 recipes come back.

---

## Project layout

```
ask_moms_recipe/
├── agent/                # Python Strands agent + tools (Lambda code)
│   ├── askmom/
│   │   ├── agent.py      # build_agent(), ask(), refine()
│   │   ├── handler.py    # Lambda entry point (3 routes)
│   │   ├── prompts.py    # System + refine prompts
│   │   ├── models.py     # Dataclasses for recipes, nutrition, origin
│   │   ├── session_store.py  # DynamoDB in prod, in-memory locally
│   │   └── tools/
│   │       ├── extract_ingredients.py   # text + vision
│   │       ├── suggest_recipes.py       # Bedrock call, 3 recipes
│   │       ├── lookup_food_facts.py     # USDA API
│   │       ├── lookup_food_origin.py    # curated dict
│   │       └── format_recipe_card.py    # pure Python assembly
│   ├── tests/            # pytest suite (offline)
│   ├── local_run.py      # run the agent locally, no AWS deploy
│   └── requirements.txt
├── infra/                # AWS CDK (Python)
│   ├── app.py
│   ├── stacks/
│   │   └── askmom_stack.py   # single stack, all resources
│   ├── Makefile          # install / bootstrap / deploy / destroy
│   ├── cdk.json
│   └── requirements.txt
├── web/                  # Frontend (plain HTML / CSS / JS)
│   ├── index.html
│   ├── styles.css        # pink Mother's Day theme
│   ├── app.js            # upload, API calls, rendering
│   ├── config.js         # API_BASE_URL (populated after deploy)
│   └── Makefile          # serve / sync / invalidate / deploy
├── .env.example
├── .gitignore
└── README.md             # you are here
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Agent framework | [Strands Agents](https://strandsagents.com) 1.37 (Python) |
| LLM | Claude 3 Haiku on Amazon Bedrock |
| Compute | AWS Lambda (Python 3.12, arm64, 1GB) |
| API | Amazon API Gateway (HTTP API v2) |
| State | Amazon DynamoDB (on-demand, TTL) |
| Uploads | Amazon S3 (pre-signed PUT, 7-day lifecycle) |
| Static hosting | Amazon S3 + CloudFront (Origin Access Control) |
| Secrets | AWS Systems Manager Parameter Store (SecureString) |
| Nutrition data | [USDA FoodData Central](https://fdc.nal.usda.gov/api-guide.html) |
| IaC | AWS CDK (Python) |
| Region | `us-east-1` |

---

## Prerequisites

Before you can deploy your own copy:

### AWS

- An **AWS account** with admin or sufficient deploy permissions.
- **Amazon Bedrock model access enabled** for `anthropic.claude-3-haiku-20240307-v1:0` in `us-east-1`. Request access at the [Bedrock model access page](https://console.aws.amazon.com/bedrock/home#/modelaccess).
- **AWS credentials configured locally** (env vars, `~/.aws/credentials`, SSO, etc.). Confirm with `aws sts get-caller-identity`.

### USDA FoodData Central API key

Nutrition notes ("why it's good for you") are grounded in real USDA data, not invented by the LLM. To turn that on:

1. Go to the [USDA FoodData Central API key signup](https://fdc.nal.usda.gov/api-key-signup.html).
2. Fill the tiny form. You get the key instantly via email. **The key is free and unlimited.**
3. Store it in AWS SSM Parameter Store as a SecureString named `/askmom/usda-api-key`:
   ```bash
   aws ssm put-parameter \
     --name /askmom/usda-api-key \
     --value 'YOUR_USDA_KEY' \
     --type SecureString \
     --region us-east-1
   ```

The Lambda reads this parameter once per cold start and caches it in memory. If you skip this step, everything still works — the app just omits the nutrition blurbs.

### Local tools

| Tool | Version | Install |
|---|---|---|
| Python | 3.12 | `brew install python@3.12` or your package manager |
| Node.js | 20, 22, or 24 | via nvm, fnm, etc. (needed by the CDK CLI) |
| AWS CDK CLI | 2.140+ | `npm install -g aws-cdk` |
| AWS CLI | v2 | `brew install awscli` or [AWS docs](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Make | any | preinstalled on macOS/Linux |

**Docker is not required** — Lambda bundling runs locally via `pip`.

---

## Quick start: deploy your own

Clone this repo, then from the `ask_moms_recipe/` directory:

### 1. Install infra dependencies

```bash
cd infra
make install
```

This creates a `.venv` and installs `aws-cdk-lib` and `constructs`.

### 2. Bootstrap CDK (first time per account/region)

```bash
make bootstrap
```

Takes ~60 seconds. Only needed once.

### 3. Store the USDA API key

Follow the [USDA section](#usda-fooddata-central-api-key) above to put your key in SSM.

### 4. Deploy

```bash
make deploy
```

Takes **~5-7 minutes** on a fresh account — most of that is CloudFront propagating the distribution globally. Subsequent deploys without CloudFront changes are ~1-2 minutes.

When it finishes you'll see outputs like:

```
AskMomStack.ApiUrl          = https://xxxxxxxx.execute-api.us-east-1.amazonaws.com
AskMomStack.DistributionUrl = https://xxxxxxxx.cloudfront.net
AskMomStack.DistributionId  = EXXXXXXXXXXXX
AskMomStack.WebBucketName   = askmomstack-webbucket...
AskMomStack.UploadsBucketName = askmomstack-uploadsbucket...
AskMomStack.SessionsTableName = AskMomStack-SessionsTable...
```

### 5. Wire the frontend to your API

Edit `web/config.js` and replace `API_BASE_URL` with **your own** `ApiUrl` from step 4:

```js
window.ASKMOM_CONFIG = {
  API_BASE_URL: "https://xxxxxxxx.execute-api.us-east-1.amazonaws.com",
};
```

### 6. Deploy the frontend

```bash
cd ../web
make deploy
```

This syncs `web/` to your S3 bucket and invalidates CloudFront. At the end you'll see:

```
🌸 Live at: https://xxxxxxxx.cloudfront.net
```

Open that URL. Give it a spin.

### Fast-iteration alternative: skip CloudFront

The first CloudFront deploy is the slow one. If you're iterating and want a ~2-minute deploy instead, skip CloudFront with a context flag:

```bash
cd infra
make destroy           # only if you already deployed
cdk deploy --app ".venv/bin/python3 app.py" \
  -c with_cloudfront=false --require-approval never
```

Then test the frontend locally with `cd web && make serve` pointing at your deployed API. Turn CloudFront back on for the real launch.

---

## Updating after deploy

**Backend change** (agent, tools, prompts, Lambda behavior):

```bash
cd infra && make deploy
```

**Frontend change** (HTML, CSS, JS, copy):

```bash
cd web && make deploy
```

Either Makefile does the right thing: infra rebundles and updates Lambda, web syncs to S3 and invalidates CloudFront.

---

## Security notes

- **Both S3 buckets are private.** All four `PublicAccessBlock` flags are set to `true` on each bucket. Web traffic reaches the web bucket only through CloudFront via Origin Access Control (OAC). Uploads only via short-lived pre-signed URLs issued by Lambda.
- **HTTPS-only.** Both buckets deny non-HTTPS requests at the policy level. CloudFront redirects HTTP to HTTPS.
- **No secrets in code.** The USDA key lives in SSM Parameter Store as a SecureString and is fetched at cold start. No keys in `.env`, no keys in the CDK code, no keys in the Lambda code.
- **IAM is scoped.** The Lambda role can invoke only the one Haiku model ARN, read only the one SSM parameter, read/write the one DynamoDB table, and read/put on the uploads bucket. Nothing else.
- **CORS is open by default.** The HTTP API allows `*` so readers can clone this repo and have it work immediately. For a production deploy, tighten `allow_origins` in `infra/stacks/askmom_stack.py` to just your CloudFront domain.
- **Session TTL is 24 hours.** DynamoDB deletes expired items within ~48h of the TTL time. No sensitive data is stored in sessions.

---

## Costs

Ballpark for personal / demo use in `us-east-1`:

- **Bedrock Claude Haiku**: ~$0.0001 per recipe request (2 calls, a few thousand tokens). 1,000 requests ≈ $0.10.
- **Lambda**: first 1M requests free, then $0.20 per million. Effectively free for personal use.
- **API Gateway HTTP API**: $1 per million requests.
- **DynamoDB**: on-demand, $1.25 per million writes. Personal use ≈ free tier.
- **S3**: a few cents a month for static site + uploads.
- **CloudFront**: ~$0.085 per GB transferred, first 1 TB/month. Free tier covers personal use.
- **USDA API**: free.

Total for a personal deployment answering a few dozen requests a month: **under $1**.

---

## Tear down

```bash
cd infra
make destroy
```

This removes the Lambda, API Gateway, DynamoDB table, both S3 buckets (including all objects, because `auto_delete_objects=True`), the CloudFront distribution, and all IAM roles and policies. The CDK bootstrap stack (`CDKToolkit`) stays — that's shared with any other CDK apps in the account.

You may also want to delete the SSM parameter manually:

```bash
aws ssm delete-parameter --name /askmom/usda-api-key --region us-east-1
```

---

## Troubleshooting

**`Unable to resolve AWS account` during deploy.** Your shell session lost AWS creds (common with short-lived SSO tokens). Refresh and retry. `aws sts get-caller-identity` should return your ARN cleanly.

**`Failed to publish asset: getaddrinfo ENOTFOUND`.** Transient DNS flake while uploading Lambda assets to the CDK bootstrap bucket. Retry the deploy. Adding `--asset-parallelism=false` helps on flaky networks.

**API returns HTTP 503 "Service Unavailable" after ~29 seconds.** API Gateway HTTP API has a hard 29-second integration timeout. If you changed the agent to do heavy additional work, consider moving enrichment back into pure Python (see the existing design) or switching to REST API (which supports 30-minute timeouts).

**Frontend shows old content after deploy.** CloudFront caches aggressively. `make deploy` runs an invalidation, but propagation takes ~30-60 seconds globally. Hard refresh (Cmd+Shift+R / Ctrl+F5) often helps. To manually re-invalidate: `cd infra && make invalidate`.

**`AccessDeniedException` on `bedrock:InvokeModelWithResponseStream`.** You deployed an older version of the stack before this permission was added. Redeploy: `cd infra && make deploy`.

**`Unknown output type: IQoJ...` from any AWS CLI command.** Your `~/.aws/config` has been corrupted — likely by pasting a session token at a shell prompt that got interpreted as a config line. Open `~/.aws/config` and replace the `output = IQoJ...` line with `output = json`.

**Node version warning from jsii.** CDK bundles a JS runtime via jsii and warns on untested Node versions (25+). Harmless. The Makefile silences it with `JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1`.

**Nutrition notes are empty.** You haven't set the USDA key, or it's set under the wrong parameter name. Confirm:
```bash
aws ssm get-parameter --name /askmom/usda-api-key --with-decryption --region us-east-1 --query 'Parameter.Value' --output text
```
Should print your key. If not, re-run the `aws ssm put-parameter` command from the [Prerequisites](#usda-fooddata-central-api-key) section.

---

## Acknowledgements

- [Strands Agents](https://strandsagents.com) for the agent framework.
- Amazon Bedrock + Anthropic Claude 3 Haiku for the model.
- [USDA FoodData Central](https://fdc.nal.usda.gov/api-guide.html) for the free, excellent nutrition API.

## License

MIT — see [LICENSE](./LICENSE).

Built with 💖 for Mother's Day.
