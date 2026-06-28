<script setup lang="ts">
import { onMounted, reactive, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import {
  createPurchase, listPurchases, getPurchaseCodes, getCodePricing,
  type PurchaseListItem, type ActivationCode, type CodePricing,
} from '../api/institution'

// 单价读后台配置（分 / 月），与计费同源；接口未到位时不估价（不写死遮蔽）。
const pricing = ref<CodePricing | null>(null)
const form = reactive({ tier: 'pro', duration_months: 6, quantity: 1 })
const purchases = ref<PurchaseListItem[]>([])
const codes = ref<ActivationCode[]>([])
const codesTitle = ref('')

const estimate = computed(() => {
  const fen = pricing.value?.[form.tier as keyof CodePricing]
  if (fen == null) return '—'
  return (fen * form.duration_months * form.quantity / 100).toFixed(2)
})

async function load() {
  pricing.value = await getCodePricing()
  purchases.value = await listPurchases()
}

async function submit() {
  const d = await createPurchase({ ...form })
  ElMessage.success(`已生成 ${d.codes.length} 个激活码`)
  codes.value = d.codes
  codesTitle.value = `本次采购（${d.tier} / ${d.duration_months}个月 / ${d.quantity}个）`
  await load()
}

async function viewCodes(p: PurchaseListItem) {
  codes.value = await getPurchaseCodes(p.id)
  codesTitle.value = `采购 ${p.created_at.slice(0, 10)}（${p.tier}）`
}

onMounted(load)
</script>

<template>
  <div>
    <h2 class="title">学生采购</h2>
    <el-card style="margin-bottom: 16px">
      <el-form inline>
        <el-form-item label="档位">
          <el-select v-model="form.tier" style="width: 120px">
            <el-option label="基础" value="basic" />
            <el-option label="Pro" value="pro" />
            <el-option label="ProMax" value="promax" />
          </el-select>
        </el-form-item>
        <el-form-item label="时长(月)">
          <el-input-number v-model="form.duration_months" :min="1" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="form.quantity" :min="1" />
        </el-form-item>
        <el-form-item label="预估金额">
          <span>{{ estimate === '—' ? '—' : '¥ ' + estimate }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="submit">采购（dev-mock 即付）</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="purchases" border style="margin-bottom: 16px">
      <el-table-column prop="tier" label="档位" />
      <el-table-column prop="duration_months" label="时长(月)" />
      <el-table-column prop="quantity" label="数量" />
      <el-table-column label="金额(元)">
        <template #default="{ row }">{{ (row.amount_fen / 100).toFixed(2) }}</template>
      </el-table-column>
      <el-table-column label="已用/总数">
        <template #default="{ row }">{{ row.used_count }} / {{ row.total_count }}</template>
      </el-table-column>
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button text type="primary" @click="viewCodes(row)">查看激活码</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-card v-if="codes.length">
      <div class="codes-title">{{ codesTitle }}</div>
      <el-tag v-for="c in codes" :key="c.code" :type="c.status === 'used' ? 'info' : 'success'" class="code-tag">
        {{ c.code }}{{ c.status === 'used' ? '（已用）' : '' }}
      </el-tag>
    </el-card>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.codes-title { margin-bottom: 12px; color: #555; }
.code-tag { margin: 4px 8px 4px 0; font-family: monospace; }
</style>
