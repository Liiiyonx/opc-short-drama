<template>
  <div class="page" v-loading="loading">
    <div class="head">
      <div>
        <h3 class="title">管理后台</h3>
        <span class="sub">用户与课程基础管理（平台管理员）</span>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="用户管理" name="users">
        <div class="toolbar">
          <el-select v-model="roleFilter" placeholder="全部角色" clearable style="width: 150px">
            <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
          <el-input v-model="searchText" placeholder="按用户名搜索" clearable style="width: 200px" />
          <el-button type="primary" @click="openUserDialog">新建用户</el-button>
          <span class="count-hint">共 {{ filteredUsers.length }} 人</span>
        </div>
        <el-table :data="filteredUsers" size="small" v-loading="loadingUsers">
          <el-table-column prop="id" label="ID" width="64" />
          <el-table-column prop="username" label="用户名" min-width="130" />
          <el-table-column label="角色" width="110">
            <template #default="{ row }">
              <el-tag size="small" :type="ROLE_TAG[row.role] || 'info'">{{ ROLE_LABELS[row.role] || row.role }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="phone" label="手机号" width="130">
            <template #default="{ row }">{{ row.phone || '—' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-switch
                :model-value="row.status === 1"
                :loading="statusSavingId === row.id"
                @change="(value) => onToggleStatus(row, value)"
              />
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="课程管理" name="courses">
        <div class="toolbar">
          <el-button type="primary" @click="openCourseDialog">新建课程</el-button>
          <span class="count-hint">共 {{ courses.length }} 门</span>
        </div>
        <el-table :data="courses" size="small" v-loading="loadingCourses">
          <el-table-column prop="code" label="课程代码" width="130" />
          <el-table-column prop="name" label="课程名称" min-width="200" />
          <el-table-column prop="semester" label="学期" width="140">
            <template #default="{ row }">{{ row.semester || '—' }}</template>
          </el-table-column>
          <el-table-column label="班级" min-width="220">
            <template #default="{ row }">
              <el-tag v-for="cls in row.classes" :key="cls.id" size="small" class="class-tag">
                {{ cls.name }}（{{ cls.student_count }} 人）
              </el-tag>
              <span v-if="!row.classes.length" class="muted">暂无班级</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="系统健康" name="health">
        <!-- P0-10：管理员系统级可观测（worker 心跳/依赖/AI 模式） -->
        <div class="toolbar">
          <el-tag :type="healthTagType(health && health.status)" size="large" effect="dark" round>
            {{ health && health.status === 'up' ? '系统正常' : health && health.status === 'degraded' ? '降级运行' : '故障' }}
          </el-tag>
          <el-button size="small" @click="loadHealth">刷新</el-button>
          <span class="count-hint">自动刷新 15s · 采样于 {{ formatHealthTime(health && health.checked_at) }}</span>
        </div>
        <el-row :gutter="12" class="health-grid">
          <el-col v-for="item in healthItems" :key="item.key" :xs="12" :sm="8" :md="6">
            <el-card shadow="never" class="health-card">
              <div class="health-inner">
                <span class="dot" :class="healthDotClass(item.value)"></span>
                <div>
                  <div class="health-name">{{ item.label }}</div>
                  <div class="health-value">{{ item.display }}</div>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>
        <el-alert
          v-if="health && health.worker !== 'up'"
          type="warning"
          :closable="false"
          show-icon
          title="worker 心跳缺失：配音/成片等异步任务将停摆，请检查 arq worker 进程"
          class="health-alert"
        />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="userDialog" title="新建用户" width="440px">
      <el-form :model="userForm" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="userForm.username" maxlength="50" placeholder="如 student03" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="userForm.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="userForm.role" style="width: 100%">
            <el-option v-for="(label, value) in ROLE_LABELS" :key="value" :label="label" :value="value" />
          </el-select>
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="userForm.phone" maxlength="20" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialog = false">取消</el-button>
        <el-button type="primary" :loading="userSaving" :disabled="!canCreateUser" @click="onCreateUser">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="courseDialog" title="新建课程" width="460px">
      <el-form :model="courseForm" label-width="90px">
        <el-form-item label="课程代码">
          <el-input v-model="courseForm.code" maxlength="50" placeholder="如 EB2026" />
        </el-form-item>
        <el-form-item label="课程名称">
          <el-input v-model="courseForm.name" maxlength="100" placeholder="如 电子商务出海实战" />
        </el-form-item>
        <el-form-item label="学期">
          <el-input v-model="courseForm.semester" maxlength="20" placeholder="如 2026-2027-1（选填）" />
        </el-form-item>
        <el-form-item label="班级">
          <el-input
            v-model="courseForm.class_names_text"
            type="textarea"
            :rows="2"
            placeholder="每行一个班级名，如：电商2301班"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="courseDialog = false">取消</el-button>
        <el-button type="primary" :loading="courseSaving" :disabled="!canCreateCourse" @click="onCreateCourse">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { createCourse, createUser, getSystemHealth, listCourses, listUsers, updateUserStatus } from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'

const ROLE_LABELS = { student: '学生', teacher: '教师', enterprise: '企业', admin: '管理员' }
const ROLE_TAG = { student: 'primary', teacher: 'success', enterprise: 'warning', admin: 'danger' }


const userStore = useUserStore()

const loading = ref(false)
const loadingUsers = ref(false)
const loadingCourses = ref(false)
const activeTab = ref('users')
const users = ref([])
const courses = ref([])
const roleFilter = ref('')
const searchText = ref('')
const statusSavingId = ref(null)

const userDialog = ref(false)

function openUserDialog() {
  userForm.value = { username: '', password: '', role: 'student', phone: '' }
  userDialog.value = true
}
const userSaving = ref(false)
const userForm = ref({ username: '', password: '', role: 'student', phone: '' })

const courseDialog = ref(false)

function openCourseDialog() {
  courseForm.value = { code: '', name: '', semester: '', class_names_text: '' }
  courseDialog.value = true
}
const courseSaving = ref(false)
const courseForm = ref({ code: '', name: '', semester: '', class_names_text: '' })

const filteredUsers = computed(() =>
  users.value.filter((user) => {
    if (roleFilter.value && user.role !== roleFilter.value) return false
    if (searchText.value && !user.username.includes(searchText.value.trim())) return false
    return true
  })
)

const canCreateUser = computed(
  () => userForm.value.username.trim().length >= 2 && userForm.value.password.length >= 6
)
const canCreateCourse = computed(
  () => courseForm.value.code.trim().length >= 2 && courseForm.value.name.trim().length >= 1
)

function formatTime(value) {
  if (!value) return '—'
  return String(value).replace('T', ' ').slice(0, 16)
}

async function loadUsers() {
  loadingUsers.value = true
  try {
    const data = await listUsers({ page: 1, page_size: 100 })
    users.value = data.items || []
  } catch (error) {
    ElMessage.error(error.message || '加载用户失败')
  } finally {
    loadingUsers.value = false
  }
}

async function loadCourses() {
  loadingCourses.value = true
  try {
    const data = await listCourses()
    courses.value = data.items || []
  } catch (error) {
    ElMessage.error(error.message || '加载课程失败')
  } finally {
    loadingCourses.value = false
  }
}

async function onToggleStatus(row, value) {
  statusSavingId.value = row.id
  try {
    const data = await updateUserStatus(row.id, { status: value ? 1 : 0 })
    row.status = data.status
    ElMessage.success(value ? `已启用 ${row.username}` : `已禁用 ${row.username}`)
  } catch (error) {
    ElMessage.error(error.message || '操作失败')
  } finally {
    statusSavingId.value = null
  }
}

async function onCreateUser() {
  userSaving.value = true
  try {
    const payload = {
      username: userForm.value.username.trim(),
      password: userForm.value.password,
      role: userForm.value.role
    }
    if (userForm.value.phone.trim()) payload.phone = userForm.value.phone.trim()
    await createUser(payload)
    ElMessage.success('用户已创建')
    userDialog.value = false
    userForm.value = { username: '', password: '', role: 'student', phone: '' }
    await loadUsers()
  } catch (error) {
    ElMessage.error(error.message || '创建失败')
  } finally {
    userSaving.value = false
  }
}

async function onCreateCourse() {
  courseSaving.value = true
  try {
    const classNames = courseForm.value.class_names_text
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean)
    const payload = {
      code: courseForm.value.code.trim(),
      name: courseForm.value.name.trim(),
      class_names: classNames
    }
    if (courseForm.value.semester.trim()) payload.semester = courseForm.value.semester.trim()
    await createCourse(payload)
    ElMessage.success('课程已创建')
    courseDialog.value = false
    courseForm.value = { code: '', name: '', semester: '', class_names_text: '' }
    await loadCourses()
  } catch (error) {
    ElMessage.error(error.message || '创建失败')
  } finally {
    courseSaving.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await Promise.all([loadUsers(), loadCourses(), loadHealth()])
  } finally {
    loading.value = false
  }
})

// ---------- P0-10 系统健康 ----------
const health = ref(null)
let healthTimer = null

const healthItems = computed(() => {
  const h = health.value
  if (!h) return []
  return [
    { key: 'db', label: '数据库', value: h.db, display: h.db === 'up' ? '正常' : '不可用' },
    { key: 'redis', label: 'Redis 队列', value: h.redis, display: h.redis === 'up' ? '正常' : '不可用' },
    { key: 'worker', label: 'Worker 心跳', value: h.worker, display: h.worker === 'up' ? '在线' : '失联' },
    { key: 'storage', label: '对象存储', value: h.storage, display: h.storage === 'up' ? '正常' : '不可用' },
    { key: 'ffmpeg', label: 'ffmpeg', value: h.ffmpeg, display: h.ffmpeg === 'up' ? '可用' : '缺失' },
    {
      key: 'ai',
      label: 'AI 模式',
      value: h.ai && h.ai.llm_provider === 'openai_compat' ? 'up' : 'mock',
      display: h.ai ? `${h.ai.llm_provider === 'openai_compat' ? '真实' : '确定性演示'} · ${h.ai.llm_model}` : '—'
    }
  ]
})

function healthDotClass(value) {
  if (value === 'up') return 'dot-up'
  if (value === 'mock') return 'dot-warn' // mock 是显式演示模式，不是故障
  return 'dot-down'
}

function healthTagType(status) {
  if (status === 'up') return 'success'
  if (status === 'degraded') return 'warning'
  return 'danger'
}

function formatHealthTime(seconds) {
  if (!seconds) return '—'
  return new Date(seconds * 1000).toLocaleTimeString('zh-CN', { hour12: false })
}

async function loadHealth() {
  try {
    health.value = await getSystemHealth()
  } catch {
    health.value = null
  }
}

onMounted(() => {
  healthTimer = window.setInterval(() => {
    if (activeTab.value === 'health') loadHealth()
  }, 15000)
})

onBeforeUnmount(() => {
  if (healthTimer) window.clearInterval(healthTimer)
})
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 4px 0 12px;
}
.count-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
.class-tag {
  margin: 2px 6px 2px 0;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.health-grid {
  margin-top: 4px;
}
.health-card {
  margin-bottom: 12px;
}
.health-inner {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot-up {
  background: #67c23a;
  box-shadow: 0 0 0 3px rgba(103, 194, 58, 0.18);
}
.dot-down {
  background: #f56c6c;
  box-shadow: 0 0 0 3px rgba(245, 108, 108, 0.18);
}
.dot-warn {
  background: #e6a23c;
  box-shadow: 0 0 0 3px rgba(230, 162, 60, 0.18);
}
.health-name {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.health-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.health-alert {
  margin-top: 4px;
}
</style>
