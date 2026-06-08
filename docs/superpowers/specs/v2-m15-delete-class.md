# V2 M15 — 教师班级解散功能

## 背景
backend `DELETE /teacher/classes/{id}` 和 frontend `deleteClass()` 均已存在，
但两个页面（`teacher/class-detail.vue`、`teacher/classes.vue`）均未调用。

## 目标
1. `teacher/class-detail.vue`：在"学生"tab 底部添加「解散班级」按钮，
   二次确认后调用 `deleteClass(classId)` 并返回上一页。
2. `teacher/classes.vue`：班级列表每行右侧添加「解散」按钮（阻止冒泡），
   二次确认后调用 `deleteClass(c.id)` 并刷新列表。

## 验收标准
- 点击「解散班级」弹出 showModal 确认框，取消不触发请求。
- 确认后调用 API，成功则 toast 提示、关闭/刷新页面。
- 失败时 toast 显示错误信息。
- 解散中按钮 disabled 防重复提交。
