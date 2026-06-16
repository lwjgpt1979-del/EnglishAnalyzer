<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getPricing, updatePricing, getPricingHistory, type PriceHistoryItem } from '../api/admin'

const form = reactive({ basic: 0, pro: 0, promax: 0, list_basic: 0, list_pro: 0, list_promax: 0 })
const loading = ref(false)
const saving = ref(false)
const history = ref<PriceHistoryItem[]>([])

async function load() {
  loading.value = true
  try {
    const p = await getPricing()
    form.basic = p.basic; form.pro = p.pro; form.promax = p.promax
    form.list_basic = p.list_basic || 0; form.list_pro = p.list_pro || 0; form.list_promax = p.list_promax || 0
    history.value = await getPricingHistory(20)
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await updatePricing({ ...form })
    ElMessage.success('已保存（已存档历史价格）')
    history.value = await getPricingHistory(20)
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

onMounted(load)
</script>

<template>
  <div style="display:flex; gap:16px; flex-wrap:wrap">
    <el-card v-loading="loading" style="max-width: 520px">
      <template #header>学期会员定价（元 / 学期）· 划线价为 0 则不展示</template>
      <el-form label-width="130px">
        <el-form-item label="basic 实售/划线">
          <el-input-number v-model="form.basic" :min="1" /><span class="sep">/</span>
          <el-input-number v-model="form.list_basic" :min="0" />
        </el-form-item>
        <el-form-item label="pro 实售/划线">
          <el-input-number v-model="form.pro" :min="1" /><span class="sep">/</span>
          <el-input-number v-model="form.list_pro" :min="0" />
        </el-form-item>
        <el-form-item label="promax 实售/划线">
          <el-input-number v-model="form.promax" :min="1" /><span class="sep">/</span>
          <el-input-number v-model="form.list_promax" :min="0" />
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
        <p class="hint">已支付订单按支付时价格执行，不追溯；每次保存自动存档历史价格用于退款/争议举证（§5.7）。</p>
      </el-form>
    </el-card>

    <el-card v-loading="loading" style="flex:1; min-width: 360px">
      <template #header>价格变更历史</template>
      <el-table :data="history" size="small" max-height="420">
        <el-table-column label="时间" width="150"><template #default="{ row }">{{ fmt(row.created_at) }}</template></el-table-column>
        <el-table-column label="basic" width="100"><template #default="{ row }">{{ row.snapshot.basic }}<span v-if="row.snapshot.list_basic" class="strike">/{{ row.snapshot.list_basic }}</span></template></el-table-column>
        <el-table-column label="pro" width="100"><template #default="{ row }">{{ row.snapshot.pro }}<span v-if="row.snapshot.list_pro" class="strike">/{{ row.snapshot.list_pro }}</span></template></el-table-column>
        <el-table-column label="promax" width="100"><template #default="{ row }">{{ row.snapshot.promax }}<span v-if="row.snapshot.list_promax" class="strike">/{{ row.snapshot.list_promax }}</span></template></el-table-column>
      </el-table>
      <div v-if="!history.length" class="hint">暂无历史记录</div>
    </el-card>
  </div>
</template>

<style scoped>
.sep { margin: 0 8px; color: #999; }
.hint { color: #909399; font-size: 12px; margin-top: 12px; }
.strike { color: #c0c4cc; text-decoration: line-through; margin-left: 2px; }
</style>
