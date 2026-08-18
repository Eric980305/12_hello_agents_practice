import { defineStore } from 'pinia'

import { api, ApiError } from '@/api'
import type { Expert, User } from '@/types'

interface BootstrapResponse {
  user: User
  experts: Expert[]
  sessionId: string
}

export const useSessionStore = defineStore('session', {
  state: () => ({
    user: null as User | null,
    experts: [] as Expert[],
    sessionId: '',
    initialized: false,
    selectedExpertId: localStorage.getItem('expert-platform:selected-expert') || 'default',
  }),
  getters: {
    selectedExpert(state): Expert | undefined {
      return state.experts.find((expert) => expert.id === state.selectedExpertId)
    },
    concreteExperts(state): Expert[] {
      return state.experts.filter((expert) => expert.kind !== 'aggregate')
    },
  },
  actions: {
    async restore() {
      if (this.initialized) return Boolean(this.user)
      try {
        await this.bootstrap()
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error
        this.user = null
      } finally {
        this.initialized = true
      }
      return Boolean(this.user)
    },
    async bootstrap() {
      const payload = await api<BootstrapResponse>('/bootstrap')
      this.user = payload.user
      this.experts = payload.experts
      this.sessionId = payload.sessionId
      if (!this.experts.some((expert) => expert.id === this.selectedExpertId && expert.kind !== 'aggregate')) {
        this.selectExpert('default')
      }
      this.initialized = true
    },
    async login(username: string, password: string) {
      await api<{ user: User }>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
      await this.bootstrap()
    },
    async register(username: string, password: string) {
      return api<{ user: User }>('/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      })
    },
    async logout() {
      await api<void>('/auth/logout', { method: 'POST' })
      this.$reset()
      this.initialized = true
      localStorage.removeItem('expert-platform:selected-expert')
    },
    async refreshExperts() {
      const payload = await api<{ items: Expert[] }>('/experts')
      this.experts = payload.items
      if (!this.experts.some((expert) => expert.id === this.selectedExpertId && expert.kind !== 'aggregate')) {
        this.selectExpert('default')
      }
    },
    selectExpert(expertId: string) {
      this.selectedExpertId = expertId
      localStorage.setItem('expert-platform:selected-expert', expertId)
    },
  },
})
