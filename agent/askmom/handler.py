"""AWS Lambda handler for AskMom Recipes.

One Lambda, three routes behind API Gateway HTTP API:

    POST /upload-url   -> issue a pre-signed S3 PUT URL
    POST /ingredients  -> run the agent on typed text and/or a photo
    POST /refine       -> apply a follow-up instruction to an existing session

The session store reads/writes DynamoDB when SESSIONS_TABLE_NAME is set.
"""

import json
import logging
import os
import uuid
from typing import Any

import boto3

from .agent import ask, refine


logger = logging.getLogger()
logger.setLevel(logging.INFO)


# CORS: the CloudFront origin is set at deploy time via env var. In local dev
# we allow "*" so the browser can talk to a local API.
_ALLOWED_ORIGIN = os.environ.get("CORS_ALLOWED_ORIGIN", "*")
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": _ALLOWED_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def lambda_handler(event: dict, context: Any) -> dict:
    """Entry point for API Gateway HTTP API (payload format 2.0)."""
    route = event.get("rawPath", "").rstrip("/")
    method = event.get("requestContext", {}).get("http", {}).get("method", "")

    if method == "OPTIONS":
        return _response(204, {})

    try:
        body = _parse_body(event)

        if route == "/upload-url" and method == "POST":
            return _response(200, _handle_upload_url(body))

        if route == "/ingredients" and method == "POST":
            return _response(200, _handle_ingredients(body))

        if route == "/refine" and method == "POST":
            return _response(200, _handle_refine(body))

        return _response(404, {"error": f"Unknown route {method} {route}"})

    except ValueError as e:
        logger.info("Bad request: %s", e)
        return _response(400, {"error": str(e)})
    except Exception as e:
        logger.exception("Unhandled error")
        return _response(500, {"error": "Internal error", "detail": str(e)})


# --- Route handlers ---


def _handle_upload_url(body: dict) -> dict:
    """Issue a pre-signed PUT URL the browser can upload a photo to directly."""
    bucket = os.environ.get("UPLOADS_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("UPLOADS_BUCKET_NAME not configured")

    content_type = body.get("content_type", "image/jpeg")
    if not content_type.startswith("image/"):
        raise ValueError("content_type must be an image/* MIME type")

    region = os.environ.get("AWS_REGION", "us-east-1")
    s3 = boto3.client("s3", region_name=region)
    photo_key = f"uploads/{uuid.uuid4().hex}"

    upload_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": photo_key,
            "ContentType": content_type,
        },
        ExpiresIn=300,  # 5 minutes
    )

    return {"upload_url": upload_url, "photo_key": photo_key}


def _handle_ingredients(body: dict) -> dict:
    """Run the agent on typed ingredients and/or an uploaded photo."""
    photo_key = body.get("photo_key")
    text = body.get("text")
    preferences = body.get("preferences", "none")

    if not photo_key and not text:
        raise ValueError("Provide photo_key, text, or both")

    return ask(
        photo_s3_key=photo_key,
        text_ingredients=text,
        preferences=preferences,
    )


def _handle_refine(body: dict) -> dict:
    """Apply a follow-up instruction to a previous session."""
    session_id = body.get("session_id")
    instruction = body.get("instruction")

    if not session_id:
        raise ValueError("session_id is required")
    if not instruction:
        raise ValueError("instruction is required")

    return refine(session_id=session_id, instruction=instruction)


# --- Helpers ---


def _parse_body(event: dict) -> dict:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON body: {e}")


def _response(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {**_CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(payload),
    }
