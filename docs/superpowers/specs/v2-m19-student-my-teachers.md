# V2 M19 — 学生查看已绑定老师列表

## 背景
学生可以通过 `POST /teacher/bind` 绑定老师，
但没有任何端点让学生查看自己已绑定的老师，
`teacher/students.vue` 的「绑定老师」区域也无列表显示。

## 目标
1. backend：新增 `GET /teacher/my-teachers` 端点，返回当前学生绑定的老师列表
2. frontend：`teacher.ts` 添加 `getMyTeachers()` API
3. frontend：`teacher/students.vue` 在「绑定老师」卡片下方显示「我的老师」列表

## 响应结构
```
[{ teacher_id: string, nickname: string | null, subject: string | null, bound_at: string }]
```

## 验收标准
- 已绑定老师后能在列表中看到该老师（nickname 或 teacher_id 缩略）
- 只显示 status=active 的绑定记录
