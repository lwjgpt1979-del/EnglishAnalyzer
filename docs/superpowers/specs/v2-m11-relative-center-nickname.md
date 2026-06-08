# V2 M11 Spec: 家人中心孩子列表显示昵称

## 问题
`frontend/miniprogram/src/pages/relative/center.vue` 的"我的孩子"列表显示：
```
孩子 a3b4c5d6…
```
而非学生的真实昵称，因为 `BoundStudentOut` 只返回 `{ student_id, relationship, bound_at }`，没有 `nickname`。

## 根因
- 后端 `GET /relative/students` → `BoundStudentOut` 缺 `nickname` 字段
- `list_my_students` 端点没有 JOIN User 表

## 目标
显示 `{nickname} ({relationship})`，若无昵称则退化为 `孩子 {id前8位}…`

## 需求

### 后端
1. `BoundStudentOut` 加 `nickname: str | None`
2. `list_my_students` 端点 JOIN User 表获取 nickname
3. `list_my_relatives` 同步（学生看自己的家人列表也补 nickname）

### 前端
1. `BoundStudent` interface 加 `nickname?: string | null`
2. `relative/center.vue` child 显示：`{{ c.nickname || '孩子 ' + c.student_id.slice(0,8) + '…' }}`

## 影响范围
- `backend/app/schemas/relative.py`
- `backend/app/api/v1/relative.py`
- `frontend/miniprogram/src/types/api.ts`
- `frontend/miniprogram/src/pages/relative/center.vue`
