"""The Db2 vector store, shared by index.py and ask.py."""

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
