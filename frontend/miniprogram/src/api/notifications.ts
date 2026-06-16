import { request } from '@/utils/request'
import type { NotificationListOut, NotificationOut } from '../types/api'

// 注意：request 已解包返回 body.data，故下列返回的是 data 本体（非 BaseResponse）
export function listNotifications(params: { channel?: string; unread_only?: boolean; skip?: number; limit?: number } = {}): Promise<NotificationListOut> {
  return request('/api/v1/notifications/', { method: 'GET', data: params })
}

export function getUnreadCount(): Promise<{ count: number }> {
  return request('/api/v1/notifications/unread-count', { method: 'GET' })
}

/** 未读数按频道分组（消息中心角标）。request 已解包，直接返回 {total, by_channel} */
export function getUnreadByChannel(): Promise<{ total: number; by_channel: Record<string, number> }> {
  return request('/api/v1/notifications/unread-by-channel', { method: 'GET' })
}

export function markRead(id: string): Promise<BaseResponse<NotificationOut>> {
  return request(`/api/v1/notifications/${id}/read`, { method: 'PATCH' })
}

export function markAllRead(): Promise<BaseResponse<{ affected: number }>> {
  return request('/api/v1/notifications/read-all', { method: 'POST' })
}

export function deleteRead(): Promise<BaseResponse<{ deleted: number }>> {
  return request('/api/v1/notifications/read', { method: 'DELETE' })
}
