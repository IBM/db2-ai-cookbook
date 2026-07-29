"""hybrid_search — hybrid (BM25 + vector) retrieval inside IBM Db2 12.1.5.

The engine lives in `hybrid_search.core`; import it as:

    from hybrid_search import core as h

Kept import-light on purpose: importing this package does not pull in `ibm_db`,
so tooling can introspect it without a Db2 driver present.
"""

__version__ = "0.1.0"
