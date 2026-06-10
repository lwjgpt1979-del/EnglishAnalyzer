import { createRouter, createWebHashHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('../views/Login.vue'), meta: { public: true } },
    { path: '/apply', name: 'apply', component: () => import('../views/InstitutionApply.vue'), meta: { public: true } },
    {
      path: '/',
      component: () => import('../layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/overview' },
        { path: 'overview', name: 'overview', component: () => import('../views/InstitutionOverview.vue') },
        { path: 'profile', name: 'profile', component: () => import('../views/InstitutionProfile.vue') },
        { path: 'teachers', name: 'teachers', component: () => import('../views/InstitutionTeachers.vue') },
        { path: 'purchases', name: 'purchases', component: () => import('../views/InstitutionPurchases.vue') },
        { path: 'renew', name: 'renew', component: () => import('../views/InstitutionRenew.vue') },
        { path: 'bills', name: 'bills', component: () => import('../views/InstitutionBills.vue') },
        { path: 'notifications', name: 'notifications', component: () => import('../views/Notifications.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn()) return { path: '/login' }
  if (to.path === '/login' && auth.isLoggedIn()) return { path: '/' }
  return true
})

export default router
