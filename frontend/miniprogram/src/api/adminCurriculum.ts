/**
 * 平台管理员 - 教材知识管理 API（M4）
 * 对应后端 M2/M3 admin endpoints
 */
import { request } from '@/utils/request'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

// ─── 类型定义 ──────────────────────────────────────────────────────────────

export interface CurriculumUnitStat {
  unit_id: string
  textbook_version: string
  grade: string
  semester: string
  unit_no: number
  unit_title: string
  kp_count: number
  content_count: number
  content_rate: number
}

export interface UnitSegment {
  unit_no: number
  start_page: number
  end_page: number
  detected_title?: string | null
}

export interface PdfUploadOut {
  file_id: string
  filename: string
  total_pages: number
  auto_split_success: boolean
  auto_segments: UnitSegment[]
}

export interface PagePreview {
  page_no: number
  text_snippet: string
}

export interface PdfPageListOut {
  file_id: string
  total_pages: number
  pages: PagePreview[]
}

export interface UnitGenerateResult {
  unit_no: number
  unit_title: string
  kp_count: number
  word_count: number
  status: 'ok' | 'error'
  error?: string | null
}

export interface GenerateFromPdfOut {
  results: UnitGenerateResult[]
  success_count: number
  error_count: number
}

export interface GenerateSemesterResult {
  unit_no: number
  unit_title: string
  kp_count: number
  word_count: number
  status: string
}

// ─── 单元列表 ──────────────────────────────────────────────────────────────

export function listCurriculumUnits(): Promise<CurriculumUnitStat[]> {
  return request<CurriculumUnitStat[]>('/api/v1/admin/curriculum/units', { method: 'GET' })
}

// ─── PDF 上传（使用 uni.uploadFile，不能用 request 工具）─────────────────

export function uploadCurriculumPdf(filePath: string): Promise<PdfUploadOut> {
  return new Promise((resolve, reject) => {
    const token = uni.getStorageSync('access_token') as string | undefined
    uni.uploadFile({
      url: `${BASE_URL}/api/v1/admin/curriculum/pdf/upload`,
      filePath,
      name: 'file',
      header: token ? { Authorization: `Bearer ${token}` } : {},
      success(res) {
        try {
          const body = JSON.parse(res.data) as { code: number; message: string; data: PdfUploadOut }
          if (body.code === 200) resolve(body.data)
          else reject(new Error(body.message || 'PDF 上传失败'))
        } catch {
          reject(new Error('响应解析失败'))
        }
      },
      fail(err) {
        reject(new Error(err.errMsg || '上传失败'))
      },
    })
  })
}

// ─── PDF 人工分页（自动检测失败时使用）────────────────────────────────────

export function getPdfPages(fileId: string): Promise<PdfPageListOut> {
  return request<PdfPageListOut>(`/api/v1/admin/curriculum/pdf/${fileId}/pages`, { method: 'GET' })
}

// ─── 分单元生成（PDF 流程）────────────────────────────────────────────────

export function generateFromPdf(
  fileId: string,
  body: {
    textbook_version: string
    grade: string
    semester: string
    segments: UnitSegment[]
    content_status?: string
  },
): Promise<GenerateFromPdfOut> {
  return request<GenerateFromPdfOut>(
    `/api/v1/admin/curriculum/pdf/${fileId}/generate`,
    { method: 'POST', data: { content_status: 'published', ...body } },
  )
}

// ─── 直接 AI 生成一个学期（不依赖 PDF）────────────────────────────────────

export function generateSemester(body: {
  textbook_version: string
  grade: string
  semester: string
  unit_count?: number
  content_status?: string
  reset?: boolean
}): Promise<GenerateSemesterResult[]> {
  return request<GenerateSemesterResult[]>('/api/v1/admin/curriculum/generate-semester', {
    method: 'POST',
    data: { unit_count: 6, content_status: 'published', reset: true, ...body },
  })
}
