import logging
import os
import sys

import structlog


def configure_logging(*, agent_name: str) -> None:
    structlog.reset_defaults()
    fmt = os.environ.get("LOG_FORMAT", "pretty").lower()
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        force=True,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.CallsiteParameterAdder(
            {structlog.processors.CallsiteParameter.MODULE}
        ),
        _inject_agent(agent_name),
    ]
    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=False))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _inject_agent(name: str):
    def _p(_logger, _method, event_dict):
        event_dict["agent"] = name
        return event_dict

    return _p


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
