import pytest

from agent.main_agent import RouteTarget, route_request


@pytest.mark.parametrize(
    ("text", "target"),
    [
        ("比较三个供应商的报价并给建议", RouteTarget.ANALYST),
        ("帮我创建采购订单", RouteTarget.ORDER),
        ("查询订单 PO-1 的状态", RouteTarget.ORDER),
        ("你好", RouteTarget.MAIN),
    ],
)
def test_deterministic_procurement_routing(text: str, target: RouteTarget) -> None:
    decision = route_request(text)

    assert decision.target is target
    assert decision.requires_write_confirmation is False


def test_mixed_analysis_and_order_request_requires_separate_confirmation() -> None:
    decision = route_request("先比较报价，然后按最优结果直接下单")

    assert decision.target is RouteTarget.ANALYST
    assert decision.requires_write_confirmation is True
