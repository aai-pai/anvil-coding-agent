"""Minimal stdlib HTTP client for the Anvil ``/v1`` REST surface.

Deliberately urllib-based (no httpx/requests dependency) so the harness runs
anywhere the runtime does. Mirrors the endpoints in
``anvil_runtime/api/routes_runs.py``.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class AnvilClientError(RuntimeError):
    """An HTTP-level failure talking to the runtime, with the server detail."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AnvilClient:
    """Thin typed wrapper over the run-control endpoints."""

    def __init__(self, base_url: str, timeout_s: float = 600.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _request(self, method: str, path: str, body: dict | None = None,
                 timeout_s: float | None = None) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        )
        try:
            with urllib.request.urlopen(
                request, timeout=timeout_s or self.timeout_s
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AnvilClientError(
                f"{method} {path} -> HTTP {exc.code}: {detail}", status=exc.code
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AnvilClientError(f"{method} {path} failed: {exc}") from exc
        return json.loads(raw) if raw.strip() else {}

    def health(self, timeout_s: float = 5.0) -> dict:
        return self._request("GET", "/v1/health", timeout_s=timeout_s)

    def start_run(self, *, source_path: str, workspace: str, mode: str,
                  security_profile: str, defer: bool = True) -> dict:
        """``POST /v1/runs`` — file-based build (#17) into an isolated workspace."""
        return self._request(
            "POST", f"/v1/runs?defer={'true' if defer else 'false'}",
            body={
                "mode": mode,
                "security_profile": security_profile,
                "source_path": source_path,
                "workspace": workspace,
            },
        )

    def start_run_in_place(self, *, workspace: str, mode: str,
                           security_profile: str, defer: bool = True) -> dict:
        """``POST /v1/runs`` task-less "start" flow: run in a prepared workspace.

        The workspace must already contain
        ``domain-knowledge/background-information.md``; the run executes in
        place (no isolated ``runs/`` subfolder). Used by benchmark adapters
        that stage a repo skeleton for Anvil to work inside.
        """
        return self._request(
            "POST", f"/v1/runs?defer={'true' if defer else 'false'}",
            body={
                "mode": mode,
                "security_profile": security_profile,
                "workspace": workspace,
            },
        )

    def advance(self, run_id: str) -> dict:
        """``POST /v1/runs/{id}/advance`` — run exactly one phase."""
        return self._request("POST", f"/v1/runs/{run_id}/advance")

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/v1/runs/{run_id}", timeout_s=30.0)

    def stop(self, run_id: str, reason: str) -> dict:
        return self._request(
            "POST", f"/v1/runs/{run_id}/override",
            body={"action": "stop", "reason": reason, "requesterId": "anvil-eval"},
        )


__all__ = ["AnvilClient", "AnvilClientError"]
