"""Handler unit tests with the agent mocked out.

These verify routing, CORS, and error handling without hitting Bedrock or AWS.
"""

import json
from unittest.mock import patch

import pytest


def _event(method: str, path: str, body=None) -> dict:
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method}},
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
    }


def test_options_preflight():
    pytest.importorskip("strands")
    from askmom.handler import lambda_handler

    resp = lambda_handler(_event("OPTIONS", "/ingredients"), None)
    assert resp["statusCode"] == 204
    assert "Access-Control-Allow-Origin" in resp["headers"]


def test_unknown_route():
    pytest.importorskip("strands")
    from askmom.handler import lambda_handler

    resp = lambda_handler(_event("POST", "/nope"), None)
    assert resp["statusCode"] == 404


def test_ingredients_requires_input():
    pytest.importorskip("strands")
    from askmom.handler import lambda_handler

    resp = lambda_handler(_event("POST", "/ingredients", {}), None)
    assert resp["statusCode"] == 400
    assert "Provide" in json.loads(resp["body"])["error"]


def test_ingredients_calls_agent():
    pytest.importorskip("strands")
    from askmom import handler

    with patch.object(handler, "ask") as mock_ask:
        mock_ask.return_value = {"session_id": "abc", "recipes": []}
        resp = handler.lambda_handler(
            _event("POST", "/ingredients", {"text": "chicken, rice"}),
            None,
        )
    assert resp["statusCode"] == 200
    mock_ask.assert_called_once()
    assert mock_ask.call_args.kwargs["text_ingredients"] == "chicken, rice"


def test_refine_requires_session():
    pytest.importorskip("strands")
    from askmom.handler import lambda_handler

    resp = lambda_handler(
        _event("POST", "/refine", {"instruction": "quicker"}), None
    )
    assert resp["statusCode"] == 400


def test_upload_url_requires_bucket(monkeypatch):
    pytest.importorskip("strands")
    monkeypatch.delenv("UPLOADS_BUCKET_NAME", raising=False)
    from askmom.handler import lambda_handler

    resp = lambda_handler(_event("POST", "/upload-url", {}), None)
    # Missing bucket is a server-config error, not a user error.
    assert resp["statusCode"] == 500
