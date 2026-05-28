import { request } from '@/utils/request'
import type { BaseResponse, NotificationListOut, NotificationOut } from '../types/api'

export function listNotifications(params: { channel?: string; unread_only?: boolean; skip?: number; limit?: number } = {}): Promise<BaseResponse<NotificationListOut>> {
  return request('/notifications/', { method: 'GET', data: params })
}

export function getUnreadCount(): Promise<BaseResponse<{ count: number }>> {
  return request('/notifications/unread-count', { method: 'GET' })
}

export function markRead(id: string): Promise<BaseResponse<NotificationOut>> {
  return request(`/notifications/${id}/read`, { method: 'PATCH' })
}

export function markAllRead(): Promise<BaseResponse<{ affected: number }>> {
  return request('/notifications/read-all', { method: 'POST' })
}

export function deleteRead(): Promise<BaseResponse<{ deleted: number }>> {
  return request('/notifications/read', { method: 'DELETE' })
}
