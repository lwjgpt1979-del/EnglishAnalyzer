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
    {"feature": None, "mode": "reasoning", "surface": "小程序端", "module": "作文", "service": "essay_service",
     "purpose": "作文审题(体裁/要点/人称时态/词数)", "why": "理解题干意图并推断隐含写作要求", "locations": ["essay_service.py:181"], "cache": "none", "store": "无"},
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
     "purpose": "完形填空解析(线索 clue/slot)", "why": "结合上下文推断选词线索", "locations": ["question_analysis_service.py:530"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "writing_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "写作题解析(含 model_essay 范文)", "why": "范文生成 + 解析,重推理", "locations": ["question_analysis_service.py:645"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "grammar_mc_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "语法选择题解析(含 kp_codes)", "why": "推断考点并解释语法逻辑", "locations": ["question_analysis_service.py:713"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "word_fill_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "词形填空解析(kp_codes + change_type)", "why": "推断词形变化类型与考点", "locations": ["question_analysis_service.py:775"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
    {"feature": "passage_fill_analysis", "mode": "reasoning", "surface": "运营后台", "module": "真题·题目解析", "service": "question_analysis_service",
     "purpose": "短文填空解析(含 clue)", "why": "篇章填空上下文推断", "locations": ["question_analysis_service.py:839"], "cache": "global", "store": "platform_question.meta.analysis_draft / meta.analysis"},
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
    {"feature": "wrong_option_split", "mode": "chat", "surface": "小程序端", "module": "错题关系网·选项拆块", "service": "wrong_relation_service",
     "purpose": "把一道错题的各选项拆成独立语义块(词/词组),去编号去重,供建关系网", "why": "结构化抽取、规格明确、fast 档", "locations": ["wrong_relation_service.py:_extract_blocks"], "cache": "per-user", "store": "块归一进 vocabulary_words(source=wrong);关系落 student_wrong_relation(按 student+wrong_record,查看即生成)"},
    {"feature": "wrong_sense_match", "mode": "chat", "surface": "小程序端", "module": "错题关系网·义项匹配", "service": "wrong_word_net_service",
     "purpose": "判一道错题考目标词的哪个义项(多义词考点消歧,如 but 转折/除…外),结果缓存 student_wrong_word.sense_id", "why": "结构化单选判定、规格明确、fast 档", "locations": ["wrong_word_net_service.py:_classify_sense"], "cache": "per-user", "store": "student_wrong_word.sense_id(每错题+词缓存一次)"},
    {"feature": "wrong_pair_relation", "mode": "chat", "surface": "小程序端", "module": "错题关系网·两两判关系", "service": "wrong_relation_service",
     "purpose": "对同题选项块两两判语义关系(近义/反义/易混/歧义/其他/无),建个人错题网并回写全局考点", "why": "结构化关系判定、规格明确、fast 档", "locations": ["wrong_relation_service.py:_judge_pairs"], "cache": "per-user", "store": "student_wrong_relation(私有边)+ 语义关系反哺 vocab_word_relation(全局)"},
    {"feature": "vocab_validity_gate", "mode": "chat", "surface": "小程序端", "module": "词力通·缺词", "service": "vocab_intensive_service",
     "purpose": "缺词自动入库前的有效性闸门(是否真实可教学英文词/词组)", "why": "二元判定、规格明确、fast 档 + 免费正则粗筛前置", "locations": ["vocab_intensive_service.py:225"], "cache": "none", "store": "无(判定结果不落库;通过则建 vocabulary_words,不通过落 vocab_review)"},
    {"feature": "vocab_image_brief", "mode": "chat", "surface": "运营后台", "module": "词力通·媒体", "service": "vocab_media_service",
     "purpose": "单词配图用视觉简述", "why": "短文本生成、max_tokens=256,关思考提速", "locations": ["vocab_media_service.py:218"], "cache": "global", "store": "vocabulary_words 媒体字段(ensure_word_media 幂等守卫)"},
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
