import pytest
from pydantic import ValidationError

from api_view.auth import HeaderAuthenticator
from api_view.schemas import ChatRequest, ResumeRequest
from procurepilot.config import Settings


def test_chat_schema_never_accepts_identity_fields() -> None:
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"message": "hi", "user_id": "attacker"})


def test_resume_requires_exactly_one_typed_payload() -> None:
    approved = ResumeRequest.model_validate(
        {"interrupt_id": "interrupt-1", "resume": {"kind": "decision", "decision": "approve"}}
    )
    assert approved.resume.kind == "decision"
    with pytest.raises(ValidationError):
        ResumeRequest.model_validate(
            {"interrupt_id": "interrupt-1", "resume": {"kind": "decision", "supplement": "x"}}
        )


def test_header_auth_is_limited_to_test_and_development() -> None:
    test_settings = Settings(
        app_env="test", mysql_dsn=None, agent_checkpoint_mysql_dsn=None
    )
    context = HeaderAuthenticator(test_settings).authenticate(
        {
            "x-user-id": "user-1",
            "x-user-name": "tester",
            "x-roles": "buyer,procurement_reader",
        },
        thread_id="thread-1",
        trace_id="trace-1",
    )
    assert context.user_id == "user-1"
    assert context.roles == {"buyer", "procurement_reader"}
    with pytest.raises(RuntimeError):
        HeaderAuthenticator(
            Settings(
                app_env="production", mysql_dsn=None, agent_checkpoint_mysql_dsn=None
            )
        )
