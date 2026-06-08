# V2 M18 — 教师移除学生

## 背景
TeacherStudent 模型支持 soft-delete（status=inactive + unbound_at），
但后端无 DELETE 端点，前端无移除 UI，教师无法从自己的学生列表移除学生。
另外 `GET /teacher/students` 未过滤 status='active'，会显示已解绑学生。

## 目标
1. backend：添加 `DELETE /teacher/students/{student_id}` 端点
2. backend：修复 `GET /teacher/students` 增加 `.where(status == 'active')` 过滤
3. frontend：`teacher.ts` 添加 `removeStudent(studentId)` API 函数
4. frontend：`teacher/students.vue` 每个学生行添加「移除」按钮

## 验收标准
- 移除后学生从列表消失（status=inactive）
- 不能移除别人的学生，返回 404
- 前端二次确认后执行，成功刷新列表
