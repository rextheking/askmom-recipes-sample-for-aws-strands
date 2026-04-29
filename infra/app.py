#!/usr/bin/env python3
"""CDK app entry point for AskMom Recipes."""

import os

import aws_cdk as cdk

from stacks.askmom_stack import AskMomStack


app = cdk.App()

AskMomStack(
    app,
    "AskMomStack",
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION", "us-east-1"),
    ),
    description="AskMom Recipes — AI-powered recipe helper for Mother's Day.",
)

app.synth()
