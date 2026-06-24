"""R9.1 词汇「可输入性理解」· 接收探针 + 接收掌握度(BKT)。

设计见 docs/R9-技术方案-词汇可输入性理解.md §9。
- 探针库(词级公共复用):ensure_probes 生成并缓存到 VocabularyWord.probes_json。
- 语境句(个性化):pick_context 优先取学生真实原句(错题/作业/真题)→ 词典例句 → 兜底。
- 接收探针:语境 cloze(学生句挖空 + 缓存诊断干扰项)+ 多义辨析 sense。
- 判分 → 接收掌握度 mastery_recep 走 BKT(复用 mastery_judge_service.bkt_update)。
复用:llm_provider.complete_json(分档/智能重试)、usage_log_service(台账+预算熔断)。
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.d5_learning import VocabularyWord, VocabularyLearning
from app.models.d16_question_domain import WrongRecord, PlatformQuestion, UploadedQuestion
from app.models.d18_vocab_kg import VocabWrong, VocabQuestion
from app.services import mastery_judge_service, usage_log_service
from app.services.llm_provider import complete_json, fast_model, is_llm_dev_mode

_log = logging.getLogger(__name__)

RECEP_MASTERED = 0.85   # 接收掌握度阈值 = 「可输入性理解」达成


# ── 文本工具 ──────────────────────────────────────────────────────────
def _blank(sentence: str, word: str) -> str | None:
    """把句中第一个整词(忽略大小写)替换成 ____;句中无该词→None。"""
    m = re.search(rf"\b{re.escape(word)}\b", sentence, re.I)
    if not m:
        return None
    return sentence[:m.start()] + "____" + sentence[m.end():]


def _sentence_with(text: str | None, word: str) -> str | None:
    """从一段文本里切出含该词、长度适中(4-40 词)的一句。"""
    if not text:
        return None
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        s = s.strip()
        if re.search(rf"\b{re.escape(word)}\b", s, re.I) and 4 <= len(s.split()) <= 40:
            return s
    return None


# ── 探针库(词级公共缓存)─────────────────────────────────────────────
async def ensure_probes(db: AsyncSession, word: VocabularyWord) -> dict:
    """取该词探针库;无缓存则 LLM 生成(走 fast 档)并写回 probes_json。"""
    p = word.probes_json or {}
    if p.get("distractors"):
        return p
    w = word.word
    if is_llm_dev_mode():
        p = {
            "distractors": [w + "s", w + "ed", w + "ing"][:3],
            "misconceptions": {w + "s": "(dev)形近", w + "ed": "(dev)形近", w + "ing": "(dev)形近"},
            "cloze_fallback": [{"sentence": f"This is a sentence using {w} clearly.", "answer": w}],
            "sense": [],
        }
    else:
        defs = word.definitions if isinstance(word.definitions, (list, dict)) else str(word.definitions)
        exs = word.examples or []
        system = (
            "你是英语词汇命题专家。给定单词 + 释义,生成「理解检测」题料,严格输出 JSON:\n"
            "{\"distractors\":[3个干扰项(英文单词:形近词/近义词/该词他义对应词,要像读半懂的人会选的,不得等于正确词)],\n"
            " \"misconceptions\":{\"干扰项\":\"一句中文错因\"},\n"
            " \"cloze_fallback\":[{\"sentence\":\"一句含该词的地道英文例句(把词写出,不要挖空)\",\"answer\":\"该词\"}](1-2条),\n"
            " \"sense\":[ 若该词多义,每义一题 {\"sentence\":\"体现该义的英文句\",\"answer\":\"中文义\",\"options\":[\"2-4个中文义\"]} ;无多义则空数组]}"
        )
        user = f"单词:{w}\n释义:{defs}\n参考例句:{exs}\n返回 JSON:"
        d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=900,
                                model=fast_model(), feature="vocab_probe",
                                validate=lambda x: bool(x.get("distractors")))
        if not d:
            p = {"distractors": [], "misconceptions": {}, "cloze_fallback": [], "sense": []}
        else:
            p = {
                "distractors": [str(x) for x in (d.get("distractors") or []) if str(x).strip() and str(x).strip().lower() != w.lower()][:3],
                "misconceptions": {str(k): str(v) for k, v in (d.get("misconceptions") or {}).items()},
                "cloze_fallback": [c for c in (d.get("cloze_fallback") or []) if c.get("sentence")][:2],
                "sense": [s for s in (d.get("sense") or []) if s.get("sentence") and s.get("answer") and s.get("options")][:3],
            }
    word.probes_json = p
    await db.flush()
    return p


# ── 语境句(个性化,决策①:学生原句 > 例句 > 兜底)─────────────────────
async def _stem(db: AsyncSession, q_scope: str, question_id) -> str | None:
    if q_scope == "platform":
        return (await db.execute(sa.select(PlatformQuestion.stem).where(PlatformQuestion.id == question_id))).scalar_one_or_none()
    return (await db.execute(sa.select(UploadedQuestion.stem).where(UploadedQuestion.id == question_id))).scalar_one_or_none()


async def pick_context(db: AsyncSession, *, student_id: uuid.UUID, word: VocabularyWord) -> dict | None:
    """取一条含该词的语境句:错题原句 > 作业/试卷(uploaded,本人)> 真题(platform)> 词典例句。
    返回 {text, source} 或 None(调用方用 cloze_fallback 兜底)。"""
    w = word.word
    # 1) 错题原句(学生自己的错题)
    rows = (await db.execute(
        sa.select(WrongRecord.q_scope, WrongRecord.question_id)
        .join(VocabWrong, VocabWrong.wrong_record_id == WrongRecord.id)
        .where(VocabWrong.word_id == word.id, WrongRecord.student_id == student_id))).all()
    for q_scope, qid in rows:
        s = _sentence_with(await _stem(db, q_scope, qid), w)
        if s:
            return {"text": s, "source": "错题原句"}
    # 2/3) vocab_question:uploaded(本人作业/试卷)优先,platform(真题)次之
    vq = (await db.execute(sa.select(VocabQuestion.q_scope, VocabQuestion.question_id)
                           .where(VocabQuestion.word_id == word.id))).all()
    for want, label in (("uploaded", "作业/试卷原句"), ("platform", "真题原句")):
        for q_scope, qid in vq:
            if q_scope != want:
                continue
            if want == "uploaded":   # 仅取本人的上传题
                own = (await db.execute(sa.select(UploadedQuestion.owner_id).where(UploadedQuestion.id == qid))).scalar_one_or_none()
                if own != student_id:
                    continue
            s = _sentence_with(await _stem(db, q_scope, qid), w)
            if s:
                return {"text": s, "source": label}
    # 4) 词典/教材例句
    for ex in (word.examples or []):
        s = _sentence_with(ex.get("en") if isinstance(ex, dict) else str(ex), w)
        if s:
            return {"text": s, "source": "词典例句"}
    return None


# ── 接收探针组装 ──────────────────────────────────────────────────────
def _shuffle(seq, seed_word: str):
    """确定性打乱(按词名+长度,避免每次顺序变;无需真随机)。"""
    out = list(seq)
    k = sum(ord(c) for c in seed_word)
    return out[k % len(out):] + out[:k % len(out)] if out else out


async def comprehension_probes(db: AsyncSession, *, student_id: uuid.UUID, word: VocabularyWord) -> dict:
    """组装该词接收探针:语境 cloze(学生句挖空 + 缓存干扰项)+ 多义 sense。
    返回 {context:{text,source}|None, probes:[{key,kind,prompt,options}]}。"""
    p = await ensure_probes(db, word)
    ctx = await pick_context(db, student_id=student_id, word=word)
    if ctx is None and p.get("cloze_fallback"):
        fb = p["cloze_fallback"][0]
        ctx = {"text": fb["sentence"], "source": "词典/AI 例句"}
    probes: list[dict] = []
    if ctx:
        blanked = _blank(ctx["text"], word.word)
        if blanked:
            opts = _shuffle([word.word] + (p.get("distractors") or [])[:3], word.word)
            probes.append({"key": "cloze", "kind": "cloze", "prompt": f"选词填空:{blanked}", "options": opts})
    for i, s in enumerate((p.get("sense") or [])[:1]):
        probes.append({"key": f"sense:{i}", "kind": "sense",
                       "prompt": f"句中 {word.word} 的意思是?\n{s['sentence']}", "options": s["options"]})
    return {"context": ctx, "probes": probes}


# ── 判分 + 接收掌握度(BKT)────────────────────────────────────────────
async def _get_or_create_learning(db, student_id, word_id) -> VocabularyLearning:
    lr = (await db.execute(sa.select(VocabularyLearning).where(
        VocabularyLearning.student_id == student_id, VocabularyLearning.word_id == word_id))).scalar_one_or_none()
    if lr is None:
        now = datetime.now(timezone.utc)
        lr = VocabularyLearning(id=uuid.uuid4(), student_id=student_id, word_id=word_id,
                                interval_days=1, repetitions=0, easiness_factor=2.5, level="new",
                                next_review_at=now + timedelta(days=1), last_reviewed_at=now)
        db.add(lr)
        await db.flush()
    return lr


async def submit_probe(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID,
                       key: str, answer: str) -> dict:
    """提交一道接收探针:判分 → 接收掌握度 BKT → 错词本。返回 {correct, correct_answer, misconception, recep, recep_mastered}。"""
    from app.core.exceptions import AppError
    word = (await db.execute(sa.select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if word is None:
        raise AppError(code=404, message="单词不存在")
    p = await ensure_probes(db, word)
    ans = (answer or "").strip()
    misconception = None
    if key == "cloze":
        correct_answer = word.word
        correct = ans.lower() == word.word.lower()
        if not correct:
            misconception = (p.get("misconceptions") or {}).get(ans)
    elif key.startswith("sense:"):
        idx = int(key.split(":")[1]) if key.split(":")[1].isdigit() else 0
        sense = (p.get("sense") or [])
        if idx >= len(sense):
            raise AppError(code=400, message="探针不存在")
        correct_answer = str(sense[idx]["answer"])
        correct = ans == correct_answer.strip()
    else:
        raise AppError(code=400, message="未知探针类型")

    lr = await _get_or_create_learning(db, student_id, word_id)
    prior = None if lr.mastery_recep is None else float(lr.mastery_recep)
    lr.mastery_recep = mastery_judge_service.bkt_update(prior, correct)
    if not correct:
        lr.is_wrong = True
        lr.wrong_count = (lr.wrong_count or 0) + 1
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"vocab-probe:{word_id}:{key}")
    await mastery_judge_service.log_answer(db, student_id=student_id, q_scope="platform",
                                           question_id=qid, node_id=None, is_correct=correct,
                                           feature="vocab_probe")
    await db.flush()
    recep = float(lr.mastery_recep)
    return {"correct": correct, "correct_answer": correct_answer, "misconception": misconception,
            "recep": round(recep, 4), "recep_mastered": recep >= RECEP_MASTERED}


# ── 批量回填探针(带预算熔断)──────────────────────────────────────────
async def backfill_probes(db: AsyncSession, *, limit: int | None = None,
                          only_missing: bool = True, max_tokens_budget: int | None = 200_000) -> dict:
    """给词典里的词批量生成探针库(probes_json)。累计 token 超预算即停。返回 {scanned, filled, stopped, spent_tokens}。"""
    rows = (await db.execute(sa.select(VocabularyWord))).scalars().all()
    scanned = filled = 0
    stopped = False
    spent = 0
    with usage_log_service.budget(max_tokens_budget):
        for w in rows:
            if usage_log_service.over_budget():
                stopped = True
                break
            if only_missing and (w.probes_json or {}).get("distractors"):
                continue
            scanned += 1
            before = usage_log_service.spent()
            p = await ensure_probes(db, w)
            if (p or {}).get("distractors") and usage_log_service.spent() > before:
                filled += 1
            if limit and filled >= limit:
                break
        spent = usage_log_service.spent()
    await db.commit()
    return {"scanned": scanned, "filled": filled, "stopped": stopped, "spent_tokens": spent}
