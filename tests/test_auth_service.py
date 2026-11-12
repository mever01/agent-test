from unittest.mock import AsyncMock, Mock
from uuid import uuid4

from app.db.models.user import User
from app.services import auth_service
from app.services.auth_service import AuthService, hash_password, verify_password
from scripts.seed_data import seed_base_user


async def test_auth_tokens_expire_and_are_local_to_service(monkeypatch):
    user = User(
        id=uuid4(),
        email="manager@example.org",
        role="manager",
        password_hash=hash_password("test-password"),
    )
    users = Mock(
        by_email=AsyncMock(return_value=user),
        by_id=AsyncMock(return_value=user),
    )
    clock = Mock(return_value=100)
    monkeypatch.setattr(auth_service, "monotonic", clock)
    service = AuthService(users, ttl_seconds=10)

    assert await service.login(user.email, "wrong-password") is None
    token = await service.login(" MANAGER@example.org ", "test-password")
    assert token
    assert token not in service._sessions
    assert await service.authenticate(token) is user
    assert await AuthService(users, ttl_seconds=10).authenticate(token) is None

    clock.return_value = 110
    assert await service.authenticate(token) is None


async def test_seed_manager_creates_account_once():
    users = Mock(
        by_email=AsyncMock(side_effect=[None, User(email="manager@example.org", role="manager")]),
        add_seed_manager=AsyncMock(),
    )

    await seed_base_user(users, " Manager@example.org ", "test-password")
    await seed_base_user(users, "Manager@example.org", "different-password")

    users.add_seed_manager.assert_awaited_once()
    email, digest = users.add_seed_manager.await_args.args
    assert email == "manager@example.org"
    assert verify_password("test-password", digest)

