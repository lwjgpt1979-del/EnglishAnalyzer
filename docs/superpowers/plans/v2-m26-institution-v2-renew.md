# V2 M26 Plan — 机构批量续费迁移 V2

## 步骤

### 1. Backend schema
`app/schemas/institution.py`：
```python
class BatchRenewRequest(BaseModel):
    student_ids: list[uuid.UUID]
    semesters: int = 1  # 1学期 = 6个月（替代 duration_months）
```

### 2. `institution_renew_service` 改写
- `list_renewable_students`：改查 `purchased_semesters` 表（取每位学生 expires_at 最近的记录）
- `batch_renew`：
  - 查每位学生在机构内的 `purchased_semesters` 最新记录
  - 无记录则 skip
  - 有记录则：`new_expires = max(expires_at, now) + timedelta(days=semesters * 183)`
  - 更新 `purchased_semesters.expires_at`（或新建续费记录）
  - 计价：参考 `TIER_SEMESTER_FEN`（basic=3900, pro=7900, promax=15900）

### 3. Institution frontend
`InstitutionRenew.vue`：
- `months` → `semesters`（label 改为「续费学期数」）
- API 调用改传 `semesters`

### 4. TDD
`tests/api/test_institution_renew_v2.py`
- 续费后 `purchased_semesters.expires_at` 顺延 N * 183 天

## 文件修改清单
- `backend/app/schemas/institution.py`（BatchRenewRequest 改 semesters）
- `backend/app/api/v1/institution.py`（batch_renew 端点更新）
- `backend/app/services/institution_renew_service.py`（改查 purchased_semesters）
- `frontend/institution/src/views/InstitutionRenew.vue`（UI 改为学期）
- `frontend/institution/src/api/institution.ts`（batchRenew 参数类型）
- `tests/api/test_institution_renew_v2.py`（新建）
