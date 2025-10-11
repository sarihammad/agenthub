"""End-to-end integration tests."""

import pytest


def test_e2e_create_session_and_list_tools(app, client_headers) -> None:  # type: ignore
    """Test creating a session and listing tools."""
    # Create session
    response = app.post("/v1/sessions", json={}, headers=client_headers)
    assert response.status_code == 200
    data = response.json()
    assert "session_id" in data

    # List tools
    response = app.get("/v1/tools", headers=client_headers)
    assert response.status_code == 200
    tools = response.json()
    assert len(tools) == 4  # 4 built-in tools
    tool_names = [t["name"] for t in tools]
    assert "search" in tool_names
    assert "http_fetch" in tool_names
    assert "retrieve_doc" in tool_names
    assert "ads_metrics_mock" in tool_names


def test_e2e_session_plan_execute(app, client_headers) -> None:  # type: ignore
    """Test complete flow: session -> plan -> execute."""
    # Create session
    response = app.post("/v1/sessions", json={}, headers=client_headers)
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # Create a simple plan manually (skip LLM planning for test)
    from agenthub.models.schemas import Plan, ToolCall

    plan = Plan(
        steps=[
            ToolCall(
                tool="search",
                args={"query": "test"},
                step_id="step_0",
            )
        ],
        rationale="Test plan",
    )

    # Execute plan
    response = app.post(
        "/v1/execute",
        json={
            "session_id": session_id,
            "plan": plan.model_dump(),
        },
        headers=client_headers,
    )
    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert len(result["steps"]) == 1


def test_e2e_idempotency(app, client_headers) -> None:  # type: ignore
    """Test idempotency key handling."""
    # Create session
    response = app.post("/v1/sessions", json={}, headers=client_headers)
    session_id = response.json()["session_id"]

    from agenthub.models.schemas import Plan, ToolCall

    plan = Plan(
        steps=[
            ToolCall(
                tool="search",
                args={"query": "idempotency test"},
            )
        ],
        rationale="Idempotency test",
    )

    idempotency_key = "test-idempotency-key-123"

    # First request
    response1 = app.post(
        "/v1/execute",
        json={
            "session_id": session_id,
            "plan": plan.model_dump(),
        },
        headers={**client_headers, "Idempotency-Key": idempotency_key},
    )
    assert response1.status_code == 200

    # Second request with same key (should return cached result)
    response2 = app.post(
        "/v1/execute",
        json={
            "session_id": session_id,
            "plan": plan.model_dump(),
        },
        headers={**client_headers, "Idempotency-Key": idempotency_key},
    )
    assert response2.status_code == 200

    # Results should be the same
    assert response1.json() == response2.json()


def test_health_and_readiness(app) -> None:  # type: ignore
    """Test health and readiness endpoints."""
    # Health
    response = app.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

    # Readiness
    response = app.get("/readyz")
    assert response.status_code in [200, 503]  # May fail if Redis not available

