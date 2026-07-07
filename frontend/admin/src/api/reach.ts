import request, { unwrap } from './request'

// 分群字段元数据(后端 segment_service.FIELDS)
export interface SegmentField {
  label: string
  type: 'int' | 'bool' | 'enum' | 'str'
  options?: string[]
  hint?: string
}
export interface ReachFields {
  fields: Record<string, SegmentField>
  channels: string[]
}
export function getReachFields(): Promise<ReachFields> {
  return unwrap(request.get('/admin/reach/fields'))
}

export interface SegmentCondition { field: string; value: unknown }
export interface SegmentRule { conditions: SegmentCondition[] }

export interface Segment {
  id: string
  name: string
  description: string | null
  rule: SegmentRule
  last_count: number | null
  updated_at: string | null
}

export interface ResolveResult {
  count: number
  sample: { id: string; phone: string | null; nickname: string | null; city_code: string | null }[]
}
export function resolveSegment(rule: SegmentRule): Promise<ResolveResult> {
  return unwrap(request.post('/admin/reach/segments/resolve', { rule }))
}
export function listSegments(params?: { skip?: number; limit?: number }): Promise<{ total: number; items: Segment[] }> {
  return unwrap(request.get('/admin/reach/segments', { params }))
}
export function upsertSegment(body: { id?: string; name: string; description?: string | null; rule: SegmentRule }): Promise<Segment> {
  return unwrap(request.put('/admin/reach/segments', body))
}
export function deleteSegment(id: string): Promise<{ deleted: string }> {
  return unwrap(request.delete(`/admin/reach/segments/${id}`))
}

export interface Variant { label: string; title?: string | null; content: string }
export interface Campaign {
  id: string
  name: string
  segment_id: string | null
  channel: 'station' | 'sales_lead' | 'sms'
  title: string | null
  content: string | null
  lead_tag: string | null
  variants: Variant[] | null
  recurring: boolean
  enabled: boolean
  total_reached: number
  status: 'draft' | 'done' | 'failed' | 'active'
  stats: { matched: number; sent: number; failed: number; skipped: number } | null
  created_at: string | null
  executed_at: string | null
}
export interface ReachLogItem {
  user_id: string; nickname: string | null; phone: string | null
  channel: string; variant: string | null; reached_at: string | null
}
export interface ReachLogs {
  total: number
  items: ReachLogItem[]
  variant_summary: { variant: string; count: number }[]
}
export function listCampaigns(params?: { skip?: number; limit?: number }): Promise<{ total: number; items: Campaign[] }> {
  return unwrap(request.get('/admin/reach/campaigns', { params }))
}
export function createCampaign(body: {
  name: string; channel: string; segment_id?: string | null; rule?: SegmentRule | null
  title?: string | null; content?: string | null; lead_tag?: string | null; recurring?: boolean
  variants?: Variant[] | null
}): Promise<Campaign> {
  return unwrap(request.post('/admin/reach/campaigns', body))
}
export function getCampaignLogs(id: string, params?: { skip?: number; limit?: number }): Promise<ReachLogs> {
  return unwrap(request.get(`/admin/reach/campaigns/${id}/logs`, { params }))
}
export function runCampaign(id: string): Promise<Campaign> {
  return unwrap(request.post(`/admin/reach/campaigns/${id}/run`))
}
export function toggleCampaign(id: string, enabled: boolean): Promise<Campaign> {
  return unwrap(request.post(`/admin/reach/campaigns/${id}/toggle`, { enabled }))
}

export const CHANNEL_LABEL: Record<string, string> = {
  station: '站内通知',
  sales_lead: '生成电销线索',
  sms: '营销短信',
}
