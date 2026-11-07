"""Authentication request and safe public response schemas."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints

from app.schemas.organizations import OrganizationRead

DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
RegistrationPassword = Annotated[
    str,
    StringConstraints(min_length=12, max_length=128),
]
LoginPassword = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
]


class RegisterRequest(BaseModel):
    """New user data; passwords are never included in response schemas."""

    name: DisplayName
    email: EmailStr
    password: RegistrationPassword


class LoginRequest(BaseModel):
    """Email/password login request."""

    email: EmailStr
    password: LoginPassword


class UserRead(BaseModel):
    """Public user fields only."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    email: EmailStr
    created_at: datetime


class RegistrationResponse(BaseModel):
    """Registration result including the automatically created default organization."""

    user: UserRead
    organization: OrganizationRead


class LoginResponse(BaseModel):
    """Login returns public user data; the opaque token is set only as an HttpOnly cookie."""

    user: UserRead
