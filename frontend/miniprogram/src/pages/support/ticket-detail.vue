<!-- 客服工单对话（§13.1）-->
<template>
  <view class="dt-page">
    <view class="msgs">
      <view v-for="m in messages" :key="m.id" class="msg" :class="m.sender_role">
        <text class="who">{{ m.sender_role === 'admin' ? '客服' : '我' }} · {{ fmt(m.created_at) }}</text>
        <view class="bubble">{{ m.content }}</view>
      </view>
    </view>
    <view v-if="ticket && ticket.status !== 'closed'" class="composer">
      <input v-model="reply" class="ipt" placeholder="输入回复…" maxlength="1000" confirm-type="send" @confirm="send" />
      <button class="send" :disabled="sending || !reply.trim()" @tap="send">发送</button>
    </view>
    <view v-else-if="ticket" class="closed">该工单已结案</view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { ticketThread, replyTicket, type Ticket, type TicketMessage } from '@/api/support'

const id = ref('')
const ticket = ref<Ticket | null>(null)
const messages = ref<TicketMessage[]>([])
const reply = ref('')
const sending = ref(false)
function fmt(s: string | null) { return (s || '').replace('T', ' ').slice(0, 16) }

async function load() {
  try { const r = await ticketThread(id.value); ticket.value = r.ticket; messages.value = r.messages }
  catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
}
async function send() {
  if (!reply.value.trim()) return
  sending.value = true
  try { await replyTicket(id.value, reply.value.trim()); reply.value = ''; await load() }
  catch (e: any) { uni.showToast({ title: e?.message || '发送失败', icon: 'none' }) }
  finally { sending.value = false }
}

onLoad((q) => { id.value = (q as any)?.id || ''; if (id.value) load() })
</script>

<style scoped>
.dt-page { padding: 24rpx 24rpx 140rpx; background: #f5f6f8; min-height: 100vh; }
.msgs { display: flex; flex-direction: column; gap: 20rpx; }
.msg { display: flex; flex-direction: column; }
.msg.admin { align-items: flex-start; }
.msg.user { align-items: flex-end; }
.who { font-size: 22rpx; color: #999; margin-bottom: 6rpx; }
.bubble { max-width: 80%; padding: 18rpx 24rpx; border-radius: 16rpx; font-size: 28rpx; line-height: 1.5; white-space: pre-wrap; }
.msg.admin .bubble { background: #fff; color: #333; }
.msg.user .bubble { background: #409eff; color: #fff; }
.composer { position: fixed; left: 0; right: 0; bottom: 0; display: flex; gap: 16rpx; padding: 20rpx 24rpx; background: #fff; box-shadow: 0 -2rpx 8rpx rgba(0,0,0,0.05); }
.ipt { flex: 1; background: #f0f2f5; border-radius: 999rpx; padding: 16rpx 28rpx; font-size: 28rpx; }
.send { background: #409eff; color: #fff; border-radius: 999rpx; font-size: 28rpx; padding: 0 36rpx; }
.closed { text-align: center; color: #999; font-size: 26rpx; margin-top: 40rpx; }
</style>
