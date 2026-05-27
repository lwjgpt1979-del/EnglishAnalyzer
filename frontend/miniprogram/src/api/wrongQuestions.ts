import { request } from '@/utils/request'
import type {
  AiAnalysisOut,
  ConfirmOcrTextRequest,
  OcrStatusOut,
  WrongQuestionCreate,
  WrongQuestionListOut,
  WrongQuestionOut,
} from '@/types/api'

export function createWrongQuestion(data: WrongQuestionCreate): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>('/api/v1/wrong-questions/', {
    method: 'POST',
    data,
  })
}

export function listWrongQuestions(skip = 0, limit = 20): Promise<WrongQuestionListOut> {
  return request<WrongQuestionListOut>(
    `/api/v1/wrong-questions/?skip=${skip}&limit=${limit}`,
  )
}

export function getWrongQuestion(id: string): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}`)
}

export function markMastered(id: string, isMastered: boolean): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/mastered`, {
    method: 'PATCH',
    data: { is_mastered: isMastered },
  })
}

export function analyzeWrongQuestion(id: string): Promise<AiAnalysisOut> {
  return request<AiAnalysisOut>(`/api/v1/wrong-questions/${id}/analyze`, {
    method: 'POST',
  })
}

export function listAnalyses(id: string): Promise<AiAnalysisOut[]> {
  return request<AiAnalysisOut[]>(`/api/v1/wrong-questions/${id}/analyses`)
}

/** 触发 OCR 识别 */
export function triggerOcr(id: string): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/ocr`, {
    method: 'POST',
  })
}

/** 查询 OCR 任务状态 */
export function getOcrStatus(id: string): Promise<OcrStatusOut> {
  return request<OcrStatusOut>(`/api/v1/wrong-questions/${id}/ocr`)
}

/** 手动确认/覆盖 OCR 识别结果 */
export function confirmOcrText(
  id: string,
  data: ConfirmOcrTextRequest,
): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/text`, {
    method: 'PATCH',
    data,
  })
}
