import { request } from '@/utils/request'
import type { UnitOut, UnitDetailOut, KPContentOut } from '@/types/api'

export function listUnits(
  textbook_version: string,
  grade: string,
  semester: string,
): Promise<UnitOut[]> {
  return request<UnitOut[]>('/api/v1/curriculum/units', {
    method: 'GET',
    data: { textbook_version, grade, semester },
  })
}

export function getUnitDetail(unitId: string): Promise<UnitDetailOut> {
  return request<UnitDetailOut>(`/api/v1/curriculum/units/${unitId}`, {
    method: 'GET',
  })
}

export function getKpContents(kpId: string): Promise<KPContentOut[]> {
  return request<KPContentOut[]>(
    `/api/v1/curriculum/knowledge-points/${kpId}/contents`,
    { method: 'GET' },
  )
}
