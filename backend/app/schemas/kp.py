"""KP 候选审核 DTO(R0.4)。"""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class KpCandidateItem(BaseModel):
    id: uuid.UUID
    raw_name: str
    name_norm: str
    suggested_axis: str | None = None
    suggested_stage: str | None = None
    occur_count: int
    source_type: str | None = None
    context_sample: dict | None = None
    status: str


class KpCandidateListOut(BaseModel):
    total: int
    items: list[KpCandidateItem]


class KpNodeItem(BaseModel):
    id: uuid.UUID
    axis: str
    node_kind: str | None = None
    name: str
    code: str
    applicable_stages: list[str] | None = None


class KpNodeOverviewItem(BaseModel):
    id: uuid.UUID
    axis: str
    node_kind: str | None = None
    name: str
    code: str
    status: str
    applicable_stages: list[str] | None = None
    source: str | None = None     # seed/textbook/exam/manual(manual=人工新建)
    lecture_filled: int       # 讲解已填环节数
    lecture_total: int        # 该考点类型模板环节数(分母)
    unit_refs: int            # 被多少教材单元引用
    question_refs: int        # 被多少真题/仿真引用
    alias_count: int


class KpNodeOverviewOut(BaseModel):
    total: int
    items: list[KpNodeOverviewItem]


# ── 节点详情 / 维护(D2)──
class NodeAliasItem(BaseModel):
    alias: str
    source: str


class NodeUnitRef(BaseModel):
    unit_id: uuid.UUID
    unit_title: str
    textbook_version: str
    grade: str
    semester: str


class LectureSectionCell(BaseModel):
    """考点讲解的一个教学环节(按类型模板)。status: empty/draft/published。"""
    section_key: str
    title: str
    order: int
    content_md: str | None = None
    media_url: str | None = None
    status: str
    source: str | None = None
    has_content: bool


class LectureOut(BaseModel):
    kp_type: str          # grammar/reading/listening/writing
    kp_type_label: str    # 语法/阅读/听力/写作
    total: int            # 该类型模板环节数
    filled: int           # 已填(有正文)环节数
    sections: list[LectureSectionCell]


class NodeMastery(BaseModel):
    learners: int
    avg: float | None = None
    mastered: int
    mid: int
    weak: int


class KpNodeDetailOut(BaseModel):
    id: uuid.UUID
    axis: str
    node_kind: str | None = None
    name: str
    code: str
    status: str
    applicable_stages: list[str] | None = None
    description: str | None = None
    source: str
    lecture: LectureOut
    aliases: list[NodeAliasItem]
    units: list[NodeUnitRef]
    question_real: int
    question_sim: int
    mastery: NodeMastery


class UpdateNodeIn(BaseModel):
    name: str | None = None
    node_kind: str | None = None
    applicable_stages: list[str] | None = None
    description: str | None = None


# ── 受控知识树(E1)──
class NodeTreeItem(BaseModel):
    id: uuid.UUID
    name: str
    axis: str
    node_kind: str | None = None
    status: str
    code: str
    applicable_stages: list[str] | None = None   # 适用学段(小/初/高);null=通用脚手架
    source: str | None = None             # 来源:seed/textbook/exam/manual(manual=人工新建)
    unit_refs: int | None = None          # 教材单元挂载数(子树聚合,with_counts 时有)
    question_refs: int | None = None       # 真题挂载数(子树聚合)
    children: list["NodeTreeItem"] = []


class NodeTreeOut(BaseModel):
    items: list[NodeTreeItem]


NodeTreeItem.model_rebuild()


class CreateNodeIn(BaseModel):
    name: str
    parent_id: uuid.UUID | None = None
    axis: str | None = None
    node_kind: str | None = None
    applicable_stages: list[str] | None = None


class MoveNodeIn(BaseModel):
    parent_id: uuid.UUID | None = None


class KpNodeListOut(BaseModel):
    total: int
    items: list[KpNodeItem]


class ApproveCandidateRequest(BaseModel):
    axis: str = Field(..., description="knowledge|ability|exam")
    stage: str | None = Field(None, description="小|初|高;空=全学段通用")
    node_kind: str | None = None
    parent_id: uuid.UUID | None = None


class MergeCandidateRequest(BaseModel):
    target_node_id: uuid.UUID = Field(..., description="把候选名并为该节点的别名")


class RejectCandidateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500, description="驳回理由")


# ── R1 教材接入 ──────────────────────────────────────────────
class UnitNodeItem(BaseModel):
    node_id: uuid.UUID
    name: str
    axis: str
    node_kind: str | None = None
    source: str


class UnitNodeListOut(BaseModel):
    total: int
    items: list[UnitNodeItem]


class UnitExtractOut(BaseModel):
    matched: int
    candidate: int
    edges_created: int


# ── R2 平台题 ────────────────────────────────────────────────
class PlatformQuestionItem(BaseModel):
    id: uuid.UUID
    type: str
    parent_real_id: uuid.UUID | None = None
    is_fallback: bool
    question_type: str | None = None
    stem: str | None = None
    options: list | dict | str | None = None  # 选项(JSONB:list / {A:..} / 整段字符串)
    answer: str | None = None
    explanation: str | None = None
    difficulty: int | None = None
    status: str
    sim_version: int | None = None          # 仿真题按题位累加的版本号
    kp_names: list[str] = []                # 关联考点名(继承自母题)
    block_id: uuid.UUID | None = None       # 题组(短文)外键;同篇阅读/完形小问共享
    passage: str | None = None              # 题组短文正文(同 block_id 的题相同)


class PlatformQuestionListOut(BaseModel):
    total: int
    items: list[PlatformQuestionItem]


class GenSimOut(BaseModel):
    generated: int
    sim_ids: list[uuid.UUID]


# ── 真题导入(平台真题页 TK1)──────────────────────────────────
class RealQuestionIn(BaseModel):
    stem: str = Field(..., min_length=1)
    options: object | None = None          # list 或 {A:..,B:..}
    answer: str | None = None
    question_type: str | None = None
    explanation: str | None = None
    difficulty: int | None = None
    question_no: str | None = None
    kp_names: list[str] = []               # 知识点名 → match_kp 挂 node
    meta: dict | None = None               # 考试元信息(地区/年份/卷别…)
    stage_hint: str | None = None
    status: str = "published"
    passage: str | None = None             # 题组短文正文(同 block_key 的题共享一份)
    block_key: str | None = None           # 同短文小问共享;为空=独立题
    section: str | None = None             # 原卷大题名(听力选择/单项填空…)


class RealQuestionBulkIn(BaseModel):
    items: list[RealQuestionIn] = Field(..., min_length=1)
    stage_hint: str | None = None          # 学段(小/初/高)→ 助 KP 匹配,批次统一
    status: str | None = None              # 覆盖每题 status(可空)
    meta: dict | None = None               # 批次考试元信息(教材/学段/年级/学期/地区),并入每题
    paper_name: str | None = None          # 试卷名(可空,缺省由 meta 自动合成)


class RealImportItemOut(BaseModel):
    question_id: uuid.UUID
    matched_nodes: list[uuid.UUID] = []
    candidates: list[uuid.UUID] = []


class RealImportBulkOut(BaseModel):
    imported: int
    failed: int
    paper_id: uuid.UUID | None = None
    items: list[RealImportItemOut] = []


# ── 平台试卷(整卷聚合 / 发布 / 选题仿真)────────────────────────
class PaperListItem(BaseModel):
    id: uuid.UUID
    name: str
    textbook_version: str | None = None
    stage: str | None = None
    grade: str | None = None
    semester: str | None = None
    region_name: str | None = None
    exam_type: str | None = None
    status: str
    question_count: int = 0
    published_count: int = 0
    source_file_url: str | None = None
    source_filename: str | None = None
    parse_status: str | None = None
    parse_error: str | None = None
    convert_status: str | None = None      # .doc→pdf 转换:pending|converting|converted|failed
    year: int | None = None                # 从试卷名提取的年份
    created_at: datetime | None = None


class PaperListOut(BaseModel):
    total: int
    items: list[PaperListItem]


class QuestionKpRef(BaseModel):
    node_id: uuid.UUID
    name: str
    code: str | None = None


class PaperQuestionItem(BaseModel):
    id: uuid.UUID
    question_no: str | None = None
    section: str | None = None
    question_type: str | None = None
    stem: str | None = None
    answer: str | None = None
    difficulty: int | None = None
    status: str
    block_id: uuid.UUID | None = None
    passage: str | None = None
    kps: list[QuestionKpRef] = []        # 该题关联的受控知识点(母题派生仿真依据)


class AttachKpIn(BaseModel):
    node_id: uuid.UUID


class KpBulkPair(BaseModel):
    question_id: uuid.UUID
    node_id: uuid.UUID


class KpBulkAttachIn(BaseModel):
    pairs: list[KpBulkPair] = Field(..., min_length=1)


class SectionKpIn(BaseModel):
    section: str
    node_id: uuid.UUID


class KpProposal(BaseModel):
    """AI 发现考点缺口:目录里没有合适考点 → 建议新建一个并归到某分类(人工确认后创建)。"""
    name: str                              # 建议的新考点名
    parent_node_id: uuid.UUID | None = None   # 建议归属分类(现有节点)
    parent_name: str | None = None


class SuggestKpItem(BaseModel):
    question_id: uuid.UUID
    suggestions: list[QuestionKpRef] = []
    proposals: list[KpProposal] = []       # 无现成考点时的"新建考点"建议


class SuggestKpOut(BaseModel):
    items: list[SuggestKpItem] = []


class SuggestKpIn(BaseModel):
    sections: list[str] | None = None      # 仅对这些大题(供「一键挂某大题」)
    prompt_id: str | None = None           # 指定提示词;空=按题型默认
    skip_attached: bool = False            # True=跳过已挂考点的题(整卷匹配用,避免重复)


# ── 知识点 AI 提示词配置(按题型,多套选默认)──
class KpPromptItem(BaseModel):
    id: str | None = None
    name: str
    text: str
    question_type: str                     # 单选/填空/完型/阅读/写作
    is_default: bool = False
    focus_node_ids: list[uuid.UUID] = []   # 关注的知识脑图分类(空=全部考点)
    min_kp: int = 0                        # 每题至少挑几个考点(提示给 AI)
    max_kp: int = 2                        # 每题至多挑几个考点(解析封顶)
    # 每个关注分类各自的考点数范围 {分类id: [至少, 至多]};未配的分类回退 min_kp/max_kp
    # 用宽松 list(非 list[int]):前端 input 可能传 null/float,交由 save_prompts 清洗夹紧,避免 422
    focus_ranges: dict[str, list] = {}


class KpPromptsIn(BaseModel):
    prompts: list[KpPromptItem]
    # 学期 scope（教材版本|年级|学期）;空=全局默认。该 scope 的提示词整体覆盖
    scope: str | None = None
    # 短文是否也匹配「答题技能类」考点(推理判断/情景反应等);默认 False=排除(收紧)
    passage_include_skill: bool = False


class SuggestTextIn(BaseModel):
    text: str
    source_type: str = "教材·其他"
    stage: str | None = None        # 小|初|高;限定候选考点学段(空=不限)


class KpPromptsOut(BaseModel):
    prompts: list[KpPromptItem]
    passage_include_skill: bool = False


class PaperDetailOut(BaseModel):
    paper: PaperListItem
    questions: list[PaperQuestionItem]


class PaperDeleteIn(BaseModel):
    paper_ids: list[uuid.UUID] = Field(..., min_length=1)


class GenSimBulkIn(BaseModel):
    question_ids: list[uuid.UUID] = Field(..., min_length=1)
    count: int = 3


class ReviewBulkIn(BaseModel):
    question_ids: list[uuid.UUID] = Field(..., min_length=1)
    approve: bool                          # True→published / False→retired


class GenSimBulkOut(BaseModel):
    generated: int
    per_question: int


# ── 真题抽题任务(TK2)──────────────────────────────────────────
class ParsedRealQuestion(BaseModel):
    question_no: str | None = None
    question_type: str | None = None
    stem: str | None = None
    answer: str | None = None
    explanation: str | None = None
    passage: str | None = None             # 题组短文(阅读/完形/信息还原);独立题为空
    block_key: str | None = None           # 同短文小问共享;独立题为空
    section: str | None = None             # 原卷大题名(听力选择/单项填空/完形填空…)


class RealExtractCreatedOut(BaseModel):
    job_id: uuid.UUID


class RealExtractJobOut(BaseModel):
    job_id: uuid.UUID
    source: str
    status: str                          # running|done|failed
    error: str | None = None
    parsed: list[ParsedRealQuestion] = []


# ── 地区维护(后台)──────────────────────────────────────────
class RegionIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=12)
    name: str = Field(..., min_length=1, max_length=64)
    parent_code: str | None = None
    level: int = Field(..., ge=1, le=4)


class RegionRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


class RegionItem(BaseModel):
    code: str
    name: str
    parent_code: str | None = None
    level: int
    leaf: bool = True


class ReviewRequest(BaseModel):
    approve: bool = Field(..., description="true=通过→published,false=驳回→retired")


# ── R3 错题中心/复习 ──────────────────────────────────────────
import datetime as _dt  # noqa: E402


class WrongReviewItem(BaseModel):
    id: uuid.UUID
    q_scope: str
    question_id: uuid.UUID
    node_id: uuid.UUID | None = None
    review_count: int
    next_review_at: _dt.date | None = None


class WrongReviewQueueOut(BaseModel):
    due_count: int
    items: list[WrongReviewItem]


class WrongReviewSubmitIn(BaseModel):
    wrong_record_id: uuid.UUID
    quality: int = Field(..., ge=0, le=5, description="0-5,SM-2 复习质量")


class WrongReviewSubmitOut(BaseModel):
    status: str
    review_count: int
    next_review_at: _dt.date | None = None


# ── R4 个人知识图谱 ──────────────────────────────────────────
class StudentGraphItem(BaseModel):
    node_id: uuid.UUID
    name: str
    axis: str
    node_kind: str | None = None
    mastery: float | None = None
    practice_count: int
    wrong_count: int
    source_tags: list[str]
    in_scope: bool
    status: str   # mastered|weak|practiced|unlearned


class StudentGraphSummary(BaseModel):
    in_scope: int
    practiced: int
    weak: int
    mastered: int


class StudentGraphOut(BaseModel):
    summary: StudentGraphSummary
    items: list[StudentGraphItem]


class EnrollOut(BaseModel):
    enrolled: int


class StudentTrendPoint(BaseModel):
    date: _dt.date
    accuracy: float
    correct: int
    wrong: int


class StudentTrendOut(BaseModel):
    node_id: uuid.UUID
    points: list[StudentTrendPoint]


# ── R5 通用词库(admin) ───────────────────────────────────────
class VocabListCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    exam_level: str | None = None
    source_type: str | None = None
    status: str = "draft"


class VocabListOut(BaseModel):
    id: uuid.UUID
    name: str
    exam_level: str | None = None
    source_type: str | None = None
    status: str


class VocabListsOut(BaseModel):
    items: list[VocabListOut]


class VocabItemIn(BaseModel):
    word: str | None = None
    word_id: uuid.UUID | None = None
    rank: int | None = None
    frequency: int | None = None
    star: int = 0
    verified: bool = False


class VocabItemsIn(BaseModel):
    items: list[VocabItemIn] = Field(..., min_length=1)


class VocabItemOut(BaseModel):
    word_id: uuid.UUID
    word: str
    rank: int | None = None
    frequency: int | None = None
    star: int
    verified: bool


class VocabItemsOut(BaseModel):
    total: int
    items: list[VocabItemOut]


# ── R6 知识节点资源 ──────────────────────────────────────────
class NodeResourceItem(BaseModel):
    id: uuid.UUID
    node_id: uuid.UUID
    node_name: str | None = None
    resource_type: str
    dimension: str | None = None
    title: str | None = None
    content_md: str | None = None
    media_url: str | None = None
    resource_json: object | None = None
    status: str


class NodeResourceListOut(BaseModel):
    total: int
    items: list[NodeResourceItem]


# ── 单元补全总览(发布前预览完整度 + 补全缺失维度)──
class LectureCell(BaseModel):
    id: uuid.UUID
    status: str
    has_content: bool
    pending_version_id: uuid.UUID | None = None


class UnitContentNode(BaseModel):
    node_id: uuid.UUID
    name: str
    dims: dict[str, LectureCell | None]


class UnitContentOverviewOut(BaseModel):
    total_nodes: int
    items: list[UnitContentNode]


class UnitPublishOut(BaseModel):
    published: int
    already_published: int
    missing_dims: int


# ── 版本对比 / 审核(C2)──
class VersionDiffSide(BaseModel):
    label: str
    content_md: str
    version_no: int | None = None
    source: str | None = None
    status: str | None = None


class VersionDiffOut(BaseModel):
    base: VersionDiffSide
    incoming: VersionDiffSide


class VersionItem(BaseModel):
    id: uuid.UUID
    version_no: int
    source: str
    status: str
    content_md: str | None = None
    created_at: datetime | None = None
    reviewed_at: datetime | None = None


class VersionListOut(BaseModel):
    resource_id: uuid.UUID
    total: int
    items: list[VersionItem]


class AddResourceIn(BaseModel):
    node_id: uuid.UUID
    resource_type: str = Field(..., description="lecture|video|example|essay|mindmap")
    dimension: str | None = Field(None, description="仅 lecture:听/词汇/语法/阅读/翻译/写作")
    title: str | None = None
    content_md: str | None = None
    media_url: str | None = None
    resource_json: object | None = None
    status: str = "draft"


class UpdateResourceIn(BaseModel):
    content_md: str | None = None
    media_url: str | None = None
    title: str | None = None
    resource_json: object | None = None


# ── 长难句(学生端) ──────────────────────────────────────────
class LongSentenceNodeRef(BaseModel):
    node_id: uuid.UUID
    name: str
    node_kind: str | None = None


class LongSentenceItem(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    syntax_points: list[str] = []
    favorited: bool = False
    difficulty: int | None = None


class LongSentenceListOut(BaseModel):
    total: int
    items: list[LongSentenceItem]


class LongSentenceDetailOut(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    analysis: dict | None = None      # main_clause/layers/translation/difficulty_points/syntax_points
    audio_url: str | None = None      # 听原句直链(已合成则有,前端直接播;无则调 /audio 生成)
    favorited: bool = False           # 当前用户是否已收藏
    nodes: list[LongSentenceNodeRef] = []   # 句法点 → 跳 /curriculum/nodes/{node_id}/resources


class VerifyTypesOut(BaseModel):
    types: list[str]                  # 已开放(且本期可用)的验证题型,学生自选


class VerifyQuestionOut(BaseModel):
    type: str
    prompt: str
    options: list[str]                # 不含答案


class VerifySubmitIn(BaseModel):
    type: str
    answer: str = Field(..., min_length=1)


class VerifySubmitOut(BaseModel):
    correct: bool
    correct_answer: str
    mastered_nodes: list[str] = []    # 本次达标判掌握的句法点


# ── 理解检测(Phase1 双探针:过关才算学;θ 实测为主)──────────────
class ComprehensionProbe(BaseModel):
    key: str                          # main_clause / paraphrase / cloze / struct_type
    type: str
    prompt: str
    options: list[str]                # 不含答案


class ComprehensionOut(BaseModel):
    probes: list[ComprehensionProbe]  # 通常 2 个:点主干 + 释义/意义


class ComprehensionSubmitIn(BaseModel):
    answers: dict[str, str]           # {probe_key: 学生答案}
    self_rating: str | None = None    # 可选自评(easy|ok|hard),小权重修正 θ


class ComprehensionProbeResult(BaseModel):
    key: str
    correct: bool
    correct_answer: str
    misconception: str | None = None  # 选错时:该错项对应的理解失败诊断


class ComprehensionResultOut(BaseModel):
    passed: bool                      # 双探针全过 = 这句算「学会了」
    probes: list[ComprehensionProbeResult]
    theta: float
    target: float
    tier: str


# ── 短翻译产出项(Phase3:维度 rubric 评分,检验「会输出」)────────
class TranslateCheckIn(BaseModel):
    answer: str = Field(..., min_length=1)   # 学生中文翻译


class TranslateDim(BaseModel):
    key: str                          # proposition/logic/modifier/trunk
    label: str                        # 命题准确/逻辑关系/修饰归属/主干完整
    score: int
    max: int
    note: str | None = None           # 该维一句点评


class TranslateCheckOut(BaseModel):
    dimensions: list[TranslateDim]
    total: int
    max: int
    passed: bool                      # 总分达标且命题≥1 = 输出达标
    feedback: str | None = None       # 总评:最该改进的一处
    theta: float
    target: float
    tier: str


# ── 迁移项(Phase3b:同结构新句,区分「记住题」vs「会技能」)──────────
class TransferItem(BaseModel):
    id: uuid.UUID
    text: str
    difficulty: int | None = None


class TransferOut(BaseModel):
    item: TransferItem | None = None         # 找不到同结构新句→None
    shared: list[str] = []                    # 与原句共享的句法结构名
    probes: list[ComprehensionProbe] = []     # 迁移句的理解检测题(双探针)


class TransferSubmitIn(BaseModel):
    transfer_id: uuid.UUID
    answers: dict[str, str]


class TransferResultOut(BaseModel):
    passed: bool
    verdict: str                              # transferred=真掌握 / memorized=疑似记住原题
    shared: list[str]
    probes: list[ComprehensionProbeResult]
    theta: float
    target: float
    tier: str


# ── 长难句(后台 L5) ──────────────────────────────────────────
class LSAdminItem(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    status: str
    syntax_points: list[str] = []
    difficulty: int | None = None
    textbook_version: str | None = None
    stage: str | None = None
    grade: str | None = None
    semester: str | None = None
    exam_type: str | None = None


class LSAdminListOut(BaseModel):
    total: int
    items: list[LSAdminItem]


class LSExtractIn(BaseModel):
    source: str = "config"
    limit: int = 200
    filters: dict | None = None   # 教材:textbook_version/grade/semester/unit_ids;真题:+stage/exam_type/region(多值列表)


class LSExtractOut(BaseModel):
    created: int
    long_kept: int
    edges: int
    candidates: int
    skipped_done: int


class LSConfigOut(BaseModel):
    sources: list[str]
    verify_types: list[str]
    min_words: int
    required_pass: int
    textbook_difficulty_min: int | None = None
    textbook_top_n: int = 3


class LSConfigIn(BaseModel):
    sources: list[str] | None = None
    verify_types: list[str] | None = None
    min_words: int | None = None
    required_pass: int | None = None
    textbook_difficulty_min: int | None = None
    textbook_top_n: int | None = None
