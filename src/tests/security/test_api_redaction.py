from procurepilot.observability import audit_fields, redact_sensitive


def test_logs_redact_secrets_dsns_prompts_and_absolute_paths() -> None:
    raw = (
        "api_key=top-secret mysql://u:p@db/prod "
        "D:\\private\\report.md /home/user/report.md"
    )
    redacted = redact_sensitive(raw)

    assert "top-secret" not in redacted
    assert "mysql://" not in redacted
    assert "D:\\private" not in redacted
    assert "/home/user" not in redacted


def test_audit_fields_hash_identity_and_keep_trace_dimensions() -> None:
    fields = audit_fields(
        trace_id="trace-1",
        thread_id="thread-1",
        user_id="real-user",
        agent_name="procurement-analyst",
        tool_name="quotation_query",
    )

    assert fields["user_ref"] != "real-user"
    assert fields["trace_id"] == "trace-1"
    assert fields["tool_name"] == "quotation_query"
