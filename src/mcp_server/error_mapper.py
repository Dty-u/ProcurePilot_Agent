"""将内部异常转换为安全的 MCP 错误契约。"""

import logging

from pydantic import ValidationError

from procurepilot.business.errors import (
    ApprovalRequiredError,
    ConflictError,
    DomainValidationError,
    EntityNotFoundError,
    InfrastructureError,
    PermissionDeniedError,
)

from .schemas import ToolEnvelope, ToolError, ToolErrorCode

logger = logging.getLogger(__name__)


def error_envelope(error: Exception, *, trace_id: str) -> ToolEnvelope[None]:
    """映射异常，且不暴露堆栈或依赖细节。"""

    code: ToolErrorCode
    retryable = False
    if isinstance(error, (DomainValidationError, ValidationError, ValueError)):
        code, message = "VALIDATION_ERROR", "Invalid input"
    elif isinstance(error, EntityNotFoundError):
        code, message = "NOT_FOUND", str(error) or "Resource not found"
    elif isinstance(error, ConflictError):
        code, message = "CONFLICT", str(error) or "Resource conflict"
    elif isinstance(error, (PermissionDeniedError, PermissionError)):
        code, message = "PERMISSION_DENIED", str(error) or "Permission denied"
    elif isinstance(error, ApprovalRequiredError):
        code, message = "APPROVAL_REQUIRED", str(error) or "Approval required"
    elif isinstance(error, TimeoutError):
        code, message, retryable = "DEPENDENCY_TIMEOUT", "Dependency timeout", True
    elif isinstance(error, InfrastructureError):
        code, message, retryable = "INTERNAL_ERROR", "Dependency unavailable", True
    else:
        code, message = "INTERNAL_ERROR", "Internal error"

    logger.error("MCP tool failed; trace_id=%s", trace_id)
    return ToolEnvelope[None](
        ok=False,
        data=None,
        error=ToolError(code=code, message=message, retryable=retryable),
        trace_id=trace_id,
    )
