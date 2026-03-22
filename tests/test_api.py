"""Tests for the FastAPI API endpoints."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, settings
from app.models import AzCliResponse


@pytest.mark.asyncio
class TestExecuteEndpoint:
    """Tests for POST /execute."""

    async def test_valid_request_uses_default_subscription_when_omitted(self):
        mock_response = AzCliResponse(
            success=True,
            exit_code=0,
            result=["rg1"],
            stderr="",
            timings=None,
        )
        with patch(
            "app.main.subprocess_executor.execute",
            new_callable=AsyncMock,
            return_value=mock_response,
        ) as mock_execute:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/execute",
                    json={"command": "az group list"},
                )

        assert resp.status_code == 200
        mock_execute.assert_awaited_once_with(
            ["group", "list"],
            "12345678-1234-1234-1234-123456789abc",
        )

    async def test_valid_request(self):
        mock_response = AzCliResponse(
            success=True, exit_code=0, result=["rg1"], stderr="", timings=None
        )
        with patch(
            "app.main.subprocess_executor.execute",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/execute",
                    json={
                        "command": "az group list",
                        "subscription_id": "12345678-1234-1234-1234-123456789abc",
                    },
                )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        data = resp.json()
        assert data["success"] is True
        assert data["result"] == ["rg1"]
        assert data["timings"] is None

    async def test_blocked_command_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/execute",
                json={
                    "command": "az login",
                    "subscription_id": "12345678-1234-1234-1234-123456789abc",
                },
            )
        assert resp.status_code == 400
        assert "not allowed" in resp.json()["detail"]

    async def test_invalid_subscription_id_returns_422(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/execute",
                json={
                    "command": "az group list",
                    "subscription_id": "not-a-uuid",
                },
            )
        assert resp.status_code == 422

    async def test_missing_subscription_and_no_default_returns_400(self):
        original_default = settings.default_subscription_id
        settings.default_subscription_id = None
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/execute",
                    json={"command": "az group list"},
                )
        finally:
            settings.default_subscription_id = original_default

        assert resp.status_code == 400
        assert "DEFAULT_SUBSCRIPTION_ID" in resp.json()["detail"]

    async def test_empty_command_returns_400(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/execute",
                json={
                    "command": "",
                    "subscription_id": "12345678-1234-1234-1234-123456789abc",
                },
            )
        assert resp.status_code == 400

    async def test_runtime_error_returns_500(self):
        with patch(
            "app.main.subprocess_executor.execute",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Missing credentials"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/execute",
                    json={
                        "command": "az group list",
                        "subscription_id": "12345678-1234-1234-1234-123456789abc",
                    },
                )
        assert resp.status_code == 500
        assert "Missing credentials" in resp.json()["detail"]

    async def test_failed_command_returns_null_result(self):
        mock_response = AzCliResponse(
            success=False,
            exit_code=2,
            result=None,
            stderr="Resource not found",
            timings=None,
        )
        with patch(
            "app.main.subprocess_executor.execute",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/execute",
                    json={
                        "command": "az group show --name missing",
                        "subscription_id": "12345678-1234-1234-1234-123456789abc",
                    },
                )

        assert resp.status_code == 200
        assert resp.json()["result"] is None
        assert resp.json()["stderr"] == "Resource not found"

    async def test_unhandled_exception_returns_json(self):
        with patch(
            "app.main.parse_command",
            side_effect=ValueError("boom"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app, raise_app_exceptions=False),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/execute",
                    json={
                        "command": "az group list",
                        "subscription_id": "12345678-1234-1234-1234-123456789abc",
                    },
                )

        assert resp.status_code == 500
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"detail": "Internal server error"}

@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for GET /health."""

    async def test_health_check(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        assert resp.json() == {"status": "healthy"}
