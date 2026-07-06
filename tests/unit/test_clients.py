"""Unit tests for raw httpx-based NSX-T and AVI clients."""

import json

import httpx
import pytest

from app.clients.avi_client import AVIClient
from app.clients.nsxt_client import NSXTClient
from app.core.inventory import AVIEndpoint, NSXTEndpoint


@pytest.mark.asyncio
async def test_nsxt_client_uses_policy_api_via_httpx(monkeypatch):
    """NSX-T operations should use the Policy API over raw httpx."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["auth_header"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "id": "seg-web",
                "display_name": "seg-web",
                "path": "/infra/segments/seg-web",
                "subnets": [{"gateway_address": "10.0.10.1/24"}],
                "vlan_ids": [110],
            },
        )

    transport = httpx.MockTransport(handler)

    class RecordingAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            captured["base_url"] = str(kwargs["base_url"])
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        "app.clients.nsxt_client.httpx.AsyncClient", RecordingAsyncClient
    )

    client = NSXTClient(
        NSXTEndpoint(
            manager_url="https://nsxt.example.com",
            username="api-user",
            password="api-secret",
            verify_ssl=False,
        )
    )

    result = await client.create_segment(
        name="seg-web",
        tier1_gateway="/infra/tier-1s/T1",
        subnets=["10.0.10.1/24"],
        vlan=110,
    )
    await client.disconnect()

    assert captured["base_url"] == "https://nsxt.example.com"
    assert captured["path"] == "/policy/api/v1/infra/segments/seg-web"
    assert str(captured["auth_header"]).startswith("Basic ")
    assert captured["body"] == {
        "display_name": "seg-web",
        "tier1_path": "/infra/tier-1s/T1",
        "subnets": [{"gateway_address": "10.0.10.1/24"}],
        "tags": [],
        "vlan_ids": [110],
    }
    assert result["segment_id"] == "seg-web"
    assert result["path"] == "/infra/segments/seg-web"


@pytest.mark.asyncio
async def test_avi_client_uses_controller_api_via_httpx(monkeypatch):
    """AVI operations should use the controller REST API over raw httpx."""
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["tenant"] = request.headers.get("x-avi-tenant")
        captured["version"] = request.headers.get("x-avi-version")
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "uuid": "vs-123",
                "name": "vs-web",
                "pool_ref": "/api/pool/pool-1",
                "services": [{"port": 443}],
                "runtime": {"oper_status": {"state": "OPER_UP"}},
                "url": "/api/virtualservice/vs-123",
            },
        )

    transport = httpx.MockTransport(handler)

    class RecordingAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            captured["base_url"] = str(kwargs["base_url"])
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(
        "app.clients.avi_client.httpx.AsyncClient", RecordingAsyncClient
    )

    client = AVIClient(
        AVIEndpoint(
            controller_url="https://avi.example.com",
            username="api-user",
            password="api-secret",
            tenant="engineering",
            api_version="30.1.1",
            verify_ssl=False,
        )
    )

    result = await client.create_virtual_service(
        name="vs-web",
        vip="10.0.20.10",
        pool_ref="/api/pool/pool-1",
        services=[{"port": 443}],
    )
    await client.disconnect()

    assert captured["base_url"] == "https://avi.example.com/api/"
    assert captured["path"] == "/api/virtualservice"
    assert captured["tenant"] == "engineering"
    assert captured["version"] == "30.1.1"
    assert captured["body"] == {
        "name": "vs-web",
        "vip": [{"ip_address": {"addr": "10.0.20.10", "type": "V4"}}],
        "pool_ref": "/api/pool/pool-1",
        "services": [{"port": 443}],
    }
    assert result["uuid"] == "vs-123"
    assert result["state"] == "OPER_UP"
