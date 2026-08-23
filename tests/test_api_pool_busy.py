import asyncio
from types import SimpleNamespace

from api import main
from db.connection import DatabasePoolBusyError


def test_authentication_pool_busy_returns_503(monkeypatch):
    request = SimpleNamespace(
        url=SimpleNamespace(path="/api/pricing-task-background-batches/42/workspace"),
        cookies={},
        state=SimpleNamespace(),
    )
    downstream_called = False

    async def call_next(_request):
        nonlocal downstream_called
        downstream_called = True

    monkeypatch.setattr(main, "is_auth_enabled", lambda: True)
    monkeypatch.setattr(
        main,
        "resolve_session",
        lambda _token: (_ for _ in ()).throw(DatabasePoolBusyError("busy")),
    )

    response = asyncio.run(main.attach_authenticated_user(request, call_next))

    assert response.status_code == 503
    assert downstream_called is False
