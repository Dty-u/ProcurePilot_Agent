"""不记录 Prompt 和敏感原文的结构化观测边界。"""

from __future__ import annotations

import hashlib
import re

_WINDOWS_PATH = re.compile(r"(?i)\b[A-Z]:\\[^\s,;，；]+")
_UNIX_PATH = re.compile(r"(?<![\w:])/(?:home|root|Users|tmp)/[^\s,;，；]+")
_SECRET = re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*[^\s,;，；]+")
_DSN = re.compile(r"(?i)\b(?:mysql(?:\+\w+)?|postgres(?:ql)?(?:\+\w+)?|redis)://[^\s,;，；]+")


def redact_sensitive(value: str) -> str:
    redacted = _SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)
    redacted = _DSN.sub("[REDACTED_DSN]", redacted)
    redacted = _WINDOWS_PATH.sub("[REDACTED_PATH]", redacted)
    return _UNIX_PATH.sub("[REDACTED_PATH]", redacted)


def audit_fields(
    *,
    trace_id: str,
    thread_id: str,
    user_id: str,
    agent_name: str,
    tool_name: str | None = None,
) -> dict[str, str | None]:
    return {
        "trace_id": trace_id,
        "thread_id": thread_id,
        "user_ref": hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:16],
        "agent_name": agent_name,
        "tool_name": tool_name,
    }
