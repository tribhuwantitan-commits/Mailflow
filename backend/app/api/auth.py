"""Registration, login, logout, and current-user routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    extract_access_token,
    get_current_user,
    get_db_session,
    get_settings,
)
from app.api.errors import APIError
from app.config import AUTH_COOKIE_NAME, Settings
from app.models import AuthSession, Organization, User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegistrationResponse,
    UserRead,
)
from app.schemas.organizations import OrganizationRead
from app.security.passwords import burn_password_hash, hash_password, verify_password
from app.security.tokens import create_access_token, hash_access_token
from app.services.organizations import add_organization_with_owner

router = APIRouter()


def _organization_read(organization: Organization, role: str) -> OrganizationRead:
    return OrganizationRead(
        id=organization.id,
        name=organization.name,
        owner_user_id=organization.owner_user_id,
        role=role,
        created_at=organization.created_at,
    )


def _set_no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def _duplicate_email_error() -> APIError:
    return APIError(
        status_code=409,
        code="email_already_registered",
        message="A user with this email already exists.",
    )


def _authentication_unavailable(headers: dict[str, str] | None = None) -> APIError:
    return APIError(
        status_code=503,
        code="authentication_unavailable",
        message="Authentication is temporarily unavailable.",
        headers=headers,
    )


def _delete_access_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=AUTH_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
    )


def _deleted_access_cookie_header(settings: Settings) -> str:
    response = Response()
    _delete_access_cookie(response, settings)
    return response.headers["set-cookie"]


def _invalid_credentials() -> APIError:
    return APIError(
        status_code=401,
        code="invalid_credentials",
        message="Email or password is invalid.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db_session),
) -> RegistrationResponse:
    """Create a user and their default owner organization atomically."""
    email = str(payload.email).strip().casefold()
    try:
        duplicate_exists = db.scalar(select(User.id).where(User.email == email)) is not None
    except SQLAlchemyError:
        raise _authentication_unavailable() from None
    if duplicate_exists:
        raise _duplicate_email_error()

    user = User(
        name=payload.name,
        email=email,
        password_hash=hash_password(payload.password),
    )
    default_organization_name = f"{payload.name[:105].rstrip()}'s Organization"
    try:
        db.add(user)
        db.flush()
        organization = add_organization_with_owner(
            db,
            name=default_organization_name,
            owner_user_id=user.id,
        )
        db.commit()
        db.refresh(user)
        db.refresh(organization)
    except IntegrityError:
        db.rollback()
        try:
            duplicate_exists = db.scalar(select(User.id).where(User.email == email)) is not None
        except SQLAlchemyError:
            raise _authentication_unavailable() from None
        if duplicate_exists:
            raise _duplicate_email_error() from None
        raise _authentication_unavailable() from None
    except SQLAlchemyError:
        db.rollback()
        raise _authentication_unavailable() from None

    _set_no_store(response)
    return RegistrationResponse(
        user=UserRead.model_validate(user),
        organization=_organization_read(organization, "owner"),
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Verify credentials and issue an opaque token in an HttpOnly cookie."""
    email = str(payload.email).strip().casefold()
    try:
        user = db.scalar(select(User).where(User.email == email))
    except SQLAlchemyError:
        raise _authentication_unavailable() from None

    if user is None:
        burn_password_hash(payload.password)
        raise _invalid_credentials()

    password_valid = verify_password(user.password_hash, payload.password)
    if not password_valid or not user.is_active:
        raise _invalid_credentials()

    token, token_hash = create_access_token()
    now = datetime.now(timezone.utc)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=settings.auth_token_expire_minutes),
    )
    try:
        db.add(auth_session)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise _authentication_unavailable() from None

    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=token,
        max_age=settings.auth_token_expire_minutes * 60,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path="/",
    )
    _set_no_store(response)
    return LoginResponse(user=UserRead.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
def logout(
    request: Request,
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db_session),
) -> Response:
    """Revoke the presented session when possible and always clear the local cookie."""
    token = extract_access_token(request)
    if token and len(token) <= 256:
        try:
            auth_session = db.scalar(
                select(AuthSession).where(AuthSession.token_hash == hash_access_token(token))
            )
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = datetime.now(timezone.utc)
                db.commit()
        except SQLAlchemyError:
            db.rollback()
            raise _authentication_unavailable(
                headers={"Set-Cookie": _deleted_access_cookie_header(settings)}
            ) from None

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _delete_access_cookie(response, settings)
    _set_no_store(response)
    return response


@router.get("/me", response_model=UserRead)
def me(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> UserRead:
    """Return only public fields for the authenticated user."""
    _set_no_store(response)
    return UserRead.model_validate(current_user)
