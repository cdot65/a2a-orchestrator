import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from a2a_orchestrator.common.recipe import Recipe, slugify


@dataclass(frozen=True)
class SavedPaths:
    json_path: Path
    md_path: Path


def _recipes_dir() -> Path:
    return Path(os.environ.get("RECIPES_DIR", "./recipes"))


def _render_markdown(recipe: Recipe) -> str:
    parts = [f"# {recipe.title}", "", recipe.description, ""]
    if recipe.source_url is not None:
        parts += [f"Source: {recipe.source_url}", ""]

    parts += ["## Ingredients", ""]
    parts += [f"- {i}" for i in recipe.ingredients]

    parts += ["", "## Prep Steps", ""]
    parts += [f"{n}. {s}" for n, s in enumerate(recipe.prep_steps, 1)]

    parts += ["", "## Cooking Steps", ""]
    parts += [f"{n}. {s}" for n, s in enumerate(recipe.cooking_steps, 1)]

    if recipe.chef_notes is not None:
        parts += ["", "## Chef Notes", "", recipe.chef_notes]

    parts.append("")
    return "\n".join(parts)


def save_recipe(recipe: Recipe) -> SavedPaths:
    out_dir = _recipes_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = slugify(recipe.title) or "recipe"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{slug}-{stamp}"

    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"

    json_path.write_text(recipe.model_dump_json(indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(recipe), encoding="utf-8")

    return SavedPaths(json_path=json_path, md_path=md_path)
