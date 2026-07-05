<script setup lang="ts">
import { ref } from 'vue'
import MapLeadPanel from './MapLeadPanel.vue'

const tab = ref<'baidu' | 'amap'>('baidu')
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">地图获客</h3>
      <span class="hint">百度、高德各自独立配置(AK/Key、行业)与采集;两家数据都去重入库同一电销 CRM,额度用尽自动停。</span>
    </div>

    <el-tabs v-model="tab" type="border-card">
      <el-tab-pane label="百度地图" name="baidu" lazy>
        <MapLeadPanel source="baidu" />
      </el-tab-pane>
      <el-tab-pane label="高德地图" name="amap" lazy>
        <MapLeadPanel source="amap" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
</style>
