import uuid
import pytest
from pydantic import ValidationError
from app.agent.tools.schemas import TOOLS_DEFINITIONS, SearchEmailsArgs, ReadThreadArgs, CreateDraftArgs

def test_tools_definitions_match_tz():
    tool_names = [t["function"]["name"] for t in TOOLS_DEFINITIONS]
    assert "search_emails" in tool_names
    assert "read_thread" in tool_names
    assert "create_draft" in tool_names

    # Проверка обязательных параметров search_emails
    search_tool = next(t for t in TOOLS_DEFINITIONS if t["function"]["name"] == "search_emails")
    assert "words" in search_tool["function"]["parameters"]["properties"]
    assert "sender" in search_tool["function"]["parameters"]["properties"]
    assert "start_date" in search_tool["function"]["parameters"]["properties"]
    assert "end_date" in search_tool["function"]["parameters"]["properties"]

    # Проверка обязательных параметров read_thread
    read_tool = next(t for t in TOOLS_DEFINITIONS if t["function"]["name"] == "read_thread")
    assert "thread_id" in read_tool["function"]["parameters"]["properties"]

    # Проверка обязательных параметров create_draft
    draft_tool = next(t for t in TOOLS_DEFINITIONS if t["function"]["name"] == "create_draft")
    props = draft_tool["function"]["parameters"]["properties"]
    assert "thread_id" in props
    assert "recipient" in props
    assert "subject" in props
    assert "text" in props

def test_tools_pydantic_args_validation():
    valid_uuid_str = "da9a4c99-6016-4b6c-84c5-7b82fc7109fc"
    
    # ReadThreadArgs
    args = ReadThreadArgs.model_validate({"thread_id": valid_uuid_str})
    assert isinstance(args.thread_id, uuid.UUID)
    assert str(args.thread_id) == valid_uuid_str

    with pytest.raises(ValidationError):
        ReadThreadArgs.model_validate({"thread_id": "not-a-uuid"})

    # CreateDraftArgs
    draft_args = CreateDraftArgs.model_validate({
        "thread_id": valid_uuid_str,
        "recipient": "test@client.ru",
        "subject": "Re: Test",
        "text": "Hello world"
    })
    assert isinstance(draft_args.thread_id, uuid.UUID)

    with pytest.raises(ValidationError):
        CreateDraftArgs.model_validate({
            "thread_id": "invalid-uuid",
            "recipient": "test@client.ru",
            "subject": "Re: Test",
            "text": "Hello world"
        })


