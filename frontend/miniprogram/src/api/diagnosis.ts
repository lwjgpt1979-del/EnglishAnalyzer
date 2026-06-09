import { request } from '@/utils/request'
import type { DiagnosisReport } from '@/types/api'

export function getDiagnosisReport(): Promise<DiagnosisReport> {
  return request<DiagnosisReport>('/api/v1/diagnosis/report')
}

export interface PdfExportOut {
  pdf_base64: string
  filename: string
}

export function exportDiagnosisPdf(): Promise<PdfExportOut> {
  return request<PdfExportOut>('/api/v1/diagnosis/export-pdf')
}
