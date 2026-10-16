from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KBDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    kind: str
    chunk_count: int
    created_at: datetime