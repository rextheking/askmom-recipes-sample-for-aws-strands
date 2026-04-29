"""Grounded origin/history lookup.

We ship a small curated dict of common foods. The LLM is NOT allowed to invent
origins. If we don't have a grounded answer, we return None and the agent is
instructed to say "origin varies" rather than make something up.
"""

from typing import Optional

from strands import tool


# Tiny seed set. Facts here should be short, verifiable, and uncontroversial.
_CURATED_ORIGINS = {
    "tomato": {
        "origin_country": "Peru (Andes)",
        "history_note": "Native to western South America; spread worldwide after Spanish contact in the 1500s.",
    },
    "potato": {
        "origin_country": "Peru (Andes)",
        "history_note": "Domesticated in the Andes over 7,000 years ago; a staple across the Americas before reaching Europe.",
    },
    "rice": {
        "origin_country": "China",
        "history_note": "Domesticated along the Yangtze River roughly 9,000 years ago.",
    },
    "chicken": {
        "origin_country": "Southeast Asia",
        "history_note": "Descended from the red junglefowl, domesticated thousands of years ago.",
    },
    "lemon": {
        "origin_country": "South Asia",
        "history_note": "Likely originated in the Assam region of India; spread through the Middle East and Mediterranean.",
    },
    "garlic": {
        "origin_country": "Central Asia",
        "history_note": "Cultivated for over 5,000 years; used in ancient Egyptian, Greek, and Chinese cuisines.",
    },
    "spinach": {
        "origin_country": "Persia (modern Iran)",
        "history_note": "Cultivated in Persia for centuries before spreading to China in the 7th century and Europe in the 12th.",
    },
    "onion": {
        "origin_country": "Central Asia",
        "history_note": "One of humanity's oldest cultivated vegetables, dating back at least 5,000 years.",
    },
    "olive oil": {
        "origin_country": "Mediterranean basin",
        "history_note": "Produced since at least 4000 BCE; central to Greek, Roman, and Levantine cuisine and trade.",
    },
    "pasta": {
        "origin_country": "Italy",
        "history_note": "Durum wheat pasta traces to medieval Sicily; popularized across Italy from the 13th century onward.",
    },
    "chickpea": {
        "origin_country": "Middle East",
        "history_note": "Domesticated in what is now Turkey around 7,500 years ago.",
    },
    "lentil": {
        "origin_country": "Near East",
        "history_note": "One of the earliest domesticated crops, cultivated for over 8,000 years.",
    },
}


def _normalize(food_name: str) -> str:
    name = food_name.strip().lower()
    # Strip a trailing 's' for a naive plural check, but only if the base exists.
    if name.endswith("s") and name[:-1] in _CURATED_ORIGINS:
        return name[:-1]
    return name


@tool
def lookup_food_origin(food_name: str) -> Optional[dict]:
    """Look up the country of origin and a short history note for a food.

    Use this to enrich recipes with a grounded one-liner about where the dish
    or its main ingredient comes from. Only returns curated, verifiable facts.
    Returns None if the food isn't in our dataset.

    Args:
        food_name: The name of the food or ingredient to look up.

    Returns:
        A dict with keys "origin_country" and "history_note", or None if the
        food isn't in the curated dataset. Never returns invented data.
    """
    return _CURATED_ORIGINS.get(_normalize(food_name))
