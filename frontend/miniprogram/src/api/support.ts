import { request } from '@/utils/request'

// ── FAQ（§13.2）──
export interface FaqGroup { category: string; items: { id: string; question: string; answer: string }[] }
export function getFaq(audience = 'c'): Promise<{ categories: FaqGroup[] }> {
  return request(`/api/v1/faq?audience=${audience}`, { method: 'GET' })
}

// ── 客服工单（§13.1）──
export interface Ticket {
  id: string; category: string; subject: string; status: string
  last_reply_role: string | null; updated_at: string | null; created_at: string | null
}
export interface TicketMessage { id: string; sender_role: string; content: string; created_at: string | null }

export function createTicket(body: { category: string; subject: string; content: string; order_id?: string }): Promise<{ id: string; status: string }> {
  return request('/api/v1/support/tickets', { method: 'POST', data: body })
}
export function myTickets(): Promise<{ total: number; items: Ticket[] }> {
  return request('/api/v1/support/tickets', { method: 'GET' })
}
export function ticketThread(id: string): Promise<{ ticket: Ticket; messages: TicketMessage[] }> {
  return request(`/api/v1/support/tickets/${id}`, { method: 'GET' })
}
export function replyTicket(id: string, content: string): Promise<{ id: string }> {
  return request(`/api/v1/support/tickets/${id}/reply`, { method: 'POST', data: { content } })
}
