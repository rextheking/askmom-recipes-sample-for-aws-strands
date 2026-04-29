"""Grounded nutrition lookup using USDA FoodData Central.

The API key is resolved once per cold start, preferring a plain env var
(USDA_API_KEY) for local dev, and falling back to SSM Parameter Store
(USDA_API_KEY_PARAM) in production.
"""

import logging
import os
from functools import lru_cache
from typing import Optional

import boto3
import requests
from strands import tool


logger = logging.getLogger(__name__)

_USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"

# USDA FoodData Central nutrient IDs.
# See https://fdc.nal.usda.gov/docs/Nutrient-Lookup.pdf
_NUTRIENT_IDS = {
    "calories": 1008,
    "protein_g": 1003,
    "fiber_g": 1079,
    "sodium_mg": 1093,
}


@lru_cache(maxsize=1)
def _api_key() -> Optional[str]:
    """Resolve the USDA API key once per cold start.

    Precedence:
      1. USDA_API_KEY env var (set directly for local dev)
      2. USDA_API_KEY_PARAM env var pointing at an SSM SecureString (prod)
    """
    direct = os.environ.get("USDA_API_KEY")
    if direct:
        return direct

    param_name = os.environ.get("USDA_API_KEY_PARAM")
    if not param_name:
        return None

    try:
        region = os.environ.get("AWS_REGION", "us-east-1")
        ssm = boto3.client("ssm", region_name=region)
        resp = ssm.get_parameter(Name=param_name, WithDecryption=True)
        return resp["Parameter"]["Value"]
    except Exception as e:
        logger.warning("Failed to resolve USDA key from SSM (%s): %s", param_name, e)
        return None


def _extract_nutrient(food: dict, target_id: int) -> Optional[float]:
    for n in food.get("foodNutrients", []):
        if n.get("nutrientId") == target_id:
            value = n.get("value")
            return float(value) if value is not None else None
    return None


def _make_note(calories, protein, fiber, sodium) -> str:
    """Turn real numbers into a short friendly line."""
    bits = []
    if protein is not None and protein >= 10:
        bits.append(f"a good source of protein ({protein:.0f}g per 100g)")
    if fiber is not None and fiber >= 3:
        bits.append(f"rich in fiber ({fiber:.0f}g per 100g)")
    if sodium is not None and sodium <= 140:
        bits.append("naturally low in sodium")
    if not bits and calories is not None:
        bits.append(f"around {calories:.0f} calories per 100g")
    return "This one is " + " and ".join(bits) + "." if bits else ""


@tool
def lookup_food_facts(food_name: str) -> Optional[dict]:
    """Look up grounded nutrition facts for a food from USDA FoodData Central.

    Numbers come from USDA, not the model. Returns None when the API key
    isn't configured or the food isn't found.

    Args:
        food_name: The name of the food to look up.

    Returns:
        A dict with calories, protein_g, fiber_g, sodium_mg, and a human-
        readable notes string, or None.
    """
    key = _api_key()
    if not key:
        logger.info("USDA API key not available; skipping nutrition lookup.")
        return None

    try:
        resp = requests.get(
            _USDA_SEARCH_URL,
            params={
                "api_key": key,
                "query": food_name,
                "pageSize": 1,
                "dataType": "Foundation,SR Legacy",
            },
            timeout=5,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.warning("USDA lookup failed for %r: %s", food_name, e)
        return None

    foods = resp.json().get("foods", [])
    if not foods:
        return None

    food = foods[0]
    calories = _extract_nutrient(food, _NUTRIENT_IDS["calories"])
    protein = _extract_nutrient(food, _NUTRIENT_IDS["protein_g"])
    fiber = _extract_nutrient(food, _NUTRIENT_IDS["fiber_g"])
    sodium = _extract_nutrient(food, _NUTRIENT_IDS["sodium_mg"])

    return {
        "calories": calories,
        "protein_g": protein,
        "fiber_g": fiber,
        "sodium_mg": sodium,
        "notes": _make_note(calories, protein, fiber, sodium),
    }
