"""受控环境的 Header 认证适配器。"""

from collections.abc import Mapping

from agent.context import ProcurementContext
from procurepilot.config import Settings

_ROLES: frozenset[str] = frozenset(
    {"procurement_reader", "order_reader", "buyer", "order_executor", "admin"}
)


class HeaderAuthenticator:
    """仅供本地开发和测试；生产环境必须替换为真实认证。"""

    def __init__(self, settings: Settings) -> None:
        if settings.app_env == "production":
            raise RuntimeError("production requires a real authentication provider")

    def authenticate(
        self,
        headers: Mapping[str, str],
        *,
        thread_id: str,
        trace_id: str,
    ) -> ProcurementContext:
        normalized = {key.casefold(): value for key, value in headers.items()}
        user_id = normalized.get("x-user-id", "")
        username = normalized.get("x-user-name", user_id)
        raw_roles = {item.strip() for item in normalized.get("x-roles", "").split(",") if item.strip()}
        if not user_id or not raw_roles or not raw_roles <= _ROLES:
            raise PermissionError("missing or invalid trusted test identity headers")
        return ProcurementContext(
            user_id=user_id,
            username=username,
            roles=frozenset(raw_roles),  # type: ignore[arg-type]
            thread_id=thread_id,
            trace_id=trace_id,
        )
