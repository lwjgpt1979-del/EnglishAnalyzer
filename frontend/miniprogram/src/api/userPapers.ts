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
// 「我的作业」列表(C-a):每卷四模块聚合进度 + 综合环 + 状态
export interface HomeworkModule { studied: number; total: number }
export interface HomeworkPaper {
  paper_id: string; title: string; date: string; ocr_status: string | null
  modules: { word: HomeworkModule; grammar: HomeworkModule; sentence: HomeworkModule; reading: HomeworkModule }
  studied: number; total: number; overall_pct: number
  status: 'todo' | 'doing' | 'done'
}
export function getHomeworkProgress(): Promise<{ papers: HomeworkPaper[] }> {
  return request<{ papers: HomeworkPaper[] }>('/api/v1/user-papers/homework-progress', { method: 'GET' })
}
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
// 阅读精讲:按单篇短文取「本地生词(完整卡片媒体)+ 长难句」
export function getPassageStudy(passage: string, paperId?: string): Promise<{ words: StudyWord[]; sentences: string[] }> {
  return request<{ words: StudyWord[]; sentences: string[] }>(`/api/v1/user-papers/passage-study`, {
    method: 'POST', data: { passage, paper_id: paperId },
  })
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
/** 阅读理解精讲·题目层解析(题型/定位句/为何对/干扰项),缓存复用 */
export interface ReadingAnalysis {
  rc_code?: string
  skill?: string          // 题型中文名(细节理解/推理判断/词义猜测…)
  evidence?: string
  answer_reason?: string
  distractors?: Record<string, { meaning?: string; why_wrong?: string }>
  skill_tip?: string      // 该题型通用解题技巧
  _warnings?: string[]
  error?: string
}
export function getReadingAnalysis(qid: string): Promise<ReadingAnalysis> {
  return request(`/api/v1/user-papers/questions/${qid}/reading-analysis`, { method: 'GET' })
}
/** 阅读理解「练同类」:基于本篇短文出理解新题(非语法题) */
export function readingPractice(qid: string): Promise<{ questions: SimilarQuestion[]; error?: string }> {
  return request(`/api/v1/user-papers/questions/${qid}/reading-practice`, { method: 'POST' })
}
export interface ReadingSummarySkill { skill: string; total: number; wrong: number }
export interface ReadingSummaryVocab { word: string; tag: string }
export interface ReadingSummaryStruct { name: string; count: number }
export interface ReadingSummary {
  total: number; answered: number; unanswered: number; wrong: number
  by_skill: ReadingSummarySkill[]; diagnosis: string
  vocab: { weak_count: number; weak: ReadingSummaryVocab[] }
  sentences: { total: number; stuck: number; structures: ReadingSummaryStruct[] }
}
/** P2 单篇读后小结·提问块:该卷阅读题按题型的对错 + 一句话诊断(题型按需补标) */
export function getReadingSummary(paperId: string): Promise<ReadingSummary> {
  return request(`/api/v1/user-papers/papers/${paperId}/reading-summary`, { method: 'GET' })
}
/** P3 精讲里主动作答某阅读题 → 记 is_correct(治 OCR 抓不到卷面圈选) */
export function recordReadingAnswer(qid: string, chosen: string): Promise<{ chosen: string | null; correct_answer: string | null; is_correct: boolean | null }> {
  return request(`/api/v1/user-papers/questions/${qid}/reading-answer`, { method: 'POST', data: { chosen } })
}
export interface ReadingAnalyticsSkill { skill: string; total: number; wrong: number; rate: number }
export interface ReadingAnalyticsWord { word: string; tag: string; papers: number }
export interface ReadingAnalyticsStruct { name: string; count: number }
export interface ReadingAnalytics {
  days: number; papers: number
  skills: ReadingAnalyticsSkill[]
  weak_skills: ReadingAnalyticsSkill[]
  weak_structures: ReadingAnalyticsStruct[]
  weak_words: ReadingAnalyticsWord[]
  diagnosis: string
}
/** P5 阶段薄弱点:近 days 天多卷聚合(days=0 全部) */
export function getReadingAnalytics(days = 14): Promise<ReadingAnalytics> {
  return request(`/api/v1/user-papers/reading-analytics?days=${days}`, { method: 'GET' })
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
  pending_create?: boolean   // 缺词占位卡:词库没有,点开触发「查看即生成」入库
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
// 传 sentence+kind(component|grammar)则同时落「长难句薄弱」练习衍生(错→句·维;对→连对+1)
export function recordGrammarAnswer(gpKey: string, label: string, correct: boolean, nodeId?: string | null, sentence?: string, kind?: 'component' | 'grammar'): Promise<{ correct: number; total: number }> {
  return request<{ correct: number; total: number }>(`/api/v1/long-sentences/grammar-answer`, {
    method: 'POST', data: { gp_key: gpKey, label, correct, node_id: nodeId || undefined, sentence: sentence || undefined, kind: kind || undefined },
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
