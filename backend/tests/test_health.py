"""Smoke tests of the API skeleton."""

import httpx

from grod.main import API_PREFIX, VERSION, create_app


async def test_health_reports_instance_and_version() -> None:
    transport = httpx.ASGITransport(create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://api") as client:
        response = await client.get(f"{API_PREFIX}/health")

    assert response.status_code == httpx.codes.OK
    assert response.json() == {"status": "ok", "instance": "Gród", "version": VERSION}
