"""Strands agent entry points for AskMom Recipes.

Design note (important for the blog):

The agent drives only the steps that genuinely need an LLM:
  1. extract_ingredients_from_image (vision)
  2. extract_ingredients_from_text (normalization)
  3. suggest_recipes (creative generation)

Enrichment is deterministic Python:
  - lookup_food_facts (USDA API, grounded)
  - lookup_food_origin (curated dict, grounded)
  - format_recipe_card (pure assembly)

Separating "planning" (LLM) from "enrichment" (code) makes the system fast,
cheap, and predictable. The original design had the agent call every tool,
which produced 10+ Bedrock round-trips per request. This version does 2.
"""

import logging
import os
import uuid
from typing import Optional

from strands import Agent
from strands.models import BedrockModel

from .prompts import SYSTEM_PROMPT, REFINE_PROMPT
from .session_store import load_session, save_session
from .tools import (
    extract_ingredients_from_image,
    extract_ingredients_from_text,
    suggest_recipes,
    lookup_food_facts,
    lookup_food_origin,
    format_recipe_card,
)


logger = logging.getLogger(__name__)


def build_agent(model_id: Optional[str] = None) -> Agent:
    """Construct the Strands agent.

    Only the LLM-dispatched tools are bound. Grounded enrichment tools
    (origin, facts, formatting) are called directly from Python after the
    agent finishes.
    """
    model_id = model_id or os.environ.get(
        "BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0"
    )
    region = os.environ.get("AWS_REGION", "us-east-1")

    model = BedrockModel(
        model_id=model_id,
        region_name=region,
        temperature=0.4,
    )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            extract_ingredients_from_image,
            extract_ingredients_from_text,
            suggest_recipes,
        ],
    )


def ask(
    photo_s3_key: Optional[str] = None,
    text_ingredients: Optional[str] = None,
    preferences: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """Run the agent end-to-end for a fresh request."""
    if not photo_s3_key and not text_ingredients:
        raise ValueError("Provide photo_s3_key, text_ingredients, or both.")

    session_id = session_id or str(uuid.uuid4())
    preferences = preferences or "none"

    agent = build_agent()
    user_msg_parts = [
        "A user wants healthy recipe ideas.",
        f"Dietary preference: {preferences}.",
    ]
    if photo_s3_key:
        user_msg_parts.append(f"Grocery photo S3 key: {photo_s3_key}")
    if text_ingredients:
        user_msg_parts.append(f'Typed ingredients: "{text_ingredients}"')
    user_msg_parts.append(
        "Follow your standard process and return the final JSON object."
    )

    result = agent("\n".join(user_msg_parts))
    raw_recipes, extracted = _parse_agent_response(result)

    enriched = [_enrich_recipe(r) for r in raw_recipes]

    response = {
        "session_id": session_id,
        "recipes": enriched,
        "extracted_ingredients": extracted,
        "preferences": preferences,
    }
    save_session(session_id, response)
    return response


def refine(session_id: str, instruction: str) -> dict:
    """Apply a follow-up instruction to an existing session."""
    prior = load_session(session_id)
    if not prior:
        raise ValueError(f"No session {session_id}")

    agent = build_agent()
    user_msg = (
        f"{REFINE_PROMPT}\n\n"
        f"Previous ingredients: {', '.join(prior['extracted_ingredients'])}\n"
        f"Dietary preference: {prior['preferences']}\n"
        f"Previous recipes: {prior['recipes']}\n\n"
        f'New instruction from the user: "{instruction}"\n\n'
        "Return a fresh JSON object with a \"recipes\" array of 3 suggestions "
        "and an \"extracted_ingredients\" array."
    )

    result = agent(user_msg)
    raw_recipes, extracted = _parse_agent_response(result)

    enriched = [_enrich_recipe(r) for r in raw_recipes]

    response = {
        "session_id": session_id,
        "recipes": enriched,
        "extracted_ingredients": extracted or prior["extracted_ingredients"],
        "preferences": prior["preferences"],
    }
    save_session(session_id, response)
    return response


def _enrich_recipe(recipe: dict) -> dict:
    """Add grounded origin + nutrition facts to a recipe, deterministically.

    Picks the most defining ingredient heuristically (the first item in
    ingredients_you_have, falling back to the recipe name). Then looks up
    origin and facts without any LLM calls.
    """
    # Pick a reasonable "main" ingredient for enrichment.
    defining = None
    if recipe.get("ingredients_you_have"):
        defining = recipe["ingredients_you_have"][0]
    elif recipe.get("name"):
        defining = recipe["name"]

    origin = lookup_food_origin(defining) if defining else None
    facts = lookup_food_facts(defining) if defining else None

    return format_recipe_card(recipe=recipe, nutrition=facts, origin=origin)


def _parse_agent_response(result) -> tuple[list, list]:
    """Pull recipes and extracted ingredients out of the agent's final message."""
    import json
    import re

    text = str(result).strip() if result is not None else ""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        logger.warning("Agent returned non-JSON final message: %s", text[:300])
        return [], []
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Failed to parse agent JSON: %s", match.group(0)[:300])
        return [], []
    return parsed.get("recipes", []), parsed.get("extracted_ingredients", [])
