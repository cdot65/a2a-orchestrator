import os

import uvicorn

from a2a_orchestrator.common.logging import configure_logging
from a2a_orchestrator.recipe_gen.executor import RecipeGenExecutor, build_card


def main() -> None:
    configure_logging(agent_name="recipe-gen")
    port = int(os.environ.get("RECIPE_GEN_PORT", "8002"))
    url = f"http://localhost:{port}"
    card_dict = build_card(url)

    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import AgentCard

    agent_card = AgentCard.model_validate(card_dict)
    handler = DefaultRequestHandler(
        agent_executor=RecipeGenExecutor(),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
