"""Smoke tests for the AskMom agent.

Kept unit-y and offline: no Bedrock calls, no network.
"""

import pytest


def test_prompts_import():
    from askmom import prompts, models  # noqa: F401


def test_curated_origin_lookup():
    # This import pulls in strands (via @tool decorator). If strands isn't
    # installed in the test env, skip rather than fail the whole suite.
    strands = pytest.importorskip("strands")  # noqa: F841
    from askmom.tools.lookup_food_origin import lookup_food_origin

    tomato = lookup_food_origin.original("tomato") if hasattr(lookup_food_origin, "original") else lookup_food_origin("tomato")
    # When @tool wraps the function, calling directly may still work; either
    # way we just verify the curated data is reachable.
    assert tomato is not None
    assert "Peru" in tomato["origin_country"]


def test_text_extraction_basic():
    strands = pytest.importorskip("strands")  # noqa: F841
    from askmom.tools.extract_ingredients import extract_ingredients_from_text

    fn = (
        extract_ingredients_from_text.original
        if hasattr(extract_ingredients_from_text, "original")
        else extract_ingredients_from_text
    )
    result = fn("chicken, some spinach, and a bit of rice")
    assert "chicken" in result
    assert "spinach" in result
    assert "rice" in result
    # No stop words should leak through.
    assert "some" not in result
    assert "bit" not in result
