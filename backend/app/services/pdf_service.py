"""PDF 生成服务（V2 M37）— 学情诊断报告导出。

依赖：fpdf2（pip install fpdf2）
字体：app/static/fonts/AlibabaPuHuiTi.ttf（阿里巴巴普惠体，Apache 2.0）
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

from fpdf import FPDF, XPos, YPos

from app.schemas.diagnosis import DiagnosisReport

_FONT_PATH = Path(__file__).parent.parent / "static" / "fonts" / "AlibabaPuHuiTi.ttf"
_FALLBACK_FONT = "helvetica"  # 纯 ASCII fallback（无中文字体时）

# 颜色常量（RGB）
_C_GOLD = (180, 140, 30)
_C_INK = (30, 30, 30)
_C_SECOND = (100, 100, 100)
_C_LINE = (220, 220, 220)
_C_BG = (250, 247, 235)


def _has_cn_font() -> bool:
    return _FONT_PATH.exists()


class _ReportPDF(FPDF):
    """自定义 FPDF 子类，封装重复渲染逻辑。"""

    def __init__(self) -> None:
        super().__init__(unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=15)
        if _has_cn_font():
            self.add_font("cn", fname=str(_FONT_PATH))
            self._fn = "cn"
        else:
            self._fn = _FALLBACK_FONT

    # ── 便捷方法 ────────────────────────────────────────────────────────────

    def cn(self, size: int = 11) -> None:
        self.set_font(self._fn, size=size)

    def set_ink(self) -> None:
        self.set_text_color(*_C_INK)

    def set_second(self) -> None:
        self.set_text_color(*_C_SECOND)

    def set_gold(self) -> None:
        self.set_text_color(*_C_GOLD)

    def divider(self) -> None:
        self.set_draw_color(*_C_LINE)
        self.line(15, self.get_y(), 195, self.get_y())
        self.ln(3)

    def section_title(self, title: str) -> None:
        self.ln(4)
        self.set_gold()
        self.cn(12)
        self.cell(0, 8, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.divider()
        self.set_ink()

    def kv_row(self, label: str, value: str) -> None:
        self.cn(10)
        self.set_second()
        self.cell(55, 7, label)
        self.set_ink()
        self.cn(11)
        self.cell(0, 7, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bar_row(self, label: str, count: int, max_count: int, width: float = 100.0) -> None:
        """横向条形图行。"""
        self.cn(10)
        self.set_ink()
        self.cell(55, 6, label[:20])  # 截断超长标签
        # 背景条
        self.set_fill_color(230, 230, 230)
        self.rect(self.get_x(), self.get_y() + 1, width, 4, style="F")
        # 数值条
        bar_w = (count / max_count * width) if max_count > 0 else 0
        self.set_fill_color(*_C_GOLD)
        if bar_w > 0:
            self.rect(self.get_x(), self.get_y() + 1, bar_w, 4, style="F")
        self.set_x(self.get_x() + width + 3)
        self.set_second()
        self.cn(9)
        self.cell(15, 6, str(count), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def generate_diagnosis_pdf(report: DiagnosisReport, *, student_name: str | None = None) -> bytes:
    """生成学情诊断报告 PDF，返回 bytes。"""
    pdf = _ReportPDF()
    pdf.add_page()

    today = date.today().strftime("%Y 年 %m 月 %d 日")

    # ── 封面标题 ─────────────────────────────────────────────────────────────
    # 金色背景标题区
    pdf.set_fill_color(*_C_BG)
    pdf.rect(0, 0, 210, 40, style="F")

    pdf.ln(6)
    pdf.set_gold()
    pdf.cn(22)
    pdf.cell(0, 12, "学情诊断报告", align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_second()
    pdf.cn(10)
    subline = f"engGramer  ·  {today}"
    if student_name:
        subline += f"  ·  {student_name}"
    pdf.cell(0, 6, subline, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)

    # ── 总览数据 ─────────────────────────────────────────────────────────────
    pdf.section_title("📊 总览")
    mastery_pct = f"{report.mastery_rate * 100:.1f}%"
    pdf.kv_row("累计错题数", str(report.total_questions))
    pdf.kv_row("已完成 AI 分析", str(report.total_analyzed))
    pdf.kv_row("已标记掌握", str(report.mastered_count))
    pdf.kv_row("掌握率", mastery_pct)

    # ── 题型分布 ─────────────────────────────────────────────────────────────
    if report.question_type_distribution:
        pdf.section_title("📝 题型分布")
        max_v = max(report.question_type_distribution.values(), default=1)
        for qtype, cnt in sorted(
            report.question_type_distribution.items(), key=lambda x: -x[1]
        ):
            pdf.bar_row(qtype or "未标注", cnt, max_v)

    # ── 薄弱知识点 ───────────────────────────────────────────────────────────
    if report.top_weak_knowledge_points:
        pdf.section_title("⚠️ 薄弱知识点（Top 10）")
        max_cnt = report.top_weak_knowledge_points[0].count if report.top_weak_knowledge_points else 1
        for item in report.top_weak_knowledge_points:
            pdf.bar_row(item.knowledge_point, item.count, max_cnt)

    # ── 错误类型分布 ─────────────────────────────────────────────────────────
    if report.top_error_types:
        pdf.section_title("🔍 错误类型分布（Top 10）")
        max_cnt = report.top_error_types[0].count if report.top_error_types else 1
        for item in report.top_error_types:
            pdf.bar_row(item.error_type, item.count, max_cnt)

    # ── AI 综合建议 ──────────────────────────────────────────────────────────
    if report.top_suggestions:
        pdf.section_title("💡 AI 综合建议")
        for i, sug in enumerate(report.top_suggestions, 1):
            pdf.cn(10)
            pdf.set_ink()
            # 包裹长文本（multi_cell 自动换行）
            pdf.set_x(15)
            pdf.multi_cell(175, 6, f"{i}. {sug}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)

    # ── 页脚 ──────────────────────────────────────────────────────────────────
    pdf.set_y(-20)
    pdf.set_second()
    pdf.cn(8)
    pdf.cell(0, 5, "本报告由 engGramer AI 自动生成，仅供参考。", align="C")

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf.read()
