"""Data shapes passed between tools and returned to the frontend.

Using simple dataclasses for now. If we outgrow this we can move to Pydantic.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Ingredient:
    name: str
    quantity: Optional[str] = None  # e.g., "2", "a handful"
    confidence: Optional[float] = None  # for vision-extracted items


@dataclass
class NutritionFacts:
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sodium_mg: Optional[float] = None
    notes: Optional[str] = None  # human-readable "why this is good for you"


@dataclass
class OriginFact:
    origin_country: Optional[str] = None
    history_note: Optional[str] = None  # one-liner


@dataclass
class RecipeCard:
    name: str
    hook: str  # one-line description
    ingredients_you_have: List[str] = field(default_factory=list)
    ingredients_to_grab: List[str] = field(default_factory=list)
    steps: List[str] = field(default_factory=list)
    why_good_for_you: Optional[str] = None
    origin_note: Optional[str] = None
    minutes: Optional[int] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RecipeResponse:
    session_id: str
    recipes: List[RecipeCard] = field(default_factory=list)
    extracted_ingredients: List[str] = field(default_factory=list)
    preferences: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "recipes": [r.to_dict() for r in self.recipes],
            "extracted_ingredients": self.extracted_ingredients,
            "preferences": self.preferences,
        }
