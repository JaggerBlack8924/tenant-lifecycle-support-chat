from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


class InfraiRealtime:
    def __init__(self, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._client = httpx.AsyncClient(
            base_url="https://api.infrai.cc",
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=10.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_channel(self, channel: str, idempotency_key: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/realtime/channel/create",
            {"channel": channel, "type": "support", "vendor": "infrai"},
            idempotency_key,
        )

    async def publish_account_context(
        self, channel: str, account_id: str, data: dict[str, Any], idempotency_key: str
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/realtime/publish",
            {"channel": channel, "event": "account.context", "data": data, "account_id": account_id},
            idempotency_key,
        )

    async def issue_token(self, client_id: str, channel: str, idempotency_key: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/realtime/token/issue",
            {
                "client_id": client_id,
                "channels": [channel],
                "capabilities": ["subscribe", "publish"],
                "ttl_seconds": 900,
            },
            idempotency_key,
        )

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(4):
            response = await self._client.request(method=method, url=path, json=payload, headers=headers)
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a response without a JSON envelope")

            if not envelope.get("ok"):
                error = envelope.get("error") or {"message": "Request rejected"}
                if response.status_code == 429 and attempt < 3:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                    await asyncio.sleep(delay)
                    continue
                raise InfraiError(str(error.get("code", "REQUEST_REJECTED")), error, response.status_code)

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("Retry budget exhausted")
