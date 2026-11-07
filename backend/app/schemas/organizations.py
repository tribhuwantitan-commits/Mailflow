"""Organization request and response schemas."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

OrganizationName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
]
OrganizationRole = Literal["owner", "member"]


class OrganizationCreate(BaseModel):
    """Fields allowed when creating an organization."""

    name: OrganizationName


class OrganizationRead(BaseModel):
    """Organization fields visible to a member, including their membership role."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    owner_user_id: UUID
    role: OrganizationRole
    created_at: datetime
