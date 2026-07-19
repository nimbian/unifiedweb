"""Declarative base for all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base (SQLAlchemy 2.0 typed style)."""
