"""AI assistant: no-key honesty, tool RBAC, loop behavior, prompt secrecy."""
import app as app_module
from lendsure import assistant as asst


def _conn():
    return app_module.db()


def test_status_reports_unconfigured(client, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    r = client.get("/api/ls/assistant/status")
    assert r.status_code == 200
    d = r.json()
    assert d["configured"] is False
    assert d["provider"] in ("openai", "groq", "cerebras", "gemini", "deepseek")
    assert "key" not in str(d).lower().replace("turkey", "")


def test_chat_without_key_is_503_not_mocked(client, lender, guest, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    for c in (lender, guest):
        r = c.post("/api/ls/assistant/chat", json={"message": "hello", "history": []})
        assert r.status_code == 503, r.text


def test_chat_validation(client, lender):
    r = lender.post("/api/ls/assistant/chat", json={"message": "", "history": []})
    assert r.status_code in (400, 422)
    r = lender.post("/api/ls/assistant/chat",
                    json={"message": "x" * 1001, "history": []})
    assert r.status_code in (400, 422)


def test_guest_tool_gating(client, guest):
    conn = _conn()
    try:
        sess = {"phone": "guest", "role": "guest", "display_name": "G"}
        # allowed: search (scrubbed), analysis reads, model numbers
        out = asst._run_tool(conn, "search_borrowers", {"q": "B90001"}, "guest", sess, None)
        assert out["borrowers"] and out["borrowers"][0]["borrower_id"] == "B90001"
        assert "phone" not in out["borrowers"][0]
        det = asst._run_tool(conn, "borrower_detail", {"borrower_id": "B90001"},
                             "guest", sess, None)
        assert "phone" not in det and det["name"] == "Test Borrower"
        # forbidden: everything money/governance
        import pytest
        from fastapi import HTTPException
        for name, args in [("list_loans", {}), ("loan_detail", {"loan_id": 1}),
                           ("recovery_cases", {}), ("case_transfers", {}),
                           ("officers", {}), ("grievances", {}),
                           ("system_policy", {})]:
            with pytest.raises(HTTPException) as e:
                asst._run_tool(conn, name, args, "guest", sess, None)
            assert e.value.status_code == 403, name
    finally:
        conn.close()


def test_lender_tools_open(client, lender):
    conn = _conn()
    try:
        sess = {"phone": "t@example.com", "role": "lender", "display_name": "T"}
        assert asst._run_tool(conn, "list_loans", {}, "lender", sess, None)["loans"] == []
        assert asst._run_tool(conn, "officers", {}, "lender", sess, None)["officers"] == []
        assert "borrowers" in asst._run_tool(conn, "portfolio_stats", {}, "lender", sess, None)
        pol = asst._run_tool(conn, "system_policy", {}, "lender", sess, None)
        assert isinstance(pol.get("policy"), dict)
    finally:
        conn.close()


def test_officer_city_default(client, lender):
    conn = _conn()
    try:
        conn.execute("INSERT INTO ls_officers (name, phone, city, active, created_at)"
                     " VALUES (?,?,?,?,?)",
                     ("T Officer", "t@example.com", "Mumbai", 1, "2026-01-01T00:00:00"))
        conn.commit()
        sess = {"phone": "t@example.com", "role": "lender", "display_name": "T"}
        assert asst._officer_city(conn, sess) == "Mumbai"
        out = asst._run_tool(conn, "search_borrowers", {}, "lender", sess, "Mumbai")
        assert out["city_scope"] == "Mumbai"
        assert all(b["city"] == "Mumbai" for b in out["borrowers"])
    finally:
        conn.close()


def test_unknown_tool_rejected(client, lender):
    conn = _conn()
    try:
        from fastapi import HTTPException
        import pytest
        with pytest.raises(HTTPException) as e:
            asst._run_tool(conn, "drop_database", {}, "lender", {}, None)
        assert e.value.status_code == 400
    finally:
        conn.close()


def _stub_answer(content="Final answer here.", calls=()):
    state = {"n": 0}

    def transport(messages, tools):
        state["n"] += 1
        if state["n"] <= len(calls):
            name, args = calls[state["n"] - 1]
            return {"role": "assistant", "content": None,
                    "tool_calls": [{"id": f"call-{state['n']}",
                                    "function": {"name": name, "arguments": "{}"}}]}
        return {"role": "assistant", "content": content}

    transport.state = state
    return transport


def test_loop_calls_tool_then_answers(client, lender, monkeypatch):
    monkeypatch.setattr(asst, "_TRANSPORT",
                        _stub_answer("B90001 carries High risk.", [("portfolio_stats", {})]))
    sess = {"phone": "t@example.com", "role": "lender", "display_name": "T"}
    out = asst.run_chat("summarize portfolio risk", [], sess, "lender")
    assert out["reply"] == "B90001 carries High risk."
    assert out["tools_used"] == ["portfolio_stats"]


def test_loop_cannot_spin_forever(client, lender, monkeypatch):
    calls = [("portfolio_stats", {})] * 20
    transport = _stub_answer("never reached", calls)
    monkeypatch.setattr(asst, "_TRANSPORT", transport)
    sess = {"phone": "t@example.com", "role": "lender", "display_name": "T"}
    out = asst.run_chat("go", [], sess, "lender")
    assert transport.state["n"] <= asst.MAX_ITERS
    assert "narrower question" in out["reply"]


def test_prompt_never_contains_key(client, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "gsk_super_secret_123")
    prompt = asst._system_prompt("lender", "T", "Mumbai",
                                 {"borrowers": 1, "open_cases": 0, "city": "Mumbai"}, ["a"])
    assert "gsk_super_secret_123" not in prompt
    assert "Mumbai" in prompt and "lender" in prompt


def test_rate_limiter_trips(client):
    assert asst._rate_limited("probe-x", limit=2, window=60) is False
    assert asst._rate_limited("probe-x", limit=2, window=60) is False
    assert asst._rate_limited("probe-x", limit=2, window=60) is True


def test_provider_failure_is_safe_and_keyless(client, lender, monkeypatch):
    import urllib.request
    monkeypatch.setenv("LLM_API_KEY", "gsk_test_value_999")
    def boom(*a, **k):
        raise urllib.error.URLError("dns down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    r = lender.post("/api/ls/assistant/chat", json={"message": "hi", "history": []})
    assert r.status_code == 502
    assert "gsk_test_value_999" not in r.text


def test_provider_failure_is_safe_and_keyless(client, lender, monkeypatch):
    import urllib.request
    monkeypatch.setenv("LLM_API_KEY", "gsk_test_value_999")
    def boom(*a, **k):
        raise urllib.error.URLError("dns down")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    r = lender.post("/api/ls/assistant/chat", json={"message": "hi", "history": []})
    assert r.status_code == 502
    assert "gsk_test_value_999" not in r.text
