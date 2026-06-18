<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listNodeResources, addNodeResource, reviewNodeResource } from '../api/admin'
import type { NodeResourceItem2 } from '../types'

const status = ref('draft')
const typeFilter = ref('')
const rows = ref<NodeResourceItem2[]>([])
const total = ref(0)
const loading = ref(false)

const statusOptions = ['draft', 'reviewing', 'published', 'retired']
const types = [
  { label: '全部类型', value: '' },
  { label: '讲解', value: 'lecture' },
  { label: '视频', value: 'video' },
  { label: '例句库', value: 'example' },
  { label: '写作范文', value: 'essay' },
  { label: '思维导图', value: 'mindmap' },
]
const dimensions = ['listening', 'vocabulary', 'grammar', 'reading', 'translation', 'writing']

const addDlg = ref(false)
const form = ref({ node_id: '', resource_type: 'video', dimension: 'grammar',
                   title: '', content_md: '', media_url: '', status: 'draft' })

async function load() {
  loading.value = true
  try {
    const data = await listNodeResources({
      status: status.value || undefined,
      resource_type: typeFilter.value || undefined,
      limit: 50,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function onReview(row: NodeResourceItem2, approve: boolean) {
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '驳回'}该资源？`, '确认', { type: 'warning' })
  await reviewNodeResource(row.id, approve)
  ElMessage.success(approve ? '已发布' : '已驳回')
  await load()
}

async function confirmAdd() {
  if (!form.value.node_id.trim()) { ElMessage.warning('请填知识节点 node_id'); return }
  const body: any = {
    node_id: form.value.node_id.trim(), resource_type: form.value.resource_type,
    title: form.value.title || undefined, content_md: form.value.content_md || undefined,
    media_url: form.value.media_url || undefined, status: form.value.status,
  }
  if (form.value.resource_type === 'lecture') body.dimension = form.value.dimension
  try {
    await addNodeResource(body)
    ElMessage.success('已新增')
    addDlg.value = false
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '新增失败') }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>状态：</span>
      <el-select v-model="status" style="width: 130px" @change="load">
        <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <span style="margin-left: 16px">类型：</span>
      <el-select v-model="typeFilter" style="width: 130px" @change="load">
        <el-option v-for="t in types" :key="t.value" :label="t.label" :value="t.value" />
      </el-select>
      <el-button style="margin-left: 12px" type="success" @click="addDlg = true">+ 新增资源</el-button>
      <el-button @click="load">刷新</el-button>
      <span class="hint">资源挂知识图谱节点(knowledge_nodes);讲解六维度/视频/例句/范文/思维导图</span>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column prop="resource_type" label="类型" width="90" />
      <el-table-column prop="dimension" label="维度" width="100" />
      <el-table-column prop="title" label="标题" min-width="140" show-overflow-tooltip />
      <el-table-column prop="content_md" label="正文" min-width="180" show-overflow-tooltip />
      <el-table-column prop="media_url" label="媒体URL" min-width="160" show-overflow-tooltip />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status !== 'published'">
            <el-button size="small" type="success" @click="onReview(row, true)">发布</el-button>
            <el-button size="small" type="danger" @click="onReview(row, false)">驳回</el-button>
          </template>
          <span v-else class="muted">已发布</span>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="addDlg" title="新增知识节点资源" width="520px">
      <el-form label-width="90px">
        <el-form-item label="node_id"><el-input v-model="form.node_id" placeholder="knowledge_nodes.id" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.resource_type" style="width:100%">
            <el-option v-for="t in types.filter(x=>x.value)" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.resource_type === 'lecture'" label="维度">
          <el-select v-model="form.dimension" style="width:100%">
            <el-option v-for="d in dimensions" :key="d" :label="d" :value="d" />
          </el-select>
        </el-form-item>
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="正文"><el-input v-model="form.content_md" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="媒体URL"><el-input v-model="form.media_url" placeholder="视频/音频/图 直链" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="success" @click="confirmAdd">新增</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.muted { color: #c0c4cc; }
</style>
