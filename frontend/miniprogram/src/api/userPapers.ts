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

// 学生修改某大题的题型分类(AI 建议不准时可改)
export function updatePaperSection(sectionId: string, label: string): Promise<{ updated: boolean; label: string }> {
  return request(`/api/v1/user-papers/sections/${sectionId}`, { method: 'PUT', data: { label } })
}

// P1:本卷语法点 对照掌握度 → 已学/薄弱/未学
export interface PrereqItem { node_id: string; name: string; learned: boolean }
export interface GrammarNodeItem { node_id: string; name: string; code: string; mastery: number | null; events: number; prereq?: PrereqItem[] }
export interface PaperGrammarStatus { learned: GrammarNodeItem[]; weak: GrammarNodeItem[]; new: GrammarNodeItem[]; total: number }

// P2 生词:本卷原文里的生词(未学/接收度低),挑选加入词力通优先学
export interface PaperVocabWord { word_id: string; word: string; phonetic: string | null; recep: number | null; pinned: boolean }
export function getPaperVocab(paperId: string): Promise<{ words: PaperVocabWord[] }> {
  return request<{ words: PaperVocabWord[] }>(`/api/v1/user-papers/${paperId}/vocab`, { method: 'GET' })
}

// P3 长难句:从本卷短文拆出的长难句 + 按需解析
export function getPaperLongSentences(paperId: string): Promise<{ sentences: string[] }> {
  return request<{ sentences: string[] }>(`/api/v1/user-papers/${paperId}/long-sentences`, { method: 'GET' })
}
export function analyzePaperSentence(sentence: string): Promise<any> {
  return request<any>(`/api/v1/user-papers/analyze-sentence`, { method: 'POST', data: { sentence } })
}

// 长难句学习页交互素材:语法提问式选择 + 重点词卡片
export interface GrammarQuizItem {
  node_id: string; node_name: string; code: string
  clause: string | null; question: string; options: string[]; answer: number
}
export interface StudyWord {
  word_id: string | null; word: string; phonetic: string | null; definitions: any
  image_url: string | null; word_audio_url: string | null
  en_description: string | null; example: { en?: string; zh?: string; audio?: string } | null
  in_vocab: boolean
}
export interface SentenceStudyAids { grammar_quiz: GrammarQuizItem[]; words: StudyWord[] }
export function getSentenceStudyAids(sentence: string): Promise<SentenceStudyAids> {
  return request<SentenceStudyAids>(`/api/v1/long-sentences/study-aids`, { method: 'POST', data: { sentence } })
}
// 「查看讲解」时把该语法结构加入作业精讲·语法(按来源卷归组)
export function addGrammarTarget(nodeId: string, paperId?: string): Promise<{ added: number }> {
  return request<{ added: number }>(`/api/v1/long-sentences/add-grammar`, { method: 'POST', data: { node_id: nodeId, paper_id: paperId } })
}
// 长难句「加入学习」:打包该句 + 句中单词 + 句中语法点 → 作业精讲(长难句/单词/语法,同批次)
export interface SaveSentenceResult { added: boolean; sentence_added: boolean; words_added: number; grammar_added: number }
export function savePaperSentence(sentence: string, paperId?: string): Promise<SaveSentenceResult> {
  return request<SaveSentenceResult>(`/api/v1/user-papers/save-sentence`, { method: 'POST', data: { sentence, paper_id: paperId } })
}
export function getPaperGrammarStatus(paperId: string): Promise<PaperGrammarStatus> {
  return request<PaperGrammarStatus>(`/api/v1/user-papers/${paperId}/grammar-status`, { method: 'GET' })
}

// P4 闭环:本卷未学+薄弱语法一键加入学习计划
export interface AddToPlanResult { added: number; selected: number; new: number; weak: number }
export function addPaperToPlan(paperId: string): Promise<AddToPlanResult> {
  return request<AddToPlanResult>(`/api/v1/user-papers/${paperId}/add-to-plan`, { method: 'POST' })
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
