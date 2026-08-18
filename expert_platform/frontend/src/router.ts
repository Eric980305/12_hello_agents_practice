import { createRouter, createWebHistory } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import AuthView from '@/views/AuthView.vue'
import ChatView from '@/views/ChatView.vue'
import ExpertsView from '@/views/ExpertsView.vue'
import ProfileView from '@/views/ProfileView.vue'
import MonthlyReportView from '@/views/MonthlyReportView.vue'
import AdminView from '@/views/AdminView.vue'
import { useSessionStore } from '@/stores/session'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: AuthView, props: { mode: 'login' }, meta: { guest: true } },
    { path: '/register', name: 'register', component: AuthView, props: { mode: 'register' }, meta: { guest: true } },
    {
      path: '/',
      component: AppShell,
      meta: { authenticated: true },
      children: [
        { path: '', redirect: '/chat' },
        { path: 'chat', name: 'chat', component: ChatView },
        { path: 'experts', name: 'experts', component: ExpertsView },
        { path: 'reports', name: 'reports', component: MonthlyReportView },
        { path: 'stats', redirect: '/reports' },
        { path: 'profile', name: 'profile', component: ProfileView },
        { path: 'admin', name: 'admin', component: AdminView, meta: { admin: true } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/chat' },
  ],
})

router.beforeEach(async (to) => {
  const session = useSessionStore()
  const authenticated = await session.restore()
  if (to.meta.authenticated && !authenticated) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !session.user?.isAdmin) return { name: 'chat' }
  if (to.meta.guest && authenticated) return { name: 'chat' }
})
