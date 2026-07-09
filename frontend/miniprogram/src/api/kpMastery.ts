// src/api/kpMastery.ts — M42 知识点掌握台账 API
import { request } from '@/utils/request'

export interface KpMasteryItem {
  kp_key: string
  kp_id: string | null
  kp_description: string | null
  correct_count: number
  wrong_count: number
  accuracy: number          // 原始正确率 0~1（兼容保留）
  mastery: number           // 加权掌握度 0~1（展示口径）
  mastery_events: number    // 事件数 C；< 10 证据不足
  sources: string[]         // e.g. ["practice","assignment"]
  last_activity_at: string | null
}

/** GET /api/v1/kp-mastery/ — 返回当前学生的知识点台账，按掌握度 ASC 排序（弱项优先） */
export function getKpMastery(): Promise<KpMasteryItem[]> {
  return request<KpMasteryItem[]>('/api/v1/kp-mastery/')
}

// ── M46 趋势（加权掌握度，从 answer_log 重放）───────────────────────────────────

export interface KpTrendPoint {
  date: string          // YYYY-MM-DD
  mastery: number       // 加权掌握度 0~1（当日日末值）
  mastery_events: number
}

/** GET /api/v1/kp-mastery/trend — 返回指定 node 最近 N 天的日掌握度趋势 */
export function getKpTrend(nodeId: string, days = 30): Promise<KpTrendPoint[]> {
  return request<KpTrendPoint[]>(
    `/api/v1/kp-mastery/trend?node_id=${encodeURIComponent(nodeId)}&days=${days}`,
  )
}
