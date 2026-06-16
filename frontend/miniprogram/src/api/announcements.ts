import { request } from '@/utils/request'

export interface Announcement {
  id: string; title: string; content: string; pinned: boolean; created_at: string | null
}
/** 当前用户可见的生效公告（全平台 + 命中其机构/年级）*/
export function getAnnouncements(): Promise<{ items: Announcement[] }> {
  return request('/api/v1/announcements', { method: 'GET' })
}
