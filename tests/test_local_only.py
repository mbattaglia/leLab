# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Only LeLab's own pages on this machine may call the API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from lelab.local_only import allowed_origins, host_is_loopback

EVIL = "https://evil.example"


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000", "localhost"])
def test_loopback_hosts_are_accepted(host: str) -> None:
    assert host_is_loopback(host)


@pytest.mark.parametrize(
    "host", ["attacker.example:8000", "localhost.attacker.example", "192.168.1.5:8000", ""]
)
def test_other_hosts_are_rejected(host: str) -> None:
    assert not host_is_loopback(host)


def test_extra_origins_come_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LELAB_ALLOWED_ORIGINS", "https://lerobot-lelab.hf.space/, ")
    assert "https://lerobot-lelab.hf.space" in allowed_origins()
    assert EVIL not in allowed_origins()


def test_same_origin_request_passes(client: TestClient) -> None:
    response = client.get(
        "/health", headers={"Origin": "http://localhost:8000", "Sec-Fetch-Site": "same-origin"}
    )
    assert response.status_code == 200


def test_dev_frontend_origin_passes(client: TestClient) -> None:
    response = client.get("/health", headers={"Origin": "http://localhost:8080"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8080"


def test_foreign_origin_is_blocked(client: TestClient) -> None:
    response = client.post("/robots/evil-test?create=true", json={}, headers={"Origin": EVIL})
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_foreign_preflight_is_blocked(client: TestClient) -> None:
    response = client.options(
        "/robots/evil-test",
        headers={"Origin": EVIL, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 403


def test_cross_site_fetch_without_origin_is_blocked(client: TestClient) -> None:
    response = client.post("/system/update", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert "cross-site" in response.json()["detail"]


def test_rebound_host_is_blocked(client: TestClient) -> None:
    response = client.get("/health", headers={"Host": "attacker.example:8000"})
    assert response.status_code == 403


def test_websocket_from_foreign_origin_is_refused(client: TestClient) -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws/joint-data", headers={"Origin": EVIL}),
    ):
        pass


def test_local_script_without_browser_headers_passes(client: TestClient) -> None:
    assert client.get("/health").status_code == 200


def test_self_update_is_disabled(client: TestClient) -> None:
    response = client.post("/system/update")
    assert response.status_code == 403
    assert response.json()["success"] is False


def test_update_check_reports_nothing_without_network(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from lelab import update

    def fail(*_args, **_kwargs):
        raise AssertionError("update check must not contact GitHub")

    monkeypatch.setattr(update, "_github_json", fail)
    response = client.get("/system/update-check")
    assert response.status_code == 200
    assert response.json()["update_available"] is False


@pytest.mark.parametrize(
    "path",
    ["/system/training-extra/install", "/system/wandb-extra/install", "/system/policy-extra/smolvla/install"],
)
def test_in_app_installs_are_disabled(client: TestClient, path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    from lelab.utils import system

    def fail(*_args, **_kwargs):
        raise AssertionError("installs must not spawn a process")

    monkeypatch.setattr(system.subprocess, "Popen", fail)
    response = client.post(path)
    assert response.status_code == 403
    body = response.json()
    assert body["started"] is False
    assert "install" in body["message"]


def test_policy_extra_command_keeps_the_pinned_lerobot(monkeypatch: pytest.MonkeyPatch) -> None:
    from lelab.utils import system

    pinned = "lerobot[feetech,dataset,pynput-dep] @ git+https://github.com/mbattaglia/lerobot.git@abc123"
    monkeypatch.setattr(system.importlib.metadata, "requires", lambda _name: ["fastapi>=0.115", pinned])
    assert (
        system.pinned_lerobot_target("lerobot[smolvla]")
        == "lerobot[smolvla] @ git+https://github.com/mbattaglia/lerobot.git@abc123"
    )
    assert system.pinned_lerobot_target("wandb") == "wandb"


def test_core_policy_install_stays_a_noop(client: TestClient) -> None:
    response = client.post("/system/policy-extra/act/install")
    assert response.status_code == 200
    assert response.json()["started"] is False


def test_hub_is_offline_by_default() -> None:
    import os
    import subprocess
    import sys

    env = {k: v for k, v in os.environ.items() if k != "HF_HUB_OFFLINE"}
    code = "import lelab, huggingface_hub.constants as c; print(c.is_offline_mode())"
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "True"


def test_uploads_default_to_private() -> None:
    from lelab.record import RecordingRequest, UploadRequest

    assert UploadRequest(dataset_repo_id="u/d").private is True
    fields = RecordingRequest.model_fields
    assert fields["private"].default is True
    assert fields["push_to_hub"].default is False
