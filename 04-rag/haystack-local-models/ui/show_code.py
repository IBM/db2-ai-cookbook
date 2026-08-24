"""The "Show code" data — read out of the running modules, never hand-copied.

The UI claims to show the code behind each step, so the only honest source for it is
the module that actually ran. `inspect.getsource` gives the whole file; the per-step
snippets are cut from that same text by finding each

    pipeline.add_component("<name>", ...)

call in the AST and taking its exact source span. The string literal in that call is
the same name Haystack reports on the trace span (`haystack.component.name`), so steps
and snippets line up by construction. Edit ingest.py, reload the page, see the change.
"""

import ast
import inspect
from types import ModuleType

from haystack_db2_rag import ingest, search

MODULES: dict[str, ModuleType] = {"ingest": ingest, "search": search}


def component_snippets(source: str) -> dict[str, str]:
    """Map component name -> the source of the add_component() call that creates it."""
    snippets = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_component"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant)):
            continue
        name = node.args[0].value
        segment = ast.get_source_segment(source, node)
        if isinstance(name, str) and segment:
            snippets[name] = segment
    return snippets


def connections(source: str) -> list[str]:
    """The pipeline.connect() calls, in file order — how the components are wired."""
    return [
        segment
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "connect"
        and (segment := ast.get_source_segment(source, node))
    ]


def for_module(key: str) -> dict:
    """Everything the UI needs to render Show code for one workflow."""
    module = MODULES[key]
    source = inspect.getsource(module)
    payload = {
        "file": f"src/haystack_db2_rag/{key}.py",
        "full": source,
        "steps": component_snippets(source),
        "connections": connections(source),
    }
    if key == "search":
        # The prompt is the most instructive part of this file, so it gets its own block.
        payload["prompt"] = module.PROMPT
    return payload
