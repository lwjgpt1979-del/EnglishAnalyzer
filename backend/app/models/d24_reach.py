"""域24: 存量用户召回 / 分群触达(与电销 CRM 同一块肌肉:找对人→对的时机→说对的话)。

user_segment  : 可复用分群(rule=JSON 条件组,resolve 成用户集)。
reach_campaign: 触达任务(选分群+渠道+文案→执行→触达统计)。
渠道 MVP:station(站内通知)、sales_lead(生成电销线索,喂电销CRM)。SMS 营销后置(退订+资质)。

枚举一律 varchar 存(免迁移),取值见列注释。
"""
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base


class UserSegment(Base):
    """用户分群(可存可复用)。rule 为条件组,AND 连接;字段见 segment_service.FIELDS。"""

    __tablename__ = "user_segment"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String(80), nullable=False)
    description = mapped_column(sa.String(255), nullable=True)
    # rule: {"conditions": [{"field": "membership_expires_within_days", "op": "lte", "value": 7}, ...]}
    rule = mapped_column(JSONB, nullable=False, server_default=sa.text("'{\"conditions\": []}'"))
    last_count = mapped_column(sa.Integer, nullable=True)          # 上次 resolve 命中数(缓存展示)
    created_by = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now())


class ReachCampaign(Base):
    """触达任务:分群 × 渠道 × 文案 → 执行。渠道=station|sales_lead。

    执行结果统计在 stats(matched/sent/failed/skipped);sales_lead 渠道跳过已存在同号线索。
    """

    __tablename__ = "reach_campaign"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String(120), nullable=False)
    segment_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("user_segment.id", ondelete="SET NULL"), nullable=True)
    rule_snapshot = mapped_column(JSONB, nullable=True)           # 执行时的规则快照(分群改了也可追溯)
    channel = mapped_column(sa.String(16), nullable=False)        # station | sales_lead | sms
    # 文案:station/sms 用 title/content;sales_lead 用 lead_tag(打到线索标签)+ source_note
    title = mapped_column(sa.String(120), nullable=True)
    content = mapped_column(sa.Text, nullable=True)
    lead_tag = mapped_column(sa.String(40), nullable=True)        # 生成线索时打的运营标签,如 会员将到期
    # 生命周期自动化:recurring=True 由 cron 每日增量触达(仅新进入分群、未触达过的人),
    # 状态停留 active(不置 done);enabled 为总开关。one-shot(recurring=False)执行一次即 done。
    recurring = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    enabled = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("true"))
    status = mapped_column(sa.String(12), nullable=False, server_default=sa.text("'draft'"))
    # draft | done | failed | active(recurring 运行中)
    stats = mapped_column(JSONB, nullable=True)                   # 最近一次:{matched,sent,failed,skipped}
    total_reached = mapped_column(sa.Integer, nullable=False, server_default=sa.text("0"))  # 累计触达
    created_by = mapped_column(UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True)
    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    executed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)  # 最近一次执行

    __table_args__ = (sa.Index("ix_reach_campaign_created", "created_at"),)


class ReachLog(Base):
    """触达明细:谁在何时被哪个任务/渠道触达。用于审计 + recurring 去重(每人每任务一次)。"""

    __tablename__ = "reach_log"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("reach_campaign.id", ondelete="CASCADE"), nullable=False)
    user_id = mapped_column(UUID(as_uuid=True), nullable=False)   # 不设 FK(用户注销不牵连历史触达)
    channel = mapped_column(sa.String(16), nullable=False)
    reached_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_reach_log_campaign_user", "campaign_id", "user_id"),)
