from __future__ import annotations

import os
from enum import StrEnum
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .infrai_realtime import InfraiError, InfraiRealtime


class AccountLifecycle(StrEnum):
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    CLOSED = "closed"


class OpenSupportChat(BaseModel):
    tenant_id: str = Field(min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    account_id: str = Field(min_length=2, max_length=80)
    user_id: str = Field(min_length=2, max_length=80)
    lifecycle: AccountLifecycle
    onboarding_step: str | None = Field(default=None, max_length=120)


class SupportChatSession(BaseModel):
    channel: str
    token: str
    lifecycle: AccountLifecycle
    routing_note: str


def realtime_client() -> InfraiRealtime:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    return InfraiRealtime(api_key)


def build_service(client: InfraiRealtime | None = None) -> FastAPI:
    service = FastAPI(title="Tenant lifecycle support desk")

    def get_client() -> InfraiRealtime:
        return client or realtime_client()

    @service.exception_handler(InfraiError)
    async def handle_infrai_error(_request: Request, error: InfraiError):
        status = error.status_code if 400 <= error.status_code < 500 else 502
        return JSONResponse(
            status_code=status,
            content={"detail": {"code": error.code, "message": error.detail.get("message", "Request rejected")}},
        )

    @service.post("/support/sessions", response_model=SupportChatSession, status_code=201)
    async def open_session(
        request: OpenSupportChat,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8)],
        realtime: InfraiRealtime = Depends(get_client),
    ) -> SupportChatSession:
        if request.lifecycle in {AccountLifecycle.SUSPENDED, AccountLifecycle.CLOSED}:
            raise HTTPException(status_code=409, detail="Support chat is unavailable for this account lifecycle")

        channel = f"tenant-{request.tenant_id}-support"
        await realtime.create_channel(channel, f"{idempotency_key}:channel")
        context: dict[str, Any] = {"lifecycle": request.lifecycle.value, "user_id": request.user_id}
        if request.onboarding_step:
            context["onboarding_step"] = request.onboarding_step
        await realtime.publish_account_context(
            channel, request.account_id, context, f"{idempotency_key}:context"
        )
        token_data = await realtime.issue_token(request.user_id, channel, f"{idempotency_key}:token")
        routing_note = "onboarding queue" if request.lifecycle == AccountLifecycle.ONBOARDING else "account support queue"
        return SupportChatSession(
            channel=channel,
            token=str(token_data["token"]),
            lifecycle=request.lifecycle,
            routing_note=routing_note,
        )

    return service


app = build_service()
