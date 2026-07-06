"""Sanity tests for tests_mock/mock_nsx_server.py itself.

If this harness is broken, the contract tests in tests_mock/ would silently pass or
fail for the wrong reason — so it gets a small amount of direct coverage too.
"""

import pytest
import requests
from mock_nsx_server import MockNsxServer


@pytest.fixture
def server():
    srv = MockNsxServer()
    port = srv.start(port=0)
    base = f"http://127.0.0.1:{port}"
    yield srv, base
    srv.stop()


def test_patch_is_recorded_and_echoed_on_get(server):
    srv, base = server
    resp = requests.patch(f"{base}/policy/api/v1/infra/tier-1s/t1", json={"display_name": "T1"})
    assert resp.status_code == 200
    assert resp.json() == {"display_name": "T1"}

    resp = requests.get(f"{base}/policy/api/v1/infra/tier-1s/t1")
    assert resp.status_code == 200
    assert resp.json() == {"display_name": "T1"}

    last = srv.get_last_request()
    assert last["method"] == "GET"
    assert last["path"] == "/policy/api/v1/infra/tier-1s/t1"


def test_get_unknown_path_is_404(server):
    _srv, base = server
    resp = requests.get(f"{base}/policy/api/v1/infra/tier-1s/nope")
    assert resp.status_code == 404


def test_delete_removes_stored_object(server):
    srv, base = server
    requests.patch(f"{base}/policy/api/v1/infra/tier-1s/t1", json={"display_name": "T1"})
    resp = requests.delete(f"{base}/policy/api/v1/infra/tier-1s/t1")
    assert resp.status_code == 200
    resp = requests.get(f"{base}/policy/api/v1/infra/tier-1s/t1")
    assert resp.status_code == 404


def test_realized_state_status_is_canned_success(server):
    _srv, base = server
    resp = requests.get(
        f"{base}/policy/api/v1/infra/realized-state/status?intent_path=%2Finfra%2Ftier-1s%2Ft1"
    )
    assert resp.status_code == 200
    assert resp.json()["consolidated_status"]["consolidated_status"] == "SUCCESS"


def test_post_returns_202(server):
    _srv, base = server
    resp = requests.post(f"{base}/policy/api/v1/infra/tier-0s/t0/locale-services/default", json={})
    assert resp.status_code == 202


def test_reset_clears_requests_not_objects(server):
    srv, base = server
    requests.patch(f"{base}/policy/api/v1/infra/tier-1s/t1", json={"display_name": "T1"})
    srv.reset()
    assert srv.get_requests() == []
    resp = requests.get(f"{base}/policy/api/v1/infra/tier-1s/t1")
    assert resp.status_code == 200


def test_get_last_request_raises_when_nothing_recorded(server):
    srv, _base = server
    with pytest.raises(AssertionError, match="No requests recorded"):
        srv.get_last_request()
