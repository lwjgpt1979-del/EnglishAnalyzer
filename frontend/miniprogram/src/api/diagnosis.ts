import { request } from '@/utils/request'
import type { DiagnosisReport } from '@/types/api'

export function getDiagnosisReport(): Promise<DiagnosisReport> {
  return request<DiagnosisReport>('/api/v1/diagnosis/report')
}
