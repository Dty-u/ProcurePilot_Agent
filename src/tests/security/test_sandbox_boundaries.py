import ipaddress

import pytest

from agent.sandbox.protocol import SandboxPolicyDenied
from agent.sandbox.security import (
    OutputLimits,
    URLPolicy,
    limit_output,
    normalize_sandbox_path,
)


@pytest.mark.parametrize(
    "path",
    [
        "relative.txt",
        "/workspace/../secret",
        "/etc/passwd",
        "C:/Windows/System32",
        r"\\server\share\secret",
        "/workspace/bad\x00name",
    ],
)
def test_path_policy_rejects_escape_and_non_posix_paths(path: str) -> None:
    with pytest.raises(SandboxPolicyDenied):
        normalize_sandbox_path(path)


def test_path_policy_accepts_canonical_allowed_path_and_rejects_symlink_escape() -> None:
    assert normalize_sandbox_path("/workspace/reports/result.md") == (
        "/workspace/reports/result.md"
    )
    with pytest.raises(SandboxPolicyDenied, match="symbolic link"):
        normalize_sandbox_path(
            "/workspace/link/secret",
            resolved_path="/etc/secret",
        )


@pytest.mark.asyncio
async def test_url_policy_requires_https_allowlist_and_public_dns() -> None:
    answers = {"api.example.com": (ipaddress.ip_address("93.184.216.34"),)}

    async def resolve(host: str):
        return answers[host]

    policy = URLPolicy(frozenset({"api.example.com"}), resolver=resolve)
    validated = await policy.validate("https://api.example.com/v1/quotes")

    assert validated.host == "api.example.com"
    with pytest.raises(SandboxPolicyDenied):
        await policy.validate("http://api.example.com/v1/quotes")
    with pytest.raises(SandboxPolicyDenied):
        await policy.validate("https://127.0.0.1/admin")


@pytest.mark.asyncio
async def test_url_policy_rejects_private_resolution_and_dns_rebinding() -> None:
    current = [ipaddress.ip_address("10.0.0.8")]

    async def resolve(_host: str):
        return tuple(current)

    policy = URLPolicy(frozenset({"api.example.com"}), resolver=resolve)
    with pytest.raises(SandboxPolicyDenied, match="public"):
        await policy.validate("https://api.example.com/data")

    current[:] = [ipaddress.ip_address("93.184.216.34")]
    validated = await policy.validate("https://api.example.com/data")
    current[:] = [ipaddress.ip_address("93.184.216.35")]
    with pytest.raises(SandboxPolicyDenied, match="changed"):
        await policy.revalidate(validated)


@pytest.mark.asyncio
async def test_large_output_is_spilled_and_only_summary_is_returned() -> None:
    writes: dict[str, bytes] = {}

    async def write(path: str, content: bytes) -> None:
        writes[path] = content

    result = await limit_output(
        "secret-output-" * 100,
        limits=OutputLimits(max_bytes=80, max_tokens=20),
        artifact_path="/artifacts/tool-output.txt",
        write=write,
        token_counter=lambda text: len(text.split("-")),
    )

    assert result.truncated is True
    assert result.artifact_path == "/artifacts/tool-output.txt"
    assert len(result.text.encode("utf-8")) <= 80
    assert writes["/artifacts/tool-output.txt"].startswith(b"secret-output")
