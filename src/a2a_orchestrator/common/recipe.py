import re

from pydantic import BaseModel, Field


class Recipe(BaseModel):
    title: str
    description: str
    ingredients: list[str] = Field(min_length=1)
    prep_steps: list[str]
    cooking_steps: list[str]
    chef_notes: str | None = None
    source_url: str | None = None


def recipe_json_schema() -> dict:
    """JSON schema for forced tool-use with Claude."""
    return Recipe.model_json_schema()


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    lower = title.lower().strip()
    return _SLUG_RE.sub("-", lower).strip("-")
