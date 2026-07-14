import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/overview' },
        { path: 'overview', name: 'overview', component: () => import('../views/Overview.vue') },
        { path: 'questions', name: 'questions', component: () => import('../views/QuestionsReview.vue') },
        { path: 'kp-candidates', name: 'kp-candidates', component: () => import('../views/KpCandidatesReview.vue') },
        { path: 'vocab-lists', name: 'vocab-lists', component: () => import('../views/VocabLists.vue') },
        { path: 'vocab-reviews', name: 'vocab-reviews', component: () => import('../views/VocabReviews.vue') },
        { path: 'knowledge-graph', name: 'knowledge-graph', component: () => import('../views/KnowledgeGraph.vue') },
        { path: 'kp-prompts', name: 'kp-prompts', component: () => import('../views/KpPrompts.vue') },
        { path: 'llm-config', name: 'llm-config', component: () => import('../views/LlmConfig.vue') },
        { path: 'llm-features', name: 'llm-features', component: () => import('../views/LlmFeatures.vue') },
        { path: 'third-party', name: 'third-party', component: () => import('../views/ThirdPartyResources.vue') },
        { path: 'exam-type-stats', name: 'exam-type-stats', component: () => import('../views/ExamTypeStats.vue') },
        { path: 'grammar-calibration', name: 'grammar-calibration', component: () => import('../views/GrammarCalibration.vue') },
        { path: 'baidu-leads', name: 'baidu-leads', component: () => import('../views/BaiduLeads.vue') },
        { path: 'textbook-map', name: 'textbook-map', component: () => import('../views/TextbookMap.vue') },
        { path: 'audit-logs', name: 'audit-logs', component: () => import('../views/AuditLogs.vue') },
        { path: 'admin-accounts', name: 'admin-accounts', component: () => import('../views/AdminAccounts.vue') },
        { path: 'task-runs', name: 'task-runs', component: () => import('../views/TaskRuns.vue') },
        { path: 'textbook-word-stats', name: 'textbook-word-stats', component: () => import('../views/TextbookWordStats.vue') },
        { path: 'long-sentences', name: 'long-sentences', component: () => import('../views/LongSentences.vue') },
        { path: 'platform-questions', name: 'platform-questions', component: () => import('../views/PlatformQuestions.vue') },
        { path: 'regions', name: 'regions', component: () => import('../views/RegionAdmin.vue') },
        { path: 'textbook-catalog', name: 'textbook-catalog', component: () => import('../views/TextbookCatalog.vue') },
        { path: 'curriculum-units', name: 'curriculum-units', component: () => import('../views/CurriculumUnits.vue') },
        { path: 'curriculum-gen-jobs', name: 'curriculum-gen-jobs', component: () => import('../views/CurriculumGenJobs.vue') },
        { path: 'theme-center', name: 'theme-center', component: () => import('../views/ThemeCenter.vue') },
        { path: 'vocab-media', name: 'vocab-media', component: () => import('../views/VocabMedia.vue') },
        { path: 'teacher-cert', name: 'teacher-cert', component: () => import('../views/TeacherCertReview.vue') },
        { path: 'pricing', name: 'pricing', component: () => import('../views/Pricing.vue') },
        { path: 'tts-speed', name: 'tts-speed', component: () => import('../views/TtsSpeed.vue') },
        { path: 'tts-usage', name: 'tts-usage', component: () => import('../views/TtsUsage.vue') },
        { path: 'speaking-scenarios', name: 'speaking-scenarios', component: () => import('../views/SpeakingScenarios.vue') },
        { path: 'vocab-image-gen', name: 'vocab-image-gen', component: () => import('../views/VocabImageGen.vue') },
        { path: 'essay-templates', name: 'essay-templates', component: () => import('../views/EssayTemplates.vue') },
        { path: 'institutions', name: 'institutions', component: () => import('../views/Institutions.vue') },
        { path: 'notifications', name: 'notifications', component: () => import('../views/Notifications.vue') },
        { path: 'entitlements', name: 'entitlements', component: () => import('../views/Entitlements.vue') },
        { path: 'refunds', name: 'refunds', component: () => import('../views/Refunds.vue') },
        { path: 'approvals', name: 'approvals', component: () => import('../views/SensitiveApprovals.vue') },
        { path: 'payment-accounts', name: 'payment-accounts', component: () => import('../views/PaymentAccounts.vue') },
        { path: 'branch-companies', name: 'branch-companies', component: () => import('../views/BranchCompanies.vue') },
        { path: 'users', name: 'users', component: () => import('../views/Users.vue') },
        { path: 'finance', name: 'finance', component: () => import('../views/Finance.vue') },
        { path: 'invoices', name: 'invoices', component: () => import('../views/Invoices.vue') },
        { path: 'ban-appeals', name: 'ban-appeals', component: () => import('../views/BanAppeals.vue') },
        { path: 'content-feedback', name: 'content-feedback', component: () => import('../views/ContentFeedback.vue') },
        { path: 'support', name: 'support', component: () => import('../views/Support.vue') },
        { path: 'faq', name: 'faq', component: () => import('../views/Faq.vue') },
        { path: 'feedback', name: 'feedback', component: () => import('../views/Feedback.vue') },
        { path: 'coupons', name: 'coupons', component: () => import('../views/Coupons.vue') },
        { path: 'sensitive-words', name: 'sensitive-words', component: () => import('../views/SensitiveWords.vue') },
        { path: 'campaigns', name: 'campaigns', component: () => import('../views/Campaigns.vue') },
        { path: 'announcements', name: 'announcements', component: () => import('../views/Announcements.vue') },
        { path: 'teacher-limits', name: 'teacher-limits', component: () => import('../views/TeacherLimits.vue') },
        { path: 'system-settings', name: 'system-settings', component: () => import('../views/SystemSettings.vue') },
        { path: 'institution-packages', name: 'institution-packages', component: () => import('../views/InstitutionPackages.vue') },
        { path: 'sales-leads', name: 'sales-leads', component: () => import('../views/SalesLeads.vue') },
        { path: 'sales-call-center', name: 'sales-call-center', component: () => import('../views/SalesCallCenter.vue') },
        { path: 'reach', name: 'reach', component: () => import('../views/Reach.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn()) {
    return { path: '/login' }
  }
  if (to.path === '/login' && auth.isLoggedIn()) {
    return { path: '/' }
  }
  return true
})

export default router
