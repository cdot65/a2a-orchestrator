.PHONY: install lint fmt test shell-image run-all clean

install:
	uv sync

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest -v

shell-image:
	./scripts/build_shell_image.sh

run-all:
	./scripts/run_all.sh

clean:
	rm -rf .pytest_cache .ruff_cache dist *.egg-info
