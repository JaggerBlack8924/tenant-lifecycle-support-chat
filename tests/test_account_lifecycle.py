from fastapi.testclient import TestClient

from tenant_support.support_desk import build_service


class RecordingRealtime:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def create_channel(self, channel: str, idempotency_key: str) -> dict:
        self.calls.append(("create", channel))
        return {"channel": channel}

    async def publish_account_context(self, channel: str, account_id: str, data: dict, idempotency_key: str) -> dict:
        self.calls.append(("publish", data))
        return {}

    async def issue_token(self, client_id: str, channel: str, idempotency_key: str) -> dict:
        self.calls.append(("token", client_id))
        return {"token": "browser-session-token"}


def test_onboarding_account_gets_contextual_support_session() -> None:
    realtime = RecordingRealtime()
    client = TestClient(build_service(realtime))

    response = client.post(
        "/support/sessions",
        headers={"Idempotency-Key": "session-ada-001"},
        json={
            "tenant_id": "acme",
            "account_id": "acct-42",
            "user_id": "ada",
            "lifecycle": "onboarding",
            "onboarding_step": "invite teammates",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "channel": "tenant-acme-support",
        "token": "browser-session-token",
        "lifecycle": "onboarding",
        "routing_note": "onboarding queue",
    }
    assert realtime.calls[1] == (
        "publish",
        {"lifecycle": "onboarding", "user_id": "ada", "onboarding_step": "invite teammates"},
    )


def test_suspended_account_is_rejected_before_realtime_calls() -> None:
    realtime = RecordingRealtime()
    client = TestClient(build_service(realtime))

    response = client.post(
        "/support/sessions",
        headers={"Idempotency-Key": "session-ada-002"},
        json={
            "tenant_id": "acme",
            "account_id": "acct-42",
            "user_id": "ada",
            "lifecycle": "suspended",
        },
    )

    assert response.status_code == 409
    assert realtime.calls == []
