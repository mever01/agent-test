import inspect
import uuid
import pytest
from app.services.mail_service import MailService
from app.services.exceptions import ThreadNotFoundError
from app.db.schemas import MailSnippet as EmailSnippet, MailThreadDetails as ThreadDetails


def test_mail_service_structure():
    assert inspect.iscoroutinefunction(MailService.get_thread)
    assert inspect.iscoroutinefunction(MailService.close_thread)
    assert inspect.iscoroutinefunction(MailService.search_emails)
    assert inspect.iscoroutinefunction(MailService.create_draft)
    assert inspect.iscoroutinefunction(MailService.list_drafts)


@pytest.mark.asyncio
async def test_mail_service_search_emails():
    expected_snippets = [
        EmailSnippet(
            email_id=str(uuid.uuid4()),
            thread_id=str(uuid.uuid4()),
            subject="Тестовое письмо",
            sender="boss@corp.ru",
            date="2026-01-01 10:00:00",
            snippet="Привет мир",
        )
    ]

    class FakeRepo:
        async def search_emails(self, words, sender, start_date, end_date, limit, *, participant):
            assert words == "тест"
            return expected_snippets

    class FakePublisher:
        pass

    mail_service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    res = await (mail_service.search_emails(words="тест"))
    assert res == expected_snippets


@pytest.mark.asyncio
async def test_mail_service_create_draft():
    draft_id = str(uuid.uuid4())
    test_thread = uuid.uuid4()

    class FakeRepo:
        async def save_draft(self, thread_id, recipient, subject, text_content):
            assert thread_id == test_thread
            assert recipient == "client@corp.ru"
            return draft_id

    class FakePublisher:
        pass

    mail_service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    res = await (
        mail_service.create_draft(
            thread_id=test_thread,
            recipient="client@corp.ru",
            subject="Re: Test",
            text_content="Содержимое ответа",
        )
    )
    assert res == draft_id


@pytest.mark.asyncio
async def test_mail_service_list_drafts():
    expected_drafts = [{"id": str(uuid.uuid4()), "subject": "Draft 1"}]

    class FakeRepo:
        async def list_drafts(self, limit):
            assert limit == 10
            return expected_drafts

    class FakePublisher:
        pass

    mail_service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    res = await (mail_service.list_drafts(limit=10))
    assert res == expected_drafts


@pytest.mark.asyncio
async def test_mail_service_get_thread_found():
    test_id = uuid.uuid4()
    expected = ThreadDetails(
        thread_id=str(test_id),
        subject="Тема",
        client_email="c@ex.ru",
        status="active",
        messages=[],
    )

    class FakeRepo:
        async def get_thread(self, thread_id):
            assert thread_id == test_id
            return expected

    class FakePublisher:
        pass

    service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    result = await (service.get_thread(test_id))
    assert result == expected


@pytest.mark.asyncio
async def test_mail_service_get_thread_not_found():
    test_id = uuid.uuid4()

    class FakeRepo:
        async def get_thread(self, thread_id):
            return None

    class FakePublisher:
        pass

    service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    with pytest.raises(ThreadNotFoundError):
        await (service.get_thread(test_id))


@pytest.mark.asyncio
async def test_mail_service_close_thread_success():
    test_id = uuid.uuid4()
    publisher_called = []

    class FakeRepo:
        async def close_thread(self, thread_id):
            assert thread_id == test_id
            return True

    class FakePublisher:
        async def publish_thread_closed(self, thread_id):
            publisher_called.append(thread_id)
            return None

    service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    result = await (service.close_thread(test_id))

    assert result.status == "closed"
    assert result.thread_id == str(test_id)
    assert result.queued_for_rag is True
    assert publisher_called == [test_id]


@pytest.mark.asyncio
async def test_mail_service_close_thread_not_found():
    test_id = uuid.uuid4()

    class FakeRepo:
        async def close_thread(self, thread_id):
            return False

    class FakePublisher:
        async def publish_thread_closed(self, thread_id):
            return None

    service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    with pytest.raises(ThreadNotFoundError):
        await (service.close_thread(test_id))


@pytest.mark.asyncio
async def test_mail_service_close_thread_queue_failure_resilient():
    test_id = uuid.uuid4()

    class FakeRepo:
        async def close_thread(self, thread_id):
            return True

    class FakePublisher:
        async def publish_thread_closed(self, thread_id):
            raise RuntimeError("Broker unavailable")

    service = MailService(mail_repo=FakeRepo(), rag_producer=FakePublisher())
    result = await (service.close_thread(test_id))

    assert result.status == "closed"
    assert result.thread_id == str(test_id)
    assert result.queued_for_rag is False
