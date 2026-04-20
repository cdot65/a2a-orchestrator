import os
import sys

import uvicorn

from a2a_orchestrator.common.logging import configure_logging, get_logger
from a2a_orchestrator.shell.executor import ShellExecutor, build_card
from a2a_orchestrator.shell.sandbox import docker_available


def main() -> None:
    configure_logging(agent_name="shell")
    log = get_logger("shell")

    if not docker_available():
        log.error("docker_not_available", hint="start Docker or run `make shell-image`")
        sys.exit(1)

    port = int(os.environ.get("SHELL_PORT", "8003"))
    url = f"http://localhost:{port}"
    card_dict = build_card(url)

    from a2a.server.apps import A2AStarletteApplication
    from a2a.server.request_handlers import DefaultRequestHandler
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import AgentCard

    agent_card = AgentCard.model_validate(card_dict)
    handler = DefaultRequestHandler(
        agent_executor=ShellExecutor(),
        task_store=InMemoryTaskStore(),
    )
    app = A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
