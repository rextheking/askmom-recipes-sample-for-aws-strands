"""Extract ingredients from typed text or a photo.

Two separate tools so the agent can call whichever makes sense (or both).
"""

import base64
import json
import logging
import os
import re
from typing import List

import boto3
from strands import tool


logger = logging.getLogger(__name__)

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "the",
    "some",
    "bit",
    "of",
    "little",
    "few",
    "couple",
    "lots",
    "lot",
    "bunch",
    "handful",
    "fresh",
    "my",
    "also",
    "plus",
    "have",
    "got",
    "i",
}

_QUANTITY_PATTERN = re.compile(r"^[\d/.\s]+(cups?|tbsp|tsp|oz|lb|lbs|g|kg|ml|l)?$")


def _clean_token(token: str) -> str:
    token = token.strip().lower()
    # Drop pure quantity tokens like "2" or "1/2 cup".
    if _QUANTITY_PATTERN.match(token):
        return ""
    # Drop stop words.
    words = [w for w in token.split() if w not in _STOP_WORDS]
    # Drop leading quantity words like "2 tomatoes" -> "tomatoes".
    cleaned = []
    for w in words:
        if _QUANTITY_PATTERN.match(w):
            continue
        cleaned.append(w)
    return " ".join(cleaned).strip()


@tool
def extract_ingredients_from_text(text: str) -> List[str]:
    """Normalize a free-form ingredient string into a clean list of ingredient names.

    Use this when the user has typed what they have in their kitchen as free text
    (e.g., "chicken, some spinach, lemon, and a bit of rice"). Returns a deduped,
    lowercased list of ingredient names with quantity words stripped.

    Args:
        text: Free-form text describing ingredients the user has.

    Returns:
        A list of ingredient names. Returns an empty list if nothing usable is found.
    """
    if not text:
        return []

    # Split on commas, "and", newlines, semicolons.
    raw_tokens = re.split(r",|\band\b|;|\n", text, flags=re.IGNORECASE)

    seen = set()
    result = []
    for tok in raw_tokens:
        cleaned = _clean_token(tok)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


@tool
def extract_ingredients_from_image(s3_key: str) -> List[str]:
    """Look at a photo of groceries and return the ingredients visible in it.

    Use this when the user has uploaded a photo of groceries on their counter.
    Calls Amazon Bedrock with vision to identify food items in the photo.

    Args:
        s3_key: The S3 object key of the uploaded photo.

    Returns:
        A list of ingredient names visible in the photo. Empty list if none detected.
    """
    bucket = os.environ.get("UPLOADS_BUCKET_NAME")
    if not bucket:
        logger.warning("UPLOADS_BUCKET_NAME not set; cannot read photo.")
        return []

    region = os.environ.get("AWS_REGION", "us-east-1")
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
    )

    s3 = boto3.client("s3", region_name=region)
    obj = s3.get_object(Bucket=bucket, Key=s3_key)
    image_bytes = obj["Body"].read()
    content_type = obj.get("ContentType", "image/jpeg")
    media_type = content_type if content_type.startswith("image/") else "image/jpeg"

    bedrock = boto3.client("bedrock-runtime", region_name=region)
    prompt = (
        "List only the food ingredients you can clearly see in this photo. "
        "Return a JSON array of short lowercase names, nothing else. "
        'Example: ["tomato", "onion", "chicken breast"]. '
        "If you can't identify any food, return []."
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 400,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": base64.standard_b64encode(image_bytes).decode(),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    response = bedrock.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    text_out = payload.get("content", [{}])[0].get("text", "").strip()

    # Extract the JSON array from the model's response, defensively.
    match = re.search(r"\[.*?\]", text_out, re.DOTALL)
    if not match:
        logger.warning("Vision model returned no JSON array: %s", text_out)
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Failed to parse vision JSON: %s", match.group(0))
        return []

    return [str(x).strip().lower() for x in items if str(x).strip()]
