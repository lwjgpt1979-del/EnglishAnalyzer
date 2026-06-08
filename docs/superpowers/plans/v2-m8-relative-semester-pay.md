# V2 M8 Plan: relative/student-view 代付迁移至 V2 学期购买

## 实现步骤

### Step 1: 更新 `relative/student-view.vue`

#### Script 变更
1. 新增 `textbook`, `grade`, `semester` ref（默认值：'译林版', '小学5年级', '上'）
2. 复制 semester-purchase.vue 的 textbookOptions / gradeOptions / semesterOptions 常量
3. 将 `tiers` 价格改为 `[{ key:'basic', label:'基础版', price:39 }, { key:'pro', label:'Pro', price:79 }, { key:'promax', label:'ProMax', price:159 }]`
4. 将 `selectedTier` 的 key 改为 `'basic'`（原本是 `tier` 字段，改为 `key`）
5. `onPay` 里 createOrder 改为：
   ```ts
   createOrder({
     tier: selectedTier.value,
     order_type: 'new',
     semesters: [{ textbook_version: textbook.value, grade: grade.value, semester: semester.value }],
     target_student_id: studentId.value,
   })
   ```

#### Template 变更
1. 在代付卡片标题下方加教材版本 picker、年级 picker、学期 picker
2. 价格显示改为 `/学期`
3. 代付卡片 title 改为"为孩子购买学期会员"

### Step 2: TDD
- 测试文件：`tests/api/test_relative_semester_order.py`
- 测试：家人用 V2 semesters 参数给学生下单，断言订单成功创建 (RED → GREEN)

### Step 3: Build verify
```bash
cd frontend/miniprogram && npx tsc --noEmit
```

## 风险
- 无后端变更，仅前端修改
- `createOrder` API 已支持 `semesters` + `target_student_id` 参数（现有 semester-purchase.vue 已在用）
