import { defineStore } from 'pinia'

import { getMe, login as apiLogin } from '../api/index.js'

const ROLE_HOME = {
  student: '/student',
  teacher: '/teacher',
  enterprise: '/enterprise',
  admin: '/student'
}

export function roleHome(role) {
  return ROLE_HOME[role] || '/student'
}

export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('opc_token') || '',
    profile: null
  }),
  getters: {
    isLoggedIn: (state) => !!state.token,
    role: (state) => (state.profile ? state.profile.role : '')
  },
  actions: {
    async login(credentials) {
      const data = await apiLogin(credentials)
      this.token = data.access_token
      localStorage.setItem('opc_token', data.access_token)
      if (data.refresh_token) {
        localStorage.setItem('opc_refresh_token', data.refresh_token)
      }
      await this.fetchMe()
      return data.user
    },
    async fetchMe() {
      if (!this.token) {
        return null
      }
      try {
        this.profile = await getMe()
      } catch {
        this.profile = null
      }
      return this.profile
    },
    logout() {
      this.token = ''
      this.profile = null
      localStorage.removeItem('opc_token')
      localStorage.removeItem('opc_refresh_token')
    }
  }
})
