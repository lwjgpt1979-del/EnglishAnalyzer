"""user_paper_questions 加 options(JSONB):选择题选项结构化落库。

拆卷写入时从 stem 内联拆出;存量在 upgrade 里批刷。幂等。

Revision ID: m201_upq_options
Revises: m200_dict_ecdict
Create Date: 2026-07-27
"""
from __future__ import annotations

import json
import re

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "m201_upq_options"
down_revision = "m200_dict_ecdict"
branch_labels = None
depends_on = None

_MARK = re.compile(r"(?:(?<=\s)|^)([A-D])[.、)．]\s*")


def _parse(text: str) -> tuple[str, list[str] | None]:
    if not text:
        return "", None
    ms = list(_MARK.finditer(text))
    letters = [m.group(1) for m in ms]
    if len(letters) < 3 or letters[:3] != ["A", "B", "C"]:
        return text, None
    stem = text[: ms[0].start()].strip()
    opts: list[str] = []
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        body = text[m.end() : end].strip().rstrip(".;,、。")
        if not body:
            continue
        letter = m.group(1)
        opts.append(f"{letter}. {body}")
    if len(opts) < 3:
        return text, None
    return (stem or text), opts


def upgrade() -> None:
    op.add_column(
        "user_paper_questions",
        sa.Column("options", JSONB(), nullable=True),
    )
    # 存量批刷:stem 内含 A./B./C. 的拆出 options 并净化 stem
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, stem FROM user_paper_questions "
        "WHERE stem IS NOT NULL AND options IS NULL"
    )).fetchall()
    for rid, stem in rows:
        clean, opts = _parse(stem or "")
        if not opts:
            continue
        conn.execute(
            sa.text(
                "UPDATE user_paper_questions SET stem=:stem, options=CAST(:opts AS jsonb) "
                "WHERE id=:id"
            ),
            {"stem": clean, "opts": json.dumps(opts, ensure_ascii=False), "id": rid},
        )


def downgrade() -> None:
    # 降级不把 options 拼回 stem(避免重复);只丢列
    op.drop_column("user_paper_questions", "options")
