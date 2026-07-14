"""LLM 调用清单(维护登记)——系统里每一处调 DeepSeek LLM 的地方 + 深度思考/对话 分档 + 原因。

单一真源:后台「LLM 调用清单」维护页从这里取。新增/改动 LLM 调用点时,请同步更新本表
(尤其给深度思考的调用补 `feature=` 标签,否则用量无法单独统计)。

字段:
- 所有 LLM 代码都在**后端** backend/app/services(见 locations);surface = **消费端(前端项目)**,module = 功能模块。
- surface:小程序端(miniprogram,含学生/教师/家长实时功能)/ 运营后台(admin,内容生产·真题·销售等)。
  依据「哪个 api 路由调用该 service」判定(如 ai_service←wrong_questions=学生端,curriculum_ai_service←admin=后台);
  同时被两端调用的按主要实时消费端归类。
- mode:reasoning(深度思考)= 不传 model= → 主模型/推理档(active_model,当前 deepseek-v4-pro),thinking 开;
  chat(对话)= 传 model=fast_model()(快档 deepseek-v4-flash)或 disable_thinking=True,规格明确无需重推理。
"""
from __future__ import annotations

# 每条:feature(有=用量可单独统计;None=未打标签)、mode、surface(端)、module(模块)、service、purpose、why、locations
LLM_FEATURES: list[dict] = [
    # ── 深度思考(reasoning / 推理档)──────────────────────────────────────────
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "错题本", "service": "ai_service",
     "purpose": "错题归因分析 + 讲解/订正建议", "why": "多步推断错因并生成结构化讲解,重推理", "locations": ["ai_service.py:92"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "从单元原文抽取整理成多篇课文段落", "why": "长文篇章理解 + 结构化重组,需推理判断边界", "locations": ["curriculum_ai_service.py:42"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "从零生成完整课程单元结构", "why": "整套课程内容规划 + 多步生成", "locations": ["curriculum_ai_service.py:270"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "从 PDF 文本生成课程单元", "why": "长文理解 + 课程结构生成", "locations": ["curriculum_ai_service.py:478"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "作文", "service": "essay_service",
     "purpose": "作文批改评分", "why": "综合评估语言/结构/内容,重推理判分", "locations": ["essay_service.py:57"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "作文", "service": "essay_service",
     "purpose": "作文审题(体裁/要点/人称时态/词数)", "why": "理解题干意图并推断隐含写作要求", "locations": ["essay_service.py:181"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "作文", "service": "essay_service",
     "purpose": "作文分阶段诊断 + 改写范文", "why": "诊断 + 改写范文需多步推理与质量判断", "locations": ["essay_service.py:244"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_classifier_service",
     "purpose": "题目归类到知识点", "why": "理解题意并映射到知识体系,属推断", "locations": ["kp_classifier_service.py:73"]},
    {"feature": "kp_lecture", "mode": "reasoning", "surface": "运营后台", "module": "知识点·讲义", "service": "kp_lecture_service",
     "purpose": "生成知识点讲解小节(Markdown 讲义)", "why": "组织知识并推理表达生成教学内容", "locations": ["kp_lecture_service.py:253"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_suggest_service",
     "purpose": "为一组题从目录建议匹配知识点", "why": "题干 × 知识目录匹配推断", "locations": ["kp_suggest_service.py:246"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_suggest_service",
     "purpose": "为一段文本建议知识点编码", "why": "文本→知识点语义推断", "locations": ["kp_suggest_service.py:289"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_suggest_service",
     "purpose": "整篇文章按范围收集建议知识点", "why": "篇章级知识点归纳推理", "locations": ["kp_suggest_service.py:354"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "真题·录入解析", "service": "ocr_parser_service",
     "purpose": "OCR 文本解析为结构化题目", "why": "从噪声 OCR 重建题目结构需推理纠错", "locations": ["ocr_parser_service.py:75"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "真题·仿真题", "service": "platform_question_service",
     "purpose": "真题改写生成仿真题变体", "why": "保持考点同时生成新内容,生成推理", "locations": ["platform_question_service.py:807"]},
    {"feature": "writing_sim", "mode": "reasoning", "surface": "运营后台", "module": "真题·仿真题", "service": "platform_question_service",
     "purpose": "真实写作题→仿真写作题(含范文解析)", "why": "生成题目 + model_essay 解析,重推理", "locations": ["platform_question_service.py:849"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "真题·仿真题", "service": "platform_question_service",
     "purpose": "整篇短文题组改写生成仿真题", "why": "篇章题组改写保持逻辑一致,生成推理", "locations": ["platform_question_service.py:941"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "练习", "service": "practice_service",
     "purpose": "按知识点生成练习题", "why": "从零命题需规划与生成,重推理", "locations": ["practice_service.py:196"]},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "题库·AI 生题", "service": "question_ai_service",
     "purpose": "AI 生题(多题型)", "why": "题目生成需内容规划与推理", "locations": ["question_ai_service.py:349"]},
    {"feature": "reading_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "阅读题解析(含定位句 evidence)", "why": "原文定位证据并推断答案依据", "locations": ["question_analysis_service.py:442"]},
    {"feature": "cloze_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "完形填空解析(线索 clue/slot)", "why": "结合上下文推断选词线索", "locations": ["question_analysis_service.py:530"]},
    {"feature": "writing_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "写作题解析(含 model_essay 范文)", "why": "范文生成 + 解析,重推理", "locations": ["question_analysis_service.py:645"]},
    {"feature": "grammar_mc_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "语法选择题解析(含 kp_codes)", "why": "推断考点并解释语法逻辑", "locations": ["question_analysis_service.py:713"]},
    {"feature": "word_fill_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "词形填空解析(kp_codes + change_type)", "why": "推断词形变化类型与考点", "locations": ["question_analysis_service.py:775"]},
    {"feature": "passage_fill_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "短文填空解析(含 clue)", "why": "篇章填空上下文推断", "locations": ["question_analysis_service.py:839"]},
    {"feature": "sentence_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "句子改写/翻译题解析(kp_codes + target_structure)", "why": "推断目标结构与考点", "locations": ["question_analysis_service.py:904"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "读写表达", "service": "reading_expression_service",
     "purpose": "读写表达题批改评分", "why": "开放作答判分需语义理解与推理", "locations": ["reading_expression_service.py:63"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "口语", "service": "speaking_dialogue_service",
     "purpose": "口语教练:鼓励 + 纠错反馈", "why": "结合发音数据给个性化教学反馈", "locations": ["speaking_dialogue_service.py:659"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "口语", "service": "speaking_dialogue_service",
     "purpose": "口语场景对话:AI 角色回复", "why": "理解语境生成自然连贯回复", "locations": ["speaking_dialogue_service.py:720"]},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "口语", "service": "speaking_dialogue_service",
     "purpose": "整段口语对话总结与评价", "why": "综合多轮对话做评估总结", "locations": ["speaking_dialogue_service.py:960"]},
    {"feature": "writing_grade", "mode": "reasoning", "surface": "小程序端", "module": "作文·判分", "service": "writing_grade_service",
     "purpose": "依据解析/范文逐点批改作文", "why": "判分 + 逐点反馈需多维推理", "locations": ["writing_grade_service.py:130"]},

    # ── 对话(chat / 快档,规格明确无需重推理)────────────────────────────────
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "单元文本解析为结构化字段(挑索引)", "why": "输出小、规格明确;走 fast 避免主模型耗预算返空", "locations": ["curriculum_ai_service.py:107"]},
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "教材·单词", "service": "curriculum_vocab_service",
     "purpose": "从文本抽取单词/词组列表", "why": "纯抽取、固定 JSON 格式", "locations": ["curriculum_vocab_service.py:139"]},
    {"feature": "grammar_probe", "mode": "chat", "surface": "小程序端", "module": "语法", "service": "grammar_probe_service",
     "purpose": "生成语法识别/检测探针题 + 迁移题种子", "why": "固定字段 + validate 校验,快档即可", "locations": ["grammar_probe_service.py:155", "grammar_probe_service.py:365"]},
    {"feature": "grammar_produce", "mode": "chat", "surface": "小程序端", "module": "语法", "service": "grammar_probe_service",
     "purpose": "语法造句作答按维度打分", "why": "打分维度固定、规格明确", "locations": ["grammar_probe_service.py:293"]},
    {"feature": "kp_match", "mode": "chat", "surface": "运营后台", "module": "知识点·整卷匹配", "service": "kp_match_service",
     "purpose": "从候选知识点受控单选最匹配项", "why": "受控单选、max_tokens=128,显式 disable_thinking 提速", "locations": ["kp_match_service.py:111"]},
    {"feature": "ls_analyze", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "长难句成分切分/结构分析", "why": "结构化抽取,有 validate/升档兜底,关思考提速", "locations": ["long_sentence_service.py:389"]},
    {"feature": "ls_paraphrase", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "长句同义改写选择题", "why": "固定选项格式、规格明确", "locations": ["long_sentence_service.py:435"]},
    {"feature": "ls_translate", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "长句翻译作答按维度打分", "why": "打分维度固定(_TRANS_DIMS)", "locations": ["long_sentence_service.py:661"]},
    {"feature": "ls_verify_subj", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "主观验证题作答是否通过(pass 布尔)", "why": "二分判定、max_tokens=64", "locations": ["long_sentence_service.py:769"]},
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "长难句·录入", "service": "long_sentence_upload_service",
     "purpose": "上传文本解析为长难句列表入库", "why": "纯抽取、固定 JSON 格式", "locations": ["long_sentence_upload_service.py:55"]},
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "真题·录入解析", "service": "paper_split_service",
     "purpose": "整卷 OCR 文本切分为题目/短文块", "why": "切分规格明确、输出固定,快档处理长文", "locations": ["paper_split_service.py:508"]},
    {"feature": "sales_intent", "mode": "chat", "surface": "运营后台", "module": "电销·意向分析", "service": "sales_analysis_service",
     "purpose": "销售通话转写→意向分析打分", "why": "抽取 + 固定打分规格,有 validate 兜底", "locations": ["sales_analysis_service.py:88"]},
    {"feature": "vocab_enrich", "mode": "chat", "surface": "小程序端", "module": "词力通", "service": "vocab_intensive_service",
     "purpose": "补全单词释义/例句/短语", "why": "词典式抽取、固定字段", "locations": ["vocab_intensive_service.py:165"]},
    {"feature": "vocab_image_brief", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "单词配图用视觉简述", "why": "短文本生成、max_tokens=256,关思考提速", "locations": ["vocab_media_service.py:218"]},
    {"feature": "vocab_en_desc", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "用简单英文(A2)解释单词", "why": "固定简短输出、规格明确", "locations": ["vocab_media_service.py:298"]},
    {"feature": "vocab_example", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "生成单词例句 + 短语(含中译 JSON)", "why": "固定 JSON 结构、A2 简单句", "locations": ["vocab_media_service.py:324"]},
    {"feature": "vocab_video_motion", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "判断单词可否动画化 + 动作描述", "why": "规格明确,有 validate 与升档兜底", "locations": ["vocab_media_service.py:503"]},
    {"feature": "vocab_probe", "mode": "chat", "surface": "小程序端", "module": "词力通", "service": "vocab_probe_service",
     "purpose": "生成单词探针题(干扰项/误区/搭配)+ 迁移例句", "why": "固定字段 + validate 校验", "locations": ["vocab_probe_service.py:85", "vocab_probe_service.py:375"]},
    {"feature": "vocab_produce", "mode": "chat", "surface": "小程序端", "module": "词力通", "service": "vocab_probe_service",
     "purpose": "单词造句作答按维度打分", "why": "打分维度固定(_PROD_DIMS)", "locations": ["vocab_probe_service.py:298"]},
]


def counts() -> dict:
    r = sum(1 for e in LLM_FEATURES if e["mode"] == "reasoning")
    c = sum(1 for e in LLM_FEATURES if e["mode"] == "chat")
    untagged = sum(1 for e in LLM_FEATURES if not e["feature"])
    mini = sum(1 for e in LLM_FEATURES if e["surface"] == "小程序端")
    admin = sum(1 for e in LLM_FEATURES if e["surface"] == "运营后台")
    return {"total": len(LLM_FEATURES), "reasoning": r, "chat": c, "untagged": untagged,
            "mini": mini, "admin": admin}
