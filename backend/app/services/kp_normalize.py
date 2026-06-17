"""KP 名归一化(R0.2/R0.3/R0.4 共享)。

把"知识点名"折叠成一个**确定性**归一键,用于:
  - `node_alias.alias_norm`(全局唯一,一个写法只指一个节点)
  - `kp_candidate.name_norm`((name_norm, suggested_axis) 唯一去重累加)
  - 受控匹配第 1 步(归一化精确命中)

刻意只做确定性折叠(全半角/大小写/空白/标点),**不做语义同义改写**
("过去完成式" vs "过去完成时" 的合并交受控匹配模糊步 + 人工审核 merge 别名)。

归一键仅用于比对/去重,不用于展示;原始写法保留在 alias / raw_name。
"""

from __future__ import annotations

import unicodedata


def normalize_kp_name(raw: str) -> str:
    """折叠成归一键:NFKC 全角→半角 → 去除空白与标点 → ASCII 小写,仅保留 CJK 与字母数字。

    例:
      "定语从句。"            -> "定语从句"
      "过去  完成时"          -> "过去完成时"
      "现在完成时(Present)"   -> "现在完成时present"
      "Present Perfect"       -> "presentperfect"
    """
    if not raw:
        return ""
    # 1) 全角→半角 / 兼容字符规范化
    s = unicodedata.normalize("NFKC", raw)
    # 2) 仅保留字母数字与 CJK(isalnum 对汉字/字母/数字均为真),其余(空白/标点/符号)丢弃;ASCII 统一小写
    return "".join(ch.lower() for ch in s if ch.isalnum())


def stages_from_grades(grades: list[str] | None) -> list[str]:
    """年级名(如 ["小学5年级","初中7年级"])→ 学段子集 ["小","初","高"](去重保序)。

    grade→stage 的单一真源(R0.2 种子迁移与 R1 教材抽取共用)。
    """
    out: list[str] = []
    for g in grades or []:
        seg = "小" if "小" in g else "初" if "初" in g else "高" if "高" in g else None
        if seg and seg not in out:
            out.append(seg)
    return out
