<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { getProfile, updateProfile } from '../api/institution'

const form = reactive({
  name: '', contact_phone: '', address: '',
  province_code: '', city_code: '', status: '',
})

onMounted(async () => {
  Object.assign(form, await getProfile())
})

async function save() {
  const r = await updateProfile({
    name: form.name, contact_phone: form.contact_phone, address: form.address,
  })
  Object.assign(form, r)
  ElMessage.success('已保存')
}
</script>

<template>
  <div>
    <h2 class="title">机构资料</h2>
    <el-card style="max-width: 560px">
      <el-form label-width="100px">
        <el-form-item label="机构名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.address" /></el-form-item>
        <el-form-item label="省/市编码"><span>{{ form.province_code }} / {{ form.city_code }}</span></el-form-item>
        <el-form-item label="状态"><el-tag>{{ form.status }}</el-tag></el-form-item>
        <el-form-item>
          <el-button type="primary" @click="save">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
</style>
