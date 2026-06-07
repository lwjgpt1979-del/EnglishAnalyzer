import { request } from '@/utils/request'
import type { KPSearchItem } from '@/types/api'

export function searchKPs(q = '', limit = 10): Promise<KPSearchItem[]> {
  return request<KPSearchItem[]>('/api/v1/curriculum/kps/search', {
    method: 'GET',
    data: { q, limit },
  })
}
