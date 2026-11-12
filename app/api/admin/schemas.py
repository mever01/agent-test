from pydantic import BaseModel, Field


class DocumentIngestRequest(BaseModel):
    doc_id: str = Field(..., description="Уникальный идентификатор документа")
    title: str = Field(..., description="Название документа")
    file_path: str = Field(..., description="Путь к markdown-файлу документа")
