import { request } from '@/utils/request'

export interface CheckinStatus {
  checked_in_today: boolean
  current_streak: number
  longest_streak: number
  today_new_words?: number
  today_review_done?: boolean
}
export interface CheckinDay { date: string; new_words_count?: number; streak_days?: number; wrong_count?: number }
export interface CheckinCalendar {
  year: number; month: number
  days: CheckinDay[]
  checked_count: number
  current_streak: number
  longest_streak: number
}

/** 今日打卡(记录学习日,幂等)。 */
export function checkin(): Promise<CheckinStatus> {
  return request<CheckinStatus>('/api/v1/checkin', { method: 'POST' })
}

export function getCheckinStatus(): Promise<CheckinStatus> {
  return request<CheckinStatus>('/api/v1/checkin/status', { method: 'GET' })
}

export function getCheckinCalendar(year?: number, month?: number): Promise<CheckinCalendar> {
  const data: Record<string, number> = {}
  if (year) data.year = year
  if (month) data.month = month
  return request<CheckinCalendar>('/api/v1/checkin/calendar', { method: 'GET', data })
}
