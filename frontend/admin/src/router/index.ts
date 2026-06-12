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
        { path: 'contents', name: 'contents', component: () => import('../views/ContentsReview.vue') },
        { path: 'curriculum-units', name: 'curriculum-units', component: () => import('../views/CurriculumUnits.vue') },
        { path: 'theme-center', name: 'theme-center', component: () => import('../views/ThemeCenter.vue') },
        { path: 'vocab-media', name: 'vocab-media', component: () => import('../views/VocabMedia.vue') },
        { path: 'teacher-cert', name: 'teacher-cert', component: () => import('../views/TeacherCertReview.vue') },
        { path: 'pricing', name: 'pricing', component: () => import('../views/Pricing.vue') },
        { path: 'tts-speed', name: 'tts-speed', component: () => import('../views/TtsSpeed.vue') },
        { path: 'tts-usage', name: 'tts-usage', component: () => import('../views/TtsUsage.vue') },
        { path: 'essay-templates', name: 'essay-templates', component: () => import('../views/EssayTemplates.vue') },
        { path: 'institutions', name: 'institutions', component: () => import('../views/Institutions.vue') },
        { path: 'notifications', name: 'notifications', component: () => import('../views/Notifications.vue') },
        { path: 'exam-papers', name: 'exam-papers', component: () => import('../views/ExamPapers.vue') },
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
