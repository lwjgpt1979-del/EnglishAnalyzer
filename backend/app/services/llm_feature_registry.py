"""LLM 调用清单(维护登记)——系统里每一处调 DeepSeek LLM 的地方 + 深度思考/对话 分档 + 原因 + 缓存。

单一真源:后台「LLM 调用清单」维护页从这里取。新增/改动 LLM 调用点时,请同步更新本表
(尤其给深度思考的调用补 `feature=` 标签,否则用量无法单独统计)。

字段:
- 所有 LLM 代码都在**后端** backend/app/services(见 locations);surface = **消费端(前端项目)**,module = 功能模块。
- surface:小程序端(miniprogram,含学生/教师/家长实时功能)/ 运营后台(admin,内容生产·真题·销售等)。
  依据「哪个 api 路由调用该 service」判定(如 wrong_questions=学生端,curriculum_ai_service←admin=后台);
  同时被两端调用的按主要实时消费端归类。
- mode:reasoning(深度思考)= 不传 model= → 主模型/推理档(active_model,当前 deepseek-v4-pro),thinking 开;
  chat(对话)= 传 model=fast_model()(快档 deepseek-v4-flash)或 disable_thinking=True,规格明确无需重推理。
- cache(防重复付费维度,对应「第三方付费暂存」铁律):
  global = 按内容 hash / 业务主键缓存,跨用户同输入不二次付费(如 probes_json、paper_split_cache、meta.analysis);
  per_user = 结果随业务表天然持久化、同(用户,内容)不重调(如作文批改落 Essay 行);
  none = 实时真调不复用(判分/对话/内容生产触发即真调)。store = 缓存/落库位置(表.字段),none 时为「无」。
"""
from __future__ import annotations

# 每条:feature、mode、surface(端)、module(模块)、service、purpose、why、locations、cache(缓存作用域)、store(缓存位置)
LLM_FEATURES: list[dict] = [
    # ── 深度思考(reasoning / 推理档)──────────────────────────────────────────
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "从单元原文抽取整理成多篇课文段落", "why": "长文篇章理解 + 结构化重组,需推理判断边界", "locations": ["curriculum_ai_service.py:42"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "从零生成完整课程单元结构", "why": "整套课程内容规划 + 多步生成", "locations": ["curriculum_ai_service.py:270"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "从 PDF 文本生成课程单元", "why": "长文理解 + 课程结构生成", "locations": ["curriculum_ai_service.py:478"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "作文", "service": "essay_service",
     "purpose": "作文批改评分", "why": "综合评估语言/结构/内容,重推理判分", "locations": ["essay_service.py:57"], "cache": "per_user", "store": "essay.polished_text / essay.dimensions"},
    {"feature": "essay_analyze", "mode": "reasoning", "surface": "小程序端", "module": "作文·提问式审题", "service": "essay_service",
     "purpose": "作文审题(体裁/要点/人称时态/词数)+ 四卡审题的干扰项与体裁讲解", "why": "理解题干意图、推断隐含写作要求、造似是而非干扰项", "locations": ["essay_service.py:analyze_prompt"], "cache": "none", "store": "无"},
    {"feature": "essay_upgrade", "mode": "chat", "surface": "小程序端", "module": "作文·逐句升级", "service": "essay_service",
     "purpose": "挑 3-5 句平句升成高分句,优先套用学生已学过的长难句句式(from_mine 标注)", "why": "受控改写、规格明确(给定原句+可套句式清单)、fast 档即可", "locations": ["essay_service.py:upgrade_sentences"], "cache": "none", "store": "无"},
    {"feature": "essay_adapt_sentence", "mode": "chat", "surface": "小程序端", "module": "作文·搭作文(自学句适配)", "service": "essay_service",
     "purpose": "搭作文时把学生已学长难句改写/适配到各段功能(称呼/开头/主体/结尾),每段给贴合本题的候选句", "why": "受控改写、给定句式+段功能、fast 档即可", "locations": ["essay_service.py:adapt_sentences"], "cache": "per-user", "store": "essay_adapt_cache(按 学生+体裁段句集md5 缓存,同输入不二次付费)"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "作文", "service": "essay_service",
     "purpose": "作文分阶段诊断 + 改写范文", "why": "诊断 + 改写范文需多步推理与质量判断", "locations": ["essay_service.py:244"], "cache": "per_user", "store": "essay.dimensions(kind=exam_diagnose)"},
    {"feature": "kp_classify", "mode": "chat", "surface": "小程序端", "module": "作业上传·题目归类", "service": "kp_classifier_service",
     "purpose": "整卷题目批量归类到知识点", "why": "题干→知识点映射抽取,规格明确,关思考走快档(开思考会截断致整卷失败)", "locations": ["kp_classifier_service.py:73"], "cache": "global", "store": "kp_classify_cache.kp_key(按小题 content_md5)"},
    {"feature": "paper_split", "mode": "chat", "surface": "小程序端", "module": "作业上传·拆题", "service": "paper_split_service",
     "purpose": "整卷 OCR 文字拆成结构化题目", "why": "结构化抽取,关思考走快档防长卷 JSON 截断", "locations": ["paper_split_service.py:508"], "cache": "global", "store": "paper_split_cache.raw_json(按 input_md5)"},
    {"feature": "paper_title", "mode": "chat", "surface": "小程序端", "module": "作业上传", "service": "user_paper_service",
     "purpose": "从上传作业文字里提取标题名(自动命名)", "why": "规格明确的短标题抽取,关思考走快档", "locations": ["user_paper_service.py:96"], "cache": "per_user", "store": "user_uploaded_paper.title(上游图 md5 去重复用)"},
    {"feature": "practice_gen", "mode": "chat", "surface": "小程序端", "module": "练习·练同类", "service": "practice_service",
     "purpose": "按知识点生成仿真练习题", "why": "结构化出题、规格明确,关思考走快档(开思考会截断致出题500)", "locations": ["practice_service.py:196"], "cache": "global", "store": "ai_question.content(按 knowledge_point,先查池够则不调)"},
    {"feature": "reading_qtype_classify", "mode": "chat", "surface": "小程序端", "module": "作业·阅读学情(题型按需,学情统计P1)", "service": "reading_qtype_service",
     "purpose": "把未精讲的作业阅读小题归类到固定题型(细节/主旨/推理/词义/态度/指代/图表/其他)", "why": "规格明确的单标签分类,快档即可,不占推理档;学生端学情页按需补标,非后台批量", "locations": ["reading_qtype_service.py:classify_missing"], "cache": "global", "store": "user_paper_questions.reading_skill(按题内容 md5 去重,同内容只调一次;回填优先)"},
    {"feature": "section_type_classify", "mode": "chat", "surface": "小程序端", "module": "作业上传·大题题型识别(β预留)", "service": "paper_section_taxonomy",
     "purpose": "无大题标题时对题面文本推断规范 section_type(P0 未接通,恒走规则 α)", "why": "规格明确的单标签分类,快档;按文本 md5 全局缓存", "locations": ["paper_section_taxonomy.py:classify_section_cached"], "cache": "global", "store": "section_type_cache(预留未建表);P0 classify_section_cached 返回 None"},
    {"feature": "kp_lecture", "mode": "reasoning", "surface": "运营后台", "module": "知识点·讲义", "service": "kp_lecture_service",
     "purpose": "生成知识点讲解小节(Markdown 讲义)", "why": "组织知识并推理表达生成教学内容", "locations": ["kp_lecture_service.py:253"], "cache": "global", "store": "grammar_lecture_cache.sections / kp_lecture.content_md"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_suggest_service",
     "purpose": "为一组题从目录建议匹配知识点", "why": "题干 × 知识目录匹配推断", "locations": ["kp_suggest_service.py:246"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_suggest_service",
     "purpose": "为一段文本建议知识点编码", "why": "文本→知识点语义推断", "locations": ["kp_suggest_service.py:289"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "知识点·题目归类", "service": "kp_suggest_service",
     "purpose": "整篇文章按范围收集建议知识点", "why": "篇章级知识点归纳推理", "locations": ["kp_suggest_service.py:354"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "真题·录入解析", "service": "ocr_parser_service",
     "purpose": "OCR 文本解析为结构化题目", "why": "从噪声 OCR 重建题目结构需推理纠错", "locations": ["ocr_parser_service.py:75"], "cache": "none", "store": "无(结构化题目由调用方落 UploadedQuestion)"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "真题·仿真题", "service": "platform_question_service",
     "purpose": "真题改写生成仿真题变体", "why": "保持考点同时生成新内容,生成推理", "locations": ["platform_question_service.py:807"], "cache": "none", "store": "无(仿真题落 platform_question,非防重付费缓存)"},
    {"feature": "writing_sim", "mode": "reasoning", "surface": "运营后台", "module": "真题·仿真题", "service": "platform_question_service",
     "purpose": "真实写作题→仿真写作题(含范文解析)", "why": "生成题目 + model_essay 解析,重推理", "locations": ["platform_question_service.py:849"], "cache": "none", "store": "无(仿真写作题落 platform_question)"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "真题·仿真题", "service": "platform_question_service",
     "purpose": "整篇短文题组改写生成仿真题", "why": "篇章题组改写保持逻辑一致,生成推理", "locations": ["platform_question_service.py:941"], "cache": "none", "store": "无(题组仿真题落 platform_question)"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "练习", "service": "practice_service",
     "purpose": "按知识点生成练习题", "why": "从零命题需规划与生成,重推理", "locations": ["practice_service.py:196"], "cache": "global", "store": "ai_question.content(按 knowledge_point)"},
    {"feature": None, "mode": "reasoning", "surface": "运营后台", "module": "题库·AI 生题", "service": "question_ai_service",
     "purpose": "AI 生题(多题型)", "why": "题目生成需内容规划与推理", "locations": ["question_ai_service.py:349"], "cache": "none", "store": "无(题目由调用方落库)"},
    {"feature": "reading_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "阅读题解析(含定位句 evidence)", "why": "原文定位证据并推断答案依据", "locations": ["question_analysis_service.py:442"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis(按题)"},
    {"feature": "reading_analysis", "mode": "chat", "surface": "小程序端", "module": "作业精讲·阅读理解精讲", "service": "reading_intensive_service",
     "purpose": "上传作业阅读题·题目层解析(题型/定位句/为何对/干扰项)", "why": "结构化抽取,关思考走快档(开思考会烧 token 截断致空,见真题路径 46s 截断)", "locations": ["reading_intensive_service.py:question_analysis"], "cache": "global", "store": "reading_analysis_cache(按题 md5)"},
    {"feature": "reading_practice", "mode": "chat", "surface": "小程序端", "module": "作业精讲·阅读理解精讲", "service": "reading_intensive_service",
     "purpose": "阅读练同类:按本篇短文出理解新题(细节/推断/主旨…,非语法题)", "why": "结构化生成选择题,规格明确,关思考走快档", "locations": ["reading_intensive_service.py:practice_similar"], "cache": "global", "store": "reading_practice_cache(按短文+数量 md5)"},
    {"feature": "cloze_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "完形填空解析(clue/slot/distractors + 自足 logic_stem 改写挖空句)", "why": "结合上下文推断选词线索并同次生成可独立作答的挖空句", "locations": ["question_analysis_service.py:_llm_cloze_suggestion"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "cloze_analysis", "mode": "chat", "surface": "小程序端", "module": "作业精讲·完形填空精讲", "service": "cloze_intensive_service",
     "purpose": "上传作业完形空·双轴解析(线索类型/线索句/为何对/干扰错因/载体槽)", "why": "结构化抽取,关思考走快档", "locations": ["cloze_intensive_service.py:question_analysis"], "cache": "global", "store": "cloze_analysis_cache(按题 md5)"},
    {"feature": "cloze_practice", "mode": "chat", "surface": "小程序端", "module": "作业精讲·完形填空精讲", "service": "cloze_intensive_service",
     "purpose": "完形本题巩固:按线索类型出同类单选", "why": "结构化生成选择题,规格明确,关思考走快档", "locations": ["cloze_intensive_service.py:practice_similar"], "cache": "global", "store": "cloze_practice_cache(按语篇+线索类型+数量 md5)"},
    {"feature": "writing_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "写作题解析(含 model_essay 范文)", "why": "范文生成 + 解析,重推理", "locations": ["question_analysis_service.py:645"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "grammar_mc_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "语法选择题解析(含 kp_codes)", "why": "推断考点并解释语法逻辑", "locations": ["question_analysis_service.py:713"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "word_fill_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "词形填空解析(kp_codes + change_type + logic_stem)", "why": "推断词形变化类型与考点并产出挖空展示句", "locations": ["question_analysis_service.py:_llm_word_fill_suggestion"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "passage_fill_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "短文填空解析(clue + answer_word + 自足 logic_stem 改写挖空句)", "why": "篇章填空上下文推断并同次生成可独立作答的挖空句", "locations": ["question_analysis_service.py:_llm_passage_fill_suggestion"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "sentence_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "句子改写/翻译题解析(kp_codes + target_structure)", "why": "推断目标结构与考点", "locations": ["question_analysis_service.py:904"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis(≠长难句 sentence_analysis_cache)"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "读写表达", "service": "reading_expression_service",
     "purpose": "读写表达题批改评分", "why": "开放作答判分需语义理解与推理", "locations": ["reading_expression_service.py:63"], "cache": "none", "store": "无(仅 log_answer 落对错信号)"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "口语", "service": "speaking_dialogue_service",
     "purpose": "口语教练:鼓励 + 纠错反馈", "why": "结合发音数据给个性化教学反馈", "locations": ["speaking_dialogue_service.py:659"], "cache": "none", "store": "无(实时对话反馈)"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "口语", "service": "speaking_dialogue_service",
     "purpose": "口语场景对话:AI 角色回复", "why": "理解语境生成自然连贯回复", "locations": ["speaking_dialogue_service.py:720"], "cache": "none", "store": "无(回复 TTS 后下发,不缓存)"},
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "口语", "service": "speaking_dialogue_service",
     "purpose": "整段口语对话总结与评价", "why": "综合多轮对话做评估总结", "locations": ["speaking_dialogue_service.py:960"], "cache": "none", "store": "无(仅存 overall 分/turns)"},
    {"feature": "writing_grade", "mode": "reasoning", "surface": "小程序端", "module": "作文·判分", "service": "writing_grade_service",
     "purpose": "依据解析/范文逐点批改作文", "why": "判分 + 逐点反馈需多维推理", "locations": ["writing_grade_service.py:130"], "cache": "none", "store": "无(仅 log_answer 喂 BKT)"},

    # ── 对话(chat / 快档,规格明确无需重推理)────────────────────────────────
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "教材·课程生成", "service": "curriculum_ai_service",
     "purpose": "单元文本解析为结构化字段(挑索引)", "why": "输出小、规格明确;走 fast 避免主模型耗预算返空", "locations": ["curriculum_ai_service.py:107"], "cache": "none", "store": "无"},
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "教材·单词", "service": "curriculum_vocab_service",
     "purpose": "从文本抽取单词/词组列表", "why": "纯抽取、固定 JSON 格式", "locations": ["curriculum_vocab_service.py:139"], "cache": "none", "store": "无(LLM 抽词不缓存;下游按词去重)"},
    {"feature": "grammar_probe", "mode": "chat", "surface": "小程序端", "module": "语法", "service": "grammar_probe_service",
     "purpose": "生成语法识别/检测探针题 + 迁移题种子", "why": "固定字段 + validate 校验,快档即可", "locations": ["grammar_probe_service.py:155", "grammar_probe_service.py:365"], "cache": "global", "store": "knowledge_node.grammar_probes_json(KP 级公共)"},
    {"feature": "grammar_produce", "mode": "chat", "surface": "小程序端", "module": "语法", "service": "grammar_probe_service",
     "purpose": "语法造句作答按维度打分", "why": "打分维度固定、规格明确", "locations": ["grammar_probe_service.py:293"], "cache": "none", "store": "无(仅掌握度走 BKT)"},
    {"feature": "kp_match", "mode": "chat", "surface": "运营后台", "module": "知识点·整卷匹配", "service": "kp_match_service",
     "purpose": "从候选知识点受控单选最匹配项", "why": "受控单选、max_tokens=128,显式 disable_thinking 提速", "locations": ["kp_match_service.py:111"], "cache": "none", "store": "无(命中返回 node_id;未中累计候选计数)"},
    {"feature": "ls_analyze", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "长难句成分切分/结构分析", "why": "结构化抽取,有 validate/升档兜底,关思考提速", "locations": ["long_sentence_service.py:389"], "cache": "global", "store": "sentence_analysis_cache.analysis_json(按句 md5)+ long_sentence.analysis_json"},
    {"feature": "ls_paraphrase", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "长句同义改写选择题", "why": "固定选项格式、规格明确", "locations": ["long_sentence_service.py:435"], "cache": "global", "store": "sentence_analysis_cache.analysis_json.paraphrase(按句 md5)"},
    {"feature": "ls_translate", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "长句翻译作答按维度打分", "why": "打分维度固定(_TRANS_DIMS)", "locations": ["long_sentence_service.py:661"], "cache": "none", "store": "无(实时判分)"},
    {"feature": "ls_verify_subj", "mode": "chat", "surface": "小程序端", "module": "长难句", "service": "long_sentence_service",
     "purpose": "主观验证题作答是否通过(pass 布尔)", "why": "二分判定、max_tokens=64", "locations": ["long_sentence_service.py:769"], "cache": "none", "store": "无(实时判分)"},
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "长难句·录入", "service": "long_sentence_upload_service",
     "purpose": "上传文本解析为长难句列表入库", "why": "纯抽取、固定 JSON 格式", "locations": ["long_sentence_upload_service.py:55"], "cache": "none", "store": "无(抽取结果落 long_sentence 草稿,非防重付费缓存)"},
    {"feature": None, "mode": "chat", "surface": "运营后台", "module": "真题·录入解析", "service": "paper_split_service",
     "purpose": "整卷 OCR 文本切分为题目/短文块", "why": "切分规格明确、输出固定,快档处理长文", "locations": ["paper_split_service.py:508"], "cache": "global", "store": "paper_split_cache.raw_json(按 input_md5)"},
    {"feature": "sales_intent", "mode": "chat", "surface": "运营后台", "module": "电销·意向分析", "service": "sales_analysis_service",
     "purpose": "销售通话转写→意向分析打分", "why": "抽取 + 固定打分规格,有 validate 兜底", "locations": ["sales_analysis_service.py:88"], "cache": "none", "store": "无(不落库,失败走启发式兜底)"},
    {"feature": "vocab_enrich", "mode": "chat", "surface": "小程序端", "module": "词力通", "service": "vocab_intensive_service",
     "purpose": "补全单词释义/例句/短语", "why": "词典式抽取、固定字段", "locations": ["vocab_intensive_service.py:165"], "cache": "global", "store": "vocabulary_words(definitions/examples/phrases 等,词级公共)"},
    {"feature": "vocab_word_family", "mode": "chat", "surface": "小程序端", "module": "词力通·词族(G)", "service": "word_family_service",
     "purpose": "生成单词的词根 + 同族词(构词法·义/用关展示)", "why": "构词法抽取、规格明确、fast 档", "locations": ["word_family_service.py:42"], "cache": "global", "store": "vocab_word_family.members(按 word_id,查看即生成)"},
    {"feature": "vocab_word_kp", "mode": "chat", "surface": "小程序端", "module": "词力通·考点深挖", "service": "word_kp_service",
     "purpose": "挖单词/词组考点:固定搭配/近义/反义/派生/易混/歧义/其他/考法(义关折叠卡,关系型落库,词与词组共用)", "why": "词典式考点抽取、规格明确、fast 档", "locations": ["word_kp_service.py:_gen_kp"], "cache": "global", "store": "vocab_word_kp(词根)+vocab_word_relation(各维关系,按 word_id,查看即生成+预热)"},
    {"feature": "vocab_mcq", "mode": "chat", "surface": "小程序端", "module": "词力通·测试题库", "service": "vocab_mcq_service",
     "purpose": "每词生成 3-5 道混合单选题(词→义/义→词/语境填空),测试随机取用", "why": "结构化出题、规格明确、fast 档", "locations": ["vocab_mcq_service.py:31"], "cache": "global", "store": "vocab_mcq(按 word_id,每词一次生成 3-5 道、随机取,秒回后台异步补)"},
    {"feature": "vocab_kp_mcq", "mode": "chat", "surface": "小程序端", "module": "词力通·考点扩展测试", "service": "word_kp_service",
     "purpose": "按考点维度出题:每个有内容的维度(搭配/近义/反义/派生/易混/歧义/其他/考法)各 3 道单选,测试每维随机取 1(词与词组共用)", "why": "结构化按维出题、规格明确、fast 档", "locations": ["word_kp_service.py:_gen_kp_mcqs"], "cache": "global", "store": "vocab_kp_mcq(FK vocab_word_kp,按 word_id 一次生成、每维随机取,查看即生成+预热)"},
    {"feature": "vocab_kp_mcq_fix", "mode": "reasoning", "surface": "运营后台", "module": "词力通·考点题AI审校修正", "service": "word_kp_service",
     "purpose": "被学生「换一题」报错达阈值的考点题,AI 审校修正答案/解析/干扰项(保证答案唯一无歧义);低峰 cron 批量(自动)或后台手动触发", "why": "审校要多步判断答案唯一性/干扰项是否也成立→推理档;低峰调用省钱", "locations": ["word_kp_service.py:_gen_fix_mcq"], "cache": "none", "store": "更新 vocab_kp_mcq + 记 vocab_kp_mcq_revision(before/after);report_count 归 0"},
    {"feature": "vocab_kp_review", "mode": "reasoning", "surface": "运营后台", "module": "词力通·考点AI审校(自审+报错修正)", "service": "word_kp_service",
     "purpose": "P5 低峰巡检未审校词的『用法/考法类文本维』考点(及物性/语态/句型/可数性/所有格/-ed-ing/介词辨析/用法/语义侧重/考法)+ P6 修正被学生报错达阈值的考点:删明显错项、改表述不准", "why": "逐条判断考点正确性/义项归属→多步推理→推理档;可链维已 morph/wordnet/词库背书、搭配已语料印证不重审;低峰调用省钱", "locations": ["word_kp_service.py:_review_kp_rows"], "cache": "none", "store": "改/删 vocab_word_relation + 置 vocab_word_kp.reviewed_at(P5)/report_count 归 0(P6)+ 记 vocab_word_kp_review(before/after)"},
    {"feature": "vocab_kp_prehide", "mode": "reasoning", "surface": "运营后台", "module": "词力通·考点AI预隐(二期)", "service": "word_kp_service",
     "purpose": "低峰扫中考高频词的近义/易混:明显错误的纯 LLM(无词库命中)行预隐(hidden_at+ai_prehide),供运营抽检恢复;wordnet/词库命中仅作上下文不可隐", "why": "判断近义/易混是否明显错误需多步推理→推理档;低峰调用;范围收窄控成本", "locations": ["word_kp_service.py:_gen_prehide_ids"], "cache": "none", "store": "vocab_word_relation.hidden_at/hide_note=ai_prehide + vocab_word_kp.prehide_at + vocab_word_kp_review"},
    {"feature": "wrong_option_split", "mode": "chat", "surface": "小程序端", "module": "错题关系网·选项拆块", "service": "wrong_relation_service",
     "purpose": "把一道错题的各选项拆成独立语义块(词/词组),去编号去重,供建关系网", "why": "结构化抽取、规格明确、fast 档", "locations": ["wrong_relation_service.py:_extract_blocks"], "cache": "per-user", "store": "块归一进 vocabulary_words(source=wrong);关系落 student_wrong_relation(按 student+wrong_record,查看即生成)"},
    {"feature": "wrong_sense_match", "mode": "chat", "surface": "小程序端", "module": "错题关系网·义项匹配", "service": "wrong_word_net_service",
     "purpose": "判一道错题考目标词的哪个义项(多义词考点消歧,如 but 转折/除…外),结果缓存 student_wrong_word.sense_id", "why": "结构化单选判定、规格明确、fast 档", "locations": ["wrong_word_net_service.py:_classify_sense"], "cache": "per-user", "store": "student_wrong_word.sense_id(每错题+词缓存一次)"},
    {"feature": "wrong_pair_relation", "mode": "chat", "surface": "小程序端", "module": "错题关系网·两两判关系", "service": "wrong_relation_service",
     "purpose": "对同题选项块两两判语义关系(近义/反义/易混/歧义/其他/无),建个人错题网并回写全局考点", "why": "结构化关系判定、规格明确、fast 档", "locations": ["wrong_relation_service.py:_judge_pairs"], "cache": "per-user", "store": "student_wrong_relation(私有边)+ 语义关系反哺 vocab_word_relation(全局)"},
    {"feature": "vocab_validity_gate", "mode": "chat", "surface": "小程序端", "module": "词力通·缺词", "service": "vocab_intensive_service",
     "purpose": "缺词自动入库前的有效性闸门(是否真实可教学英文词/词组)", "why": "二元判定、规格明确、fast 档 + 免费正则粗筛前置", "locations": ["vocab_intensive_service.py:225"], "cache": "none", "store": "无(判定结果不落库;通过则建 vocabulary_words,不通过落 vocab_review)"},
    {"feature": "vocab_definition_gen", "mode": "chat", "surface": "小程序端", "module": "词力通·释义补全(dict兜底)", "service": "vocab_definition_service",
     "purpose": "词典(ECDICT)没有的词,快档生成中文释义(1-2义)", "why": "结构化短释义、规格明确,关思考走快档;仅兜 dict_ecdict 未命中,量少", "locations": ["vocab_definition_service.py:_gen_definition_llm"], "cache": "per_user", "store": "vocabulary_words.definitions(落库即缓存,同词不二次)"},
    {"feature": "vocab_image_brief", "mode": "chat", "surface": "运营后台", "module": "表意配图·唯一入口", "service": "visual_brief_service",
     "purpose": "表意配图:词/考点→分类(具象/情感/心理/隐喻/抽象/空间/纯虚词)+ 一句可画场景;纯语法虚词判 text_only", "why": "结构化分类+造场景、关思考提速;是全项目表意出图的唯一 brief 入口", "locations": ["visual_brief_service.py:plan_visual"], "cache": "global", "store": "vocabulary_words 媒体字段(ensure_word_media 幂等守卫)"},
    {"feature": "vocab_en_desc", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "用简单英文(A2)解释单词", "why": "固定简短输出、规格明确", "locations": ["vocab_media_service.py:298"], "cache": "global", "store": "vocabulary_words.en_description"},
    {"feature": "vocab_example", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "生成单词例句 + 短语(含中译 JSON)", "why": "固定 JSON 结构、A2 简单句", "locations": ["vocab_media_service.py:324"], "cache": "global", "store": "vocabulary_words.examples / vocabulary_words.phrases"},
    {"feature": "vocab_video_motion", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "判断单词可否动画化 + 动作描述", "why": "规格明确,有 validate 与升档兜底", "locations": ["vocab_media_service.py:503"], "cache": "global", "store": "vocabulary_words.gif_url(动作判定下游动图产物)"},
    {"feature": "vocab_probe", "mode": "chat", "surface": "小程序端", "module": "词力通", "service": "vocab_probe_service",
     "purpose": "生成单词探针题(干扰项/误区/搭配)+ 迁移例句", "why": "固定字段 + validate 校验", "locations": ["vocab_probe_service.py:85", "vocab_probe_service.py:375"], "cache": "global", "store": "vocabulary_words.probes_json(词级 10 题池,随机出 5,全学生共享)"},
    {"feature": "vocab_produce", "mode": "chat", "surface": "小程序端", "module": "词力通", "service": "vocab_probe_service",
     "purpose": "单词造句作答按维度打分", "why": "打分维度固定(_PROD_DIMS)", "locations": ["vocab_probe_service.py:298"], "cache": "none", "store": "无(仅掌握度落 mastery_prod)"},
    {"feature": "paper_q_explain", "mode": "chat", "surface": "小程序端", "module": "作业精讲·语法", "service": "grammar_intensive_service",
     "purpose": "语法原题单段解析(正确/错误同等,查看即生成)", "why": "规格明确的短解析抽取,关思考走快档", "locations": ["grammar_intensive_service.py:ensure_question_explanation"], "cache": "global", "store": "paper_q_explain_cache + user_paper_questions.explanation(按题面 md5)"},
    {"feature": "kp_title_rewrite", "mode": "chat", "surface": "运营后台", "module": "知识图谱·标题整理", "service": "kp_title_rewrite_service",
     "purpose": "语法点粗糙 name→短展示标题+一句说明(写入 description 首行,不改 name)", "why": "规格明确的改写抽取,快档即可", "locations": ["kp_title_rewrite_service.py:_suggest_one"], "cache": "global", "store": "kp_title_rewrite_cache(按 name|description md5)"},
    {"feature": "unit_ls_extract_or_synth", "mode": "chat", "surface": "运营后台", "module": "教材·单元长难句理解向", "service": "unit_ls_understand_service",
     "purpose": "限量≤8句抽取或5-8句合成;贴本单元语法(gp)+tier梯度;截断不升档;只出en", "why": "规格明确的抽取/可控生成,快档即可;限量防截断超时", "locations": ["unit_ls_understand_service.py:_llm_extract_or_synth"], "cache": "global", "store": "unit_ls_understand_cache(v6原文md5+年级+语法范围)+unit_understand_ls"},
    {"feature": "unit_ls_enrich", "mode": "chat", "surface": "运营后台", "module": "教材·单元长难句理解向", "service": "unit_ls_understand_service",
     "purpose": "(遗留)批量为抽取句补中文译文;L1主路径不走", "why": "规格明确的短译文,快档即可", "locations": ["unit_ls_understand_service.py:_enrich_translations"], "cache": "global", "store": "unit_ls_understand_cache+unit_understand_ls"},
    {"feature": "unit_ls_synth", "mode": "chat", "surface": "运营后台", "module": "教材·单元长难句理解向", "service": "unit_ls_understand_service",
     "purpose": "空结果兜底:限量合成5-8句(gp+tier;截断不升档;只出en)", "why": "规格明确的可控生成,快档即可", "locations": ["unit_ls_understand_service.py:_synth_sentences"], "cache": "global", "store": "unit_ls_understand_cache+unit_understand_ls"},
]



def counts() -> dict:
    r = sum(1 for e in LLM_FEATURES if e["mode"] == "reasoning")
    c = sum(1 for e in LLM_FEATURES if e["mode"] == "chat")
    untagged = sum(1 for e in LLM_FEATURES if not e["feature"])
    mini = sum(1 for e in LLM_FEATURES if e["surface"] == "小程序端")
    admin = sum(1 for e in LLM_FEATURES if e["surface"] == "运营后台")
    cache_global = sum(1 for e in LLM_FEATURES if e.get("cache") == "global")
    cache_user = sum(1 for e in LLM_FEATURES if e.get("cache") == "per_user")
    cache_none = sum(1 for e in LLM_FEATURES if e.get("cache") == "none")
    return {"total": len(LLM_FEATURES), "reasoning": r, "chat": c, "untagged": untagged,
            "mini": mini, "admin": admin,
            "cache_global": cache_global, "cache_user": cache_user, "cache_none": cache_none}
