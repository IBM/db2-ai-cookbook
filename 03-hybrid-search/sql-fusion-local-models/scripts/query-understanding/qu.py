#!/usr/bin/env python3
"""Thin shim — the query-understanding orchestration now lives in the package at
`hybrid_search.understanding` (first-class engine module, importable by the API).
This re-export keeps the dev harness (qu_eval.py) working with `import qu`.
"""
from hybrid_search.understanding import (  # noqa: F401
    lexical_of, route_of, llm_expand, understand,
    gated_search, confidence_search, smart_search, clear_cache,
    HYDE_PROMPT, MODE, SIM_GATE,
)
