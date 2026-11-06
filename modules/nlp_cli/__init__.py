"""NLP-CLI as an Organism module. See docs/integrations/NLP_CLI_ON_ORGANISM.md."""

from nlp_cli.router import (
    NlpCliRouter,
    RouterError,
    RouteResult,
    dispatch,
    load_spec,
    model_digest,
    parse_result,
    path_args,
    register_tools,
    router_contract,
    tool_contracts,
)

__all__ = [
    "NlpCliRouter",
    "RouteResult",
    "RouterError",
    "dispatch",
    "load_spec",
    "model_digest",
    "parse_result",
    "path_args",
    "register_tools",
    "router_contract",
    "tool_contracts",
]
