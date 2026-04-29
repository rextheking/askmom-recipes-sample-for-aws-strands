"""Suggest 3 healthy recipes given ingredients and preferences."""

import json
import logging
import os
import re
from typing import List, Optional

import boto3
from strands import tool


logger = logging.getLogger(__name__)


_PREFERENCE_GUIDANCE = {
    "none": "No dietary restrictions. Focus on healthy, balanced meals.",
    "vegetarian": "Strictly vegetarian: no meat, poultry, or fish.",
    "low_sodium": "Low sodium: minimize salt and high-sodium ingredients like soy sauce or canned broths.",
    "diabetic_friendly": "Diabetic-friendly: low glycemic index, limit added sugars and refined carbs.",
    "gluten_free": "Strictly gluten-free: no wheat, barley, rye, or standard soy sauce.",
}


@tool
def suggest_recipes(
    ingredients: List[str],
    preferences: Optional[str] = None,
) -> List[dict]:
    """Suggest exactly 3 healthy recipes given the ingredients a user has.

    Each recipe is tailored to the user's dietary preference. Ingredients are
    split into "ingredients_you_have" and "ingredients_to_grab" so the user
    knows what they still need to buy.

    Do NOT include nutrition or origin facts here. Those are added later by
    separate tools so each tool stays focused and testable.

    Args:
        ingredients: The ingredient names the user has available.
        preferences: One of "none", "vegetarian", "low_sodium",
            "diabetic_friendly", "gluten_free". Defaults to "none".

    Returns:
        A list of exactly 3 recipe dicts, each with keys:
        name, hook, ingredients_you_have, ingredients_to_grab, steps, minutes.
    """
    if not ingredients:
        return []

    pref = (preferences or "none").lower()
    guidance = _PREFERENCE_GUIDANCE.get(pref, _PREFERENCE_GUIDANCE["none"])

    region = os.environ.get("AWS_REGION", "us-east-1")
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
    )

    user_prompt = f"""The user has these ingredients available: {', '.join(ingredients)}.

Dietary preference: {pref}
Guidance: {guidance}

Suggest exactly 3 healthy recipes. Prefer recipes that use what they already have.

CRITICAL RULES for the ingredient lists:
- "ingredients_you_have" MUST contain ONLY items that are in the user's available
  list above. Copy their exact names. This is everything they already have that
  the recipe uses.
- "ingredients_to_grab" MUST contain ONLY items the recipe needs that are NOT in
  the user's available list. Things like salt, pepper, and water don't count;
  omit them.
- Never put the same item in both lists.
- If every needed ingredient is already available, "ingredients_to_grab" MUST be [].

Return ONLY a JSON array of 3 objects. Each object must have these exact keys:
- "name": string, the recipe name
- "hook": string, a one-line description (under 15 words)
- "ingredients_you_have": array of strings (see rules above)
- "ingredients_to_grab": array of strings (see rules above)
- "steps": array of strings, 3-6 simple instructions
- "minutes": integer, estimated cook time

No prose, no markdown, no explanation. Just the JSON array."""

    bedrock = boto3.client("bedrock-runtime", region_name=region)
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    response = bedrock.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(response["body"].read())
    text_out = payload.get("content", [{}])[0].get("text", "").strip()

    # Pull out the first JSON array in the response, defensively.
    match = re.search(r"\[.*\]", text_out, re.DOTALL)
    if not match:
        logger.warning("Recipe model returned no JSON array: %s", text_out)
        return []
    try:
        recipes = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse recipe JSON: %s (%s)", match.group(0), e)
        return []

    # Defensive normalization; the agent is told the schema but LLMs drift.
    normalized = []
    for r in recipes[:3]:
        normalized.append(
            {
                "name": str(r.get("name", "")).strip(),
                "hook": str(r.get("hook", "")).strip(),
                "ingredients_you_have": [
                    str(x) for x in r.get("ingredients_you_have", [])
                ],
                "ingredients_to_grab": [
                    str(x) for x in r.get("ingredients_to_grab", [])
                ],
                "steps": [str(x) for x in r.get("steps", [])],
                "minutes": (
                    int(r["minutes"])
                    if isinstance(r.get("minutes"), (int, float, str))
                    and str(r.get("minutes")).isdigit()
                    else None
                ),
            }
        )
    return normalized
