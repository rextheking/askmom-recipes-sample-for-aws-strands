# Frontend deploy shortcuts.
#
# Syncs web/ to the deployed S3 web bucket and invalidates CloudFront.
# Looks up the bucket name and distribution id from CloudFormation outputs
# so you don't have to paste them anywhere.

STACK        := AskMomStack
REGION       ?= us-east-1

.PHONY: help serve sync invalidate deploy clean

help:
	@echo "AskMom Recipes — web targets"
	@echo ""
	@echo "  make serve        Run a local dev server on :8080"
	@echo "  make sync         Sync web/ to the deployed S3 bucket"
	@echo "  make invalidate   Invalidate the CloudFront cache"
	@echo "  make deploy       sync + invalidate in one shot"

serve:
	@echo "Open http://localhost:8080"
	@python3 -m http.server 8080

sync:
	@BUCKET=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
		--query 'Stacks[0].Outputs[?OutputKey==`WebBucketName`].OutputValue' --output text); \
	if [ -z "$$BUCKET" ] || [ "$$BUCKET" = "None" ]; then \
		echo "WebBucketName not found in stack outputs. Did you deploy the infra?"; exit 1; \
	fi; \
	echo "Syncing to s3://$$BUCKET"; \
	aws s3 sync . "s3://$$BUCKET" --delete \
		--exclude "Makefile" --exclude ".DS_Store" --exclude "README.md"

invalidate:
	@DIST_ID=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
		--query 'Stacks[0].Outputs[?OutputKey==`DistributionId`].OutputValue' --output text); \
	if [ -z "$$DIST_ID" ] || [ "$$DIST_ID" = "None" ]; then \
		echo "DistributionId not in outputs. CloudFront may be disabled (-c with_cloudfront=false)."; \
		echo "Skipping invalidation."; \
	else \
		echo "Invalidating distribution $$DIST_ID"; \
		aws cloudfront create-invalidation --distribution-id $$DIST_ID --paths "/*"; \
	fi

deploy: sync invalidate
	@DIST_URL=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
		--query 'Stacks[0].Outputs[?OutputKey==`DistributionUrl`].OutputValue' --output text); \
	echo ""; \
	if [ -n "$$DIST_URL" ] && [ "$$DIST_URL" != "None" ]; then \
		echo "🌸 Live at: $$DIST_URL"; \
	else \
		BUCKET=$$(aws cloudformation describe-stacks --stack-name $(STACK) --region $(REGION) \
			--query 'Stacks[0].Outputs[?OutputKey==`WebBucketName`].OutputValue' --output text); \
		echo "Synced to s3://$$BUCKET (no CloudFront distribution deployed)."; \
	fi
