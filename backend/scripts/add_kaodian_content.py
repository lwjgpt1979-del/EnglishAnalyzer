"""把《中考考频分区速学》PDF 每个考点的讲解正文写入 node_resource(讲解 lecture)。

如实取自 PDF 各频度分区正文(去掉读音/音标);词法考点挂"词汇(vocabulary)"维、
句法考点挂"语法(grammar)"维;generated_by=imported,status=draft(走审核/版本)。
CONTENT 按考点 code 登记,随阅读增量补全。幂等:写前清掉该节点旧讲解再写。
运行:DATABASE_URL=... python3 scripts/add_kaodian_content.py --execute
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.core.database import async_session_factory  # noqa: E402
from app.services import node_resource_service as nrs  # noqa: E402


def _dim(code: str) -> str:
    return "vocabulary" if code.startswith("cf") else "grammar"


# 考点 code → 讲解正文(Markdown,如实照 PDF,去读音)
CONTENT: dict[str, str] = {
    # ── 词法 · 名词 · 可数名词 ──
    "cf-1-1-1": """## 名词的定义及分类

**定义**:表示人、事物、地点或抽象概念名称的词。

**分类**:名词根据词汇意义可分为专有名词和普通名词。

1. **专有名词**:指个别人、事物、地点等所特有的名称。其首字母一般大写,但其中的冠词、介词或虚词的第一个字母一般不大写。
   - e.g. Beijing 北京;the United Kingdom 英国
2. **普通名词**:指一类人、事物、物质或抽象概念的名称,根据意义分为四类。
   - 个体名词:指单个人或单个事物的名词。e.g. friend 朋友;book 书
   - 集体名词:指一群人或一些事物总称的名词。e.g. family 家庭;class 班级
   - 物质名词:指无法分为个体的物质、材料的名词,如食品、饮料、液体、气体等。e.g. juice 果汁;water 水
   - 抽象名词:指人或事物的品质、情感、状态、动作等抽象概念的名词。e.g. love 热爱;honesty 诚实""",

    "cf-1-1-2": """## 可数名词变复数的规则变化

普通名词根据可数性可划分为两类:
- **可数名词**:能用具体数字计数、有单复数形式的名词。一般包括个体名词和集体名词。
- **不可数名词**:不能用具体数字计数的名词,一般只有单数形式。通常包括物质名词和抽象名词。

### 规则变化
| 变化规则 | 例词 |
| --- | --- |
| 一般情况,直接在词尾加 -s | book—books;tree—trees |
| 以 -s, -x, -ch, -sh 等结尾,在词尾加 -es | glass—glasses |
| 以辅音字母加 y 结尾,变 y 为 i 再加 -es | city—cities |
| 以元音字母加 y 结尾,直接加 -s | boy—boys |
| 以 f 或 fe 结尾,变 f 或 fe 为 v 再加 -es | wife—wives |
| 以辅音字母加 o 结尾,一般加 -es | potato—potatoes |
| 以元音字母加 o 结尾,一般加 -s | zoo—zoos |""",

    "cf-1-1-3": """## 可数名词变复数的不规则变化

| 变化规则 | 例词 |
| --- | --- |
| 单复数同形 | sheep 绵羊;deer 鹿;means 方法 |
| 变内部元音 | man → men 男子;foot → feet 脚;tooth → teeth 牙齿;goose → geese 鹅 |
| 变换词尾 | child → children 孩子们;ox → oxen 公牛 |
| 以 -ese 结尾不变 | Chinese → Chinese 中国人;Japanese → Japanese 日本人 |
| 表示"某国人"的复数(-man → -men) | Englishman → Englishmen 英国人;Frenchman → Frenchmen 法国人 |
| 一般直接加 -s | American → Americans 美国人;German → Germans 德国人;Russian → Russians 俄罗斯人 |""",

    "cf-1-1-4": """## 复合名词的构成及复数变化

**定义**:由两个或两个以上的单词合成的名词。

### 构成方式
| 构成方式 | 例词 |
| --- | --- |
| 名词 + 名词 | newspaper 报纸;classroom 教室 |
| 名词 + 动词 | haircut 理发;sunrise 日出 |
| 名词 + 动词-ing | handwriting 书法;horse-riding 骑马 |
| 动词 + 名词 | typewriter 打字机;playground 操场 |
| 形容词 + 名词 | supermarket 超市;greenhouse 温室 |

### 复数变化
1. 有主体词的复合名词,一般把主体词变成复数形式。
   - e.g. housewife → housewives 家庭妇女;daughter-in-law → daughters-in-law 儿媳妇
2. 无主体词的复合名词,一般在词尾加 -s。
   - e.g. grown-up → grown-ups 大人
3. 特殊情况:man 或 woman 所修饰的名词变复数时,前后两个名词都需要变成复数。
   - e.g. a man teacher → three men teachers 三名男老师;a woman doctor → two women doctors 两位女医生""",

    # ── 词法 · 名词 · 不可数名词 ──
    "cf-1-2-1": """## 不可数名词的定义

不可数名词指不能用具体数字计数的名词,一般只有单数形式。通常包括物质名词与抽象名词。""",

    "cf-1-2-2": """## 常见的不可数名词

**物质类**:coffee 咖啡;rice 大米;meat 肉;beef 牛肉;chicken 鸡肉;cloth 布;water 水;tea 茶;sand 沙子;chalk 粉笔;money 钱;furniture 家具;ice 冰;homework 作业

**抽象类**:happiness 幸福;courage 勇气;fun 乐趣;joy 喜悦;knowledge 知识;information 消息;advice 建议;progress 进步;sleep 睡觉;luck 幸运""",

    "cf-1-2-3": """## 不可数名词量的表达

不可数名词一般没有复数形式,作主语时谓语动词用单数。
- e.g. Water is very important so we should save it.

**不可数名词量的表达**:
1. 表示不确定的数量时,一般用 much、a little、a lot / lots of 等修饰。
2. 表示确定的数量时,一般用"冠词 / 数词 + of + 表示量的词"结构来表示;表示量的词为单数则用单数,复数则用复数。
   - e.g. a piece of paper 一张纸;four pieces of paper 四张纸

### 修饰不可数名词的常用表示量的词
| 表示量的词 | 含义 | 示例 |
| --- | --- | --- |
| piece(s) | 张 / 片 | a piece of paper 一张纸 |
| glass(es) | 杯 | three glasses of water 三杯水 |
| cup(s) | 杯 | a cup of tea 一杯茶 |
| bar(s) | 块 | a bar of chocolate 一块巧克力 |
| slice(s) | 片 | three slices of bread 三片面包 |
| carton(s) | 盒 | a carton of milk 一盒牛奶 |""",

    "cf-1-2-4": """## 既可数又不可数的名词

有些名词既属于可数名词又属于不可数名词,它们所表示的含义需要根据具体语境来判断。

| 名词(复数) | 作不可数名词时的含义 | 作可数名词时的含义 |
| --- | --- | --- |
| food(s) | 食物 | (某种)食物 |
| chicken(s) | 鸡肉 | 鸡 |
| fish(es) | 鱼肉 | 鱼 |
| time(s) | 时间 | 次 |
| paper(s) | 纸张 | 试卷,论文,文件 |
| glass(es) | 玻璃 | 玻璃杯 |
| wood(s) | 木材 | 树林 |
| sand(s) | 沙子 | 沙滩 |
| water(s) | 水 | 水域 |
| room(s) | 空间 | 房间 |
| experience(s) | 经验 | 经历 |
| work(s) | 工作 | 作品 |""",

    "cf-1-2-5": """## 名词的修饰语

| 修饰对象 | 主要修饰词 | 示例 |
| --- | --- | --- |
| 可数名词 | a / an 一个 | a pen 一支钢笔;an apple 一个苹果 |
| 可数名词 | few / a few 几乎没有 / 几个 | a few friends 几个朋友 |
| 可数名词 | many 许多 | many books 许多书 |
| 可数名词 | a number of / numbers of 许多 | a number of boys 许多男孩 |
| 不可数名词 | little / a little 几乎没有 / 一点 | little water 几乎没有水;a little water 一点水 |
| 不可数名词 | a bit of 一点 | a bit of love 一点爱 |
| 可数 / 不可数 | much 许多 | much homework 许多作业 |
| 可数 / 不可数 | a large amount of 大量的 | a large amount of water 大量的水 |
| 可数 / 不可数 | some / any 一些 | some experiences 一些经历 |
| 可数 / 不可数 | a lot of / lots of 许多 | lots of suggestions / advice 许多建议 |
| 可数 / 不可数 | plenty of 许多 | plenty of rooms / work 许多房间 / 工作 |
| 可数 / 不可数 | all 所有 | all works / work 所有作品 / 工作 |""",

    # ── 词法 · 名词 · 名词所有格 ──
    "cf-1-3-1": """## 名词所有格的定义

名词所有格表示所属关系,意为"……的"。其形式主要有三种:-'s 所有格、of 所有格和双重所有格。
- e.g. my friend's bag 我朋友的包;the leg of that table 那张桌子的腿;a friend of my brother's 我哥哥的一个朋友""",

    "cf-1-3-2": """## -'s 所有格的构成

构成:名词 + -'s / -'
1. 单数名词和不以 -s 或 -es 结尾的复数名词,一般在词尾加 -'s。
   - e.g. a boy's book 一个男孩的书;children's books 儿童读物
2. 以 -s 或 -es 结尾的复数名词,一般在词尾加 -'。
   - e.g. students' bags 学生们的包
3. 以 s 结尾的单数名词,一般在词尾加 -'s 或 -'。
   - e.g. James's hat / James' hat 詹姆斯的帽子
4. 复合名词,一般在最后一个词后加 -'s。
   - e.g. a woman teacher's dress 一个女老师的连衣裙""",

    "cf-1-3-3": """## -'s 所有格的用法

1. 通常用于表达有生命的名词的所属关系。
   - e.g. the students' favourite sports 学生们最喜爱的运动
2. 用于表示时间、距离、国家等的名词后表示所属关系;表示时间或距离时,可使用"数字 + 名词单数 + 名词复数"的形式。
   - e.g. two days' holiday = a two-day holiday 两天的假期;one hour's drive = a one-hour drive 一小时的车程
3. 用来表示所处地点(如店铺、医院、住宅等),且通常可省略 -'s 后面的名词。
   - e.g. at the barber's 在理发店;at the doctor's 在诊所;at Mr Smith's 在史密斯先生家;Children's Day 儿童节;Teachers' Day 教师节
4. 有时为了避免重复,可以单独使用 -'s 所有格,而省略后面的名词。
   - e.g. Her attitude to this thing is different from my friend's.""",

    "cf-1-3-4": """## of 所有格的用法

of 短语可用来表示所属关系,结构为:(名词)A + of + (名词)B,意为"B 的 A",主要用来修饰前面的名词。
1. 一般用于表示无生命事物间的所属关系。
   - e.g. the beauty of this park 这个公园的美景
2. 也可用于表示有生命事物的所属关系,常见于"the + 形容词",表示一类人。
   - e.g. the future of the young 年轻人的未来;the life of the rich 富人的生活;the problems of the unemployed 失业者的问题
3. 有生命名词的 -'s 所有格也可以用 of 所有格表示。
   - e.g. her daughter's birth = the birth of her daughter 她女儿的诞生
4. 当前后两个名词为同位关系时,只能用 of 所有格。
   - e.g. the city of Beijing 北京城;the month of August 八月""",

    "cf-1-3-5": """## 双重所有格的用法

1. 结构:of + -'s 所有格 / 名词性物主代词。
   - e.g. a computer of my brother's 我哥哥的一台电脑;some books of hers 她的一些书
2. of 前的名词是 picture 或 photo 时,双重所有格和 of 所有格表达的意义不同。
   - e.g. a photo of hers 她(拥有)的一张照片;a photo of her 她(本人)的一张照片""",

    "cf-1-3-6": """## 共同拥有与各自拥有

表示共同拥有或各自拥有时,通常使用的 -'s 所有格形式不同。
1. 表示两者或多者共同拥有时,通常只将最后一个名词变成所有格形式。
   - e.g. Mike and Jack's desk 迈克和杰克(共有)的书桌
2. 表示各自拥有时,需要将每个名词都变为所有格形式,这些名词通常要变成复数。
   - e.g. Mike's and Jack's desks 迈克的书桌和杰克的书桌""",
}


async def main(execute: bool):
    print(f"[content] 待写考点讲解 {len(CONTENT)} 条")
    if not execute:
        for c in CONTENT:
            print(f"  {c} [{_dim(c)}] {len(CONTENT[c])} 字")
        print("  (--execute 写库)")
        return
    async with async_session_factory() as db:
        done = miss = 0
        for code, md in CONTENT.items():
            row = (await db.execute(text("select id from knowledge_nodes where code=:c"), {"c": code})).scalar()
            if row is None:
                print(f"  ! 节点 {code} 不存在,跳过"); miss += 1; continue
            # 清掉该节点旧讲解(避免维度变更后残留 / 重复)
            await db.execute(text("delete from node_resource where node_id=:n and resource_type='lecture'"), {"n": row})
            await nrs.submit_lecture_version(db, node_id=row, dimension=_dim(code), content_md=md,
                                             source="imported", status_if_new="draft",
                                             origin_ref={"flow": "pdf_import"})
            done += 1
        await db.commit()
        print(f"[content] 已写 {done} 条讲解(草稿){'' if not miss else f';缺节点 {miss}'}")


if __name__ == "__main__":
    asyncio.run(main("--execute" in sys.argv))
