"""Assemble a final recipe card the frontend can render."""

from typing import Optional

from strands import tool

from ..models import RecipeCard


@tool
def format_recipe_card(
    recipe: dict,
    nutrition: Optional[dict] = None,
    origin: Optional[dict] = None,
) -> dict:
    """Combine a recipe with optional nutrition and origin facts into a card.

    Use this as the final step after suggesting a recipe and looking up its
    facts. If nutrition or origin is None, the corresponding field is omitted
    or set to a safe fallback rather than invented.

    Args:
        recipe: Dict with keys name, hook, ingredients_you_have,
            ingredients_to_grab, steps, minutes.
        nutrition: Optional dict from lookup_food_facts; may be None.
        origin: Optional dict from lookup_food_origin; may be None.

    Returns:
        A dict ready to send to the frontend.
    """
    card = RecipeCard(
        name=recipe.get("name", ""),
        hook=recipe.get("hook", ""),
        ingredients_you_have=list(recipe.get("ingredients_you_have", [])),
        ingredients_to_grab=list(recipe.get("ingredients_to_grab", [])),
        steps=list(recipe.get("steps", [])),
        minutes=recipe.get("minutes"),
    )

    if nutrition and nutrition.get("notes"):
        card.why_good_for_you = nutrition["notes"]

    if origin and origin.get("history_note"):
        card.origin_note = origin["history_note"]
    else:
        card.origin_note = "origin varies"

    return card.to_dict()
