"""中考真题 section 自测:验证 paper_section_taxonomy 路径①识别正确性。

用法(在 backend 目录):
  python -m scripts.selftest_section_taxonomy

金标:用与业务一致的 resolve 期望——对高频干净标题应命中对应键;
并对全量中考真题 section 字符串出分布/命中率报告。
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict

from sqlalchemy import text

from app.core.database import _async_session_factory
from app.services.paper_section_taxonomy import (
    InferSignals,
    infer_section_type,
    label_of,
    resolve_section_type,
    whitelist_labels,
    KEY_MCQ, KEY_CLOZE, KEY_READING, KEY_VOCAB_USE, KEY_WRITING,
    KEY_TASK_READING, KEY_VERB_FILL, KEY_PASSAGE_FILL, KEY_READING_QA,
)


# 干净用例(路径①):标题 → 期望键
GOLD_HEADERS = [
    ("单项选择", KEY_MCQ),
    ("单项填空", KEY_MCQ),
    ("选择题", KEY_MCQ),
    ("完形填空", KEY_CLOZE),
    ("完型填空", KEY_CLOZE),
    ("第一部分 完形填空", KEY_CLOZE),
    ("阅读理解", KEY_READING),
    ("第三部分 阅读理解", KEY_READING),
    ("任务型阅读", KEY_TASK_READING),
    ("词汇运用", KEY_VOCAB_USE),
    ("词语运用", KEY_VOCAB_USE),
    ("书面表达", KEY_WRITING),
    ("动词填空", KEY_VERB_FILL),
    ("短文填空", KEY_PASSAGE_FILL),
    ("阅读与回答问题", KEY_READING_QA),
    ("听力理解", "listening"),
]

# 无标题 α 用例
GOLD_INFER = [
    (InferSignals(has_passage=True, passage_len=300, blank_count=10, has_options=True, question_count=10), KEY_CLOZE),
    (InferSignals(has_passage=True, passage_len=400, blank_count=0, has_options=True, question_count=5), KEY_READING),
    (InferSignals(has_passage=False, has_options=True, question_count=1), KEY_MCQ),
    (InferSignals(has_passage=False, has_options=False, stem_blob="写一篇不少于80词的短文"), KEY_WRITING),
]


def gold_bucket(sec: str) -> str | None:
    """人工金标粗桶:仅对可明确归类的高频标题给期望;噪声返回 None(不计入准确率分母)。"""
    s = (sec or "").strip()
    s = re.sub(r"^[一二三四五六七八九十\d\.．、\s第部分节]+", "", s)
    s = s.replace(" ", "").replace("　", "")
    s = s.replace("完型", "完形").replace("阅谈", "阅读")
    rules = [
        ("听力", "listening"),
        ("书面表达", KEY_WRITING), ("写作", KEY_WRITING),
        ("完形填空", KEY_CLOZE), ("完形", KEY_CLOZE),
        ("信息还原", "info_restore"), ("还原信息", "info_restore"),
        ("任务型阅读", KEY_TASK_READING),
        ("阅读与回答问题", KEY_READING_QA), ("阅读并回答问题", KEY_READING_QA), ("阅读回答", KEY_READING_QA),
        ("阅读表达", "reading_expr"),
        ("阅读填空", "reading_fill"), ("阅读填词", "reading_fill"),
        ("阅读理解", KEY_READING),
        ("动词填空", KEY_VERB_FILL), ("所给动词", KEY_VERB_FILL),
        ("词汇运用", KEY_VOCAB_USE), ("词语运用", KEY_VOCAB_USE), ("词汇检测", KEY_VOCAB_USE),
        ("短文填空", KEY_PASSAGE_FILL), ("缺词填空", KEY_PASSAGE_FILL), ("综合填空", KEY_PASSAGE_FILL),
        ("选词填空", KEY_PASSAGE_FILL), ("首字母", KEY_PASSAGE_FILL),
        ("完成句子", "sentence_complete"),
        ("句子翻译", "translate"), ("翻译句子", "translate"),
        ("句型转换", "transform"),
        ("补全对话", "dialogue"),
        ("单词拼写", "spelling"),
        ("选择填空", "choice_fill"),
        ("单项选择", KEY_MCQ), ("单项填空", KEY_MCQ), ("单选题", KEY_MCQ), ("选择题", KEY_MCQ),
        ("词汇", KEY_VOCAB_USE),
    ]
    for kw, key in rules:
        if kw in s:
            return key
    if "阅读" in s and "听力" not in s:
        return KEY_READING
    return None


async def main() -> None:
    print("=" * 60)
    print("P0 题型识别自测报告 (paper_section_taxonomy)")
    print("=" * 60)

    # 1) 单元金标
    ok = fail = 0
    print("\n## 1. 干净标题路径①")
    for h, expect in GOLD_HEADERS:
        got = resolve_section_type(h)
        hit = got == expect
        ok += hit
        fail += not hit
        mark = "OK" if hit else "FAIL"
        if not hit:
            print(f"  [{mark}] {h!r} → {got} (期望 {expect})")
    print(f"  通过 {ok}/{ok+fail}")

    ok2 = fail2 = 0
    print("\n## 2. 无标题路径② α")
    for sig, expect in GOLD_INFER:
        got, conf = infer_section_type(sig)
        hit = got == expect
        ok2 += hit
        fail2 += not hit
        mark = "OK" if hit else "FAIL"
        print(f"  [{mark}] → {got} conf={conf:.2f} (期望 {expect})")
    print(f"  通过 {ok2}/{ok2+fail2}")

    print("\n## 3. 白名单")
    wl = whitelist_labels()
    print(f"  共 {len(wl)} 项: {', '.join(wl[:8])}…")

    # 2) 中考真题全量
    async with _async_session_factory() as db:
        rows = (await db.execute(text("""
            SELECT coalesce(nullif(trim(section),''),'(空)') AS sec, count(*) AS n
            FROM platform_question
            WHERE type='real' AND exam_type='中考'
            GROUP BY 1
        """))).all()
        total_q = (await db.execute(text("""
            SELECT count(*) FROM platform_question
            WHERE type='real' AND exam_type='中考'
        """))).scalar()

    pred = Counter()
    gold_hit = gold_n = 0
    confusions = Counter()
    unlabeled = 0
    by_pred_n = Counter()

    for sec, n in rows:
        key = resolve_section_type(sec if sec != "(空)" else "")
        pred[key] += n
        by_pred_n[key] += n
        g = gold_bucket(sec)
        if g is None:
            unlabeled += n
            continue
        gold_n += n
        if key == g:
            gold_hit += n
        else:
            confusions[(g, key)] += n

    print("\n## 4. 中考真题 section → resolve 分布")
    print(f"  试卷小题总数: {total_q}")
    print(f"  原始 section 种类: {len(rows)}")
    for k, n in by_pred_n.most_common():
        pct = 100.0 * n / total_q if total_q else 0
        print(f"  {n:6d} ({pct:5.1f}%)  {k:20s}  {label_of(k)}")

    rate = 100.0 * gold_hit / gold_n if gold_n else 0
    print("\n## 5. 相对语义金标准确率(可归类小题)")
    print(f"  可归类小题: {gold_n}  命中: {gold_hit}  准确率: {rate:.2f}%")
    print(f"  无法金标(噪声/空): {unlabeled}")
    print("\n  Top 混淆 (金标 → 预测):")
    for (g, p), n in confusions.most_common(15):
        print(f"  {n:6d}  {g} → {p}")

    # P0 三键覆盖
    p0 = by_pred_n[KEY_MCQ] + by_pred_n[KEY_CLOZE] + by_pred_n[KEY_READING] + by_pred_n[KEY_TASK_READING]
    print("\n## 6. P0 深做三族覆盖(mcq+cloze+reading+task_reading)")
    print(f"  {p0} / {total_q} = {100.0*p0/total_q:.1f}%")

    print("\n## 7. 结论")
    unit_ok = fail == 0 and fail2 == 0
    print(f"  单元用例: {'全部通过' if unit_ok else '有失败'}")
    print(f"  中考可归类准确率: {rate:.2f}%")
    if rate >= 95:
        print("  判定: 路径①达到上线标准(≥95%)")
    elif rate >= 90:
        print("  判定: 基本可用,建议关注混淆项")
    else:
        print("  判定: 需加强别名/归一")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
