import { defineStore } from 'pinia'

import { createWork, generateWork, getWork, listWorks } from '../api/index.js'

export const useWorkStore = defineStore('work', {
  state: () => ({
    works: [],
    total: 0,
    loading: false
  }),
  actions: {
    async loadWorks(params) {
      this.loading = true
      try {
        const data = await listWorks(params || { page: 1, page_size: 50 })
        this.works = data.items
        this.total = data.total
      } finally {
        this.loading = false
      }
    },
    async createWork(payload) {
      const work = await createWork(payload)
      this.works.unshift(work)
      return work
    },
    async getDetail(id) {
      return await getWork(id)
    },
    async generate(id, payload) {
      return await generateWork(id, payload)
    }
  }
})
