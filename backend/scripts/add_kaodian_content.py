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

    # ── 词法 · 冠词 · 不定冠词 ──
    "cf-2-1-1": """## 冠词的用法及分类

冠词是虚词,常用在名词前,帮助说明名词所表示的人或事物,不可单独使用。冠词可分为三种:不定冠词、定冠词和零冠词。""",

    "cf-2-1-2": """## 不定冠词 a / an 的基本用法

1. 泛指一类人或事物,也可以指某人或某物。
   - e.g. A teacher should be responsible for students.
2. 表示数量,意为"一"。
   - e.g. a book 一本书
3. 用在某些物质名词前,表示"一场、一阵"。
   - e.g. a terrible storm 一场可怕的暴风雨;a light rain 一场小雨;a wonderful tea 一杯好喝的茶
4. 用于序数词前,表示"又一,再一"。
   - e.g. I have three books. I want to buy a fourth book.""",

    "cf-2-1-3": """## 不定冠词 a / an 的用法区别

1. a 用于以辅音音素开头的单词或字母前。e.g. a ball 一个球;a word 一个单词
2. an 用于以元音音素开头的单词或字母前。e.g. an apple 一个苹果;an hour 一个小时
3. 以下列字母开头的单词需注意两种情况:
   - u:发辅音用 a(a university 一所大学);发元音用 an(an umbrella 一把伞)
   - h:发辅音用 a(a headmaster 一名校长);"h" 不发音用 an(an hour 一个小时;an honest boy 一个诚实的男孩)
4. 以元音音素开头的字母有 12 个:a, e, f, h, i, l, m, n, o, r, s, x。
   - e.g. There is an "i" in the word "fish".""",

    "cf-2-1-4": """## 含不定冠词的常用短语

make an effort 努力;make a living 谋生;make a difference 有影响;make a decision 决定;make an agreement 达成一致;make a fortune 发财;take a break 休息一下;take a message 传话;have a rest 休息一会儿;have a good time 玩得愉快;have a try 试一试;have a nice view 旅途愉快;come to an end 结束;catch a cold 得感冒;keep an eye on 照看;pay a visit 参观;in a word 总之;in a moment 一会儿;in a sense 在某种意义上;in a way 在某种程度上;for a while 暂时;once in a while 偶尔;as a matter of fact 事实上;as a result 因此;as a whole 总的来说;as a rule 通常""",

    "cf-2-1-5": """## 不定冠词的位置

不定冠词 a / an 一般用于可数名词单数之前,但要注意以下几种情况:
1. 位于 such、many、half 等词之后。e.g. such a wonderful book 如此精彩的一本书;many a tale 许多故事;half an hour 半小时
2. 当名词前的形容词被 so、how 等修饰时,不定冠词应放在形容词之后。e.g. how beautiful a girl 多么美丽的一个女孩;so interesting a movie 如此有趣的一部电影
3. quite、rather 与可数名词单数连用时,不定冠词位于其后(名词前有形容词时,位于其前后均可)。e.g. quite a clever person = a quite clever person 一个相当聪明的人
4. 名词被副词 hardly、scarcely、barely、exactly 和一个形容词同时修饰时,冠词须放在上述副词之后、形容词之前。e.g. This is hardly a right thing.""",

    # ── 词法 · 冠词 · 定冠词 ──
    "cf-2-2-1": """## 定冠词的功能及发音

定冠词在名词前起修饰或限定作用,不能单独使用。""",

    "cf-2-2-2": """## 定冠词的使用原则

1. 表示特指,即某个特定的人或特定的事物等。e.g. The boy standing there is my friend.
2. 指上文提到的人或事物。e.g. I have a pen. The pen is blue.
3. 指谈话双方都熟知的人或事物。e.g. Look at the blackboard, please.
4. 指世界上独一无二的事物。e.g. The sun rises in the east.""",

    "cf-2-2-3": """## 定冠词的常见用法

1. 放在乐器名前,此时通常指一类乐器。e.g. play the piano 弹钢琴
2. 放在形容词最高级前。e.g. the best person 最好的人
3. 放在形容词原级前,表示一类人或某种品质。e.g. the young 年轻人;the rich 富人;the old 老年人
4. 作主语时谓语动词一般用复数。e.g. The young are trying their best to make the world better.
5. 表示某个人或某种抽象概念时,谓语动词一般用单数。e.g. The good is always what we want.
6. 放在姓氏复数前,表示一家人。e.g. the Greens 格林一家
7. 放在序数词前。e.g. the first 第一
8. 用在江、河、海、洋、山脉、群岛、海峡、海湾等专有名词前。e.g. the Yangtze River 长江;the United Nations 联合国""",

    "cf-2-2-4": """## 含定冠词的常用短语

all the time 一直;at the age of 在……岁时;at the beginning of 在……开始;in the end 最后;in the middle of 在……中间;in the future 在将来;all the best 一切顺利;at the same time 同时;at the back of 在……的后面;in the distance 在远方;in the dark 在黑暗中;in the habit of 有……的习惯;by the way 顺便说;make the most of 充分利用;on the whole 总的说来;on the spot 当场;on the one hand …, on the other hand … 一方面……另一方面……;in the day 在白天;on the right / left 在右边 / 左边;all the same 尽管如此;go to the cinema 去看电影;on the way 在路上""",

    "cf-2-2-5": """## 定冠词的位置

定冠词通常位于名词或名词修饰语之前,但遇到 all、both、half、twice 等词时,定冠词放在这类词之后、名词之前。
- e.g. all the students 所有的学生""",

    "cf-2-2-6": """## 定冠词的易错用法

1. 有些表示时间的词在习惯用法中不使用定冠词 the。e.g. at dawn 在黎明;at noon 在中午;at dusk 在黄昏;at night 在夜晚
2. 注意:next 不同于 the next,last 不同于 the last。next Sunday 指从现在算起的"下一个星期天",the next Sunday 指将来或过去某时算起的"下一个星期天"。
   - e.g. She will be back next week. She went to England in May and went to France the next month.""",

    # ── 词法 · 冠词 · 零冠词 ──
    "cf-2-3-1": """## 零冠词的使用原则

零冠词是指名词前不加冠词的情况,以下情况会用零冠词:
1. 表示泛指的物质名词前,通常用零冠词。e.g. Paper is made from wood.
2. 表示泛指的抽象名词或部分专有名词前,通常不用冠词。e.g. My pet dog brings my family great pleasure!
3. 表示泛指的可数名词复数前,通常不用冠词。e.g. Apples are my favourite fruit.;Lions and tigers belong to the cat family.
4. 名词前有指示代词、形容词性物主代词等修饰时,前面不用冠词。e.g. That book is their teacher's.""",

    "cf-2-3-2": """## 零冠词的高频用法

1. 星期、月份、季节、节日等名词前一般不用冠词。e.g. on Monday 在星期一;in May 在五月;on Mother's Day 在母亲节
2. 表示"一日三餐"的名词前一般不用冠词。e.g. have breakfast 吃早餐;have dinner 吃晚餐
3. 球类与棋类运动等名词前不用冠词。e.g. play football 踢足球;play chess 下国际象棋
4. 表示语言或学科的名词前不用冠词。e.g. My favourite subject is English.
5. man 泛指人类时,其前不加冠词。e.g. Man can't live without water or air.
6. by + 交通工具,中间无冠词。e.g. by bus 乘公共汽车
7. 表示官衔、职位、身份的名词前一般不用冠词。e.g. The guards took him to General Lee.""",

    "cf-2-3-3": """## 零冠词的固定搭配

1. 两个相对的名词并用:father and son 父子;war and peace 战争与和平;husband and wife 夫妇
2. 对称的名词搭配:day by day 一天天;face to face 面对面;hand in hand 手拉手;one by one 逐个地;step by step 一步一步地
3. 介词短语搭配:by chance 偶然;on purpose 故意;on board 在船(或火车、飞机)上;in fact 事实上;in return 作为回报
4. 动词短语搭配:make friends with 与……交朋友;pay attention to 注意;keep in touch with 与……保持联系;keep ... in mind 记住""",

    "cf-2-3-4": """## 有无冠词的短语辨析

| 情况 | 有冠词 | 无冠词 |
| --- | --- | --- |
| 不定冠词与零冠词 | in a word 总而言之 | in words 口头上 |
| 定冠词与零冠词 | go to the school 去学校 | go to school 去上学 |
| 定冠词与零冠词 | go to the bed 去床边 | go to bed 去睡觉 |
| 定冠词与零冠词 | go to the church 去教堂(建筑) | go to church 去做礼拜 |
| 定冠词与零冠词 | at the table 在桌子旁 | at table 在吃饭 |
| 定冠词与零冠词 | by the day 按日计算 | by day 在白天 |
| 定冠词与零冠词 | in the front of 在(内部)的前面 | in front of 在……前面 |
| 定冠词与零冠词 | in the prison 在监狱(建筑) | in prison 在坐牢 |
| 定冠词与零冠词 | out of the question 不可能 | out of question 毫无疑问 |
| 定冠词与零冠词 | in the charge of 由……掌管 | in charge of 掌管 |
| 定冠词与零冠词 | take the place of 代替 | take place 发生 |""",

    # ── 词法 · 代词 · 人称代词 ──
    "cf-3-1-1": """## 代词的定义及分类

**定义**:代词是代替名词或起名词作用的短语、分句和句子的词,在句子中起指代和修饰的作用。

**分类**:英语中的代词一般分为人称代词、物主代词、指示代词、反身代词、相互代词、疑问代词、关系代词、连接代词和不定代词。""",

    "cf-3-1-2": """## 人称代词的定义

人称代词是用来替代人或物的词,有人称、数和格的变化。
- e.g. It is my best friend.;We are never too old to learn.""",

    "cf-3-1-3": """## 人称代词的形式及分类

人称代词在人称上分为第一、第二、第三人称;在数上分为单数与复数;在句法功能上分为主格与宾格。

| 人称 | 单数主格 | 单数宾格 | 复数主格 | 复数宾格 |
| --- | --- | --- | --- | --- |
| 第一人称 | I 我 | me 我 | we 我们 | us 我们 |
| 第二人称 | you 你 | you 你 | you 你们 | you 你们 |
| 第三人称 | he/she/it 他/她/它 | him/her/it 他/她/它 | they 他们 | them 他们 |""",

    "cf-3-1-4": """## 人称代词的句法功能

1. 主格是动作的发出者,通常位于句首作主语;一般现在时主语为第三人称单数时,谓语动词用第三单数。
   - e.g. We often play football after school.;She likes playing the piano in the room.
2. 宾格是动作的承受者,通常位于谓语动词或介词后作宾语,位于系动词后作表语。
   - e.g. The man teaches us English.(宾语);It was him who the girl wanted to talk with.(表语)""",

    "cf-3-1-5": """## 人称代词的易错用法

1. 人称代词与所代替的词在人称和数上保持一致。
   - e.g. Meat and fish are more expensive than they used to be.;I don't like the book because it is too dull.
2. 多个人称代词并列出现时,单数按"二三一"、复数按"一二三"顺序排列。
   - e.g. You, she and I must finish the task.;We, you and they should exercise every day.
3. 表示承担责任、承认错误或检讨工作时,把第一人称放在前。
   - e.g. I have the responsibility for solving these problems.""",

    # ── 词法 · 代词 · 物主代词和反身代词 ──
    "cf-3-2-1": """## 物主代词的定义

物主代词是表示所有关系的代词,有人称和数的变化,意为"……的",分为形容词性物主代词和名词性物主代词。
1. 形容词性物主代词:相当于形容词,置于名词前主要作定语。e.g. Her dress is beautiful.
2. 名词性物主代词:相当于名词,可作主语、宾语和表语。e.g. The book I have is not as good as his.""",

    "cf-3-2-2": """## 物主代词的形式及分类

物主代词是人称代词的属格形式,表示"所有",分第一、第二、第三人称及单复数。

| 人称 | 形容词性(单/复) | 名词性(单/复) |
| --- | --- | --- |
| 第一人称 | my / our | mine / ours |
| 第二人称 | your / your | yours / yours |
| 第三人称 | his, her, its / their | his, hers, its / theirs |

形容词性物主代词 + 名词 = 名词性物主代词。e.g. This is mine.""",

    "cf-3-2-3": """## 反身代词的定义

反身代词指动作的承受者就是动作执行者本身,也用于强调语气,有人称和数的变化,意为"……自己"。
- e.g. I can do it by myself.""",

    "cf-3-2-4": """## 反身代词的形式及分类

| 人称 | 单数 | 复数 |
| --- | --- | --- |
| 第一人称 | myself 我自己 | ourselves 我们自己 |
| 第二人称 | yourself 你自己 | yourselves 你们自己 |
| 第三人称 | himself / herself / itself 他/她/它自己 | themselves 他们自己 |""",

    "cf-3-2-5": """## 物主代词的句法功能

1. 形容词性物主代词常放在名词前作定语。e.g. His book describes happy memories.
2. 名词性物主代词可作主语、宾语和表语。e.g. He has a pencil. But mine is lost.(主语);I don't know why you want to steal mine.(宾语)""",

    "cf-3-2-6": """## 反身代词的句法功能

反身代词可作宾语及表语,也可用于谓语或宾语的同位语,表强调。
- e.g. I study by myself.(宾语);I myself can do it.(作主语的同位语)""",

    "cf-3-2-7": """## 物主代词的常用短语

earn one's living 谋生;lose one's way 迷路;hold one's breath 屏住呼吸;make up one's mind 下决心;take one's time 慢慢来;make one's way 前进;in one's opinion 依某人看;in one's eyes 在某人看来;keep one's word 守信;do one's best 尽某人最大的努力""",

    "cf-3-2-8": """## 反身代词的常用短语

**与介词搭配**:by oneself 单独;for oneself 为自己;of oneself 自发地;to oneself 独自拥有
**与动词搭配**:dress oneself 自己穿衣服;enjoy oneself 过得愉快;help oneself 自取;teach oneself 自学;make yourself at home 别拘束;devote oneself to 致力于;behave oneself 举止得体;talk to oneself 自言自语;abandon oneself to 沉溺于;come to oneself 恢复知觉;say to oneself 自言自语""",

    # ── 词法 · 代词 · 不定代词(1) ──
    "cf-3-3-1": """## 不定代词的定义及句法功能

**定义**:① 不明确指代某个人、某个事物、某些人、某些事物的代词;② 表示不同的数量概念且没有主格和宾格之分的代词。

**句法功能**:不定代词在句中可作主语和宾语,部分可作定语;作主语时谓语动词视其指代内容可用单数也可用复数。
- e.g. Everybody needs to study hard.(主语);I know nothing about this history.(宾语);I would like to buy another one.(定语);We all have our troubles.(作主语的同位语)""",

    "cf-3-3-2": """## some 与 any 的用法

1. **some** 常用于肯定句,意为"一些"。e.g. There is some water in the glass.;用在一般疑问句中,表示提出建议或期望得到肯定回答。e.g. Would you like some bread?
2. **any** 常用于否定句和疑问句,意为"一些"。e.g. I don't have any money.;用在肯定句中表示强调,意为"任何,任一"。e.g. You can ask me any question.
3. some 和 any 修饰名词时,谓语动词取决于名词的单复数。e.g. Some advice indeed helps me solve problems.""",

    "cf-3-3-3": """## 复合不定代词的分类

由 some-, any-, every-, no- 加 -one, -body, -thing 构成的代词作复合不定代词,在句中作用相当于名词。

| 后缀 \\ 前缀 | some- | any- | no- | every- |
| --- | --- | --- | --- | --- |
| -one | someone 某人 | anyone 任何人 | no one 没有人 | everyone 每个人 |
| -body | somebody 某人 | anybody 任何人 | nobody 没有人 | everybody 每个人 |
| -thing | something 某物 | anything 任何事物 | nothing 没什么 | everything 每件事 |""",

    "cf-3-3-4": """## 复合不定代词的常用表达

1. There is something wrong with ... "……出问题了"。e.g. There is something wrong with my computer.
2. ... have / has something / nothing to do with ... "与……有/无关系"。e.g. It has nothing to do with me.""",

    "cf-3-3-5": """## 复合不定代词的用法

1. some- 和 any- 构成的复合不定代词的用法同 some 和 any。e.g. Something needs to be corrected.;Please don't hold anything back.
2. 复合不定代词作主语时,谓语动词用第三人称单数。e.g. Everyone is here.
3. 形容词修饰复合不定代词时,需要放在其后。e.g. something important 某些重要的事情
4. 复合不定代词后常加 else 表示"另外的",所有格形式为"复合不定代词 + else's"。e.g. You should borrow someone else's car.
5. every- 系列的复合不定代词用于否定时,常表示部分否定。e.g. Not everybody obeys the rule.
6. no one 表示"没有人",相当于 nobody。e.g. No one is here. = There is nobody here.""",

    # ── 词法 · 代词 · 不定代词(2) ──
    "cf-3-4-1": """## each 与 every 的用法及区别

1. 基本用法区别:each 意为"每一个",强调个体,多用于两者及两者以上,可与 of 连用。e.g. There are four apples here and each of them tastes sweet.;every 意为"每一个",强调整体,多用于三者及三者以上,不能直接与主语连用。e.g. I could hear every word they said.
2. "every + 数词 + 名词" 表示"每……",不能用 each 代替。e.g. We do our homework every three days.
3. 句法功能区别:each 可作主语、宾语、定语、同位语;every 只能作定语。e.g. We each have our own particular tastes.;Every book is worth reading.""",

    "cf-3-4-2": """## "三三两两"的用法及区别

**三者及三者以上**:
1. all 意为"全部",all of 结构作主语时谓语动词由后面的名词决定。e.g. All of the students are good in our school.
2. any 意为"任何一个"。e.g. any girl 任何一位女生
3. none 意为"没有一个",none of 结构作主语时单复数均可。e.g. None of them believe / believes the story.

**两者**:
1. both 意为"两者都",both ... and ... 连接主语时谓语动词用复数。e.g. Both Lily and I like playing games.
2. either 意为"两者之一",either ... or ... 连接主语时遵循就近原则。e.g. Either you or she is going to the park.
3. neither 意为"两者都不",neither ... nor ... 连接主语时遵循就近原则。e.g. Neither Jerry nor I am a student.""",

    "cf-3-4-3": """## other 系列的用法及区别

1. one ... the other ... 表示两者之间的"另一个"。e.g. I have two pens. One is blue and the other is red.
2. some ... others ... 表示"一些……另一些……"。e.g. Some are reading books and others are cleaning the window.
3. another 表示三者或三者以上中的"另一个"。e.g. This coat is too big for me. Can you show me another one?
4. another + 数词 + 名词复数 = 数字 + more + 名词复数,表示"另外几个"。e.g. another two apples = two more apples 另外两个苹果""",

    "cf-3-4-4": """## "多多少少"的用法及区别

| 含义 | 后加可数名词复数 | 后加不可数名词 |
| --- | --- | --- |
| 几乎没有 | few | little |
| 一点 | a few | a little |
| 许多 | many | much |

1. not a little / quite a little / not a few / quite a few 意为"很多"。e.g. There's not a little time left.
2. too much / too many 意为"太多",后面加名词。e.g. There are too many flowers in the garden.
3. much too 意为"太……",中心词是 too,后面加形容词或副词。e.g. You are much too clever.""",

    # ── 词法 · 代词 · 指示代词、疑问代词和 it ──
    "cf-3-5-1": """## 指示代词的分类及用法

指示代词是用来指示或标识人或事物的代词。

| 指示代词 | 用法 | 例句 |
| --- | --- | --- |
| this 这个(单数,近) | 打电话指自己 | Hello, this is Jane speaking. |
| these 这些(复数,近) | | These are my books. |
| that 那个(单数,远) | 打电话指对方 | Who's that speaking? |
| those 那些(复数,远) | | Those are all basketballs. |""",

    "cf-3-5-2": """## 疑问代词的定义

疑问代词是用来表达疑问的代词,常用来构成特殊疑问句,位于句首。""",

    "cf-3-5-3": """## 疑问代词的用法

| 疑问代词 | 含义 | 基本用法 |
| --- | --- | --- |
| who | 谁 | 作主语、表语、宾语 |
| whom | 谁 | 作宾语(who 的宾格) |
| whose | 谁的 | 作定语、表语 |
| what | 什么 | 作主语、宾语、定语 |
| which | 哪个 | 作主语、宾语、定语 |

1. whom 在句中常作动词或介词的宾语,紧跟介词后作宾语时常用 whom。e.g. Whom / Who do you often play with?
2. which 表示有具体的范围,在具体范围内进行选择,指人或物。e.g. Which colour do you like better, red or yellow?""",

    "cf-3-5-4": """## what 的常用句型

1. 问职业:What + be 动词 + 主语? = What do / does + 主语 + do? e.g. What is your father? = What does your father do?
2. 问外貌:What + does + 主语 + look like? e.g. What does Angela look like?
3. 问天气:What is the weather like? = How is the weather?
4. 征求意见或提建议:What / How about ...? e.g. What / How about going for a swim?
5. 问时间:问几点 What time is it now? = What's the time now?;问日期 What date is it today?;问星期 What day is it today?
6. 问原因或目的:What ... for? / What for? e.g. What did you put it into the soup for?""",

    "cf-3-5-5": """## it 的相关用法及句型

1. 代指上文提到的人或物。e.g. The book is mine. It's very interesting.
2. 代指天气、时间、距离、不明身份的人或婴儿等。e.g. It is about three-hour drive from my home to school.
3. 用在固定搭配中:It's time to do / for ... 是时候做……;It's time for supper.
4. It takes sb. some time to do sth. 做某事花费某人一些时间。e.g. It takes me ten minutes to get to the library.
5. It's + adj. ( + for sb. ) + to do sth. e.g. It's important for us to learn English well.
6. make / feel / find / think / consider + it + adj. + to do sth. e.g. I found it difficult to finish the task on time.""",

    # ── 词法 · 动词 · 实义动词与助动词 ──
    "cf-4-1-1": """## 动词的概念及分类

**定义**:表示动作或状态的词,在句子中主要作谓语。

**分类**:
1. 实义动词:有完整意义,可以单独作谓语。e.g. I like reading books after school.
2. 连系动词:不能单独作谓语,需加表语构成系表结构。e.g. The candy tastes very sweet.
3. 助动词:本身无意义,不能单独作谓语,可帮助实义动词构成各种语法形式。e.g. She didn't finish her homework on time.
4. 情态动词:有本身词义,不能单独作谓语,表示说话人的态度或观点,后加动词原形。e.g. The bird can fly in the sky.""",

    "cf-4-1-2": """## 实义动词的分类及用法

1. 按是否带宾语:及物动词(后可直接带宾语,分单宾语、双宾语、复合宾语)e.g. Please give me the salt.;不及物动词(本身意义完整,后不需宾语,加宾语需在宾语前加合适介词)e.g. Please listen to it carefully.;有些动词既可作及物动词又可作不及物动词。e.g. We study English.
2. 按动作是否延续:持续性动词(又称延续性动词,表示可以持续的行为/过程/状态)e.g. have, keep;终止性动词(又称非延续性动词,表示瞬间完成)e.g. come, go;持续性动词可与表示"一段时间"的状语连用,终止性动词不能。e.g. I have learnt English for three years.""",

    "cf-4-1-3": """## 助动词的分类及用法

| 助动词 | 现在时 | 过去时 |
| --- | --- | --- |
| be | am / is / are | was / were |
| do | do / does | did |
| have | have / has | had |
| shall | shall | should |
| will | will | would |

1. 助动词 be:有人称、数和时态变化,可构成进行时、完成时或被动语态及疑问句形式。e.g. She is swimming now.
2. 助动词 do:主要帮助实义动词构成否定、疑问句形式。e.g. Do you like music?
3. 助动词 have:e.g. We haven't learnt English for many years.(助动词);I don't have that pen.(实义动词)
4. 助动词 will / would / shall / should:will 用于将来时或表示意愿,shall 用于各种人称。e.g. I shall leave for Canada tomorrow.""",

    "cf-4-1-4": """## 常见动词短语搭配

**动词 + 介词**:arrive at / in 到达;believe in 相信;care for 关心;go through 经历;deal with 处理;look into 调查;ask for 请求;break into 闯入;think of 想起;laugh at 嘲笑;lead to 导致;depend on 依靠
**动词 + 副词**:find out 查明;give up 放弃;give out 分发;clear up 清理;cut down 削减;hand out 分发;grow up 长大;break out 发生;break down 出故障
**动词 + 名词 + 介词**:get rid of 摆脱;catch sight of 看见;take care of 照料;take part in 参加;have an effect on 对……有影响;keep an eye on 留心;make friends with 和……交朋友;have influence on 对……有影响""",

    # ── 词法 · 动词 · 系动词 ──
    "cf-4-2-1": """## 系动词的定义及分类

连系动词又称系动词,常用于说明主语的身份、性质和状态等,不可单独作谓语,需与表语一起构成系表结构。

| 系动词类型 | 例词 |
| --- | --- |
| be 动词 | am, is, are, was, were |
| 感官系动词 | look, sound, smell, taste, feel |
| 变化系动词 | become, get, grow, turn |
| 持续系动词 | keep, stay, remain |
| 表象系动词 | seem, appear |""",

    "cf-4-2-2": """## 感官系动词

感官系动词是表示与人的某种感觉相关的系动词,后接形容词,意为"……起来"(look 看起来;sound 听起来;smell 闻起来;taste 尝起来;feel 摸起来)。

**与实义动词的区别**:
1. 作系动词时意为"……起来",后跟形容词。e.g. The girl looks very happy.
2. 作实义动词时意为"看/听/闻"等,可单独作谓语,后接副词或宾语。e.g. The girl looks at her friends happily.""",

    "cf-4-2-3": """## 持续系动词和表象系动词

1. 持续系动词表示主语的特征、状态和身份,意为"保持……状态",常见的有 keep, stay, remain。
   - e.g. Her grandchildren keep her young.;The bookstore stays open until 10:00 p.m.;They remain opposed to the idea.
2. 表象系动词常意为"似乎;看起来",常见的有 seem, appear。
   - e.g. Life seems so unfair sometimes.;He appears to be happy.""",

    "cf-4-2-4": """## 变化系动词

变化系动词常意为"变得……",其后常跟形容词或形容词比较级形式。
- **become / get**:表示状态、心情、天气等变化(get 后跟形容词比较级)。e.g. I became nervous.;The weather gets hotter.
- **grow**:表示成长、发展中的变化。e.g. His hair grows longer and longer.
- **turn**:表示自然现象的变化(turn + 形容词;turn + 名词表示几岁)。e.g. My face turned pale.;Our son turns 3 today.
- **go**:表示朝坏的方向变化。e.g. Things go bad.""",

    # ── 词法 · 动词 · 情态动词(1) ──
    "cf-4-3-1": """## 情态动词的特征

1. 本身有词义,但不能单独作谓语,要和动词原形一起构成谓语。e.g. He can play the piano.(√)
2. 没有人称和数的变化(have to 除外)。e.g. She must go home now.(√)
3. 具有助动词的功能,可构成否定句、疑问句及肯定简略答语。e.g. You should not cross the road when the traffic lights are red.
4. 有些情态动词有过去式。e.g. can—could;may—might""",

    "cf-4-3-2": """## 情态动词表能力

1. can 表示说话人现在具备的一般能力,意为"能够";could 是 can 的过去式,表示过去具备的能力。e.g. I can speak Spanish.;When I was young, I could climb a tree in the forest.
2. can 用于自身具备的能力,be able to 表示通过努力具备的能力。e.g. I can jump high.;I am able to run 3,000 metres in 10 minutes if I practise more.
3. can 是情态动词,无人称和数的变化,主语可以是人或物;be able to 有人称和数的变化,主语一般是人。e.g. Many birds can fly.;Lucy is able to finish her homework by herself.""",

    # ── 词法 · 动词 · 情态动词(2) ──
    "cf-4-4-1": """## 情态动词表推测

| 情态动词 | 含义 | 用法 |
| --- | --- | --- |
| must | 一定 | 确定推测(肯定) |
| can't | 一定不 | 确定推测(否定) |
| may / might / can / could | 可能 | 不确定推测 |

1. 对现在或将来的情况推测:情态动词 + 动词原形。e.g. He might be at home.
2. 对现在或正在发生的情况推测:情态动词 + be doing。e.g. She may be watching TV at home now.
3. 对过去的情况推测:情态动词 + have done。e.g. He can't have seen the film yesterday.""",

    "cf-4-4-2": """## 情态动词表命令或禁止

1. must 表示义务、命令或要求,意为"必须;应该";一般疑问句肯定回答常用 must,否定回答常用 needn't 或 don't have to。e.g. — Must I drink a glass of milk before going to bed? — Yes, you must. / No, you needn't.
2. must 的否定形式为 mustn't,意为"不准;禁止"。e.g. You mustn't swim here.
3. have to 表示客观的需要,must 表示主观上的必要;have to 有人称、数和时态的变化,must 只有一种形式。e.g. My brother was ill, so I had to call the doctor.""",

    "cf-4-4-3": """## 其他常用情态动词

1. **should 的用法**:① 表示义务或责任,意为"应该",常表示主观看法。e.g. You should go home before 9 p.m.;② 用于疑问句表示惊奇、愤怒、失望等,意为"竟然"。e.g. Why should you beat that boy?;③ 表示对可能性的推测,意为"可能"。e.g. Jim should be at home because it is raining outside.
2. **had better 的用法**:① had better (not) 表示劝告或建议,意为"最好(不要)"。e.g. You had better not go by air.;② would rather 表示选择,意为"宁愿",后接动词原形。e.g. I'd rather stay alone.""",

    "cf-4-4-4": """## 情态共存的动词

need 和 dare 既可作情态动词又可作实义动词。

| 动词 | 情态动词用法 | 实义动词用法 |
| --- | --- | --- |
| need 需要 | 肯定 need + do;否定 need not + do | need + to do;don't / doesn't / didn't + need to do |
| dare 敢 | 肯定 dare + do;否定 dare not + do | dare + (to) do;don't / doesn't / didn't + dare (to) do |

- e.g. She need come here.(情态动词);She needs to come here.(实义动词)
- e.g. I dare not go home alone.(情态动词);My brother dares (to) travel by himself.(实义动词)""",
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
