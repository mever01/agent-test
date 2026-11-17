from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.dao.db_mail.draft import DraftDAO
from app.db.dao.db_mail.thread import ThreadDAO
from app.dto.db_mail import DraftWrite, MailThreadDetails
from app.services.db_mail.draft import DraftService
from app.services.db_mail.thread import ThreadService
from app.services.exceptions import ThreadNotFoundError


async def test_thread_read_keeps_owner() -> None:
    dao = AsyncMock(spec=ThreadDAO)
    thread_id, owner_id = uuid4(), uuid4()
    details = MailThreadDetails(str(thread_id), "Project X", "client", [])
    dao.get_thread.return_value = details
    service = ThreadService(dao)
    assert await service.get_thread(thread_id, owner_id) == details
    dao.get_thread.assert_awaited_once_with(thread_id, owner_id=owner_id)
    dao.get_thread.return_value = None
    with pytest.raises(ThreadNotFoundError):
        await service.get_thread(thread_id, owner_id)


async def test_draft_preserves_operation_and_owner() -> None:
    dao = AsyncMock(spec=DraftDAO)
    dao.save_draft.return_value = "draft-id"
    owner_id, thread_id, operation_id = uuid4(), uuid4(), uuid4()
    service = DraftService(dao)
    data = DraftWrite(
        thread_id=thread_id, recipient="client@example.test", subject="Re: Project X",
        text_content="Confirmed.", operation_id=operation_id,
    )
    result = await service.create_draft(data, owner_id=owner_id)
    assert result == "draft-id"
    data = dao.save_draft.await_args.args[0]
    assert data.thread_id == thread_id and data.operation_id == operation_id
    assert dao.save_draft.await_args.kwargs == {"owner_id": owner_id}
    dao.save_draft.return_value = None
    with pytest.raises(ThreadNotFoundError):
        await service.create_draft(data, owner_id=owner_id)


async def test_draft_lookup_and_list_are_scoped() -> None:
    dao = AsyncMock(spec=DraftDAO)
    dao.list_drafts.return_value = []
    dao.draft_for_operation.return_value = "existing-draft"
    owner_id, operation_id = uuid4(), uuid4()
    service = DraftService(dao)
    assert await service.draft_for_operation(operation_id, owner_id) == "existing-draft"
    dao.draft_for_operation.assert_awaited_once_with(operation_id, owner_id=owner_id)
    assert await service.list_drafts(limit=5, owner_id=owner_id) == []
    dao.list_drafts.assert_awaited_once_with(limit=5, owner_id=owner_id)
