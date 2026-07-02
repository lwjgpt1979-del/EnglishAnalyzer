"""域23: 电销 CRM(平台自用优先,预留机构维度)。

线索池 → 外呼/企微 → 分析 → 跟进 闭环。P0 只用 sales_lead + sales_lead_activity;
外呼录音/ASR/意向分析走 activity 的 nullable 列(P1),企微存档 P2 另建表。

枚举一律用 varchar 存(免迁移、免 PG enum 约束),取值见各列注释。
方案详见 docs/电销CRM-方案设计.md。
"""
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import mapped_column

from .base import Base


class SalesLead(Base):
    """销售线索/商家。地区走 region_service(存 region_code,与 user.city_code 同源)。"""

    __tablename__ = "sales_lead"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = mapped_column(sa.String(200), nullable=False)          # 商家/机构名
    contact_name = mapped_column(sa.String(80), nullable=True)    # 联系人
    phone = mapped_column(sa.String(32), nullable=True)           # 电话(外呼主键)
    wechat_id = mapped_column(sa.String(128), nullable=True)      # 微信/企微 external_userid
    address = mapped_column(sa.String(255), nullable=True)
    region_code = mapped_column(sa.String(12), nullable=True)     # region 表码,省/市
    region_name = mapped_column(sa.String(64), nullable=True)     # 冗余展示名
    industry = mapped_column(sa.String(64), nullable=True)        # 行业标签
    biz_tags = mapped_column(JSONB, nullable=True)                # 经营特征(招聘/推广/资质…,借探迹维度)

    source = mapped_column(sa.String(20), nullable=False, server_default=sa.text("'manual'"))
    # source ∈ baidu_map|meituan|dianping|tungee|manual|import|other
    source_note = mapped_column(sa.String(255), nullable=True)    # 合规:来源与合法性依据

    status = mapped_column(sa.String(16), nullable=False, server_default=sa.text("'new'"))
    # status ∈ new|contacted|interested|negotiating|won|lost|invalid

    intent_score = mapped_column(sa.Integer, nullable=True)       # 0–100 最新意向分(P1 回填)
    intent_grade = mapped_column(sa.String(2), nullable=True)     # A|B|C|D 意向分层
    product_feedback = mapped_column(JSONB, nullable=True)        # 产品意见原始抽取(聚类前)
    similar_score = mapped_column(sa.Float, nullable=True)        # 赢单画像反查得分

    consent = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))
    dnc = mapped_column(sa.Boolean, nullable=False, server_default=sa.text("false"))   # true→禁呼
    pool = mapped_column(sa.String(8), nullable=False, server_default=sa.text("'public'"))
    # pool ∈ public|private
    owner_admin_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    claimed_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)          # 认领进私海(回收计时基准)
    last_contacted_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)
    next_follow_at = mapped_column(sa.TIMESTAMP(timezone=True), nullable=True)      # 下次跟进(待办)

    # 预留机构维度:P0 恒 null,P3 生效。不加 FK 以免过早耦合 institutions 表。
    institution_id = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.Index("ix_sales_lead_pool_status", "pool", "status"),
        sa.Index("ix_sales_lead_owner", "owner_admin_id"),
        sa.Index("ix_sales_lead_region", "region_code"),
        sa.Index("ix_sales_lead_next_follow", "next_follow_at"),
        sa.Index("ix_sales_lead_phone", "phone"),
    )


class SalesLeadActivity(Base):
    """跟进记录(一线索多条)。call/wechat 的录音·转写·意向分析走 nullable 列(P1)。"""

    __tablename__ = "sales_lead_activity"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("sales_lead.id", ondelete="CASCADE"), nullable=False)
    admin_id = mapped_column(
        UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    channel = mapped_column(sa.String(8), nullable=False)         # call|wechat|note|sms
    direction = mapped_column(sa.String(4), nullable=True)        # out|in
    content = mapped_column(sa.Text, nullable=True)               # 跟进内容/备注
    outcome = mapped_column(sa.String(16), nullable=True)         # connected|no_answer|rejected|callback…

    # P1 通话/分析预留
    recording_url = mapped_column(sa.String(512), nullable=True)  # 录音(COS)
    call_duration_sec = mapped_column(sa.Integer, nullable=True)
    asr_text = mapped_column(sa.Text, nullable=True)              # 转写
    intent_score = mapped_column(sa.Integer, nullable=True)       # 本次通话意向分
    analysis = mapped_column(JSONB, nullable=True)                # 意向分析 schema 输出

    created_at = mapped_column(
        sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_sales_activity_lead", "lead_id", "created_at"),)
