# V2 M15 Plan

1. 新建 `tests/api/test_delete_class.py` — RED: import error
2. `teacher/class-detail.vue`：引入 `deleteClass`，添加 `deleting` ref，
   添加「解散班级」button，实现 `onDelete()` 函数
3. `teacher/classes.vue`：引入 `deleteClass`，添加 `deletingId` ref，
   每行添加「解散」button + `.stop` 阻止冒泡，实现 `onDelete(id)` 函数
4. 后端测试文件实现（GREEN）
5. build verify → commit
