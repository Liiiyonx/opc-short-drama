<template>
  <div class="page">
    <div class="head">
      <div>
        <h3 class="title">学生工作台</h3>
        <span class="sub">{{ greeting }}</span>
      </div>
      <div class="actions">
        <el-button @click="router.push('/student/transcript')">学习档案</el-button>
        <el-button @click="sharePortfolio">分享作品集</el-button>
        <el-button @click="router.push('/student/orders')">工单大厅</el-button>
        <el-button type="primary" @click="newDialog = true">新建剧集</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="stat-row">
      <el-col :xs="12" :sm="6" v-for="stat in stats" :key="stat.key">
        <el-card shadow="never" class="stat-card">
          <div class="stat-inner">
            <span class="stat-icon" :class="stat.cls" v-html="stat.icon"></span>
            <div>
              <div class="stat-num">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="12" class="mid-row">
      <el-col :xs="24" :md="14">
        <el-card shadow="never" class="mid-card">
          <template #header><span>我的任务</span></template>
          <!-- P0-07：桌面端表格 / 移动端卡片双形态，移动端不再压扁列 -->
          <el-table v-if="!isMobile" :data="tasks" size="small" empty-text="暂时没有进行中的实训任务">
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
          <template v-else>
            <el-empty v-if="!tasks.length" description="暂时没有进行中的实训任务" :image-size="60" />
            <div v-for="task in tasks" :key="task.id" class="task-card">
              <div class="task-card-main">
                <p class="task-card-title">{{ task.title }}</p>
                <p class="task-card-meta">
                  截止 {{ task.deadline ? String(task.deadline).slice(5, 16).replace('T', ' ') : '不限' }}
                </p>
              </div>
              <div class="task-card-side">
                <el-tag v-if="task.my_status === 'reviewed'" size="small" type="success">已批改</el-tag>
                <el-tag v-else-if="task.my_status === 'submitted'" size="small" type="warning">待批改</el-tag>
                <el-tag v-else size="small" type="info">未提交</el-tag>
                <el-button
                  size="small"
                  type="primary"
                  :disabled="task.my_status === 'submitted' || task.my_status === 'reviewed'"
                  @click="openSubmit(task)"
                >提交</el-button>
              </div>
            </div>
          </template>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="10">
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
      <el-skeleton v-if="loading && !works.length" :rows="4" animated class="table-skeleton" />
      <el-table v-else :data="works" v-loading="loading">
        <template #empty>
          <div class="empty-guide">
            <p class="eg-title">还没有作品</p>
            <p class="eg-desc">从一句话题材开始，AI 帮你走完剧本 → 分镜 → 配音 → 成片</p>
            <el-button type="primary" @click="newDialog = true">新建第一部剧</el-button>
          </div>
        </template>
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

    <el-dialog v-model="newDialog" title="新建剧集" :width="isMobile ? '94vw' : '420px'">
      <el-form label-width="72px">
        <el-form-item label="剧名">
          <el-input v-model="newTitle" placeholder="如：外卖箱里的秘密" maxlength="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :disabled="!newTitle.trim()" @click="createAndEnter">创建并进入工坊</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="submitDialog" :title="`提交作品：${submitTarget ? submitTarget.title : ''}`" :width="isMobile ? '94vw' : '520px'">
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
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  createPortfolioShare,
  getStudentAbility,
  getTaskDetail,
  listTasks as apiListTasks,
  submitTask
} from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'
import { useWorkStore } from '../../stores/work.js'

const DIMENSIONS = ['内容创作', '跨文化沟通', '电商运营', 'AI工具应用', '数据分析']

// 统计卡图标（内联 SVG，Feather 线条风，随文字色渲染）
const STAT_ICONS = {
  script:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
  storyboard:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>',
  audio:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/></svg>',
  video:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>'
}

const TYPE_LABELS = {
  script: '剧本',
  storyboard: '分镜',
  translate: '翻译本地化',
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

// P0-07：≤640px 视为移动端——任务表格切卡片、对话框全宽、能力条全宽
const isMobile = ref(window.matchMedia('(max-width: 640px)').matches)
function onViewportChange(e) {
  isMobile.value = e.matches
}

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
    { key: 'script', label: '剧本', value: all.filter((w) => w.type === 'script').length, cls: 'g-blue' },
    { key: 'storyboard', label: '分镜', value: all.filter((w) => w.type === 'storyboard').length, cls: 'g-violet' },
    { key: 'audio', label: '配音', value: all.filter((w) => w.type === 'audio').length, cls: 'g-amber' },
    { key: 'video', label: '成片', value: all.filter((w) => w.type === 'video').length, cls: 'g-green' }
  ].map((stat) => ({ ...stat, icon: STAT_ICONS[stat.key] }))
})

const greeting = computed(() => {
  const name = userStore.profile ? userStore.profile.username : ''
  const profile = userStore.profile && userStore.profile.profile
  const major = profile && profile.major ? ` · ${profile.major}` : ''
  return `${name}${major} · 学中做，做中创`
})

async function sharePortfolio() {
  try {
    const data = await createPortfolioShare()
    const link = `${location.origin}${data.path}`
    await navigator.clipboard.writeText(link)
    ElMessage.success('脱敏分享链接已复制：' + link)
  } catch (error) {
    ElMessage.error(error.message || '分享失败')
  }
}

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

async function reload() {
  await workStore.loadWorks({ page: 1, page_size: 50 })
}

onMounted(async () => {
  window.matchMedia('(max-width: 640px)').addEventListener('change', onViewportChange)
  if (!userStore.profile) {
    await userStore.fetchMe()
  }
  await reload()
  await loadTasks()
  await loadAbility()
})

onBeforeUnmount(() => {
  window.matchMedia('(max-width: 640px)').removeEventListener('change', onViewportChange)
})
</script>

<style scoped>
.empty-guide {
  padding: 14px 0 8px;
}
.eg-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.eg-desc {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.table-skeleton {
  padding: 6px 2px 2px;
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
.ability-line :deep(.el-progress) {
  flex: 1; /* flex 行内进度条默认宽度 0（存量问题：只显示百分比、不见条） */
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
.stat-inner {
  display: flex;
  align-items: center;
  gap: 14px;
}
.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-icon :deep(svg) {
  width: 20px;
  height: 20px;
}
.g-blue {
  background: rgba(64, 158, 255, 0.12);
  color: #409eff;
}
.g-violet {
  background: rgba(124, 58, 237, 0.12);
  color: #7c3aed;
}
.g-amber {
  background: rgba(230, 162, 60, 0.15);
  color: #e6a23c;
}
.g-green {
  background: rgba(103, 194, 58, 0.15);
  color: #67c23a;
}
.stat-num {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.15;
}
.stat-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}

/* ---------- P0-07 移动端适配（≤640px） ---------- */
.task-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.task-card:last-of-type {
  border-bottom: none;
}
.task-card-main {
  min-width: 0;
}
.task-card-title {
  margin: 0 0 4px;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-card-meta {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.task-card-side {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

@media (max-width: 640px) {
  .head {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .head .actions {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  /* 触控目标 ≥ 44px（首行主操作按钮） */
  .head :deep(.el-button) {
    width: 100%;
    margin: 0;
    min-height: 44px;
  }
  .mid-row :deep(.el-card__body) {
    padding: 12px;
  }
  .ability-line {
    gap: 8px;
  }
  .ability-name {
    width: 5.5em; /* 五个汉字 + 余量，长维度名不换行不裁切 */
    font-size: 12.5px;
  }
  .ability-line :deep(.el-progress__text) {
    font-size: 12px !important;
  }
  .stat-inner {
    gap: 10px;
  }
  .stat-num {
    font-size: 20px;
  }
}
</style>
