"""Test streaming."""

import pytest


def test_streaming_endpoint_exists(app, client_headers) -> None:  # type: ignore
    """Test that streaming endpoint exists."""
    # Create a session first
    response = app.post("/v1/sessions", json={}, headers=client_headers)
    assert response.status_code == 200
    session_id = response.json()["session_id"]

    # Test streaming endpoint
    response = app.get(
        f"/v1/stream?session_id={session_id}",
        headers=client_headers,
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")

