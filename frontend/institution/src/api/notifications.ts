import request, { unwrap } from './request'

export interface AdminNotification {
  id: string
  type: string
  title: string
  content: string
  is_read: boolean
  created_at: string
}

export function listNotifications(): Promise<{ items: AdminNotification[]; total: number; unread_count: number }> {
  return unwrap(request.get('/notifications/?limit=50'))
}
export function markRead(id: string): Promise<AdminNotification> {
  return unwrap<AdminNotification>(request.patch(`/notifications/${id}/read`))
}
export function unreadCount(): Promise<{ count: number }> {
  return unwrap(request.get('/notifications/unread-count'))
}
