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

## 其它

- 中文字体:全局已设字体栈 + 抗锯齿(miniprogram 在 `App.vue` 的 `page`/`uni-page-body`;admin/institution 在 `index.html`),新页面无需重复设置。
- 主色:天空蓝 `--c-primary: #3d8bf5`,交互色一律用 CSS 变量(`var(--c-primary)` 等),勿硬编码。
