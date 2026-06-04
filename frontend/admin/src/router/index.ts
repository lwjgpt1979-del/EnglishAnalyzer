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
        { path: 'pricing', name: 'pricing', component: () => import('../views/Pricing.vue') },
        { path: 'essay-templates', name: 'essay-templates', component: () => import('../views/EssayTemplates.vue') },
        { path: 'institution/overview', name: 'institution-overview', component: () => import('../views/InstitutionOverview.vue'), meta: { roles: ['institution_admin'] } },
        { path: 'institution/profile', name: 'institution-profile', component: () => import('../views/InstitutionProfile.vue'), meta: { roles: ['institution_admin'] } },
        { path: 'institution/teachers', name: 'institution-teachers', component: () => import('../views/InstitutionTeachers.vue'), meta: { roles: ['institution_admin'] } },
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
  // 角色分流：机构管理员仅可进机构页，访问根/平台页时重定向到机构概览
  if (auth.isLoggedIn()) {
    const roles = to.meta.roles as string[] | undefined
    if (roles && !roles.includes(auth.role)) {
      return { path: auth.role === 'institution_admin' ? '/institution/overview' : '/overview' }
    }
    if (auth.role === 'institution_admin' && (to.path === '/' || to.path === '/overview')) {
      return { path: '/institution/overview' }
    }
  }
  return true
})

export default router
