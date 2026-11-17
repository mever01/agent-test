from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field, SecretStr, StringConstraints

from app.api.dependencies import require_role
from app.configs import settings
from app.configs.gmail import GMAIL_CALLBACK_PATH
from app.db.models import User
from app.dto.gmail import GmailAccountInfo
from app.services.exceptions import (
    GmailAccountNotFound,
    GmailConnectionConflict,
)
from app.services.gmail.gmail_service import OAUTH_TTL_SECONDS, GmailService

OAUTH_COOKIE = "gmail_oauth"
MailboxOwner = Annotated[User, Depends(require_role(["manager", "admin"]))]


class GmailRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def without_sensitive_inputs(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                raise HTTPException(422, "Некорректные параметры Gmail.") from exc
            except GmailAccountNotFound:
                raise HTTPException(404, "Gmail-аккаунт не найден.") from None
            except GmailConnectionConflict:
                raise HTTPException(409, "Настройте подключение Gmail.") from None

        return without_sensitive_inputs


class GmailAccountCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True,
                                           min_length=1, max_length=255)]


class GmailConnectionSettings(BaseModel):
    client_id: Annotated[str, StringConstraints(strip_whitespace=True,
                                                min_length=1, max_length=512)]
    client_secret: SecretStr = Field(min_length=1, max_length=2048)


class OAuthAuthorization(BaseModel):
    authorization_url: str


def get_gmail_service(request: Request) -> GmailService:
    service = getattr(request.app.state, "gmail_service", None)
    if service is None:
        raise HTTPException(503, "Интеграция Gmail не настроена.")
    return service


Service = Annotated[GmailService, Depends(get_gmail_service)]
router = APIRouter(prefix="/gmail", tags=["Gmail"], route_class=GmailRoute)


@router.post("/accounts", status_code=201)
async def create_account(
    payload: GmailAccountCreate, user: MailboxOwner, service: Service,
) -> GmailAccountInfo:
    return await service.create(user.id, payload.name)


@router.get("/accounts")
async def list_accounts(user: MailboxOwner, service: Service) -> list[GmailAccountInfo]:
    return await service.list_accounts(user.id)


@router.put("/accounts/{account_id}/connection", status_code=204)
async def configure_connection(
    account_id: UUID, payload: GmailConnectionSettings,
    user: MailboxOwner, service: Service,
) -> None:
    await service.configure(
        user.id, account_id, payload.client_id, payload.client_secret,
    )


@router.post("/accounts/{account_id}/oauth/start")
async def start_oauth(
    account_id: UUID, response: Response, user: MailboxOwner, service: Service,
) -> OAuthAuthorization:
    attempt = await service.start(user.id, account_id)
    response.headers["Cache-Control"] = "no-store"
    redirect_uri = settings.gmail.redirect_uri
    response.set_cookie(
        OAUTH_COOKIE,
        attempt.browser_token,
        max_age=OAUTH_TTL_SECONDS,
        path=GMAIL_CALLBACK_PATH,
        secure=redirect_uri is None or redirect_uri.scheme == "https",
        httponly=True,
        samesite="lax",
    )
    return OAuthAuthorization(authorization_url=attempt.url)


@router.get("/oauth/callback", include_in_schema=False)
async def oauth_callback(
    request: Request,
    service: Service,
    state: Annotated[str | None, Query(max_length=128)] = None,
    code: Annotated[str | None, Query(max_length=4096)] = None,
    error: Annotated[str | None, Query(max_length=256)] = None,
) -> RedirectResponse:
    browser_token = request.cookies.get(OAUTH_COOKIE)
    complete = bool(
        state and browser_token and await service.complete(
            state, browser_token, code if not error else None,
        )
    )
    result = urlencode({"gmail": "connected" if complete else "authorization_failed"})
    response = RedirectResponse(
        f"{settings.gmail.frontend_url}?{result}",
        status_code=303,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )
    if complete:
        response.delete_cookie(OAUTH_COOKIE, path=GMAIL_CALLBACK_PATH)
    return response


@router.delete("/accounts/{account_id}/connection", status_code=204)
async def disconnect(
    account_id: UUID, user: MailboxOwner, service: Service,
) -> None:
    await service.disconnect(user.id, account_id)
