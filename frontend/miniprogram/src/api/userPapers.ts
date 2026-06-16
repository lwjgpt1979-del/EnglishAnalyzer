import { request } from '@/utils/request'
import type {
  UserPaperCreateResult,
  UserPaperDetailOut,
  UserPaperListOut,
} from '@/types/api'

/** 建卷：提交一张或多张试卷图片 URL，触发后台 OCR 拆题 */
export function createUserPaper(
  sourceImageUrls: string[],
  title?: string,
): Promise<UserPaperCreateResult> {
  return request<UserPaperCreateResult>('/api/v1/user-papers', {
    method: 'POST',
    data: { source_image_urls: sourceImageUrls, title: title || undefined },
  })
}

/** 列出本人整卷 */
export function listUserPapers(): Promise<UserPaperListOut> {
  return request<UserPaperListOut>('/api/v1/user-papers', { method: 'GET' })
}

/** 整卷详情（含拆出的题目） */
export function getUserPaper(id: string): Promise<UserPaperDetailOut> {
  return request<UserPaperDetailOut>(`/api/v1/user-papers/${id}`, { method: 'GET' })
}

// M4 深化：本卷知识点归集 + 错题练同类
export interface PaperKpItem { kp_id: string; kp_name: string; total: number; wrong: number; weak: boolean }
export function getPaperKpSummary(paperId: string): Promise<{ paper_id: string; items: PaperKpItem[] }> {
  return request(`/api/v1/user-papers/${paperId}/kp-summary`, { method: 'GET' })
}
export interface SimilarQuestion {
  id: string; knowledge_point_name: string; question_type: string
  difficulty: number; stem: string; options: Record<string, string> | null
}
export function practiceForQuestion(questionId: string): Promise<{ knowledge_point: string; questions: SimilarQuestion[] }> {
  return request(`/api/v1/user-papers/questions/${questionId}/practice`, { method: 'POST' })
}
