"""FastAPI 入参模型，不包含可伪造的身份字段。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from mcp_server.context import SAFE_IDENTIFIER


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChatRequest(APIModel):
    message: StrictStr = Field(min_length=1, max_length=10_000)
    thread_id: StrictStr | None = Field(default=None, pattern=SAFE_IDENTIFIER)


class SupplementPayload(APIModel):
    kind: Literal["supplement"]
    supplement: StrictStr = Field(min_length=2, max_length=10_000)


class DecisionPayload(APIModel):
    kind: Literal["decision"]
    decision: Literal["approve", "reject"]
    message: StrictStr | None = Field(default=None, min_length=1, max_length=500)


class ResumeRequest(APIModel):
    interrupt_id: StrictStr = Field(pattern=SAFE_IDENTIFIER)
    resume: Annotated[SupplementPayload | DecisionPayload, Field(discriminator="kind")]


class ThreadSummary(APIModel):
    thread_id: str
    last_message_at: str
    message_count: int
