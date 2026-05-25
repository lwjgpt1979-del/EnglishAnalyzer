"""
Model structure tests — no live database required.
Tests run by importing models and inspecting SQLAlchemy Table objects.
"""
import pytest


def test_sqlalchemy_importable():
    import sqlalchemy as sa
    assert sa.__version__.startswith("2.")


def test_alembic_importable():
    import alembic
    assert alembic.__version__ >= "1.13"


def test_base_importable():
    from app.models.base import Base
    import sqlalchemy as sa
    # Base.metadata is a SQLAlchemy MetaData object
    assert isinstance(Base.metadata, sa.MetaData)


def test_database_engine_config():
    from app.core.database import get_engine_url
    # reads DATABASE_URL env var (returns None if not set, never crashes)
    url = get_engine_url()
    assert url is None or url.startswith("postgresql")
