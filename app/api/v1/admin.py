import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from app.api.dependencies import get_event_publisher, require_role
from app.queue.publisher import EventPublisher
from app.configs import settings

router = APIRouter(prefix="/admin", tags=["Admin & Security"])

class DocumentIngestRequest(BaseModel):
    doc_id: str
    title: str
    file_path: str

@router.post(
    "/documents",
    dependencies=[Depends(require_role(["admin"]))],
)
async def ingest_document(
    payload: DocumentIngestRequest,
    publisher: EventPublisher = Depends(get_event_publisher),
):
    """
    Загрузка и отправка регламента компании в очередь rag.documents.queue.
    Доступно ТОЛЬКО роли admin.
    """
    path = Path(payload.file_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл {payload.file_path} не существует на сервере.",
        )

    await publisher.publish_doc_ingest(
        doc_id=payload.doc_id,
        title=payload.title,
        file_path=payload.file_path,
    )
    return {
        "status": "queued",
        "doc_id": payload.doc_id,
        "title": payload.title,
        "queue": "rag.documents.queue",
    }

@router.get(
    "/security/events",
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_security_events(limit: int = Query(50, le=200)):
    """
    Просмотр зафиксированных инцидентов ИБ из security_events.jsonl.
    Доступно ТОЛЬКО роли admin.
    """
    log_path = settings.guardrails.security_log_path
    if not log_path.exists():
        return []

    events = []
    with open(log_path, mode="r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass

    return events[-limit:]

