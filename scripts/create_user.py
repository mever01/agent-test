import argparse
import asyncio
from getpass import getpass

from app.db.enums import UserRole
from app.db.models.user import User
from app.db.dao.user import UserRepository
from app.db.session import AsyncSessionLocal, engine
from app.services.auth_service import hash_password


async def create_user(email: str, role: UserRole, password: str) -> None:
    try:
        digest = await asyncio.to_thread(hash_password, password)
        await UserRepository(AsyncSessionLocal).add(
            User(email=email, role=role, password_hash=digest)
        )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--role", choices=[role.value for role in UserRole], default="manager")
    args = parser.parse_args()
    email = args.email.strip().lower()
    if not email or len(email) > 255 or "@" not in email:
        parser.error("Укажите корректный email.")
    password = getpass("Пароль: ")
    if not 12 <= len(password) <= 256:
        parser.error("Пароль должен содержать от 12 до 256 символов.")
    if password != getpass("Повторите пароль: "):
        parser.error("Пароли не совпадают.")
    asyncio.run(create_user(email, UserRole(args.role), password))


if __name__ == "__main__":
    main()
