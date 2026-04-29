"""Session storage: in-memory for local dev, DynamoDB for Lambda.

Picks its backend based on the SESSIONS_TABLE_NAME env var. Same interface
either way so the agent and handler don't care which one is active.
"""

import json
import logging
import os
import time
from typing import Optional

import boto3


logger = logging.getLogger(__name__)

_SESSION_TTL_SECONDS = 60 * 60 * 24  # 24h
_LOCAL_CACHE: dict[str, dict] = {}


def _table_name() -> Optional[str]:
    return os.environ.get("SESSIONS_TABLE_NAME")


def _table():
    region = os.environ.get("AWS_REGION", "us-east-1")
    return boto3.resource("dynamodb", region_name=region).Table(_table_name())


def save_session(session_id: str, data: dict) -> None:
    """Persist a session. DynamoDB if configured, otherwise in-memory."""
    if _table_name():
        try:
            _table().put_item(
                Item={
                    "session_id": session_id,
                    "data": json.dumps(data),
                    "expires_at": int(time.time()) + _SESSION_TTL_SECONDS,
                }
            )
            return
        except Exception as e:
            logger.warning("DynamoDB save failed, falling back to memory: %s", e)
    _LOCAL_CACHE[session_id] = data


def load_session(session_id: str) -> Optional[dict]:
    """Load a session. DynamoDB if configured, otherwise in-memory."""
    if _table_name():
        try:
            resp = _table().get_item(Key={"session_id": session_id})
            item = resp.get("Item")
            if item and "data" in item:
                return json.loads(item["data"])
            return None
        except Exception as e:
            logger.warning("DynamoDB load failed, falling back to memory: %s", e)
    return _LOCAL_CACHE.get(session_id)
