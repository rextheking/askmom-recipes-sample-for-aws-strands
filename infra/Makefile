# AskMom Recipes — infra shortcuts.
#
# Uses the venv's Python directly so you don't have to `source .venv/bin/activate`.
# Sets JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION so Node 25+ users don't see
# the untested-version banner.

STACK        := AskMomStack
APP          := .venv/bin/python3 app.py
CDK          := JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 cdk
REGION       ?= us-east-1

.PHONY: help install synth deploy destroy bootstrap diff outputs invalidate clean

help:
	@echo "AskMom Recipes — infra targets"
	@echo ""
	@echo "  make install      Create venv and install CDK deps"
	@echo "  make bootstrap    Bootstrap the current account/region for CDK (first time only)"
	@echo "  make synth        Synthesize the CloudFormation template"
	@echo "  make diff         Show pending changes vs. deployed stack"
	@echo "  make deploy       Deploy the stack"
	@echo "  make outputs      Print stack outputs (API URL, CloudFront URL, etc.)"
	@echo "  make invalidate   Invalidate the CloudFront distribution cache"
	@echo "  make destroy      Tear everything down"
	@echo "  make clean        Remove cdk.out and caches"

install:
	python3.12 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt

bootstrap:
	$(CDK) bootstrap --app "$(APP)"

synth:
	$(CDK) synth --app "$(APP)" --quiet

diff:
	$(CDK) diff --app "$(APP)"

deploy:
	$(CDK) deploy --app "$(APP)" --require-approval never

destroy:
	$(CDK) destroy --app "$(APP)" --force

outputs:
	@aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
		--query 'Stacks[0].Outputs' --output table

invalidate:
	@DIST_ID=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
		--query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' --output text); \
	aws cloudfront create-invalidation --distribution-id $$DIST_ID --paths "/*"

clean:
	rm -rf cdk.out .pytest_cache
