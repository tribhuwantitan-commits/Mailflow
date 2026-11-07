"""Declarative metadata shared by future SQLAlchemy models and Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future application models."""
