"""语音合成 service（火山引擎/豆包 TTS）。

dev-mock：tts_provider != 'volcano' 或缺凭据时返回空字节（无音频，不报错）。
生产：设 TTS_PROVIDER=volcano + VOLC_TTS_APPID/ACCESS_TOKEN/CLUSTER，调用
火山引擎语音合成 HTTP API，返回 mp3 音频字节。
文档: https://www.volcengine.com/docs/6561/79817
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
import time
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.d9_system import SystemConfig

logger = logging.getLogger(__name__)

# ── 听力语速（平台后台 system_configs 可配，带进程内短缓存）──────────────────
_SPEED_KEY = "tts_listening_speed"
_SPEED_TTL = 60.0
_speed_cache: dict = {"data": None, "ts": 0.0}


def _default_speeds() -> dict:
    return {
        "primary": float(settings.volc_tts_speed_primary),
        "junior": float(settings.volc_tts_speed_junior),
        "senior": float(settings.volc_tts_speed_senior),
    }


async def get_listening_speeds(db: AsyncSession) -> dict:
    """读后台配置的三档听力语速；缺失项回落 .env 默认。60s 缓存。"""
    now = time.time()
    if _speed_cache["data"] is not None and now - _speed_cache["ts"] < _SPEED_TTL:
        return _speed_cache["data"]
    d = _default_speeds()
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _SPEED_KEY)
    )).scalar_one_or_none()
    if row is not None and isinstance(row.value, dict):
        for k in ("primary", "junior", "senior"):
            try:
                d[k] = float(row.value.get(k, d[k]))
            except (TypeError, ValueError):
                pass
    _speed_cache["data"] = d
    _speed_cache["ts"] = now
    return d


async def speed_for_stage_db(db: AsyncSession, stage: str | None) -> float:
    d = await get_listening_speeds(db)
    return d.get((stage or "junior").lower(), d["junior"])


async def set_listening_speeds(db: AsyncSession, *, speeds: dict, updated_by) -> dict:
    """运营改三档听力语速：upsert system_configs.tts_listening_speed，并清缓存。"""
    value = {
        "primary": float(speeds.get("primary", settings.volc_tts_speed_primary)),
        "junior": float(speeds.get("junior", settings.volc_tts_speed_junior)),
        "senior": float(speeds.get("senior", settings.volc_tts_speed_senior)),
    }
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _SPEED_KEY)
    )).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(
            id=uuid.uuid4(), key=_SPEED_KEY, value=value,
            description="听力语速三档(小学/初中/高中, speed_ratio)", updated_by=updated_by,
        ))
    else:
        row.value = value
        row.updated_by = updated_by
    await db.flush()
    _speed_cache["data"] = None  # 失效缓存
    return value

# 对话行：以「英文名:」开头，如 "Anna: Hi Tom"
_DIALOGUE_LINE = re.compile(r"([A-Z][A-Za-z]{1,15})\s*[:：]\s*")


def _split_dialogue(text: str) -> list[tuple[str, str]] | None:
    """把对话体拆成 [(说话人, 台词)]；说话人少于 2 个则返回 None（非对话）。"""
    parts = _DIALOGUE_LINE.split(text or "")
    # split 结果：[前缀, 名1, 台词1, 名2, 台词2, ...]
    if len(parts) < 5:
        return None
    segs: list[tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        speaker = parts[i].strip()
        line = parts[i + 1].strip()
        if line:
            segs.append((speaker, line))
    speakers = {s for s, _ in segs}
    return segs if len(speakers) >= 2 else None


_VOICES_KEY = "tts_voices"
_voices_cache: dict = {"data": None, "ts": 0.0}


def _split_voices(s: str) -> list[str]:
    return [v.strip() for v in (s or "").split(",") if v.strip()]


def _default_voices() -> dict:
    return {
        "male": _split_voices(settings.volc_tts_voice_male),
        "female": _split_voices(settings.volc_tts_voice_female),
    }


async def get_voices(db: AsyncSession) -> dict:
    """读后台配置的男/女音色池；缺失回落 .env。60s 缓存；并刷新同步缓存供合成路径用。"""
    now = time.time()
    if _voices_cache["data"] is not None and now - _voices_cache["ts"] < _SPEED_TTL:
        return _voices_cache["data"]
    d = _default_voices()
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _VOICES_KEY)
    )).scalar_one_or_none()
    if row is not None and isinstance(row.value, dict):
        for k in ("male", "female"):
            v = row.value.get(k)
            if isinstance(v, list) and v:
                d[k] = [str(x).strip() for x in v if str(x).strip()]
    _voices_cache["data"] = d
    _voices_cache["ts"] = now
    return d


async def set_voices(db: AsyncSession, *, male: list[str], female: list[str], updated_by) -> dict:
    """运营改男/女音色池：upsert system_configs.tts_voices，并清缓存。"""
    value = {
        "male": [str(m).strip() for m in male if str(m).strip()],
        "female": [str(f).strip() for f in female if str(f).strip()],
    }
    row = (await db.execute(
        select(SystemConfig).where(SystemConfig.key == _VOICES_KEY)
    )).scalar_one_or_none()
    if row is None:
        db.add(SystemConfig(
            id=uuid.uuid4(), key=_VOICES_KEY, value=value,
            description="TTS 音色池(male/female, bigtts voice_type)", updated_by=updated_by,
        ))
    else:
        row.value = value
        row.updated_by = updated_by
    await db.flush()
    _voices_cache["data"] = None
    return value


def _male_voices() -> list[str]:
    c = _voices_cache["data"]
    return (c["male"] if c and c.get("male") else _split_voices(settings.volc_tts_voice_male))


def _female_voices() -> list[str]:
    c = _voices_cache["data"]
    return (c["female"] if c and c.get("female") else _split_voices(settings.volc_tts_voice_female))


def _all_voices() -> list[str]:
    return (_male_voices() + _female_voices()) or [settings.volc_tts_voice]


# 常见英文名性别（用于对话听力按角色选男/女声；未知名按出现顺序男女交替）
_FEMALE_NAMES = {
    "anna", "lily", "lucy", "mary", "kate", "amy", "jenny", "susan", "helen",
    "grace", "emma", "alice", "lisa", "nancy", "cindy", "sandy", "linda", "betty",
    "rose", "ann", "sally", "kitty", "eve", "may", "joy", "lulu", "mona", "miss",
}
_MALE_NAMES = {
    "tom", "jack", "mike", "tim", "bob", "peter", "david", "john", "sam", "ben",
    "mark", "tony", "jim", "eric", "frank", "jerry", "harry", "andy", "mr", "dad",
    "daniel", "kevin", "leo", "max", "nick", "paul", "tony", "bill", "george",
}


def _gender_of(name: str) -> str | None:
    n = (name or "").strip().lower()
    if n in _FEMALE_NAMES:
        return "f"
    if n in _MALE_NAMES:
        return "m"
    return None


def _voices_for_gender(g: str) -> list[str]:
    vs = _female_voices() if g == "f" else _male_voices()
    return vs or _all_voices()


def _pick_voice_for_text(text: str) -> str:
    """单词/句子：按文本哈希稳定选一个音色（同文本固定、跨文本有男有女）。"""
    voices = _all_voices()
    h = int(hashlib.md5((text or "").encode("utf-8")).hexdigest(), 16)
    return voices[h % len(voices)]


def is_dev_mode() -> bool:
    return (
        settings.tts_provider != "volcano"
        or not settings.volc_tts_appid
        or not settings.volc_tts_access_token
    )


_STAGE_SPEED = {
    "primary": "volc_tts_speed_primary",
    "junior": "volc_tts_speed_junior",
    "senior": "volc_tts_speed_senior",
}


def speed_for_stage(stage: str | None) -> float:
    """学段→语速倍率。未知/缺省按初中(junior)。"""
    attr = _STAGE_SPEED.get((stage or "").lower(), "volc_tts_speed_junior")
    try:
        return float(getattr(settings, attr))
    except (TypeError, ValueError):
        return 1.0


async def synthesize(text: str, *, voice: str | None = None, speed_ratio: float = 1.0) -> bytes:
    """把文本合成为 mp3 音频字节。dev-mock 返回空字节。"""
    text = (text or "").strip()
    if not text:
        return b""
    if is_dev_mode():
        logger.warning("[TTS DEV MOCK] 无真实语音合成，text=%r", text[:40])
        return b""

    payload = {
        "app": {
            "appid": settings.volc_tts_appid,
            "token": settings.volc_tts_access_token,
            "cluster": settings.volc_tts_cluster,
        },
        "user": {"uid": "enggramer"},
        "audio": {
            "voice_type": voice or settings.volc_tts_voice,
            "encoding": "mp3",
            "speed_ratio": speed_ratio,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "operation": "query",
        },
    }
    # 火山鉴权头格式特殊：Bearer 后跟分号
    headers = {"Authorization": f"Bearer;{settings.volc_tts_access_token}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(settings.volc_tts_url, json=payload, headers=headers)
    data = resp.json()
    # 火山成功码为 3000
    if data.get("code") != 3000 or not data.get("data"):
        logger.error("[TTS] 火山合成失败: %s", data.get("message") or data)
        return b""
    return base64.b64decode(data["data"])


# ── 持久化到腾讯 COS ─────────────────────────────────────────────────────────
_cos_client = None


def _is_cos_dev() -> bool:
    return settings.cos_secret_key.startswith("placeholder")


def _get_cos_client():
    global _cos_client
    if _cos_client is None:
        from qcloud_cos import CosConfig, CosS3Client  # type: ignore[import]
        _cos_client = CosS3Client(CosConfig(
            Region=settings.cos_region,
            SecretId=settings.cos_secret_id,
            SecretKey=settings.cos_secret_key,
        ))
    return _cos_client


def _cos_key(text: str, voice: str) -> str:
    digest = hashlib.md5(f"{voice}|{text}".encode("utf-8")).hexdigest()
    return f"tts/{digest}.mp3"


def _assign_dialogue_voices(segs: list[tuple[str, str]]) -> dict[str, str]:
    """按说话人分配音色：已知名按性别选；未知名男女交替；同性别多角色在池内轮换。"""
    speaker_voice: dict[str, str] = {}
    gidx = {"m": 0, "f": 0}
    alt = 0
    for speaker, _ in segs:
        if speaker in speaker_voice:
            continue
        g = _gender_of(speaker)
        if g is None:
            g = "m" if alt % 2 == 0 else "f"
            alt += 1
        vlist = _voices_for_gender(g)
        speaker_voice[speaker] = vlist[gidx[g] % len(vlist)]
        gidx[g] += 1
    return speaker_voice


async def _synthesize_smart(text: str, *, voice: str | None, speed: float = 1.0) -> bytes:
    """对话体→按说话人性别多音色逐句合成拼接；否则用指定音色单合成。"""
    segs = _split_dialogue(text) if voice is None else None
    if not segs:
        v = voice or _pick_voice_for_text(text)
        audio = await synthesize(text, voice=v, speed_ratio=speed)
        if not audio and v != settings.volc_tts_voice:
            audio = await synthesize(text, voice=settings.volc_tts_voice, speed_ratio=speed)
        return audio

    speaker_voice = _assign_dialogue_voices(segs)
    chunks: list[bytes] = []
    for speaker, line in segs:
        v = speaker_voice[speaker]
        audio = await synthesize(line, voice=v, speed_ratio=speed)
        if not audio and v != settings.volc_tts_voice:  # 音色不可用→退默认
            audio = await synthesize(line, voice=settings.volc_tts_voice, speed_ratio=speed)
        if audio:
            chunks.append(audio)
    return b"".join(chunks)


async def get_or_create_audio_url(
    text: str, *, voice: str | None = None, speed: float = 1.0,
) -> str | None:
    """返回该文本对应的 COS 音频直链（不存在则现合成并上传）。

    对话体自动多说话人不同音色；speed 为语速倍率（按学段）；
    COS 为 dev 占位时返回 None，调用方回退流式。
    """
    text = (text or "").strip()
    if not text or _is_cos_dev():
        return None
    # 缓存 key：对话按音色池标记；单文本按所选(哈希稳定)音色；并入语速，保证幂等
    is_dlg = voice is None and _split_dialogue(text) is not None
    if is_dlg:
        v = f"dialogue:{settings.volc_tts_voice_male}|{settings.volc_tts_voice_female}"
    elif voice:
        v = voice
    else:
        v = _pick_voice_for_text(text)
    key = _cos_key(text, f"{v}@{speed}")
    url = f"{settings.cos_base_url}/{key}"

    def _exists() -> bool:
        try:
            return bool(_get_cos_client().object_exists(Bucket=settings.cos_bucket, Key=key))
        except Exception as e:  # noqa: BLE001
            logger.warning("[TTS] COS object_exists 失败: %s", e)
            return False

    if await asyncio.to_thread(_exists):
        return url

    audio = await _synthesize_smart(text, voice=voice, speed=speed)
    if not audio:
        return None

    def _put() -> None:
        _get_cos_client().put_object(
            Bucket=settings.cos_bucket, Key=key, Body=audio,
            ContentType="audio/mpeg",
            ACL="public-read",  # 对象级公开读，音频直链可匿名播放（不依赖桶ACL）
        )

    try:
        await asyncio.to_thread(_put)
    except Exception as e:  # noqa: BLE001
        logger.error("[TTS] COS 上传失败: %s", e)
        return None
    return url


# ── TTS 用量看板 + 预热 ────────────────────────────────────────────────────────
async def cos_usage() -> dict:
    """统计 COS 上 tts/ 前缀下的对象数与总字节（每个对象=一次已付费合成）。"""
    if _is_cos_dev():
        return {"available": False, "object_count": 0, "total_bytes": 0, "total_mb": 0.0}

    def _scan() -> tuple[int, int]:
        cli = _get_cos_client()
        count = 0
        total = 0
        marker = ""
        while True:
            resp = cli.list_objects(
                Bucket=settings.cos_bucket, Prefix="tts/", Marker=marker, MaxKeys=1000)
            for obj in resp.get("Contents", []) or []:
                count += 1
                total += int(obj.get("Size", 0))
            if resp.get("IsTruncated") == "true":
                marker = resp.get("NextMarker", "")
                if not marker:
                    break
            else:
                break
        return count, total

    try:
        count, total = await asyncio.to_thread(_scan)
    except Exception as e:  # noqa: BLE001
        logger.warning("[TTS] COS 用量统计失败: %s", e)
        return {"available": False, "object_count": 0, "total_bytes": 0, "total_mb": 0.0}
    return {
        "available": True,
        "object_count": count,
        "total_bytes": total,
        "total_mb": round(total / 1048576, 2),
    }


# 预热任务进程内状态（单任务串行，避免并发打爆火山配额）
_prewarm_state: dict = {
    "running": False, "label": "", "total": 0, "done": 0, "ok": 0, "failed": 0,
}


def prewarm_status() -> dict:
    return dict(_prewarm_state)


async def _run_prewarm(texts: list[str], speed: float) -> None:
    _prewarm_state.update(running=True, total=len(texts), done=0, ok=0, failed=0)
    try:
        for t in texts:
            try:
                url = await get_or_create_audio_url(t, speed=speed)
                if url:
                    _prewarm_state["ok"] += 1
                else:
                    _prewarm_state["failed"] += 1
            except Exception:  # noqa: BLE001
                _prewarm_state["failed"] += 1
            _prewarm_state["done"] += 1
    finally:
        _prewarm_state["running"] = False


async def start_prewarm(
    db: AsyncSession, *, textbook_version: str, grade: str, semester: str,
    scope: str = "vocab", limit: int = 50, speed: float = 1.0,
) -> dict:
    """收集某学期的词表(单词+英文描述)/听力文本，后台串行预生成入 COS。

    scope: vocab | listening | all。返回 {started, total, label}。
    """
    if _prewarm_state["running"]:
        return {"started": False, "reason": "已有预热任务进行中", **prewarm_status()}

    texts: list[str] = []
    label_parts: list[str] = []

    if scope in ("vocab", "all"):
        from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
        from app.models.d5_learning import VocabularyWord
        rows = (await db.execute(
            select(VocabularyWord.word, VocabularyWord.en_description)
            .join(CurriculumWord, CurriculumWord.word_id == VocabularyWord.id)
            .join(CurriculumUnit, CurriculumUnit.id == CurriculumWord.unit_id)
            .where(
                CurriculumUnit.textbook_version == textbook_version,
                CurriculumUnit.grade == grade,
                CurriculumUnit.semester == semester,
            )
            .distinct()
            .limit(max(1, min(limit, 500)))
        )).all()
        for word, desc in rows:
            if word:
                texts.append(word)
            if desc:
                texts.append(desc)
        label_parts.append(f"词表{len(rows)}词")

    if scope in ("listening", "all"):
        from app.services import listening_service
        for ex in getattr(listening_service, "_EXERCISES", []):
            tr = ex.get("transcript")
            if tr:
                texts.append(tr)
        label_parts.append("听力素材")

    # 去重保序
    seen: set[str] = set()
    uniq = [t for t in texts if not (t in seen or seen.add(t))]

    if not uniq:
        return {"started": False, "reason": "该学期无可预热文本", "total": 0}

    label = f"{textbook_version}/{grade}/{semester} · " + "+".join(label_parts)
    _prewarm_state.update(label=label)
    asyncio.create_task(_run_prewarm(uniq, speed))
    return {"started": True, "total": len(uniq), "label": label}


async def prewarm_semesters(db: AsyncSession, *, limit: int = 50) -> list[dict]:
    """列出有词汇的学期(供后台选择预热)，按词数倒序。"""
    from app.models.d4_knowledge import CurriculumUnit, CurriculumWord
    from sqlalchemy import func
    rows = (await db.execute(
        select(
            CurriculumUnit.textbook_version, CurriculumUnit.grade,
            CurriculumUnit.semester,
            func.count(func.distinct(CurriculumWord.word_id)).label("wc"),
        )
        .join(CurriculumWord, CurriculumWord.unit_id == CurriculumUnit.id)
        .group_by(CurriculumUnit.textbook_version, CurriculumUnit.grade, CurriculumUnit.semester)
        .order_by(func.count(func.distinct(CurriculumWord.word_id)).desc())
        .limit(limit)
    )).all()
    return [
        {"textbook_version": r[0], "grade": r[1], "semester": r[2], "word_count": int(r[3])}
        for r in rows
    ]
