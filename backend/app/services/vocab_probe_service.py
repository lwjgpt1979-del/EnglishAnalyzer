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
PROD_MASTERED = 0.85    # 产出掌握度阈值
# 产出造句 rubric 维度(每维 0-2):用对义 / 搭配用法 / 词性句法
_PROD_DIMS = [("sense", "用对意思"), ("collocation", "搭配用法"), ("grammar", "词性句法")]
_PROD_PASS = 4          # 总分 ≥4/6 且「用对意思」≥1 视为产出达标


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
    if p.get("distractors") and "produce_hint" in p:   # R9.2:需含产出字段;R9.1 旧缓存会补齐一次
        return p
    w = word.word
    if is_llm_dev_mode():
        p = {
            "distractors": [w + "s", w + "ed", w + "ing"][:3],
            "misconceptions": {w + "s": "(dev)形近", w + "ed": "(dev)形近", w + "ing": "(dev)形近"},
            "cloze_fallback": [{"sentence": f"This is a sentence using {w} clearly.", "answer": w}],
            "sense": [],
            "collocation": [],
            "produce_hint": f"用 {w} 造一个句子(用对意思和搭配)",
        }
    else:
        defs = word.definitions if isinstance(word.definitions, (list, dict)) else str(word.definitions)
        exs = word.examples or []
        system = (
            "你是英语词汇命题专家。给定单词 + 释义,生成「理解 + 产出检测」题料,严格输出 JSON:\n"
            "{\"distractors\":[3个干扰项(英文单词:形近词/近义词/该词他义对应词,像读半懂的人会选的,不得等于正确词)],\n"
            " \"misconceptions\":{\"干扰项\":\"一句中文错因\"},\n"
            " \"cloze_fallback\":[{\"sentence\":\"一句含该词的地道英文例句(把词写出,不要挖空)\",\"answer\":\"该词\"}](1-2条),\n"
            " \"sense\":[ 若该词多义,每义一题 {\"sentence\":\"体现该义的英文句\",\"answer\":\"中文义\",\"options\":[\"2-4个中文义\"]} ;无多义空数组],\n"
            " \"collocation\":[1-2题 {\"q\":\"中文问法(如:「对…感兴趣」用哪个搭配?)\",\"options\":[\"3个英文搭配\"],\"answer\":\"正确搭配\"}],\n"
            " \"produce_hint\":\"一句中文,引导学生用该词造句(点明要表达的意思/搭配)\"}"
        )
        user = f"单词:{w}\n释义:{defs}\n参考例句:{exs}\n返回 JSON:"
        d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=1100,
                                model=fast_model(), feature="vocab_probe",
                                validate=lambda x: bool(x.get("distractors")))
        if not d:
            p = {"distractors": [], "misconceptions": {}, "cloze_fallback": [], "sense": [],
                 "collocation": [], "produce_hint": f"用 {w} 造一个句子"}
        else:
            p = {
                "distractors": [str(x) for x in (d.get("distractors") or []) if str(x).strip() and str(x).strip().lower() != w.lower()][:3],
                "misconceptions": {str(k): str(v) for k, v in (d.get("misconceptions") or {}).items()},
                "cloze_fallback": [c for c in (d.get("cloze_fallback") or []) if c.get("sentence")][:2],
                "sense": [s for s in (d.get("sense") or []) if s.get("sentence") and s.get("answer") and s.get("options")][:3],
                "collocation": [c for c in (d.get("collocation") or []) if c.get("q") and c.get("options") and c.get("answer")][:2],
                "produce_hint": str(d.get("produce_hint") or f"用 {w} 造一个句子"),
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
    """组装该词探针:接收(语境 cloze + 多义 sense)+ 产出(搭配 colloc + 造句 produce)。
    返回 {context, probes:[{key,kind,prompt,options}], produce:{key,prompt}|None}。"""
    p = await ensure_probes(db, word)
    ctx = await pick_context(db, student_id=student_id, word=word)
    if ctx is None and p.get("cloze_fallback"):
        fb = p["cloze_fallback"][0]
        ctx = {"text": fb["sentence"], "source": "词典/AI 例句"}
    probes: list[dict] = []
    # 接收
    if ctx:
        blanked = _blank(ctx["text"], word.word)
        if blanked:
            opts = _shuffle([word.word] + (p.get("distractors") or [])[:3], word.word)
            probes.append({"key": "cloze", "kind": "cloze", "prompt": f"选词填空:{blanked}", "options": opts})
    for i, s in enumerate((p.get("sense") or [])[:2]):   # 多义深度:逐义辨析
        probes.append({"key": f"sense:{i}", "kind": "sense",
                       "prompt": f"句中 {word.word} 的意思是?\n{s['sentence']}", "options": s["options"]})
    # 产出·搭配(客观)
    for i, c in enumerate((p.get("collocation") or [])[:1]):
        probes.append({"key": f"colloc:{i}", "kind": "colloc", "prompt": c["q"], "options": c["options"]})
    # 产出·造句(主观,单独走 produce 端点)
    produce = {"key": "produce", "prompt": p.get("produce_hint") or f"用 {word.word} 造一个句子"}
    return {"context": ctx, "probes": probes, "produce": produce}


# ── 判分 + 接收掌握度(BKT)────────────────────────────────────────────
def _mastered(lr: VocabularyLearning) -> bool:
    """真正掌握 = 接收达标 且 产出达标 且 通过同词新语境迁移。"""
    return (float(lr.mastery_recep or 0) >= RECEP_MASTERED
            and float(lr.mastery_prod or 0) >= PROD_MASTERED and bool(lr.transfer_ok))


def _schedule(lr: VocabularyLearning) -> None:
    """R9.4 双维调度:按两维里**较弱**的一维定复习间隔(越弱越快再推);真正掌握→拉长间隔并移出错词本。"""
    weak = min(float(lr.mastery_recep or 0), float(lr.mastery_prod or 0))
    if _mastered(lr):
        days = 7
        lr.is_wrong = False           # 三维达标 → 移出错词本
    elif weak < 0.4:
        days = 1
    elif weak < 0.7:
        days = 2
    else:
        days = 4
    now = datetime.now(timezone.utc)
    lr.interval_days = days
    lr.next_review_at = now + timedelta(days=days)
    lr.last_reviewed_at = now


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
    axis = "recep"
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
    elif key.startswith("colloc:"):     # 产出·搭配(客观)→ prod 轴
        axis = "prod"
        idx = int(key.split(":")[1]) if key.split(":")[1].isdigit() else 0
        coll = (p.get("collocation") or [])
        if idx >= len(coll):
            raise AppError(code=400, message="探针不存在")
        correct_answer = str(coll[idx]["answer"])
        correct = ans == correct_answer.strip()
    else:
        raise AppError(code=400, message="未知探针类型")

    lr = await _get_or_create_learning(db, student_id, word_id)
    if axis == "recep":
        lr.mastery_recep = mastery_judge_service.bkt_update(
            None if lr.mastery_recep is None else float(lr.mastery_recep), correct)
    else:
        lr.mastery_prod = mastery_judge_service.bkt_update(
            None if lr.mastery_prod is None else float(lr.mastery_prod), correct)
    if not correct:
        lr.is_wrong = True
        lr.wrong_count = (lr.wrong_count or 0) + 1
    _schedule(lr)
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"vocab-probe:{word_id}:{key}")
    await mastery_judge_service.log_answer(db, student_id=student_id, q_scope="platform",
                                           question_id=qid, node_id=None, is_correct=correct,
                                           feature="vocab_probe")
    await db.flush()
    recep = float(lr.mastery_recep or 0)
    prod = float(lr.mastery_prod or 0)
    return {"correct": correct, "correct_answer": correct_answer, "misconception": misconception,
            "axis": axis, "recep": round(recep, 4), "prod": round(prod, 4),
            "recep_mastered": recep >= RECEP_MASTERED, "prod_mastered": prod >= PROD_MASTERED,
            "transfer_ok": bool(lr.transfer_ok), "mastered": _mastered(lr)}


# ── 产出·造句(主观 rubric → prod 轴)──────────────────────────────────
async def grade_produce(word: str, sentence: str) -> dict:
    """给学生用该词造的句子按维度打分(用对义/搭配/语法 各 0-2)。
    返回 {dimensions, total, max, passed, feedback}。dev mock 用规则近似。"""
    sentence = (sentence or "").strip()
    total_max = 2 * len(_PROD_DIMS)
    if not sentence:
        return {"dimensions": [{"key": k, "label": l, "score": 0, "max": 2, "note": ""} for k, l in _PROD_DIMS],
                "total": 0, "max": total_max, "passed": False, "feedback": "还没写句子"}
    has_word = re.search(rf"\b{re.escape(word)}", sentence, re.I) is not None
    if is_llm_dev_mode():
        base = 2 if (has_word and len(sentence.split()) >= 4) else (1 if has_word else 0)
        dims = [{"key": k, "label": l, "score": base, "max": 2, "note": ""} for k, l in _PROD_DIMS]
        tot = base * len(_PROD_DIMS)
        return {"dimensions": dims, "total": tot, "max": total_max,
                "passed": tot >= _PROD_PASS and base >= 1, "feedback": "(dev)规则近似评分"}
    system = (
        "你是英语写作评分老师。学生用指定单词造了一句英文,按 3 维打分,每维 0/1/2(0 错/缺、1 部分、2 准确):\n"
        "- sense 用对意思:该词在句中用的是它的正确义;\n"
        "- collocation 搭配用法:与该词搭配/介词/句型地道;\n"
        "- grammar 词性句法:词形、时态、句子语法正确。\n"
        "若句子根本没用到该词,三维均 0。每维给一句简短中文点评(note),再给一句总评(feedback,指出最该改进处)。\n"
        "严格输出 JSON:{\"sense\":{\"score\":0-2,\"note\":..},\"collocation\":{..},\"grammar\":{..},\"feedback\":..}"
    )
    user = f"单词:{word}\n学生造句:{sentence}\n返回 JSON:"
    d = await complete_json(system_prompt=system, user_prompt=user, max_tokens=700,
                            model=fast_model(), feature="vocab_produce",
                            validate=lambda x: any(x.get(k) for k, _ in _PROD_DIMS))
    if not d:   # 评分服务瞬时失败:不计分、不扣掌握度(graded=False)
        return {"dimensions": [{"key": k, "label": l, "score": 0, "max": 2, "note": ""} for k, l in _PROD_DIMS],
                "total": 0, "max": total_max, "passed": False, "graded": False,
                "feedback": "评分服务暂忙,请重试(本次不计分)"}
    dims = []
    for k, l in _PROD_DIMS:
        cell = d.get(k) or {}
        try:
            sc = max(0, min(2, int(cell.get("score", 0))))
        except (ValueError, TypeError):
            sc = 0
        dims.append({"key": k, "label": l, "score": sc, "max": 2, "note": str(cell.get("note") or "")})
    if not has_word:   # 没用到该词,直接判 0(防 LLM 宽松)
        dims = [{**x, "score": 0} for x in dims]
    tot = sum(x["score"] for x in dims)
    sense_sc = next((x["score"] for x in dims if x["key"] == "sense"), 0)
    return {"dimensions": dims, "total": tot, "max": total_max,
            "passed": tot >= _PROD_PASS and sense_sc >= 1, "feedback": str(d.get("feedback") or "")}


async def submit_produce(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID, sentence: str) -> dict:
    """提交造句:rubric 评分 → 产出掌握度 prod BKT(达标=正确)。返回 rubric + {prod, prod_mastered, mastered, recep}。"""
    from app.core.exceptions import AppError
    word = (await db.execute(sa.select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if word is None:
        raise AppError(code=404, message="单词不存在")
    res = await grade_produce(word.word, sentence)
    lr = await _get_or_create_learning(db, student_id, word_id)
    if res.get("graded", True):    # 评分服务失败(graded=False)→ 不动掌握度、不计错、不排期
        lr.mastery_prod = mastery_judge_service.bkt_update(
            None if lr.mastery_prod is None else float(lr.mastery_prod), res["passed"])
        if not res["passed"]:
            lr.is_wrong = True
            lr.wrong_count = (lr.wrong_count or 0) + 1
        _schedule(lr)
        qid = uuid.uuid5(uuid.NAMESPACE_OID, f"vocab-produce:{word_id}")
        await mastery_judge_service.log_answer(db, student_id=student_id, q_scope="platform",
                                               question_id=qid, node_id=None, is_correct=res["passed"],
                                               feature="vocab_produce")
    await db.flush()
    recep = float(lr.mastery_recep or 0)
    prod = float(lr.mastery_prod or 0)
    return {**res, "recep": round(recep, 4), "prod": round(prod, 4),
            "prod_mastered": prod >= PROD_MASTERED, "transfer_ok": bool(lr.transfer_ok),
            "mastered": _mastered(lr)}


# ── 迁移项(同词新语境,区分「记住这道题」vs「会这个词」)──────────────
def _norm(s: str | None) -> str:
    return re.sub(r"\W+", "", (s or "")).lower()


async def find_transfer_context(db: AsyncSession, *, student_id: uuid.UUID, word: VocabularyWord,
                                exclude_text: str | None) -> dict | None:
    """找一条与原语境不同、含该词的新句子(同词新语境)。来源:缓存例句/词典例句/学生其它真实语境。"""
    p = await ensure_probes(db, word)
    ex = _norm(exclude_text)
    cands: list[tuple[str | None, str]] = []
    for c in (p.get("cloze_fallback") or []):
        cands.append((c.get("sentence"), "新例句"))
    for e in (word.examples or []):
        cands.append((e.get("en") if isinstance(e, dict) else str(e), "词典例句"))
    # 学生其它真实语境(作业/真题),也可作迁移新句
    other = await pick_context(db, student_id=student_id, word=word)
    if other:
        cands.insert(0, (other["text"], other["source"]))
    for text, src in cands:
        s = _sentence_with(text, word.word)
        if s and _norm(s) != ex and _blank(s, word.word):
            return {"text": s, "source": src}
    # 兜底:现生成一句"同词新内容"的句子(迁移项正需新语境),并入缓存供复用
    if is_llm_dev_mode():
        gen = f"They will {word.word} it again next week."
    else:
        d = await complete_json(
            system_prompt="你是英语例句作者。给定单词,造一句**全新内容**的地道英文短句(8-16词,含该词原形或常见变形,适合初中生),严格输出 JSON {\"sentence\":..}。",
            user_prompt=f"单词:{word.word}\n避免与这句雷同:{exclude_text or '(无)'}\n返回 JSON:",
            max_tokens=400, model=fast_model(), feature="vocab_probe",
            validate=lambda x: bool(x.get("sentence")))
        gen = (d or {}).get("sentence") if d else None
    s = _sentence_with(gen, word.word) if gen else None
    if s and _norm(s) != ex and _blank(s, word.word):
        fb = list(p.get("cloze_fallback") or [])
        fb.append({"sentence": s, "answer": word.word})
        word.probes_json = {**(word.probes_json or {}), "cloze_fallback": fb[:4]}
        await db.flush()
        return {"text": s, "source": "AI 新句"}
    return None


async def transfer_probe(db: AsyncSession, *, student_id: uuid.UUID, word: VocabularyWord,
                         exclude_text: str | None) -> dict | None:
    """组装迁移题:同词新语境的语境 cloze(新句挖空 + 缓存干扰项)。无新语境→None。"""
    ctx = await find_transfer_context(db, student_id=student_id, word=word, exclude_text=exclude_text)
    if not ctx:
        return None
    p = word.probes_json or {}
    blanked = _blank(ctx["text"], word.word)
    opts = _shuffle([word.word] + (p.get("distractors") or [])[:3], word.word + "t")
    return {"context": ctx, "probe": {"key": "transfer", "kind": "cloze",
                                      "prompt": f"换个句子 · 选词填空:{blanked}", "options": opts}}


async def submit_transfer(db: AsyncSession, *, student_id: uuid.UUID, word_id: uuid.UUID, answer: str) -> dict:
    """提交迁移题:判分 → 接收 BKT + 通过则置 transfer_ok=True。
    verdict=transferred(真懂这个词)/ memorized(疑似记住原题)。"""
    from app.core.exceptions import AppError
    word = (await db.execute(sa.select(VocabularyWord).where(VocabularyWord.id == word_id))).scalar_one_or_none()
    if word is None:
        raise AppError(code=404, message="单词不存在")
    p = await ensure_probes(db, word)
    ans = (answer or "").strip()
    correct = ans.lower() == word.word.lower()
    misconception = None if correct else (p.get("misconceptions") or {}).get(ans)
    lr = await _get_or_create_learning(db, student_id, word_id)
    lr.mastery_recep = mastery_judge_service.bkt_update(
        None if lr.mastery_recep is None else float(lr.mastery_recep), correct)
    if correct:
        lr.transfer_ok = True
    else:
        lr.is_wrong = True
        lr.wrong_count = (lr.wrong_count or 0) + 1
    _schedule(lr)
    qid = uuid.uuid5(uuid.NAMESPACE_OID, f"vocab-transfer:{word_id}")
    await mastery_judge_service.log_answer(db, student_id=student_id, q_scope="platform",
                                           question_id=qid, node_id=None, is_correct=correct,
                                           feature="vocab_probe")
    await db.flush()
    return {"correct": correct, "verdict": "transferred" if correct else "memorized",
            "correct_answer": word.word, "misconception": misconception,
            "recep": round(float(lr.mastery_recep or 0), 4), "prod": round(float(lr.mastery_prod or 0), 4),
            "transfer_ok": bool(lr.transfer_ok), "mastered": _mastered(lr)}


# ── 跨模块真实复现(在长难句/真题文本里命中词单未掌握词)────────────────
async def incidental_hits(db: AsyncSession, *, student_id: uuid.UUID, text: str, limit: int = 5) -> list[dict]:
    """文本里命中该生词单中**未掌握**的词 → 可在阅读语境里顺势轻测复现。返回 [{word_id, word, recep, prod}]。"""
    if not text:
        return []
    rows = (await db.execute(
        sa.select(VocabularyWord.id, VocabularyWord.word, VocabularyLearning)
        .join(VocabularyLearning, VocabularyLearning.word_id == VocabularyWord.id)
        .where(VocabularyLearning.student_id == student_id))).all()
    hits = []
    for wid, w, lr in rows:
        if _mastered(lr):
            continue
        if re.search(rf"\b{re.escape(w)}\b", text, re.I):
            hits.append({"word_id": str(wid), "word": w,
                         "recep": round(float(lr.mastery_recep or 0), 2),
                         "prod": round(float(lr.mastery_prod or 0), 2)})
            if len(hits) >= limit:
                break
    return hits


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
