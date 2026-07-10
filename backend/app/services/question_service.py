"""判分工具（KP-First 收敛后本模块仅保留纯字符串判分器 _grade）。

历史:原含 SimulatedQuestion 提交/去重/运营审核/学情读(知识点正确率/模考历史/班级排名)等,
均在 R8 Phase6a-1/6a-2 退役——练习/仿真统一到节点化 platform_question,真值走 answer_log/
student_kp;诊断页三张读冻结 sim 表的卡片(part3)一并退。_grade 无老表耦合,仍被
question_serve_service / wrong_review_service / assignment_service 复用。
"""
from __future__ import annotations


def _grade(question_type: str, correct_answer: str, user_answer: str) -> bool:
    ua = user_answer.strip()
    ca = correct_answer.strip()
    if question_type in ("单选", "完型", "阅读"):
        return ua.upper() == ca.upper()
    if question_type == "判断":
        return ua == ca
    if question_type == "填空":
        candidates = [c.strip().lower() for c in ca.split("|") if c.strip()]
        return ua.lower() in candidates
    if question_type == "写作":
        return True  # 写作不判分，永远视为完成（前端展示范文供对照）
    if question_type == "连线":
        # 答案格式 "1-A|2-B|3-C"，set 比较忽略顺序
        ua_pairs = {p.strip() for p in ua.split("|") if p.strip()}
        ca_pairs = {p.strip() for p in ca.split("|") if p.strip()}
        return ua_pairs == ca_pairs
    return ua == ca
