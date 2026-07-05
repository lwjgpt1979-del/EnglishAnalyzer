"""词汇运用/动词填空「语境+所给词→词形考点」确定性归桶测试(Phase A-4,离线)。

用例含三轮真题抽检发现并修复的全部误标类型——回归防线,勿删。
"""
from app.services.kp_suggest_service import classify_word_form as c


def test_positive_buckets():
    assert c("Two more ___________ (library) will be built next year.") == "cf-1-1-2"
    assert c("There are many ___________ (child) in the park.") == "cf-1-1-3"
    assert c("much ___________ (heavy) than that one.") == "cf-5-3-3"
    assert c("get even ___________ (ill) later on.") == "cf-5-3-4"
    assert c("one of the ___________ (famous) places in China.") == "cf-5-3-3"
    assert c("his sister's ___________ (twelve) birthday.") == "cf-6-1-2"
    assert c("live on the ____________(seven) floor") == "cf-6-1-2"
    assert c("What about ___________ (have) a view?") == "jf-5-2-1"
    assert c("We are told ___________ (not laugh) at people.") == "jf-5-1-2"
    assert c("There is no need for you ____▲___(go) to school tomorrow.") == "jf-5-1-2"
    assert c("saved the boy from the fire ___________ (successful).") == "cf-5-2-1"
    assert c("Last week, we ________ (watch) a fashion show.") == "jf-3-2"
    assert c("Listen! Someone_____________(ring) the doorbell.") == "jf-3-4"


def test_priority_morphology_over_tense():
    # 数量词复数须先于 yesterday 时态,避免 two ___(watch) 误判过去时
    assert c("I bought two ___________ (watch) yesterday.") == "cf-1-1-2"


def test_rejects_derivation_and_ambiguity():
    """派生构词/词性歧义 → None(交 LLM/人工),三轮抽检误标类型全覆盖。"""
    assert c("records the _______ (nature) beauty of") is None            # 形容词化
    assert c("the ___▲___ (win) of the 20th FIFA World Cup?") is None      # 名词化
    assert c("a great____ __ __ (invent) of ancient China.") is None       # -ent 动词
    assert c("The party yesterday was a big __________(succeed).") is None  # 名词槽+时间标志
    assert c("went to England for _______ (far) study in 1935.") is None   # 歧义词+介词
    assert c("search the Internet for some ________ (suggest) on how to") is None
    assert c("Everyone's small acts of ________（kind）can make a difference.") is None
    assert c("the snake is ________ (lucky) saved by a young man.") is None  # 副词槽被动误判
    assert c("It's __________ (high) possible that humans move to Mars in the future.") is None
    assert c("destroyed its________ (beautiful) completely") is None       # 物主代词=名词槽


def test_rejects_clause_and_idiom_traps():
    assert c("How will you go to school if it _________( snow) tomorrow?") is None  # 主将从现
    assert c("Grandpa is in his ________ (ninety), but he is willing") is None      # 年龄惯用
    assert c("think_____________ (two) before you take the final action.") is None  # →twice
    assert c("playing football ________（it）is great fun") is None                  # 代词
    assert c("There was ___ (沉默) for a moment. 1. X We ___ (work) right now and ___ (go).") is None  # 多空/OCR合并


def test_no_blank_returns_none():
    assert c("") is None
    assert c("A plain sentence without blank.") is None
