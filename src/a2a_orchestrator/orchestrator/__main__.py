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
from a2a_orchestrator.orchestrator.executor import OrchestratorExecutor, build_card
from a2a_orchestrator.orchestrator.openai_compat import router as openai_router

# Path to the full merged static spec (A2A + OpenAI-compat paths).
# Distinct from /v1/openapi.json which is FastAPI-auto-generated (OpenAI-compat only).
_OPENAPI_DOC = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "docs"
    / "openapi"
    / "orchestrator.openapi.json"
)


def main() -> None:
    configure_logging(agent_name="orchestrator")
    port = int(os.environ.get("ORCHESTRATOR_PORT", "8000"))
    url = f"http://localhost:{port}"
    card_dict = build_card(url)
    agent_card = AgentCard.model_validate(card_dict)

    handler = DefaultRequestHandler(
        agent_executor=OrchestratorExecutor(),
        task_store=InMemoryTaskStore(),
    )
    a2a_app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()

    # /v1/openapi.json  — FastAPI auto-generated, covers only the OpenAI-compat surface.
    # /openapi.json     — Our explicit route below: full merged static doc (A2A + OpenAI-compat).
    app = FastAPI(
        title="A2A Orchestrator",
        description="Orchestrator agent with A2A protocol and OpenAI-compatible chat API.",
        version="0.1.0",
        openapi_url="/v1/openapi.json",
        docs_url="/v1/docs",
        redoc_url=None,
    )
    app.include_router(openai_router)

    @app.get("/openapi.json", include_in_schema=False)
    def _serve_openapi() -> JSONResponse:
        return JSONResponse(json.loads(_OPENAPI_DOC.read_text()))

    # Mount A2A at root so /.well-known/agent-card.json and POST / still work.
    app.mount("/", a2a_app)

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
