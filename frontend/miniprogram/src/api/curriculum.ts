import { request } from '@/utils/request'
import type { UnitOut, UnitDetailOut, KPContentOut, KpMasterySummaryItem, KpMasteryItem } from '@/types/api'

export interface CurriculumOptions {
  textbook_versions: string[]
  grades: string[]
  semesters: string[]
}

/** 教材版本/年级/学期可选值——后台单一真源(curriculum_service.preference_options)。 */
export function getCurriculumOptions(): Promise<CurriculumOptions> {
  return request<CurriculumOptions>('/api/v1/curriculum/options', { method: 'GET' })
}

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

export function getKpMastery(kpId: string): Promise<KpMasteryItem | null> {
  return request<KpMasteryItem | null>(
    `/api/v1/curriculum/knowledge-points/${kpId}/mastery`,
    { method: 'GET' },
  )
}

export function getUnitMasterySummary(unitId: string): Promise<KpMasterySummaryItem[]> {
  return request<KpMasterySummaryItem[]>(
    `/api/v1/curriculum/units/${unitId}/mastery-summary`,
    { method: 'GET' },
  )
}
