import { createRouter, createWebHistory } from 'vue-router'

import { roleHome, useUserStore } from '../stores/user.js'

const routes = [
  { path: '/', redirect: '/login' },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/Login.vue'),
    meta: { public: true }
  },
  {
    path: '/student',
    name: 'student-home',
    component: () => import('../views/student/Home.vue'),
    meta: { role: 'student' }
  },
  {
    path: '/student/orders',
    name: 'student-orders',
    component: () => import('../views/student/Orders.vue'),
    meta: { role: 'student' }
  },
  {
    path: '/student/workshop',
    name: 'workshop',
    component: () => import('../views/student/Workshop.vue'),
    meta: { role: 'student' }
  },
  {
    path: '/student/workshop/:workId',
    name: 'workshop-anchor',
    component: () => import('../views/student/Workshop.vue'),
    meta: { role: 'student' }
  },
  {
    path: '/teacher',
    name: 'teacher-home',
    component: () => import('../views/teacher/Home.vue'),
    meta: { role: 'teacher' }
  },
  {
    path: '/teacher/tasks/:taskId',
    name: 'teacher-task-detail',
    component: () => import('../views/teacher/TaskDetail.vue'),
    meta: { role: 'teacher' }
  },
  {
    path: '/enterprise',
    name: 'enterprise-home',
    component: () => import('../views/enterprise/Home.vue'),
    meta: { role: 'enterprise' }
  },
  {
    path: '/admin',
    name: 'admin-home',
    component: () => import('../views/admin/AdminHome.vue'),
    meta: { role: 'admin' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to) => {
  const token = localStorage.getItem('opc_token')
  if (!to.meta.public && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && token) {
    const userStore = useUserStore()
    if (!userStore.profile) {
      await userStore.fetchMe()
    }
    return { path: roleHome(userStore.profile ? userStore.profile.role : '') }
  }
  if (to.meta.role && token) {
    const userStore = useUserStore()
    if (!userStore.profile) {
      await userStore.fetchMe()
    }
    if (userStore.profile && userStore.profile.role !== to.meta.role) {
      return { path: roleHome(userStore.profile.role) }
    }
  }
  return true
})

export { router }
