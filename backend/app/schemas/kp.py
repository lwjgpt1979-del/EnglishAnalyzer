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
    dims_filled: int          # 六维讲解已有几维(0-6)
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


class NodeDimCell(BaseModel):
    id: uuid.UUID
    status: str


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
    dims: dict[str, NodeDimCell | None]
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
    answer: str | None = None
    difficulty: int | None = None
    status: str
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


class SuggestKpItem(BaseModel):
    question_id: uuid.UUID
    suggestions: list[QuestionKpRef] = []


class SuggestKpOut(BaseModel):
    items: list[SuggestKpItem] = []


class SuggestKpIn(BaseModel):
    sections: list[str] | None = None      # 仅对这些大题(供「一键挂某大题」)
    prompt_id: str | None = None           # 指定提示词;空=按题型默认


# ── 知识点 AI 提示词配置(按题型,多套选默认)──
class KpPromptItem(BaseModel):
    id: str | None = None
    name: str
    text: str
    question_type: str                     # 单选/填空/完型/阅读/写作
    is_default: bool = False
    focus_node_ids: list[uuid.UUID] = []   # 关注的知识脑图分类(空=全部考点)


class KpPromptsIn(BaseModel):
    prompts: list[KpPromptItem]


class KpPromptsOut(BaseModel):
    prompts: list[KpPromptItem]


class PaperDetailOut(BaseModel):
    paper: PaperListItem
    questions: list[PaperQuestionItem]


class PaperDeleteIn(BaseModel):
    paper_ids: list[uuid.UUID] = Field(..., min_length=1)


class GenSimBulkIn(BaseModel):
    question_ids: list[uuid.UUID] = Field(..., min_length=1)
    count: int = 3


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


class LongSentenceListOut(BaseModel):
    total: int
    items: list[LongSentenceItem]


class LongSentenceDetailOut(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    analysis: dict | None = None      # main_clause/layers/translation/difficulty_points/syntax_points
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


# ── 长难句(后台 L5) ──────────────────────────────────────────
class LSAdminItem(BaseModel):
    id: uuid.UUID
    text: str
    source_kind: str
    status: str
    syntax_points: list[str] = []


class LSAdminListOut(BaseModel):
    total: int
    items: list[LSAdminItem]


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


class LSConfigIn(BaseModel):
    sources: list[str] | None = None
    verify_types: list[str] | None = None
    min_words: int | None = None
    required_pass: int | None = None
