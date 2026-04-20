import json
import os
from pathlib import Path

import uvicorn
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCard
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from a2a_orchestrator.common.logging import configure_logging
from a2a_orchestrator.recipe_gen.executor import RecipeGenExecutor, build_card

_OPENAPI_DOC = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "openapi"
    / "recipe-gen.openapi.json"
)


def main() -> None:
    configure_logging(agent_name="recipe-gen")
    port = int(os.environ.get("RECIPE_GEN_PORT", "8002"))
    url = f"http://localhost:{port}"
    card_dict = build_card(url)
    agent_card = AgentCard.model_validate(card_dict)

    handler = DefaultRequestHandler(
        agent_executor=RecipeGenExecutor(),
        task_store=InMemoryTaskStore(),
    )
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()

    app = FastAPI(
        title="A2A Recipe Generator Agent",
        version="0.1.0",
        openapi_url=None,  # static file is the canonical spec
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/openapi.json", include_in_schema=False)
    def _serve_openapi() -> JSONResponse:
        return JSONResponse(json.loads(_OPENAPI_DOC.read_text()))

    app.mount("/", a2a_app)

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
