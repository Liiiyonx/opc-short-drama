<template>
  <div class="page">
    <div class="home-head">
      <div>
        <h3 class="title">学生工作台</h3>
        <span class="sub">{{ greeting }}</span>
      </div>
      <div class="actions">
        <el-button @click="router.push('/student/orders')">工单大厅</el-button>
        <el-button type="primary" @click="newDialog = true">新建剧集</el-button>
        <el-button text @click="logout">退出登录</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="stat-row">
      <el-col :span="6" v-for="stat in stats" :key="stat.label">
        <el-card shadow="never" class="stat-card">
          <div class="stat-num">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="mid-row">
      <el-col :span="14">
        <el-card shadow="never" class="mid-card">
          <template #header><span>我的任务</span></template>
          <el-table :data="tasks" size="small" empty-text="暂时没有进行中的实训任务">
            <el-table-column prop="title" label="任务" min-width="150" show-overflow-tooltip />
            <el-table-column label="截止" width="120">
              <template #default="{ row }">{{ row.deadline ? String(row.deadline).slice(5, 16).replace('T', ' ') : '不限' }}</template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag v-if="row.my_status === 'reviewed'" size="small" type="success">已批改</el-tag>
                <el-tag v-else-if="row.my_status === 'submitted'" size="small" type="warning">待批改</el-tag>
                <el-tag v-else size="small" type="info">未提交</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="primary"
                  :disabled="row.my_status === 'submitted' || row.my_status === 'reviewed'"
                  @click="openSubmit(row)"
                >提交作品</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never" class="mid-card">
          <template #header>
            <span>我的能力</span>
            <el-button size="small" text type="primary" @click="loadAbility">刷新</el-button>
          </template>
          <template v-if="abilityLatest.length">
            <div v-for="item in abilityLatest" :key="item.dimension" class="ability-line">
              <span class="ability-name">{{ item.dimension }}</span>
              <el-progress :percentage="item.score" :stroke-width="10" :color="abilityColor" />
            </div>
          </template>
          <el-empty v-else description="完成实训批改后展示五维能力" :image-size="60" />
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <span>我的作品</span>
        <el-button size="small" text type="primary" @click="reload">刷新</el-button>
      </template>
      <el-table :data="works" v-loading="loading" empty-text="还没有作品，点击「新建剧集」开始创作">
        <el-table-column label="标题" prop="title" min-width="160" show-overflow-tooltip />
        <el-table-column label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ TYPE_LABELS[row.type] || row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ STATUS_LABELS[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" prop="version" width="70" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="openWorkshop(row.id)">进入工坊</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="newDialog" title="新建剧集" width="420px">
      <el-form label-width="72px">
        <el-form-item label="剧名">
          <el-input v-model="newTitle" placeholder="如：外卖箱里的秘密" maxlength="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :disabled="!newTitle.trim()" @click="createAndEnter">创建并进入工坊</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submitDialog" :title="`提交作品：${submitTarget ? submitTarget.title : ''}`" width="520px">
      <p class="submit-tip">选择要提交的作品（可多选），提交后教师将按 Rubric 批改并更新你的五维能力。</p>
      <el-checkbox-group v-model="submitWorkIds" class="submit-works">
        <el-checkbox v-for="work in readyWorks" :key="work.id" :label="work.id" border>
          {{ TYPE_LABELS[work.type] || work.type }} · {{ work.title }}
        </el-checkbox>
      </el-checkbox-group>
      <el-empty v-if="!readyWorks.length" description="暂无已完成的作品，请先在创作工坊完成生成" :image-size="60" />
      <el-input v-model="submitNote" type="textarea" :rows="2" maxlength="200" placeholder="给老师的留言（选填）" class="submit-note" />
      <template #footer>
        <el-button type="primary" :disabled="!submitWorkIds.length" :loading="submitting" @click="doSubmit">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  getStudentAbility,
  getTaskDetail,
  listTasks as apiListTasks,
  submitTask
} from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'
import { useWorkStore } from '../../stores/work.js'

const DIMENSIONS = ['内容创作', '跨文化沟通', '电商运营', 'AI工具应用', '数据分析']

const TYPE_LABELS = {
  script: '剧本',
  storyboard: '分镜',
  audio: '配音',
  subtitle: '字幕',
  video: '成片'
}

const STATUS_LABELS = {
  draft: '草稿',
  generating: '生成中',
  ready: '已完成',
  failed: '失败'
}

const userStore = useUserStore()
const workStore = useWorkStore()
const router = useRouter()

const newDialog = ref(false)
const newTitle = ref('')
const tasks = ref([])
const abilityLatest = ref([])
const submitDialog = ref(false)
const submitTarget = ref(null)
const submitWorkIds = ref([])
const submitNote = ref('')
const submitting = ref(false)

const readyWorks = computed(() =>
  workStore.works.filter((work) => work.status === 'ready')
)

function abilityColor(percentage) {
  if (percentage >= 85) return '#67c23a'
  if (percentage >= 60) return '#e6a23c'
  return '#f56c6c'
}

async function loadTasks() {
  try {
    const data = await apiListTasks()
    const items = []
    for (const task of data.items) {
      let myStatus = null
      try {
        const detail = await getTaskDetail(task.id)
        myStatus = detail.my_submission ? detail.my_submission.status : null
      } catch {
        myStatus = null
      }
      items.push({ ...task, my_status: myStatus })
    }
    tasks.value = items
  } catch {
    tasks.value = []
  }
}

async function loadAbility() {
  const me = userStore.profile
  if (!me) return
  try {
    const data = await getStudentAbility(me.id)
    abilityLatest.value = DIMENSIONS
      .filter((dimension) => data.latest[dimension] !== undefined)
      .map((dimension) => ({
        dimension,
        score: Math.round(data.latest[dimension])
      }))
  } catch {
    abilityLatest.value = []
  }
}

function openSubmit(task) {
  submitTarget.value = task
  submitWorkIds.value = []
  submitNote.value = ''
  submitDialog.value = true
}

async function doSubmit() {
  submitting.value = true
  try {
    await submitTask(submitTarget.value.id, {
      work_ids: submitWorkIds.value,
      note: submitNote.value || null
    })
    ElMessage.success('提交成功，等待教师批改')
    submitDialog.value = false
    await loadTasks()
  } catch (error) {
    ElMessage.error(error.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

const works = computed(() => workStore.works)
const loading = computed(() => workStore.loading)

const stats = computed(() => {
  const all = workStore.works
  return [
    { label: '剧本', value: all.filter((w) => w.type === 'script').length },
    { label: '分镜', value: all.filter((w) => w.type === 'storyboard').length },
    { label: '配音', value: all.filter((w) => w.type === 'audio').length },
    { label: '成片', value: all.filter((w) => w.type === 'video').length }
  ]
})

const greeting = computed(() => {
  const name = userStore.profile ? userStore.profile.username : ''
  const profile = userStore.profile && userStore.profile.profile
  const major = profile && profile.major ? ` · ${profile.major}` : ''
  return `${name}${major} · 学中做，做中创`
})

function statusType(status) {
  if (status === 'ready') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'generating') return 'warning'
  return 'info'
}

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function openWorkshop(workId) {
  router.push(`/student/workshop/${workId}`)
}

async function createAndEnter() {
  const title = newTitle.value.trim()
  const work = await workStore.createWork({ title, type: 'script' })
  newDialog.value = false
  newTitle.value = ''
  router.push(`/student/workshop/${work.id}`)
}

function logout() {
  userStore.logout()
  router.push('/login')
}

async function reload() {
  await workStore.loadWorks({ page: 1, page_size: 50 })
}

onMounted(async () => {
  if (!userStore.profile) {
    await userStore.fetchMe()
  }
  await reload()
  await loadTasks()
  await loadAbility()
})
</script>

<style scoped>
.page {
  padding: 20px 24px 40px;
  max-width: 1080px;
  margin: 0 auto;
}
.home-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.title {
  margin: 0 0 4px;
  font-weight: 500;
}
.sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.stat-row {
  margin-bottom: 16px;
}
.mid-row {
  margin-bottom: 16px;
}
.mid-card {
  height: 100%;
}
.ability-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.ability-name {
  width: 84px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.submit-tip {
  margin: 0 0 10px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.submit-works {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.submit-note {
  margin-top: 12px;
}
.stat-card {
  text-align: center;
}
.stat-num {
  font-size: 24px;
  font-weight: 500;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
