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
  mine?: boolean; dnc?: boolean; has_phone?: boolean; due?: boolean; sla?: boolean; tag?: string; q?: string; skip?: number; limit?: number
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
export interface Seat { id: string; name: string }
export function listSeats(): Promise<Seat[]> {
  return unwrap(request.get('/admin/sales/seats'))
}
// 批量派单/认领:owner_admin_id 缺省=认领给自己
export function batchAssign(leadIds: string[], ownerAdminId?: string): Promise<{ assigned: number }> {
  return unwrap(request.post('/admin/sales/leads/assign', { lead_ids: leadIds, owner_admin_id: ownerAdminId }))
}
// 自动分配:公海线索轮询派给座席(排除 DNC,可按地区)
export function autoAssign(seatIds: string[], count = 100, regionCode?: string): Promise<{ assigned: number; by_seat: Record<string, number> }> {
  return unwrap(request.post('/admin/sales/leads/auto-assign', { seat_ids: seatIds, count, region_code: regionCode }))
}
export interface SeatRank { admin_id: string; name: string; leads: number; won: number; conversion: number; calls: number; connected: number; connect_rate: number }
export function leaderboard(days = 7): Promise<SeatRank[]> {
  return unwrap(request.get('/admin/sales/leaderboard', { params: { days } }))
}
export interface AuditRow { id: string; admin_id: string | null; action: string; lead_id: string | null; detail: any; created_at: string | null }
export function leadAudit(leadId: string, params?: { skip?: number; limit?: number }): Promise<{ total: number; items: AuditRow[] }> {
  return unwrap(request.get('/admin/sales/audit', { params: { lead_id: leadId, ...params } }))
}
export const AUDIT_ACTION: Record<string, string> = {
  create: '创建', import: '导入', claim: '认领', release: '退回公海', assign: '派单',
  auto_assign: '自动分配', merge: '合并', status_change: '改状态', dnc: 'DNC 开关', update: '编辑', recycle: '回收',
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
export interface SalesBoard {
  total: number
  by_status: Record<string, number>
  by_pool: Record<string, number>
  today_new: number
  today_calls: number
  today_connected: number
  connect_rate: number
  my_due: number
  sla_breach: number
  sla_overdue_hours: number
}
export function salesBoard(): Promise<SalesBoard> {
  return unwrap(request.get('/admin/sales/board'))
}
export interface SourceStat { source: string; total: number; won: number; conversion: number }
export function sourceStats(): Promise<SourceStat[]> {
  return unwrap(request.get('/admin/sales/source-stats'))
}
export interface DupGroup { phone: string; leads: Array<{ id: string; name: string; contact_name: string | null; region_name: string | null; status: string; source: string; pool: string; created_at: string | null }> }
export function findDuplicates(): Promise<DupGroup[]> {
  return unwrap(request.get('/admin/sales/duplicates'))
}
export function mergeLeads(survivorId: string, dupIds: string[]): Promise<{ merged: number; moved_activities: number; moved_wecom: number }> {
  return unwrap(request.post('/admin/sales/leads/merge', { survivor_id: survivorId, dup_ids: dupIds }))
}
export function importExcel(file: File, source = 'import'): Promise<{ created: number; skipped: number }> {
  const form = new FormData()
  form.append('file', file)
  form.append('source', source)
  return unwrap(request.post('/admin/sales/leads/import-excel', form))
}
export async function exportLeads(params: LeadListParams): Promise<Blob> {
  const r = await request.get('/admin/sales/leads/export', { params, responseType: 'blob' })
  return r.data as Blob
}

export interface SalesConfig {
  public_pool_recycle_days: number; sla_overdue_hours: number
  seat_only_admin_ids: string[]; tag_catalog: string[]
  recommend_weights?: Record<string, number>; intent_grade_thresholds?: Record<string, number>
}
export function getSalesConfig(): Promise<SalesConfig> {
  return unwrap(request.get('/admin/sales/config'))
}
export function updateSalesConfig(patch: Partial<SalesConfig>): Promise<SalesConfig> {
  return unwrap(request.put('/admin/sales/config', patch))
}

export interface Script { title: string; content: string; stage?: string | null }
export function getScripts(): Promise<Script[]> {
  return unwrap(request.get('/admin/sales/scripts'))
}
export function setScripts(scripts: Script[]): Promise<Script[]> {
  return unwrap(request.put('/admin/sales/scripts', { scripts }))
}
export function recyclePublicPool(): Promise<{ recycled: number }> {
  return unwrap(request.post('/admin/sales/recycle-public-pool'))
}

export interface IntentAnalysis {
  intent_score: number
  intent_grade?: string
  signals: { asked_price: boolean; asked_next_step: boolean; competitor_mentioned: string[]; objections: string[]; red_flags: string[] }
  product_feedback: string[]
  summary: string
  next_action: string
  compliance: { violations: string[] }
}
// 试跑:任意转写 → 意向分析(不落库)
export function analyzeText(text: string, source = 'call'): Promise<IntentAnalysis> {
  return unwrap(request.post('/admin/sales/analyze', { text, source }))
}
// 呼叫中心接入位:回传一通电话(录音/转写)→ 落 call 跟进 + 有转写则分析回填
export function callRecord(id: string, body: { recording_url?: string; asr_text?: string; call_duration_sec?: number; outcome?: string; content?: string }): Promise<SalesActivity> {
  return unwrap(request.post(`/admin/sales/leads/${id}/call-record`, body))
}
// 对已有转写的跟进(重新)跑分析
export function analyzeActivity(activityId: string): Promise<SalesActivity> {
  return unwrap(request.post(`/admin/sales/activities/${activityId}/analyze`))
}

export interface WecomMsg {
  id: string
  msg_id: string
  from_userid: string | null
  external_userid: string | null
  msgtype: string
  content_text: string | null
  media_url: string | null
  msgtime: string | null
  analyzed: boolean
  analysis: IntentAnalysis | null
  created_at: string
}
// 某线索的企微会话记录(分页)
export function leadWecomMessages(id: string, params?: { skip?: number; limit?: number }): Promise<{ total: number; items: WecomMsg[] }> {
  return unwrap(request.get(`/admin/sales/leads/${id}/wecom`, { params }))
}

export const LEAD_STATUS: Record<string, string> = {
  new: '新线索', contacted: '已联系', interested: '有意向',
  negotiating: '谈单中', won: '成交', lost: '流失', invalid: '无效',
}
export const LEAD_SOURCE: Record<string, string> = {
  baidu_map: '百度地图', meituan: '美团', dianping: '大众点评',
  tungee: '探迹', manual: '手动', import: '导入', other: '其他',
}
