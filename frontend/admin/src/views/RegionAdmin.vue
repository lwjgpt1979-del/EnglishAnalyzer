<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminListRegions, createRegion, updateRegion, deleteRegion, type RegionNode } from '../api/admin'

const treeKey = ref(0)              // 自增强制重载懒加载树
const treeProps = { label: 'name', isLeaf: 'leaf' }
const LEVEL_NAME: Record<number, string> = { 1: '省', 2: '市', 3: '区县', 4: '乡镇' }

async function loadNode(node: any, resolve: (rows: RegionNode[]) => void) {
  const parent = node.level === 0 ? undefined : node.data.code
  try { resolve(await adminListRegions(parent)) } catch (e: any) { ElMessage.error(e?.message || '加载失败'); resolve([]) }
}
function reload() { treeKey.value++ }

// 新增
const addDlg = ref(false)
const addParent = ref<string | null>(null)
const addLevel = ref(1)
const addForm = ref({ code: '', name: '' })
function openAdd(parentData: RegionNode | null) {
  addParent.value = parentData ? parentData.code : null
  addLevel.value = parentData ? parentData.level + 1 : 1
  addForm.value = { code: '', name: '' }
  addDlg.value = true
}
async function confirmAdd() {
  if (!addForm.value.code.trim() || !addForm.value.name.trim()) { ElMessage.warning('请填代码和名称'); return }
  try {
    await createRegion({ code: addForm.value.code.trim(), name: addForm.value.name.trim(),
      parent_code: addParent.value, level: addLevel.value })
    ElMessage.success('已新增')
    addDlg.value = false
    reload()
  } catch (e: any) { ElMessage.error(e?.message || '新增失败') }
}

async function rename(data: RegionNode) {
  const { value } = await ElMessageBox.prompt('新名称', `改名 ${data.name}`, { inputValue: data.name })
  await updateRegion(data.code, value.trim())
  ElMessage.success('已改名')
  reload()
}
async function del(data: RegionNode) {
  await ElMessageBox.confirm(`确认删除「${data.name}(${data.code})」?有下级会被拒绝。`, '确认', { type: 'warning' })
  try { await deleteRegion(data.code); ElMessage.success('已删除'); reload() }
  catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}
</script>

<template>
  <div>
    <div class="toolbar">
      <el-button type="primary" @click="openAdd(null)">+ 新增省级</el-button>
      <el-button @click="reload">刷新</el-button>
      <span class="hint">行政区划唯一数据源(region 表);省→市→区县→乡镇逐级展开。code 与学生 city_code 同源;
        区县/乡镇批量请用 scripts/import_regions.py。</span>
    </div>

    <el-tree :key="treeKey" :props="treeProps" :load="loadNode" lazy node-key="code"
             :expand-on-click-node="false" style="max-width:760px">
      <template #default="{ data }">
        <span class="row">
          <span class="name">{{ data.name }}</span>
          <span class="meta">{{ data.code }} · {{ LEVEL_NAME[data.level] || data.level }}</span>
          <span class="ops">
            <el-button link size="small" type="primary" @click.stop="openAdd(data)">加下级</el-button>
            <el-button link size="small" @click.stop="rename(data)">改名</el-button>
            <el-button link size="small" type="danger" @click.stop="del(data)">删除</el-button>
          </span>
        </span>
      </template>
    </el-tree>

    <AppDialog v-model="addDlg" :title="`新增${LEVEL_NAME[addLevel] || ''}地区`" width="420px">
      <el-form label-width="90px">
        <el-form-item label="上级">
          <span style="color:#909399">{{ addParent || '(省级,无上级)' }}</span>
        </el-form-item>
        <el-form-item label="区划代码" required>
          <el-input v-model="addForm.code" placeholder="如 省2位/市4位/区县6位/乡镇9位" />
        </el-form-item>
        <el-form-item label="名称" required><el-input v-model="addForm.name" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmAdd">新增</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.row { display: flex; align-items: center; gap: 12px; flex: 1; }
.name { font-weight: 500; }
.meta { color: #909399; font-size: 12px; }
.ops { margin-left: auto; }
</style>
