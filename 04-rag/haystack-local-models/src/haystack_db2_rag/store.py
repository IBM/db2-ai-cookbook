"""The Db2 vector store, shared by ingest.py, search.py and metadata.py."""

from contextlib import contextmanager

from haystack.utils import Secret
from haystack_integrations.document_stores.ibm_db import IBMDb2DocumentStore

from . import settings


def document_store(recreate_table: bool = False) -> IBMDb2DocumentStore:
    """Connect to Db2. The table (with its VECTOR column) is created for us."""
    return IBMDb2DocumentStore(
        database=settings.DB2_DATABASE,
        hostname=settings.DB2_HOSTNAME,
        port=settings.DB2_PORT,
        username=Secret.from_token(settings.DB2_USERNAME),
        password=Secret.from_token(settings.DB2_PASSWORD),
        table_name=settings.DB2_TABLE,
        embedding_dim=settings.EMBED_DIM,
        distance_metric="COSINE",
        recreate_table=recreate_table,
    )


@contextmanager
def open_store(recreate_table: bool = False):
    """A store that closes its Db2 connection when the block ends.

    A short-lived script can skip this — the connection dies with the process. A long
    running server cannot: every store holds a connection, and a run that raises leaves
    its transaction open. The lock that transaction holds then blocks every reader of
    the table until the process exits. So anything that opens a store inside a request
    or a job closes it here, on the way out, error or not.
    """
    store = document_store(recreate_table=recreate_table)
    try:
        yield store
    finally:
        store.close()
