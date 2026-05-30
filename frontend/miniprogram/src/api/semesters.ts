import { request } from '@/utils/request'
import type { PurchasedSemesterOut } from '../types/api'

export function listMySemesters(): Promise<PurchasedSemesterOut[]> {
  return request('/api/v1/semesters/mine', { method: 'GET' })
}
