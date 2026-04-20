import json

from a2a_orchestrator.common.persistence import save_recipe
from a2a_orchestrator.common.recipe import Recipe


def _sample_recipe() -> Recipe:
    return Recipe(
        title="Spicy Vegan Ramen",
        description="A warming bowl.",
        ingredients=["noodles", "chili oil"],
        prep_steps=["boil water"],
        cooking_steps=["cook 3 min"],
        chef_notes="Add mushrooms.",
        source_url="https://example.com/ramen",
    )


def test_save_recipe_writes_json_and_md(tmp_path, monkeypatch):
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    paths = save_recipe(_sample_recipe())

    assert paths.json_path.exists()
    assert paths.md_path.exists()
    assert paths.json_path.parent == tmp_path

    data = json.loads(paths.json_path.read_text())
    assert data["title"] == "Spicy Vegan Ramen"

    md = paths.md_path.read_text()
    assert "# Spicy Vegan Ramen" in md
    assert "## Ingredients" in md
    assert "- noodles" in md
    assert "## Chef Notes" in md


def test_save_recipe_omits_chef_notes_section_when_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    recipe = _sample_recipe().model_copy(update={"chef_notes": None})
    paths = save_recipe(recipe)
    md = paths.md_path.read_text()
    assert "## Chef Notes" not in md


def test_save_recipe_filenames_use_slug_and_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("RECIPES_DIR", str(tmp_path))
    paths = save_recipe(_sample_recipe())
    name = paths.json_path.name
    assert name.startswith("spicy-vegan-ramen-")
    assert name.endswith(".json")
    stem = paths.json_path.stem
    assert len(stem.split("-")[-2]) == 8  # date
    assert len(stem.split("-")[-1]) == 6  # time


def test_save_recipe_creates_dir_if_missing(tmp_path, monkeypatch):
    out = tmp_path / "does-not-exist-yet"
    monkeypatch.setenv("RECIPES_DIR", str(out))
    paths = save_recipe(_sample_recipe())
    assert out.is_dir()
    assert paths.json_path.exists()
