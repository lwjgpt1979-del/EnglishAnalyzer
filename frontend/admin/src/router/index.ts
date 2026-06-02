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
