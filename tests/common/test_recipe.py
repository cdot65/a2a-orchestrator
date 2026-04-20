import json

import pytest
from pydantic import ValidationError

from a2a_orchestrator.common.recipe import Recipe, recipe_json_schema, slugify


def _sample_payload() -> dict:
    return {
        "title": "Spicy Vegan Ramen",
        "description": "A warming bowl of chili-infused ramen.",
        "ingredients": ["200g ramen noodles", "1 tbsp chili oil"],
        "prep_steps": ["Boil water", "Slice scallions"],
        "cooking_steps": ["Cook noodles for 3 min", "Add chili oil"],
        "chef_notes": "Add mushrooms for umami.",
        "source_url": "https://example.com/ramen",
    }


def test_recipe_roundtrip():
    recipe = Recipe(**_sample_payload())
    assert recipe.title == "Spicy Vegan Ramen"
    assert recipe.source_url == "https://example.com/ramen"
    data = json.loads(recipe.model_dump_json())
    assert data["ingredients"] == ["200g ramen noodles", "1 tbsp chili oil"]


def test_recipe_optional_fields_default_none():
    payload = _sample_payload()
    del payload["chef_notes"]
    del payload["source_url"]
    recipe = Recipe(**payload)
    assert recipe.chef_notes is None
    assert recipe.source_url is None


def test_recipe_rejects_missing_title():
    payload = _sample_payload()
    del payload["title"]
    with pytest.raises(ValidationError):
        Recipe(**payload)


def test_recipe_json_schema_has_expected_properties():
    schema = recipe_json_schema()
    assert schema["type"] == "object"
    assert "title" in schema["properties"]
    assert "ingredients" in schema["required"]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Spicy Vegan Ramen", "spicy-vegan-ramen"),
        ("Mom's Best Cookies!", "mom-s-best-cookies"),
        ("  weird   spacing ", "weird-spacing"),
        ("Crème Brûlée", "creme-brulee"),
        ("", ""),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected
