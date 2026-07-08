# engGramer 项目约定

## 图标设计规范(全项目统一)

**所有图标统一使用「线性 SVG 图标」,风格对齐学生端首页(`miniprogram/src/pages/index/index.vue` 的 `qi-*` 图标)。禁止使用 emoji 作为 UI 图标。**

规范要点:
- **样式**:Feather/Lucide 风格的描边线性图标 —— `fill='none'`、`stroke-width='2'`、`stroke-linecap='round'`、`stroke-linejoin='round'`、`viewBox='0 0 24 24'`。
- **颜色**:默认主色蓝 `#3d8bf5`(= `--c-primary`);语义色按需(火苗暖橙 `#ff8a3d`、收藏金 `#ffb020` 等)。
- **载体**:用 `<view>` 承载 `background-image: url("data:image/svg+xml,...")`(**小程序 `<text>` 不支持 background-image,必须用 `<view>`**)。SVG 内用单引号属性、`<`→`%3C`、`>`→`%3E`、`#`→`%23`,空格可保留。
- **复用**:miniprogram 端统一用全局图标类 `miniprogram/src/styles/icons.scss`(`.ic` 基类 + `.ic-xxx`),已在 `App.vue` 全局引入;新增图标加到该文件,不要在页面里重复定义。
- **尺寸**:用 `.ic` 默认尺寸或在使用处用 `.xxx.ic { width/height }` 覆盖,单位 rpx。
- **emoji 例外**:仅当 emoji 是**正文内容**(如用户输入、文案里的表情)时保留;凡作「图标/按钮/标签前缀」用途的一律换线性图标。

admin / institution 端(Vue + Element Plus):优先用 Element Plus 自带的线性图标组件(`@element-plus/icons-vue`,本身即线性描边风格),不要用 emoji 作图标;菜单/标题里的装饰 emoji 一并替换。

## 弹框统一控件:最大化 / 复原 / 关闭(admin / institution 全项目强制)

**admin 与机构(institution)系统里,所有弹出框(dialog)标题栏都必须提供「最大化 / 复原 / 关闭」三个控件**;不允许只有一个 `×`。大表格/长表单弹框尤其需要最大化来铺满屏。

铁律:
- **统一用封装组件**:用 `frontend/admin/src/components/AppDialog.vue`(institution 端照此建一份同名组件)替代裸 `el-dialog`——它在 `el-dialog` 上加了「最大化(fullscreen)/ 复原 / 关闭」三控件,近乎透明替换:把 `<el-dialog …>` 改成 `<AppDialog …>`(闭合标签同改),`v-model` / `title` / `width` / 其余属性与插槽照常透传。**不要**再各弹框自己写标题栏控件。
- **最大化 = fullscreen**、复原 = 退出 fullscreen、关闭 = 收起;组件已 `:show-close="false"` 接管标题栏,不再叠加 `el-dialog` 自带的 `×`。
- **自定义标题**:需要富标题的,给 `AppDialog` 传 `#header` 插槽(会渲染在标题位,三控件仍在最右);普通场景传 `title` 属性即可。
- **新增弹框**一律用 `AppDialog`;发现历史裸 `el-dialog` 的,收敛过来(无自定义 `#header` 的可直接换标签)。

## 运营可配置值:必须读后台配置,禁止写死遮蔽(全项目强制)

**凡「运营/后台可配置」的值——价格、额度、限制、配额、文案、开关、模型名等——业务代码必须经对应 service 从 `system_configs`(或相应配置表)读取,严禁在代码里写死常量来决定实际行为。** 否则会出现「后台改了不生效」(典型事故:会员价显示读写死的 `order_service.UNIT_PRICE_FEN`,而非后台 `semester_pricing`)。

铁律:
- **单一数据源**:同一业务量(尤其价格)只有一个真源(后台配置)。展示接口与执行/计费逻辑**必须同源**——**显示价 == 实扣价**,不允许两套常量各算各的。
- **常量仅作兜底/白名单**:写死的 dict/常量只可用于「配置缺失时的默认兜底」或「枚举 key 白名单」,**不得决定金额/额度等实际数值**;并在注释里写明「实际值见 `xxx_service.get_xxx()`,本常量仅兜底」。
- **配套后台入口**:新增一个可变值时,要么接到已有配置 key,要么同时加后台配置入口(admin 接口 + 页面);不要留「只能改代码」的价格/额度。
- **前端不写死**:小程序/admin 展示的价格、额度等一律走接口,不在前端写死(初始占位值也应尽量避免误导;接口失败要有明确兜底/提示)。

~~已知待办:机构激活码定价 `institution_purchase_service.py` 的 `_TIER_MONTHLY_FEN` 写死且无后台入口~~ —— 已配置化:计费读 `pricing_service.get_institution_code_pricing()`(`system_configs.institution_code_pricing`,分/月),后台入口 admin `/admin/institution-code-pricing` GET/PUT(定价配置页);机构采购页估价走 `/institution/code-pricing`,与计费同源。常量仅兜底/白名单。

## 主数据「上架/下架」+ 按角色可见(全项目强制)

**凡「版本/清单」类主数据——教材版本、年级/学期候选、题库/资源分类、机构可选项等——必须由后台单一主数据源产出,并带「上架/下架」状态;严禁前端或多个接口各自写死候选清单,更禁止把「后台真有内容」和「前端展示清单」割裂(典型事故:后台只有译林版有内容,前端修改偏好却写死显示 5 个版本)。**

铁律:
- **单一主数据源**:每类「版本/清单」只有一个真源(主数据表或配置),各端(学生小程序、机构平台、admin)共用同一份接口取值,不另起写死清单。前端只允许「接口失败兜底」,兜底常量必须注释「实际值见 xxx 接口」。
- **上架/下架可见性**:内容消费侧(**学生小程序、机构平台**)**只见已上架(published)**;**admin 后台上架/下架全部可见可管**。展示接口按角色/状态过滤,严禁把下架项泄露给 C 端。
- **统一控制页**:每类主数据配一个 admin 管理页做「编辑 + 上架/下架」(参照课程单元发布闸门 `curriculum_units.status` draft/published);状态切换走后端 service,不在前端本地态糊弄。
- **数量天然对齐**:C 端可选项 = 后台已上架项,不做「规范全量 ∪ distinct」这类会显示空壳版本的合并;需要「学生可填自身属性(如真实年级)」的例外,单独说明并尽量按所选版本已上架内容动态收敛。
- **遇到新的「版本/清单」类功能一律照此办理**;发现历史写死清单的,收敛到主数据 + 上下架 + 角色可见。

## 列表页必须分页(admin / institution 全项目强制)

**admin 与机构(institution)系统里,所有「列表页」都必须带翻页功能——不允许只加载前 N 条就完事。** 数据量大时不分页会导致「看不到后面的数据」(典型:真题列表只显示前 50 份、长难句管理只显示最新 50 条)。

铁律:
- **后端**:列表接口一律支持 `skip`/`limit`(或 page/pageSize)并返回 `total`;分页在 DB 层做(`.offset().limit()`),不要一次性 `SELECT` 全量再前端截断。
- **前端**:列表页放 `el-pagination`(`layout="total, prev, pager, next, jumper"`),`page`/`pageSize` 状态传给接口 `skip=(page-1)*pageSize`。
- **筛选/查询变更回第 1 页**:所有筛选控件的 `@change`、查询/重置按钮统一走 `reload()`(`page.value = 1; load()`),避免在高页码下筛选查到空页;翻页控件 `@current-change="load"`(不重置页码)。
- **新增列表页**照此办理;发现历史列表页没分页的,补上。

## 地区/城市:一律走系统 region 表匹配(全项目强制)

**凡涉及省/市/区县/城市的地方——识别、存储、筛选、匹配——都必须以系统 `region` 表为唯一数据源,经 `region_service` 解析成行政区划码,禁止写死城市清单或只存自由文本城市名。**

铁律:
- **单一数据源**:地区来自 `region` 表(`code`/`name`/`parent_code`/`level`);name→code 用 `region_service.region_from_name(db, text)`(先省后市,名字没省时按市级全国匹配再回推省),级联读用 `region_service.list_children`。
- **存码不存名(或码名并存)**:业务表存 `region_code`(与学生 `user.city_code` **同源**,便于按地区匹配/统计),展示名从 region 表取或 `region_name` 冗余;不要只留一个手输的城市字符串。
- **从文本(文件名/标题/输入)取城市**:一律调 `region_from_name`,不要自己写正则枚举城市;匹配不到再留空/人工补。
- **前端**:选地区用 region 级联(`listRegions` 懒加载省→市),不硬编码 options。

## 其它

- 中文字体:全局已设字体栈 + 抗锯齿(miniprogram 在 `App.vue` 的 `page`/`uni-page-body`;admin/institution 在 `index.html`),新页面无需重复设置。
- 主色:天空蓝 `--c-primary: #3d8bf5`,交互色一律用 CSS 变量(`var(--c-primary)` 等),勿硬编码。
