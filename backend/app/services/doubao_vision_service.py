"""豆包 Vision 服务（M40）。

实现 OcrProvider 协议，用豆包 Seed-2.0 多模态模型直接看图拆题，
替代原有「阿里云OCR + 腾讯云OCR」双引擎方案。

Dev 模式（doubao_api_key 以 'placeholder' 开头）返回与原 OCR mock 一致的
OcrResult，保证现有 344 个测试全部继续通过。
"""
from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from app.core.config import settings
from app.services.ocr_service import OcrResult

_log = logging.getLogger(__name__)

# ── mock 数据（豆包直出 JSON 格式，含正确答案供 is_wrong 判断）─────────────────
# 题27 学生答 A 正确答案 A → is_wrong=False（写 correct_count）
# 题28 学生答 B 正确答案 A → is_wrong=True（写 wrong_count）
import json as _json

_MOCK_DOUBAO_JSON = _json.dumps([
    {
        "question_no": "27",
        "question_type": "单选",
        "stem": (
            "The teacher asked the students to _____ their homework on time.\n"
            "A. hand in  B. hand out  C. hand over  D. hand up"
        ),
        "student_answer": "A",
        "correct_answer": "A",
        "explanation": "hand in 意为上交",
    },
    {
        "question_no": "28",
        "question_type": "单选",
        "stem": (
            "She _____ in Beijing for three years before she moved to Shanghai.\n"
            "A. lived  B. had lived  C. has lived  D. lives"
        ),
        "student_answer": "B",
        "correct_answer": "A",
        "explanation": "过去完成时表示过去某时之前已发生的动作",
    },
], ensure_ascii=False)

# ── dev 模式检测 ──────────────────────────────────────────────────────────────


def _is_doubao_dev_mode() -> bool:
    return settings.doubao_api_key.startswith("placeholder")


# ── Prompt ────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "你是一个专业的英语试卷结构化助手。"
    "你会收到一整张英语试卷图片（含印刷体题目和学生手写答案），"
    "请把整卷拆成结构化数据（保留原卷大题结构与阅读/完形的短文原文），严格按 JSON 输出，不要任何额外文字。"
)

_USER_PROMPT = """请分析这张英语试卷图片，把所有题目拆分为结构化数据，返回 JSON 对象：{"questions":[...], "passages":{...}}。

questions 每一项：
{
  "section": "该题所属大题名（单项选择/完形填空/阅读理解/任务型阅读/词汇运用/首字母填空/短文填空/书面表达/听力理解 等，忠实原卷大题标题；无法判断则 null）",
  "question_no": "题号（如 27），无法识别则 null",
  "question_type": "单选|填空|完型|阅读|写作|判断|连线",
  "stem": "该题完整题干（含选项，不含学生作答）",
  "block_key": "阅读理解/完形填空/任务型阅读 这类『一篇短文带多道小题』的小题，同一篇短文的小题都给同一个 key（如 readingA、readingB、cloze1）；独立小题为 null",
  "student_answer": "该题学生手写答案，无法识别则 null",
  "correct_answer": "正确答案（可推断则填，否则 null）",
  "explanation": "简要解析（可推断则填，否则 null）"
}

passages 是一个对象，键是 block_key，值是该短文/语篇的**完整原文（逐字照抄图片，不要改写、不要缩略、不要翻译）**：
{ "readingA": "短文全文……", "cloze1": "完形填空语篇全文……" }

铁律：
- **图片里有阅读理解/完形填空/任务型阅读的短文正文，必须把它完整放进 passages，并让对应小题的 block_key 指向它**——绝不能因为题干没重复短文就漏掉短文。短文通常在这组小题前面。
- **务必按原卷大题给每题填 section**；同一大题下的题 section 相同。
- 没有任何短文的卷子，passages 返回 {}。
- 按题号顺序输出；识别不到任何题目时 questions 返回 []。
只返回纯 JSON，不要任何 markdown 代码块或额外文字。"""


# ── Provider 实现 ─────────────────────────────────────────────────────────────


_TEXT_OCR_SYS = (
    "你是教材 OCR 助手。请**原样输出**图片中的全部文字(英文/中文/数字/标点),"
    "保留自然段落与换行;不要翻译、不要改写、不要加任何解释或标记。图片无文字则返回空字符串。"
)


_WORDLIST_SYS = (
    "你是英语教材词汇表识别助手。图片通常是某单元的【单词表/词汇表】(含单词、音标、词性、中文释义),"
    "也可能是带词组短语的页。请提取其中的英文单词与词组,严格输出 JSON。"
)
_WORDLIST_USER = (
    "识别这张图里的所有英文单词与词组,输出 JSON:"
    '{"items":[{"word":"英文(单词或词组原形)","phonetic":"音标(无则空串)",'
    '"pos":"词性缩写如 n./v./adj.(无则空串)","meaning":"中文释义(无则空串)",'
    '"type":"word 或 phrase(多词为 phrase)"}]}。'
    "要求:只取词汇表里的词条,忽略例句/标题/页码;按出现顺序;识别不到返回 {\"items\":[]}。只返回纯 JSON。"
)


async def recognize_word_list(image_url: str) -> list[dict]:
    """词汇表图片 → 结构化单词/词组列表 [{word, phonetic, pos, meaning, type}]。失败返回 []。"""
    import json as _json
    if _is_doubao_dev_mode():
        return []
    client = AsyncOpenAI(api_key=settings.doubao_api_key, base_url=settings.doubao_base_url)
    try:
        resp = await client.chat.completions.create(
            model=settings.doubao_vision_model,
            messages=[
                {"role": "system", "content": _WORDLIST_SYS},
                {"role": "user", "content": [
                    {"type": "text", "text": _WORDLIST_USER},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]},
            ],
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        data = _json.loads(resp.choices[0].message.content or "{}")
        items = data.get("items") if isinstance(data, dict) else None
        return [it for it in (items or []) if isinstance(it, dict) and (it.get("word") or "").strip()]
    except Exception as exc:  # noqa: BLE001
        _log.warning("doubao word-list OCR failed: %s", exc)
        return []


async def recognize_page_text(image_url: str) -> str:
    """教材页图片 → 原样页面文字(供扫描件 PDF 走 OCR;与抽题用的 recognize 区分)。"""
    if _is_doubao_dev_mode():
        return ""
    client = AsyncOpenAI(api_key=settings.doubao_api_key, base_url=settings.doubao_base_url)
    try:
        resp = await client.chat.completions.create(
            model=settings.doubao_vision_model,
            messages=[
                {"role": "system", "content": _TEXT_OCR_SYS},
                {"role": "user", "content": [
                    {"type": "text", "text": "原样输出这页教材的全部文字。"},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ]},
            ],
            max_tokens=4096,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        _log.warning("doubao page OCR failed: %s", exc)
        return ""


class DoubaoVisionProvider:
    """豆包 Vision 实现的 OcrProvider。

    接口与 DualEngineOcrProvider 完全一致（recognize(image_url) → OcrResult），
    ocr_service.get_ocr_provider() 切换到本类后其余链路零改动。

    返回的 OcrResult：
      printed_text   — 豆包解析出的原始 JSON 字符串（供 paper_split_service 兼容处理）
      handwritten_text — 空字符串（豆包已在 printed_text JSON 里含学生答案，无需分离）
    """

    async def recognize(self, image_url: str) -> OcrResult:
        if _is_doubao_dev_mode():
            # 直出 JSON 格式（handwritten_text="" 触发 paper_split_service 的豆包直解析路径）
            return OcrResult(
                printed_text=_MOCK_DOUBAO_JSON,
                handwritten_text="",
            )

        client = AsyncOpenAI(
            api_key=settings.doubao_api_key,
            base_url=settings.doubao_base_url,
        )

        try:
            response = await client.chat.completions.create(
                model=settings.doubao_vision_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": _USER_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                        ],
                    },
                ],
                max_tokens=12288,   # 含短文原文(passages),给足预算防截断
            )
        except Exception as exc:
            _log.error("DoubaoVision API failed: %s", exc)
            raise

        raw = (response.choices[0].message.content or "").strip()

        # 豆包直接返回 JSON 数组字符串，存入 printed_text 供下游 paper_split_service
        # 的 _doubao_parse_direct() 方法直接解析，跳过传统 OCR 文字拼接步骤。
        return OcrResult(
            printed_text=raw,
            handwritten_text="",  # 豆包已在 JSON 里包含 student_answer，无需分离
        )
