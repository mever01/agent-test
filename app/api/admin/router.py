from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.admin.schemas import DocumentIngestRequest
from app.api.dependencies import get_admin_service, require_role
from app.guardrails.schemas import SecurityEventLog
from app.services.admin_service import AdminService, DocumentQueued
from app.services.exceptions import (
    DocumentAccessDeniedError,
    DocumentNotFoundError,
)


router = APIRouter(prefix="/admin", tags=["Admin & Security"])


@router.post(
    "/documents",
    dependencies=[Depends(require_role(["admin"]))],
)
async def ingest_document(
    payload: DocumentIngestRequest,
    admin_service: AdminService = Depends(get_admin_service),
) -> DocumentQueued:
    """Загрузка и отправка регламента компании в очередь rag.documents.queue.

    Доступно ТОЛЬКО роли admin.
    """
    try:
        return await admin_service.ingest_document(
            doc_id=payload.doc_id,
            title=payload.title,
            file_path=payload.file_path,
        )
    except DocumentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except DocumentAccessDeniedError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get(
    "/security/events",
    response_model=list[SecurityEventLog],
    dependencies=[Depends(require_role(["admin"]))],
)
async def get_security_events(
    limit: int = Query(50, ge=1, le=200),
    admin_service: AdminService = Depends(get_admin_service),
) -> list[SecurityEventLog]:
    """Просмотр зафиксированных инцидентов ИБ из security_events.jsonl.

    Доступно ТОЛЬКО роли admin.
    """
    return await admin_service.get_security_events(limit=limit)
