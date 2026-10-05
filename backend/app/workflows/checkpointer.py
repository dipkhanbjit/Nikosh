from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings

_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    global _checkpointer
    if _checkpointer is None:
        conninfo = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        pool = ConnectionPool(
            conninfo=conninfo,
            max_size=10,
            open=True,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        _checkpointer = PostgresSaver(pool)
        _checkpointer.setup()
    return _checkpointer
