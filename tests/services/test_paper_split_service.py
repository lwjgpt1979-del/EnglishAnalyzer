"""整卷拆题服务测试（D-089 / M4）。dev mock 确定性返回 2 题。"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.ocr_service import OcrResult, _MOCK_PRINTED, _MOCK_HANDWRITTEN
from app.services.paper_split_service import (
    split_paper_questions, split_paper_text_structural, ParsedPaperQuestion,
)


@pytest.fixture(autouse=True)
def force_dev_mode(monkeypatch):
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-placeholder-for-test")


@pytest.mark.asyncio
async def test_split_dev_mock_returns_two_questions():
    ocr = OcrResult(printed_text=_MOCK_PRINTED, handwritten_text=_MOCK_HANDWRITTEN)
    questions = await split_paper_questions(ocr)

    assert isinstance(questions, list)
    assert len(questions) == 2
    assert all(isinstance(q, ParsedPaperQuestion) for q in questions)

    q27, q28 = questions
    assert q27.question_no == "27"
    assert q27.question_type == "单选"
    assert q27.student_answer == "B"
    assert q27.stem and "hand in" in q27.stem

    assert q28.question_no == "28"
    assert q28.student_answer == "B"


@pytest.mark.asyncio
async def test_split_empty_ocr_returns_empty_list():
    ocr = OcrResult(printed_text="", handwritten_text="")
    questions = await split_paper_questions(ocr)
    assert questions == []


# ─── 确定性结构拆题（文字版 docx/PDF）─────────────────────────────────────────

_PAPER = """2023 年某市七年级英语试卷
二、单项填空（满分10分）
请认真阅读下面各题, 从A、B、C、D四个选项中, 选出最佳选项。
1. I ________ an apple now.
A. eat	B. am eating	C. ate	D. will eat
2. She is good ________ math.
A. at	B. in	C. on	D. for
三、完形填空 （满分10分）
请先通读下面的短文。
Tom is a boy. He ____3____ football every day. He is ____4____ happy.
3. A. play	B. plays	C. played	D. playing
4. A. very	B. much	C. too	D. so
五、信息还原（满分5分）
根据短文内容, 从选项中选出最佳选项。
I like sports. ____5____ I play it every day. ____6____
A. Football is my favourite.
B. I also like reading.
C. It makes me strong.
七、完成句子 （满分10分）
将下列句子译成英语。
7. 他每天跑步。
He ________ every day.
九、书面表达 （满分10分）
8. 请以 My Day 为题写一篇短文。
"""


def test_structural_split_section_types_and_numbering():
    rows = split_paper_text_structural(_PAPER)
    got = {(r.question_no, r.question_type) for r in rows}
    # 大题标题定题型；题号按卷面原样（不跨大题重排）
    assert ("1", "单选") in got and ("2", "单选") in got
    assert ("3", "完型") in got and ("4", "完型") in got
    assert ("5", "阅读") in got and ("6", "阅读") in got   # 信息还原嵌入空合成
    assert ("7", "填空") in got                            # 完成句子
    assert ("8", "写作") in got                            # 书面表达


def test_structural_split_is_faithful_no_hallucinated_answers():
    rows = split_paper_text_structural(_PAPER)
    # 原卷无答案 → 一律留空，绝不臆造
    assert all(r.correct_answer is None and r.student_answer is None for r in rows)
    # 题干逐字保留：选项、完形短文、完成句子模板都在
    by_no = {r.question_no: r.stem for r in rows}
    assert "B. am eating" in by_no["1"]
    assert "Tom is a boy." in by_no["3"]          # 完形短文挂到题组
    assert "He ________ every day." in by_no["7"]  # 完成句子下划线模板保留
    # 信息还原：每空自带短文 + 共享选项框
    assert "Football is my favourite." in by_no["5"]


def test_structural_split_unknown_format_returns_empty():
    # 无大题/题号的纯文本 → 返回 []（调用方据此兜底走 LLM）
    assert split_paper_text_structural("just some random prose, no structure") == []
