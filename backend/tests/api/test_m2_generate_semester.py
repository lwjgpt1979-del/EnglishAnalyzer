"""M2 — curriculum_service.generate_semester() tests.

Tests the service directly (no HTTP client needed) with AI mocked.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from app.schemas.curriculum import AIGeneratedUnit, AIKnowledgePointItem, AIWordItem


def _make_kp(i: int) -> AIKnowledgePointItem:
    return AIKnowledgePointItem(
        code=f"test_kp_{i}",
        name=f"KP {i}",
        category="grammar",
        description="Basic grammar",
    )


def _make_word(w: str) -> AIWordItem:
    return AIWordItem(
        word=w, phonetic=f"/{w}/",
        definitions=[{"pos": "n.", "meaning": w}],
        examples=[], difficulty=1,
    )


def _make_unit(unit_no: int, textbook="测试版", grade="测试年级", semester="上") -> AIGeneratedUnit:
    return AIGeneratedUnit(
        textbook_version=textbook,
        grade=grade,
        semester=semester,
        unit_no=unit_no,
        unit_title=f"Unit {unit_no} Title",
        knowledge_points=[_make_kp(i) for i in range(1, 4)],
        words=[_make_word(w) for w in ["apple", "banana", "cat", "dog", "egg"]],
    )


@pytest.mark.asyncio
async def test_generate_semester_calls_ai_per_unit():
    """generate_semester calls AI once per unit and returns matching result list."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import os

    db_url = os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg://postgres:dev@127.0.0.1:5432/enggramer",
    )
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _fake_generate(**kw):
        return _make_unit(kw["unit_no"], kw["textbook_version"], kw["grade"], kw["semester"])

    with patch(
        "app.services.curriculum_ai_service.generate_unit",
        new=AsyncMock(side_effect=_fake_generate),
    ):
        async with session_factory() as db:
            from app.services import curriculum_service
            results = await curriculum_service.generate_semester(
                db,
                textbook_version="测试版",
                grade="测试年级",
                semester="上",
                unit_count=3,
                content_status="draft",
                reset=True,
            )
            await db.commit()

    assert len(results) == 3
    assert results[0]["unit_no"] == 1
    assert results[2]["unit_no"] == 3
    assert "unit_title" in results[0]


@pytest.mark.asyncio
async def test_reset_semester_clears_old_units():
    """reset_semester removes existing units for the given semester."""
    import os
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import text

    db_url = os.environ.get(
        "ASYNC_DATABASE_URL",
        "postgresql+psycopg://postgres:dev@127.0.0.1:5432/enggramer",
    )
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as db:
        # generate_semester with reset=True should leave exactly unit_count units
        async def _fake(**kw):
            return _make_unit(kw["unit_no"], kw["textbook_version"], kw["grade"], kw["semester"])

        with patch("app.services.curriculum_ai_service.generate_unit", new=AsyncMock(side_effect=_fake)):
            from app.services import curriculum_service
            await curriculum_service.generate_semester(
                db,
                textbook_version="测试版2",
                grade="重置测试",
                semester="上",
                unit_count=2,
                content_status="draft",
                reset=False,
            )
            # Now reset + regenerate with 1 unit
            await curriculum_service.generate_semester(
                db,
                textbook_version="测试版2",
                grade="重置测试",
                semester="上",
                unit_count=1,
                content_status="draft",
                reset=True,
            )
        count_row = (await db.execute(text(
            "SELECT count(*) FROM curriculum_units "
            "WHERE textbook_version='测试版2' AND grade='重置测试' AND semester='上'"
        ))).scalar()
        await db.commit()

    assert count_row == 1, f"Expected 1 unit after reset, got {count_row}"
