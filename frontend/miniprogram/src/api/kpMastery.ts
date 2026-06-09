// src/api/kpMastery.ts — M42 知识点掌握台账 API
import { request } from '@/utils/request'

export interface KpMasteryItem {
  kp_key: string
  kp_id: string | null
  kp_description: string | null
  correct_count: number
  wrong_count: number
  accuracy: number          // 0~1，correct/(correct+wrong)，0 题时为 0
  sources: string[]         // e.g. ["practice","assignment"]
  last_activity_at: string | null
}

/** GET /api/v1/kp-mastery/ — 返回当前学生的知识点台账，按正确率 ASC 排序（弱项优先） */
export function getKpMastery(): Promise<KpMasteryItem[]> {
  return request<KpMasteryItem[]>('/api/v1/kp-mastery/')
}

// ── M46 趋势 ────────────────────────────────────────────────────────────────

export interface KpTrendPoint {
  date: string          // YYYY-MM-DD
  accuracy: number      // 0~1
  correct_count: number
  wrong_count: number
}

/** GET /api/v1/kp-mastery/trend — 返回指定 KP 最近 N 天的日正确率快照 */
export function getKpTrend(kpKey: string, days = 30): Promise<KpTrendPoint[]> {
  return request<KpTrendPoint[]>(
    `/api/v1/kp-mastery/trend?kp_key=${encodeURIComponent(kpKey)}&days=${days}`,
  )
}
