from fastapi import APIRouter, Depends, HTTPException

from fastapi.security import OAuth2PasswordRequestForm

from app.api.auth.schemas import TokenResponse
from app.api.dependencies import get_auth_service
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/token", response_model=TokenResponse)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    token = await service.login(form.username, form.password)
    if token is None:
        raise HTTPException(
            status_code=401, detail="Неверный email или пароль.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=token)
