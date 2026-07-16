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
export function getPaperVocab(paperId: string, sectionId?: string): Promise<{ words: PaperVocabWord[] }> {
  const qs = sectionId ? `?section_id=${sectionId}` : ''
  return request<{ words: PaperVocabWord[] }>(`/api/v1/user-papers/${paperId}/vocab${qs}`, { method: 'GET' })
}

// P3 长难句:从本卷短文拆出的长难句 + 按需解析
export function getPaperLongSentences(paperId: string, sectionId?: string): Promise<{ sentences: string[] }> {
  const qs = sectionId ? `?section_id=${sectionId}` : ''
  return request<{ sentences: string[] }>(`/api/v1/user-papers/${paperId}/long-sentences${qs}`, { method: 'GET' })
}
// 重命名作业标题(改自动生成的名字)
export function renamePaper(paperId: string, title: string): Promise<{ title: string }> {
  return request<{ title: string }>(`/api/v1/user-papers/${paperId}/title`, { method: 'PUT', data: { title } })
}

export function analyzePaperSentence(sentence: string): Promise<any> {
  return request<any>(`/api/v1/user-papers/analyze-sentence`, { method: 'POST', data: { sentence } })
}
// 单题:考语法 → 加入语法学习(作业精讲·语法/个人语法树);考词汇 → 加入作业精讲·单词
export function addQuestionGrammar(qid: string): Promise<{ kind: string; added: number; personal?: boolean }> {
  return request(`/api/v1/user-papers/questions/${qid}/add-grammar`, { method: 'POST' })
}
export function addQuestionVocab(qid: string): Promise<{ kind: string; added: number }> {
  return request(`/api/v1/user-papers/questions/${qid}/add-vocab`, { method: 'POST' })
}
export function addQuestionToWrong(qid: string): Promise<{ added: boolean; kp_kind: string | null }> {
  return request(`/api/v1/user-papers/questions/${qid}/add-wrong`, { method: 'POST' })
}
/** 手动把某作业阅读理解板块加入作业精讲·阅读理解精讲 */
export function addReadingIntensive(sectionId: string): Promise<{ added: boolean; reason?: string }> {
  return request(`/api/v1/user-papers/sections/${sectionId}/add-reading-intensive`, { method: 'POST' })
}

// 长难句学习页交互素材:语法提问式选择 + 重点词卡片
export interface GrammarQuizItem {
  kind: 'component' | 'grammar'; tag: string
  gp_key: string; node_id: string | null; node_name: string | null; code: string | null
  in_syllabus: boolean; clause: string | null; explanation: string | null
  question: string; options: string[]; answer: number
  stat_correct: number; stat_total: number
  answered_before: boolean; grammar_added: boolean
}
export interface StudyWord {
  word_id: string | null; word: string; phonetic: string | null; definitions: any
  image_url: string | null; word_audio_url: string | null
  en_description: string | null; example: { en?: string; zh?: string; audio?: string } | null
  in_vocab: boolean; word_added: boolean
}
export interface SentenceStudyAids {
  analysis: any; sentence_added: boolean
  grammar_quiz: GrammarQuizItem[]; words: StudyWord[]
}
export function getSentenceStudyAids(sentence: string, paperId?: string): Promise<SentenceStudyAids> {
  return request<SentenceStudyAids>(`/api/v1/long-sentences/study-aids`, { method: 'POST', data: { sentence, paper_id: paperId } })
}
// 「查看讲解」时把该语法结构加入作业精讲·语法(按来源卷归组)
export function addGrammarTarget(nodeId: string, paperId?: string): Promise<{ added: number }> {
  return request<{ added: number }>(`/api/v1/long-sentences/add-grammar`, { method: 'POST', data: { node_id: nodeId, paper_id: paperId } })
}
// 记一次语法选择题作答(累计正确率,以往至今),返回该语法点 {correct,total}
export function recordGrammarAnswer(gpKey: string, label: string, correct: boolean, nodeId?: string | null): Promise<{ correct: number; total: number }> {
  return request<{ correct: number; total: number }>(`/api/v1/long-sentences/grammar-answer`, {
    method: 'POST', data: { gp_key: gpKey, label, correct, node_id: nodeId || undefined },
  })
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
  difficulty: number; stem: string; options: string[] | null
  answer: string | null; explanation: string | null
}
export function practiceForQuestion(questionId: string): Promise<{ knowledge_point: string; questions: SimilarQuestion[] }> {
  return request(`/api/v1/user-papers/questions/${questionId}/practice`, { method: 'POST' })
}
/** 作业详情练同类结算:回写对应错题 practice + 语法推进 SM-2 */
export interface PaperPracticeResult { recorded: boolean; just_mastered?: boolean; lifecycle?: string }
export function recordPaperPractice(questionId: string, total: number, correct: number): Promise<PaperPracticeResult> {
  return request(`/api/v1/user-papers/questions/${questionId}/practice-result`, { method: 'POST', data: { total, correct } })
}
