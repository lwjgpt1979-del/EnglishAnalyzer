import request, { unwrap } from './request'

export interface SalesLead {
  id: string
  name: string
  contact_name: string | null
  phone: string | null
  wechat_id: string | null
  address: string | null
  region_code: string | null
  region_name: string | null
  industry: string | null
  biz_tags: string[] | null
  source: string
  source_note: string | null
  status: string
  intent_score: number | null
  intent_grade: string | null
  product_feedback: unknown
  similar_score: number | null
  consent: boolean
  dnc: boolean
  pool: string
  owner_admin_id: string | null
  claimed_at: string | null
  last_contacted_at: string | null
  next_follow_at: string | null
  created_at: string
  updated_at: string
}

export interface SalesActivity {
  id: string
  lead_id: string
  admin_id: string | null
  channel: string
  direction: string | null
  content: string | null
  outcome: string | null
  recording_url: string | null
  call_duration_sec: number | null
  asr_text: string | null
  intent_score: number | null
  analysis: unknown
  created_at: string
}

export interface LeadListParams {
  pool?: string; status?: string; source?: string; region_code?: string
  mine?: boolean; dnc?: boolean; q?: string; skip?: number; limit?: number
}

export function listLeads(params: LeadListParams): Promise<{ total: number; items: SalesLead[] }> {
  return unwrap(request.get('/admin/sales/leads', { params }))
}
export function createLead(body: Partial<SalesLead>): Promise<SalesLead> {
  return unwrap(request.post('/admin/sales/leads', body))
}
export function importLeads(items: Partial<SalesLead>[], source = 'import'): Promise<{ created: number; skipped: number }> {
  return unwrap(request.post('/admin/sales/leads/import', { items, source }))
}
export function updateLead(id: string, patch: Partial<SalesLead>): Promise<SalesLead> {
  return unwrap(request.patch(`/admin/sales/leads/${id}`, patch))
}
export function claimLead(id: string): Promise<SalesLead> {
  return unwrap(request.post(`/admin/sales/leads/${id}/claim`))
}
export function releaseLead(id: string): Promise<SalesLead> {
  return unwrap(request.post(`/admin/sales/leads/${id}/release`))
}
export function listActivities(id: string, params?: { skip?: number; limit?: number }): Promise<{ total: number; items: SalesActivity[] }> {
  return unwrap(request.get(`/admin/sales/leads/${id}/activities`, { params }))
}
export function addActivity(id: string, body: { channel: string; content?: string; direction?: string; outcome?: string; next_follow_at?: string; status?: string }): Promise<SalesActivity> {
  return unwrap(request.post(`/admin/sales/leads/${id}/activities`, body))
}
export function recommendLeads(params?: { skip?: number; limit?: number }): Promise<{ total: number; items: SalesLead[] }> {
  return unwrap(request.get('/admin/sales/recommend', { params }))
}
export function salesBoard(): Promise<{ total: number; by_status: Record<string, number>; by_pool: Record<string, number> }> {
  return unwrap(request.get('/admin/sales/board'))
}
export function recyclePublicPool(): Promise<{ recycled: number }> {
  return unwrap(request.post('/admin/sales/recycle-public-pool'))
}

export const LEAD_STATUS: Record<string, string> = {
  new: '新线索', contacted: '已联系', interested: '有意向',
  negotiating: '谈单中', won: '成交', lost: '流失', invalid: '无效',
}
export const LEAD_SOURCE: Record<string, string> = {
  baidu_map: '百度地图', meituan: '美团', dianping: '大众点评',
  tungee: '探迹', manual: '手动', import: '导入', other: '其他',
}
