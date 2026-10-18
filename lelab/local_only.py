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
"""Keep the LeLab API reachable only from LeLab's own pages on this machine.

The API has no login and controls hardware, so a browser must not let other
websites call it. Three checks run on every HTTP request and WebSocket handshake:

- ``Host`` must name a loopback address. This blocks DNS rebinding, where an
  attacker's domain is pointed at 127.0.0.1.
- ``Origin``, when a browser sends one, must be a LeLab origin.
- ``Sec-Fetch-Site: cross-site`` is rejected. Browsers send it on requests that
  another site starts.

Requests without browser headers (curl, scripts on this machine) still pass.
Extra origins can be allowed with ``LELAB_ALLOWED_ORIGINS`` (comma separated).
"""

import json
import logging
import os

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]"})
LELAB_PORTS = (8000, 8080)  # backend + Vite dev server, see scripts/lelab.py


def allowed_origins() -> frozenset[str]:
    origins = {f"http://{host}:{port}" for host in LOOPBACK_HOSTS for port in LELAB_PORTS}
    extra = os.environ.get("LELAB_ALLOWED_ORIGINS", "")
    origins.update(o.strip().rstrip("/") for o in extra.split(",") if o.strip())
    return frozenset(origins)


def host_is_loopback(host_header: str) -> bool:
    host = host_header.strip().lower()
    host = host.split("]", 1)[0] + "]" if host.startswith("[") else host.split(":", 1)[0]
    return host in LOOPBACK_HOSTS


def rejection_reason(headers: dict[str, str], origins: frozenset[str]) -> str | None:
    if not host_is_loopback(headers.get("host", "")):
        return "host is not a loopback address"
    origin = headers.get("origin")
    if origin is not None and origin.rstrip("/") not in origins:
        return f"origin {origin!r} is not allowed"
    if headers.get("sec-fetch-site") == "cross-site":
        return "cross-site request"
    return None


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, origins: frozenset[str] | None = None) -> None:
        self.app = app
        self.origins = origins if origins is not None else allowed_origins()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        reason = rejection_reason(headers, self.origins)
        if reason is None:
            await self.app(scope, receive, send)
            return

        logger.warning("Blocked %s %s: %s", scope["type"], scope.get("path", ""), reason)
        if scope["type"] == "websocket":
            # Closing before accept makes the server answer the handshake with 403.
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps({"detail": f"Blocked: {reason}"}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
