"""V2 仿真题 AI 生成 service（D-079 / M3a；D-091 维度感知）。

调 DeepSeek 为某个知识点 + 某个维度生成 N 道题。维度决定题型与 prompt：
- listening 听力：读对话/短文做理解（文本近似，真音频留待 M2.5），题型 单选/阅读
- dictation 听写：拼写填空，题型 填空
- grammar 语法：单选/填空/判断/完型/阅读/写作/连线 混合（原行为）
- writing 写作：作文 + 连线
dev mode 返回固定结构供前端/集成测试无 key 时跑通。
"""
from __future__ import annotations

import json

from app.core.exceptions import AppError
from app.schemas.questions import AIGeneratedQuestion
from app.services.llm_provider import chat_completion, is_llm_dev_mode

_SYSTEM_PROMPT = (
    "你是中国中小学英语命题老师，按知识点和指定维度出仿真题。"
    "严格按 JSON 数组输出，不要任何 markdown 代码块或额外文字。"
)

# ─── grammar（语法，原行为）─────────────────────────────────────────────────
_GRAMMAR_PROMPT = """请为以下知识点生成 {count} 道语法仿真题。

知识点名称：{kp_name}
分类：{kp_category}
描述：{kp_description}

题型分配（{count} 道，建议比例）：
- 单选 ≥ 1 道：4 个选项，标记 A-D，answer 是单个字母
- 填空 ≥ 1 道：options 为 null，answer 可用 | 分隔多个合法答案（如 "goes|go"）
- 判断 ≥ 1 道：options 为 null，answer 是 "对" 或 "错"
- 完型 0-1 道：stem 是含 1 个空白的短文（< 80 字），4 个选项，answer 单字母
- 阅读 0-1 道：stem 是 100-150 字短文 + 一个理解问题，4 个选项，answer 单字母

每题必须含 explanation（≥ 20 字解析）和 difficulty（1-5）。

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "单选", "stem": "...", "options": ["A. ...","B. ...","C. ...","D. ..."], "answer": "B", "explanation": "...", "difficulty": 2}},
  {{"question_type": "填空", "stem": "He ___ to school every day.", "options": null, "answer": "goes", "explanation": "...", "difficulty": 2}},
  {{"question_type": "判断", "stem": "...", "options": null, "answer": "错", "explanation": "...", "difficulty": 1}}
]"""

# ─── listening（听力，文本近似）──────────────────────────────────────────────
_LISTENING_PROMPT = """请为以下知识点生成 {count} 道"听力理解"仿真题（暂用文本呈现听力材料，不含音频）。

知识点名称：{kp_name}
描述：{kp_description}

要求：
- 题型只用 单选 或 阅读
- 每题 stem 必须先给一段"听力材料"（一段 2-4 句的英文对话或短独白），再提一个理解问题（中文或英文）
- 4 个选项标记 A-D，answer 是单个字母
- 难度贴近该知识点对应年级
- 每题含 explanation（≥ 20 字，说明从材料哪句得出答案）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "单选", "stem": "听力材料：\\nA: What time do you get up?\\nB: I get up at seven.\\n问题：B 几点起床？", "options": ["A. 6点","B. 7点","C. 8点","D. 9点"], "answer": "B", "explanation": "B 说 at seven，即 7 点。", "difficulty": 2}}
]"""

# ─── dictation（听写，拼写）──────────────────────────────────────────────────
_DICTATION_PROMPT = """请为以下知识点生成 {count} 道"听写/拼写"仿真题（暂用文本呈现，不含音频）。

知识点名称：{kp_name}
描述：{kp_description}

要求：
- 题型只用 填空
- 每题考查一个英文单词或短语的拼写：stem 给中文释义 + 一句含空白的英文例句（如"苹果：I eat an ___ every day."）
- options 为 null；answer 是要拼写的英文单词（多个合法拼写可用 | 分隔，如 "colour|color"）
- 每题含 explanation（≥ 20 字，可给音节/词性提示）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "填空", "stem": "苹果：I eat an ___ every day.", "options": null, "answer": "apple", "explanation": "apple /ˈæpəl/ 名词，意为苹果。", "difficulty": 1}}
]"""

# ─── writing（写作）──────────────────────────────────────────────────────────
_WRITING_PROMPT = """请为以下知识点生成 {count} 道"写作"仿真题。

知识点名称：{kp_name}
描述：{kp_description}

题型分配：
- 写作 ≥ 大部分：stem 是写作要求（如"以 My weekend 为题写 30-50 字"），options 为 null，answer 是 80-200 字参考范文
- 连线 0-2 道：stem 列左侧 1-4 项中文/句子片段、右侧 A-D 项英文，options 为 null，answer 用 | 分隔的对儿（"1-A|2-B|3-C"）

每题含 explanation（≥ 20 字，写作题说明评分要点/范文亮点）和 difficulty（1-5）。

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "写作", "stem": "请以 My favorite animal 为题写 30 字短文。", "options": null, "answer": "My favorite animal is the dog. Dogs are friendly and loyal...", "explanation": "范文应包含主题句 + 2-3 个支持细节。", "difficulty": 3}}
]"""

# ─── verb_fill（动词填空：给动词原形填正确形式，反向由考点生成）──────────────────
# 输出仍用 Literal 允许的「填空」外壳；最终题型由持久层按维度盖成「动词填空」（P0）。
_VERB_FILL_PROMPT = """请为以下语法考点生成 {count} 道"动词填空"仿真题。

考点名称：{kp_name}
分类：{kp_category}
描述：{kp_description}

命题要求（这是中考核心题型，务必扣住该考点）：
- 题型统一填 "填空"，options 为 null
- 每题：一句（或含 1-2 句语境的）英文，句中给出动词原形放在括号里，挖空让考生填该考点要求的正确形式
- 句子必须自带"判定线索"：时间状语 / 从句引导词 / 主语数 / 上下文，使正确形式唯一或有限可判
- answer 是填入空格的动词形式；多个合法形式用 | 分隔（如 "has gone|has been to" 视考点而定）
- stem 里用 ___ 标空，并在其后用括号给出原形，形如："By the time we arrived, the film ___ (begin) already."
- 每题含 explanation（≥ 20 字，点明依据哪个线索、该考点用什么形式）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "填空", "stem": "Look! The children ___ (play) football on the playground.", "options": null, "answer": "are playing", "explanation": "Look! 提示现在正在发生，用现在进行时 are playing。", "difficulty": 2}}
]"""

# ─── vocab_form（词汇运用：用所给词适当形式填空）─────────────────────────────
_VOCAB_FORM_PROMPT = """请为以下考点生成 {count} 道"词汇运用（用所给词的适当形式填空）"仿真题。

考点名称：{kp_name}
分类：{kp_category}
描述：{kp_description}

命题要求：
- 题型统一填 "填空"，options 为 null
- 每题：一句英文语境，给出一个词的原形（名词/形容词/副词/数词/动词等），挖空让考生填该考点要求的正确"词形"
  （如名词单复数/所有格、形容词副词比较级最高级、副词化、派生构词、动词非谓语等）
- stem 用 ___ 标空并在其后括号给出所给词，形如："There are three ___ (knife) on the table."
- answer 是正确词形；多个合法答案用 | 分隔
- 每题含 explanation（≥ 20 字，说明为什么用该词形）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "填空", "stem": "There are three ___ (knife) on the table.", "options": null, "answer": "knives", "explanation": "three 后接可数名词复数，knife 以 -fe 结尾变复数为 knives。", "difficulty": 2}}
]"""

# ─── reading（阅读理解：按 rc-* 阅读微技能反向出「短文 + 该技能一问」）──────────────
# P1:kp_name 即具体阅读技能(细节理解/推理判断/主旨大意/词义猜测/观点态度/篇章结构)。
_READING_PROMPT = """请为以下"阅读理解"考点生成 {count} 道阅读微题（每题自带一小段短文）。

考点名称（= 具体阅读技能）：{kp_name}
描述：{kp_description}

命题要求（务必扣住该阅读技能，题目只考这一种技能）：
- 题型统一填 "阅读"
- 每题 stem = 一小段英文短文（60-110 词，题材贴近中小学）+ 换行后一个针对【{kp_name}】的理解问题
- 4 个选项标记 A-D，answer 是单个字母；干扰项要贴合该技能的典型陷阱
  （细节题→原文近似词误配；主旨题→以偏概全/局部当整体；推理题→过度推断/原文未提）
- 每题含 explanation（≥ 20 字，说明从短文哪一句、用该技能如何得出答案）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "阅读", "stem": "Tom gets up at six every morning. He runs for half an hour and then has breakfast...\\n问题：When does Tom run?", "options": ["A. Before breakfast", "B. After school", "C. At noon", "D. Before sleep"], "answer": "A", "explanation": "短文说 runs ... and then has breakfast，即跑步在早餐前，据细节定位选 A。", "difficulty": 2}}
]"""

# ─── cloze（完形填空：按 词法/搭配/篇章衔接 反向出「单空语境题」）──────────────────
_CLOZE_PROMPT = """请为以下考点生成 {count} 道"完形填空"微题（每题一个空，考一种能力）。

考点名称：{kp_name}
描述：{kp_description}

命题要求：
- 题型统一填 "完型"
- 每题 stem = 一小段 1-3 句英文语境（< 60 词），其中留 1 个空白（用 ___ 标出），空白处考【{kp_name}】
  （如实词词义辨析 / 固定搭配与介词 / 逻辑连接词 / 据上下文推断）
- 4 个选项标记 A-D，answer 是单个字母；干扰项为该考点的典型混淆词
- 每题含 explanation（≥ 20 字，说明依据语境为何选此项）和 difficulty（1-5）

返回纯 JSON 数组（不要 markdown）：
[
  {{"question_type": "完型", "stem": "It was raining hard, ___ we stayed at home and watched TV.", "options": ["A. but", "B. so", "C. or", "D. though"], "answer": "B", "explanation": "前后是因果关系（下大雨→待在家），用 so 连接，故选 B。", "difficulty": 2}}
]"""

_PROMPT_BY_DIMENSION = {
    "grammar": _GRAMMAR_PROMPT,
    "listening": _LISTENING_PROMPT,
    "dictation": _DICTATION_PROMPT,
    "writing": _WRITING_PROMPT,
    "verb_fill": _VERB_FILL_PROMPT,
    "vocab_form": _VOCAB_FORM_PROMPT,
    "reading": _READING_PROMPT,
    "cloze": _CLOZE_PROMPT,
}


# ─── dev-mock 题集（按维度）────────────────────────────────────────────────

def _mock_grammar(kp_name: str) -> list[AIGeneratedQuestion]:
    """语法维度：保留覆盖全部 7 种题型的固定集（兼容 count=9 全类型测试）。"""
    return [
        AIGeneratedQuestion(question_type="单选", stem=f"Mock 单选题 1 about {kp_name}.",
            options=["A. mock1", "B. mock2", "C. mock3", "D. mock4"], answer="B",
            explanation="Mock 解析：答案是 B 因为...", difficulty=2),
        AIGeneratedQuestion(question_type="单选", stem=f"Mock 单选题 2 about {kp_name}.",
            options=["A. opt1", "B. opt2", "C. opt3", "D. opt4"], answer="A",
            explanation="Mock 解析：选 A 是因为...", difficulty=3),
        AIGeneratedQuestion(question_type="填空", stem=f"Mock 填空题 1 about {kp_name}: He ___ play.",
            options=None, answer="can|may", explanation="Mock 解析：can 和 may 都接受。", difficulty=2),
        AIGeneratedQuestion(question_type="填空", stem=f"Mock 填空题 2 about {kp_name}: She ___ home.",
            options=None, answer="went", explanation="Mock 解析：went 是 go 的过去式。", difficulty=3),
        AIGeneratedQuestion(question_type="判断", stem=f"Mock 判断题 about {kp_name}: This rule applies always.",
            options=None, answer="错", explanation="Mock 解析：并非总是适用。", difficulty=1),
        AIGeneratedQuestion(question_type="完型", stem=f"Mock 完型 about {kp_name}: Tom ___ to school.",
            options=["A. go", "B. goes", "C. going", "D. went"], answer="B",
            explanation="Mock 解析：第三人称单数用 goes。", difficulty=2),
        AIGeneratedQuestion(question_type="阅读", stem=f"Mock 阅读 about {kp_name}: Read passage and answer. What is the topic?",
            options=["A. animals", "B. food", "C. school", "D. home"], answer="C",
            explanation="Mock 解析：根据文章主题判断。", difficulty=3),
        AIGeneratedQuestion(question_type="写作", stem=f"Mock 写作 about {kp_name}: 写一篇 30 字短文。",
            options=None, answer="This is a mock sample essay. It is short and demonstrates the topic clearly with simple English vocabulary.",
            explanation="Mock 参考范文。", difficulty=3),
        AIGeneratedQuestion(question_type="连线", stem=f"Mock 连线 about {kp_name}: 1.cat 2.dog 3.bird | A.猫 B.狗 C.鸟",
            options=None, answer="1-A|2-B|3-C", explanation="Mock 解析：对应关系。", difficulty=1),
    ]


def _mock_listening(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="单选",
            stem=f"听力材料（{kp_name}）：\nA: What time do you get up?\nB: I get up at seven.\n问题：B 几点起床？",
            options=["A. 6点", "B. 7点", "C. 8点", "D. 9点"], answer="B",
            explanation="Mock 解析：B 说 at seven，即 7 点。", difficulty=2),
        AIGeneratedQuestion(question_type="阅读",
            stem=f"听力短文（{kp_name}）：Tom likes apples. He eats one every morning.\n问题：Tom 早上吃什么？",
            options=["A. Banana", "B. Apple", "C. Orange", "D. Grape"], answer="B",
            explanation="Mock 解析：短文说 eats one(apple) every morning。", difficulty=2),
        AIGeneratedQuestion(question_type="单选",
            stem=f"听力对话（{kp_name}）：\nA: How are you?\nB: I'm fine, thank you.\n问题：B 现在怎么样？",
            options=["A. 很好", "B. 生病", "C. 难过", "D. 生气"], answer="A",
            explanation="Mock 解析：B 说 I'm fine。", difficulty=1),
    ]


def _mock_dictation(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="填空", stem=f"听写（{kp_name}）苹果：I eat an ___ every day.",
            options=None, answer="apple", explanation="Mock 解析：apple 名词，苹果。", difficulty=1),
        AIGeneratedQuestion(question_type="填空", stem=f"听写（{kp_name}）学校：I go to ___ by bus.",
            options=None, answer="school", explanation="Mock 解析：school 名词，学校。", difficulty=1),
        AIGeneratedQuestion(question_type="填空", stem=f"听写（{kp_name}）颜色：Red is my favourite ___.",
            options=None, answer="colour|color", explanation="Mock 解析：英式 colour / 美式 color 均可。", difficulty=2),
    ]


def _mock_writing(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="写作", stem=f"写作（{kp_name}）：请以 My weekend 为题写 30 字短文。",
            options=None, answer="On weekends I usually do my homework and play with my friends. I also help my mother...",
            explanation="Mock 参考范文：主题句 + 细节。", difficulty=3),
        AIGeneratedQuestion(question_type="连线", stem=f"连线（{kp_name}）：1.早上 2.中午 3.晚上 | A.evening B.morning C.noon",
            options=None, answer="1-B|2-C|3-A", explanation="Mock 解析：时间词对应。", difficulty=1),
        AIGeneratedQuestion(question_type="写作", stem=f"写作（{kp_name}）：介绍你最喜欢的食物，30-50 字。",
            options=None, answer="My favorite food is dumplings. They are delicious and my grandma makes them well...",
            explanation="Mock 参考范文。", difficulty=3),
    ]


def _mock_verb_fill(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="填空", stem=f"动词填空（{kp_name}）：Look! The boy ___ (run) very fast.",
            options=None, answer="is running", explanation="Mock 解析：Look! 提示现在进行，用 is running。", difficulty=2),
        AIGeneratedQuestion(question_type="填空", stem=f"动词填空（{kp_name}）：He ___ (finish) his homework yesterday.",
            options=None, answer="finished", explanation="Mock 解析：yesterday 提示一般过去时，用 finished。", difficulty=2),
        AIGeneratedQuestion(question_type="填空", stem=f"动词填空（{kp_name}）：The window ___ (break) by Tom just now.",
            options=None, answer="was broken", explanation="Mock 解析：by 提示被动，just now 提示过去，用 was broken。", difficulty=3),
    ]


def _mock_vocab_form(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="填空", stem=f"词汇运用（{kp_name}）：There are three ___ (knife) on the table.",
            options=None, answer="knives", explanation="Mock 解析：three 后接复数，knife→knives。", difficulty=2),
        AIGeneratedQuestion(question_type="填空", stem=f"词汇运用（{kp_name}）：This box is ___ (heavy) than that one.",
            options=None, answer="heavier", explanation="Mock 解析：than 提示比较级，heavy→heavier。", difficulty=2),
        AIGeneratedQuestion(question_type="填空", stem=f"词汇运用（{kp_name}）：She sang the song ___ (beautiful).",
            options=None, answer="beautifully", explanation="Mock 解析：修饰动词 sang 用副词 beautifully。", difficulty=2),
    ]


def _mock_reading(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="阅读",
            stem=f"阅读微题（{kp_name}）：Tom gets up at six every morning. He runs for half an hour and then has breakfast.\n问题：When does Tom run?",
            options=["A. Before breakfast", "B. After school", "C. At noon", "D. Before sleep"], answer="A",
            explanation="Mock 解析：runs ... and then has breakfast，跑步在早餐前，据细节选 A。", difficulty=2),
        AIGeneratedQuestion(question_type="阅读",
            stem=f"阅读微题（{kp_name}）：The library is quiet. Students read and study there every day.\n问题：What is the passage mainly about?",
            options=["A. A park", "B. The library", "C. A shop", "D. A game"], answer="B",
            explanation="Mock 解析：全篇围绕 library，主旨选 B。", difficulty=2),
    ]


def _mock_cloze(kp_name: str) -> list[AIGeneratedQuestion]:
    return [
        AIGeneratedQuestion(question_type="完型",
            stem=f"完形微题（{kp_name}）：It was raining hard, ___ we stayed at home.",
            options=["A. but", "B. so", "C. or", "D. though"], answer="B",
            explanation="Mock 解析：因果关系用 so，故选 B。", difficulty=2),
        AIGeneratedQuestion(question_type="完型",
            stem=f"完形微题（{kp_name}）：She is good ___ playing the piano.",
            options=["A. at", "B. in", "C. on", "D. of"], answer="A",
            explanation="Mock 解析：固定搭配 be good at，选 A。", difficulty=2),
    ]


_MOCK_BY_DIMENSION = {
    "grammar": _mock_grammar,
    "listening": _mock_listening,
    "dictation": _mock_dictation,
    "writing": _mock_writing,
    "verb_fill": _mock_verb_fill,
    "vocab_form": _mock_vocab_form,
    "reading": _mock_reading,
    "cloze": _mock_cloze,
}


def _make_mock_questions(
    kp_name: str, dimension: str, count: int
) -> list[AIGeneratedQuestion]:
    """dev mock：按维度取对应固定题集，循环填满 count 道。"""
    base = _MOCK_BY_DIMENSION.get(dimension, _mock_grammar)(kp_name)
    return [base[i % len(base)] for i in range(count)]


async def generate_questions(
    *,
    kp_name: str,
    kp_category: str,
    kp_description: str | None,
    dimension: str = "grammar",
    count: int = 5,
) -> list[AIGeneratedQuestion]:
    """为 1 个 KP 的指定维度生成 count 道仿真题。"""
    if is_llm_dev_mode():
        return _make_mock_questions(kp_name, dimension, count)

    template = _PROMPT_BY_DIMENSION.get(dimension, _GRAMMAR_PROMPT)
    prompt = template.format(
        count=count,
        kp_name=kp_name,
        kp_category=kp_category,
        kp_description=kp_description or "(无)",
    )

    try:
        response = await chat_completion(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=prompt,
            max_tokens=8192,
        )
    except Exception as exc:
        raise AppError(code=502, message=f"AI 生题失败：{exc}") from exc

    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.rstrip().endswith("```"):
            raw = raw.rstrip()[:-3].rstrip()

    try:
        # strict=False 允许字符串内出现裸换行/制表符（DeepSeek 偶尔直接输出真实换行）
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc

    if not isinstance(data, list):
        raise AppError(code=500, message="AI 生题返回格式异常")

    try:
        return [AIGeneratedQuestion(**item) for item in data]
    except Exception as exc:
        raise AppError(code=500, message="AI 生题返回格式异常") from exc
