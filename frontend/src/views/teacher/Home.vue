<template>
  <div class="page">
    <div class="head">
      <div>
        <h3 class="title">教师工作台</h3>
        <span class="sub">{{ username }} · 任务发布与 Rubric 批改</span>
      </div>
      <div>
        <el-button @click="lessonDialog = true">AI 备课</el-button>
        <el-button type="primary" @click="openForm">发布任务</el-button>
      </div>
    </div>

    <el-card v-if="pendingOrders.length" shadow="never" class="pending-card">
      <template #header>待审核工单（{{ pendingOrders.length }}）</template>
      <el-table :data="pendingOrders" size="small">
        <el-table-column prop="title" label="工单" min-width="180" show-overflow-tooltip />
        <el-table-column label="预算" width="100">
          <template #default="{ row }">{{ (row.budget_cents / 100).toFixed(0) }} 元</template>
        </el-table-column>
        <el-table-column label="提交时间" width="160">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="verifyOrderRow(row, true)">通过</el-button>
            <el-button size="small" type="danger" @click="verifyOrderRow(row, false)">驳回</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>我的任务</span>
        <el-button size="small" text type="primary" @click="reload">刷新</el-button>
      </template>
      <el-skeleton v-if="loading && !tasks.length" :rows="3" animated class="table-skeleton" />
      <el-table v-else :data="tasks" v-loading="loading">
        <template #empty>
          <div class="empty-guide">
            <p class="eg-title">还没有实训任务</p>
            <p class="eg-desc">配置评分量规 Rubric，发布后学生即可在工坊提交作品</p>
            <el-button type="primary" @click="openForm">发布第一个任务</el-button>
          </div>
        </template>
        <el-table-column prop="title" label="任务标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'published' ? 'success' : 'info'">
              {{ STATUS_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评分项" width="80">
          <template #default="{ row }">{{ (row.rubric_json && row.rubric_json.criteria || []).length }}</template>
        </el-table-column>
        <el-table-column label="截止时间" width="170">
          <template #default="{ row }">{{ formatTime(row.deadline) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170">
          <template #default="{ row }">
            <el-button size="small" text type="primary" @click="router.push(`/teacher/tasks/${row.id}`)">提交列表</el-button>
            <el-button v-if="row.status === 'published'" size="small" text type="danger" @click="closeTaskRow(row)">截止</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- AI 用量看板（Langfuse 式成本可观测） -->
    <el-card shadow="never" class="usage-card">
      <template #header>
        <span>AI 用量看板（近 {{ usageStats.days }} 天）</span>
        <el-button size="small" text type="primary" @click="loadUsage">刷新</el-button>
      </template>
      <template v-if="usageStats.total">
        <div class="usage-totals">
          <div class="u-total">
            <div class="u-num">{{ usageStats.total.calls }}</div>
            <div class="u-label">调用次数</div>
          </div>
          <div class="u-total">
            <div class="u-num">{{ usageStats.total.tokens.toLocaleString() }}</div>
            <div class="u-label">tokens</div>
          </div>
          <div class="u-total">
            <div class="u-num cost">¥{{ usageStats.total.cost.toFixed(2) }}</div>
            <div class="u-label">估算成本</div>
          </div>
        </div>

        <el-row :gutter="16" class="usage-detail">
          <el-col :span="10">
            <div class="u-sec-title">按智能体</div>
            <div v-for="item in usageStats.by_agent" :key="item.agent_type" class="bar-row">
              <span class="bar-label">{{ AGENT_LABELS[item.agent_type] || item.agent_type }}</span>
              <div class="bar-track">
                <div class="bar-fill" :style="{ width: barWidth(item.cost, usageStats.by_agent) }"></div>
              </div>
              <span class="bar-value">¥{{ item.cost.toFixed(3) }}</span>
            </div>
            <div class="u-sec-title" style="margin-top: 14px">用户 Top3</div>
            <div v-for="item in usageStats.top_users.slice(0, 3)" :key="item.username" class="bar-row">
              <span class="bar-label">{{ item.username }}</span>
              <div class="bar-track">
                <div class="bar-fill alt" :style="{ width: barWidth(item.cost, usageStats.top_users) }"></div>
              </div>
              <span class="bar-value">¥{{ item.cost.toFixed(3) }}</span>
            </div>
          </el-col>
          <el-col :span="14">
            <div class="u-sec-title">每日趋势</div>
            <div class="day-chart">
              <div
                v-for="day in usageStats.by_day"
                :key="day.date"
                class="day-col"
                :title="`${day.date}：${day.calls} 次 · ¥${day.cost.toFixed(3)}`"
              >
                <div class="day-bar-wrap">
                  <div class="day-bar" :style="{ height: dayBarHeight(day) }"></div>
                </div>
                <div class="day-label">{{ day.date.slice(5) }}</div>
              </div>
              <div v-if="!usageStats.by_day.length" class="u-empty">暂无调用记录</div>
            </div>
          </el-col>
        </el-row>
      </template>
      <el-empty v-else description="暂无调用数据" :image-size="50" />
    </el-card>

    <!-- 能力预警（P1：低分学生标红 + 辅导建议） -->
    <el-card shadow="never" class="warn-card">
      <template #header>
        <span>能力预警（达标线 {{ warnings.threshold }} 分）</span>
        <el-button size="small" text type="primary" @click="loadWarnings">刷新</el-button>
      </template>
      <el-empty v-if="!warnings.items.length" description="所有学生能力均达标，无需预警" :image-size="50" />
      <div v-for="item in warnings.items" :key="item.username" class="warn-row" :class="{ 'is-critical': item.avg !== null && item.avg < warnings.threshold - 10 }">
        <b class="warn-name">{{ item.username }}</b>
        <span class="warn-meta">{{ item.major || '—' }} · {{ item.grade || '—' }}</span>
        <el-tag v-if="item.avg === null" size="small" type="info">无数据</el-tag>
        <el-tag v-else size="small" :type="item.avg < warnings.threshold - 10 ? 'danger' : 'warning'">均分 {{ item.avg }}</el-tag>
        <span class="warn-issue">{{ item.issue }}</span>
      </div>
      <p class="warn-tip">建议：对连续预警学生安排一对一辅导，并在下一份实训任务中针对性设置薄弱维度的评分项。</p>
    </el-card>

    <!-- AI 备课助手 -->
    <el-dialog v-model="lessonDialog" title="AI 备课助手（草案，可二次编辑）" width="680px">
      <el-form label-width="90px" size="small">
        <el-form-item label="课程">
          <el-select v-model="lessonForm.course_name" filterable allow-create placeholder="选择或输入课程名" style="width: 260px">
            <el-option v-for="c in courses" :key="c.id" :label="c.name" :value="c.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="本次课主题">
          <el-input v-model="lessonForm.topic" maxlength="100" placeholder="如：第 3 周 · 竖屏短剧的开头三秒钩子" />
        </el-form-item>
        <el-form-item label="时长(分钟)">
          <el-input-number v-model="lessonForm.duration_minutes" :min="20" :max="240" :step="5" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="lessonLoading" :disabled="!lessonForm.topic.trim() || !lessonForm.course_name.trim()" @click="runLesson">
          生成教案草案
        </el-button>
      </template>
      <div v-if="lessonResult" class="lesson-result">
        <div class="lesson-sec">
          <b>教学目标</b>
          <ul><li v-for="(o, i) in lessonResult.objectives" :key="i">{{ o }}</li></ul>
        </div>
        <el-table :data="lessonResult.outline" size="small" border>
          <el-table-column prop="section" label="环节" width="150" />
          <el-table-column prop="minutes" label="分钟" width="70" />
          <el-table-column prop="content" label="内容与教法" min-width="260" />
        </el-table>
        <div class="lesson-sec">
          <b>课堂讨论题</b>
          <ul><li v-for="(q, i) in lessonResult.discussion_questions || []" :key="i">{{ q }}</li></ul>
        </div>
        <div class="lesson-sec">
          <b>课后实训</b>
          <p class="lesson-p">{{ lessonResult.assignment }}</p>
        </div>
        <div class="lesson-sec">
          <b>Rubric 建议</b>
          <p class="lesson-p">
            <el-tag v-for="(r, i) in lessonResult.rubric_suggestion || []" :key="i" size="small" effect="plain" class="rubric-tag">
              {{ r.name }} · {{ r.dimension }} · {{ r.weight }}
            </el-tag>
          </p>
        </div>
        <div class="lesson-foot">
          <el-button size="small" @click="copyLesson">复制教案全文</el-button>
          <span class="hint">AI 草案仅供参考，请按班级学情修改后使用</span>
        </div>
      </div>
    </el-dialog>

    <el-dialog v-model="formVisible" title="发布实训任务" width="760px">
      <el-form label-width="96px">
        <el-form-item label="任务标题">
          <el-input v-model="form.title" maxlength="80" placeholder="如：短剧出海实训任务一" />
        </el-form-item>
        <el-form-item label="任务说明">
          <el-input v-model="form.brief" type="textarea" :rows="3" placeholder="交付要求、注意事项" />
        </el-form-item>
        <el-form-item label="绑定课程">
          <el-select v-model="form.course_id" clearable placeholder="可不绑定" style="width: 320px">
            <el-option v-for="course in courses" :key="course.id" :label="`${course.code} ${course.name}`" :value="course.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker v-model="form.deadline" type="datetime" placeholder="可不设" />
        </el-form-item>
        <el-form-item label="组队规则">
          <el-radio-group v-model="form.team_rule">
            <el-radio label="free">自由组队</el-radio>
            <el-radio label="cross_major">跨专业组队</el-radio>
            <el-radio label="forced">强制分配</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">评分量规 Rubric（权重会自动归一化）</el-divider>
      <el-table :data="form.rubric.criteria" size="small" border>
        <el-table-column label="评分项名称" min-width="150">
          <template #default="{ row }"><el-input v-model="row.name" size="small" /></template>
        </el-table-column>
        <el-table-column label="能力维度" width="170">
          <template #default="{ row }">
            <el-select v-model="row.dimension" size="small">
              <el-option v-for="dimension in DIMENSIONS" :key="dimension" :label="dimension" :value="dimension" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="权重" width="120">
          <template #default="{ row }"><el-input-number v-model="row.weight" :min="0.1" :max="100" :step="0.5" size="small" controls-position="right" /></template>
        </el-table-column>
        <el-table-column width="64">
          <template #default="{ $index }">
            <el-button size="small" text type="danger" @click="form.rubric.criteria.splice($index, 1)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="rubric-foot">
        <el-button size="small" :disabled="form.rubric.criteria.length >= 8" @click="addCriterion">+ 添加评分项</el-button>
        <span class="pass-score">达标分：<el-input-number v-model="form.rubric.pass_score" :min="0" :max="100" size="small" controls-position="right" /></span>
      </div>

      <template #footer>
        <el-button type="primary" :loading="saving" :disabled="!form.title.trim() || !form.rubric.criteria.length" @click="submitForm">发布任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { invokeAgent, closeTask, createTask, getAbilityWarnings, getUsageStats, listCourses, listOrders, listTasks, verifyOrder } from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'

const DIMENSIONS = ['内容创作', '跨文化沟通', '电商运营', 'AI工具应用', '数据分析']
const STATUS_LABELS = { draft: '草稿', published: '进行中', closed: '已截止' }

const DEFAULT_CRITERIA = () => [
  { key: 'content_creation', name: '剧本与内容质量', dimension: '内容创作', weight: 2.5, description: '故事结构、钩子设计、台词质量' },
  { key: 'cross_culture', name: '跨文化本地化', dimension: '跨文化沟通', weight: 2, description: '目标市场文化适配与表达' },
  { key: 'ecommerce', name: '发布与运营设计', dimension: '电商运营', weight: 2, description: '发布参数、标签与投放思路' },
  { key: 'ai_tools', name: 'AI 工具运用', dimension: 'AI工具应用', weight: 2, description: '智能体使用策略与提效程度' },
  { key: 'analytics', name: '数据与复盘', dimension: '数据分析', weight: 1.5, description: '数据意识与复盘改进' }
]

const router = useRouter()
const userStore = useUserStore()
const username = computed(() => (userStore.profile ? userStore.profile.username : ''))

const tasks = ref([])
const courses = ref([])
const orders = ref([])
const loading = ref(false)
const saving = ref(false)

// 能力预警
const warnings = ref({ threshold: 60, count: 0, items: [] })

async function loadWarnings() {
  try {
    warnings.value = await getAbilityWarnings({ threshold: 60 })
  } catch {
    warnings.value = { threshold: 60, count: 0, items: [] }
  }
}

// AI 备课助手
const lessonDialog = ref(false)
const lessonLoading = ref(false)
const lessonForm = ref({ course_name: '', topic: '', duration_minutes: 45 })
const lessonResult = ref(null)

async function runLesson() {
  lessonLoading.value = true
  lessonResult.value = null
  try {
    const data = await invokeAgent('lesson', { ...lessonForm.value })
    lessonResult.value = data.result
    ElMessage.success('教案草案已生成')
  } catch (error) {
    ElMessage.error(error.message || '备课生成失败')
  } finally {
    lessonLoading.value = false
  }
}

async function copyLesson() {
  const r = lessonResult.value
  if (!r) return
  const text = [
    '【教学目标】',
    ...r.objectives.map((o) => '- ' + o),
    '',
    '【课堂环节】',
    ...r.outline.map((s) => `- ${s.section}（${s.minutes} 分钟）：${s.content}`),
    '',
    '【课堂讨论题】',
    ...(r.discussion_questions || []).map((q) => '- ' + q),
    '',
    '【课后实训】',
    r.assignment || '',
    '',
    '【Rubric 建议】',
    ...(r.rubric_suggestion || []).map((x) => `- ${x.name}（${x.dimension}，权重 ${x.weight}）`)
  ].join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('教案全文已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择')
  }
}

// AI 用量看板（近 14 天）
const AGENT_LABELS = {
  script: '剧本生成', storyboard: '分镜', translate: '翻译本地化',
  tts: '配音', compose: '成片合成', publish: '发布参数'
}
const usageStats = ref({ days: 14, total: null, by_agent: [], by_day: [], top_users: [] })

async function loadUsage() {
  try {
    usageStats.value = await getUsageStats({ days: 14 })
  } catch {
    usageStats.value = { days: 14, total: null, by_agent: [], by_day: [], top_users: [] }
  }
}

function barWidth(value, list) {
  const max = Math.max(...list.map((i) => i.cost), 0.0001)
  return `${Math.max(4, Math.round((value / max) * 100))}%`
}

function dayBarHeight(day) {
  const max = Math.max(...usageStats.value.by_day.map((d) => d.cost), 0.0001)
  return `${Math.max(6, Math.round((day.cost / max) * 100))}%`
}
const formVisible = ref(false)
const form = ref({
  title: '',
  brief: '',
  course_id: null,
  deadline: null,
  team_rule: 'free',
  rubric: { criteria: DEFAULT_CRITERIA(), pass_score: 60 }
})

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function addCriterion() {
  form.value.rubric.criteria.push({
    key: 'custom_' + Date.now(),
    name: '',
    dimension: '内容创作',
    weight: 1,
    description: ''
  })
}

const pendingOrders = computed(() =>
  orders.value.filter((order) => order.status === 'pending_review')
)

async function reload() {
  loading.value = true
  try {
    const data = await listTasks()
    tasks.value = data.items
    const courseData = await listCourses()
    courses.value = courseData.items
    const orderData = await listOrders()
    orders.value = orderData.items
  } catch (error) {
    ElMessage.error(error.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function verifyOrderRow(row, approved) {
  try {
    if (!approved) {
      const { value } = await ElMessageBox.prompt('请填写驳回意见', '驳回工单', {
        inputPlaceholder: '如：需求描述不完整，请补充交付标准'
      })
      await verifyOrder(row.id, { approved: false, note: value })
    } else {
      await ElMessageBox.confirm(`确认通过工单「${row.title}」？通过后学生可见并投标。`, '审核通过', { type: 'warning' })
      await verifyOrder(row.id, { approved: true, note: '需求清晰，通过' })
    }
    ElMessage.success(approved ? '已通过' : '已驳回')
    await reload()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '操作失败')
    }
  }
}

function openForm() {
  form.value = {
    title: '',
    brief: '',
    course_id: null,
    deadline: null,
    team_rule: 'free',
    rubric: { criteria: DEFAULT_CRITERIA(), pass_score: 60 }
  }
  formVisible.value = true
}

async function submitForm() {
  saving.value = true
  try {
    const payload = {
      title: form.value.title.trim(),
      brief: form.value.brief || null,
      course_id: form.value.course_id || null,
      deadline: form.value.deadline ? new Date(form.value.deadline).toISOString().slice(0, 19) : null,
      team_rule: form.value.team_rule,
      rubric: form.value.rubric,
      publish: true
    }
    await createTask(payload)
    ElMessage.success('任务已发布')
    formVisible.value = false
    // 成功后重置：避免残留值被意外再次提交
    form.value = {
      title: '',
      brief: '',
      course_id: null,
      deadline: null,
      team_rule: 'free',
      rubric: { criteria: DEFAULT_CRITERIA(), pass_score: 60 }
    }
    await reload()
  } catch (error) {
    ElMessage.error(error.message || '发布失败')
  } finally {
    saving.value = false
  }
}

async function closeTaskRow(row) {
  try {
    await ElMessageBox.confirm(`确认截止任务「${row.title}」？截止后学生无法再提交。`, '截止任务', { type: 'warning' })
    await closeTask(row.id)
    ElMessage.success('任务已截止')
    await reload()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '操作失败')
    }
  }
}

onMounted(async () => {
  if (!userStore.profile) {
    await userStore.fetchMe()
  }
  await reload()
  loadUsage()
  loadWarnings()
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

.rubric-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}
.pass-score {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.pending-card {
  margin-bottom: 14px;
}

/* ---------- AI 用量看板 ---------- */
.usage-card {
  margin-top: 16px;
}
.usage-totals {
  display: flex;
  gap: 40px;
  padding: 4px 0 14px;
}
.u-num {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
}
.u-num.cost {
  color: var(--el-color-success);
}
.u-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.usage-detail {
  margin-top: 4px;
}
.u-sec-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
}
.bar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 7px;
}
.bar-label {
  width: 76px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bar-track {
  flex: 1;
  height: 8px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 4px;
  background: var(--opc-gradient);
}
.bar-fill.alt {
  background: var(--el-color-success);
}
.bar-value {
  width: 70px;
  text-align: right;
  font-size: 11px;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}
.day-chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 120px;
  padding: 4px 2px 0;
}
.day-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
  min-width: 0;
}
.day-bar-wrap {
  flex: 1;
  width: 100%;
  max-width: 34px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.day-bar {
  width: 70%;
  border-radius: 4px 4px 0 0;
  background: var(--opc-gradient);
  min-height: 4px;
}
.day-label {
  font-size: 10px;
  color: var(--el-text-color-placeholder);
  margin-top: 5px;
  transform: scale(0.9);
  white-space: nowrap;
}
.u-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  padding: 20px 0;
}

/* ---------- 能力预警 ---------- */
.warn-card {
  margin-top: 16px;
}
.warn-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  margin-bottom: 6px;
  background: var(--el-fill-color-light);
}
.warn-row.is-critical {
  background: var(--el-color-danger-light-9);
}
.warn-name {
  font-size: 13px;
}
.warn-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.warn-issue {
  font-size: 12px;
  color: var(--el-text-color-regular);
  margin-left: auto;
  text-align: right;
}
.warn-tip {
  margin: 10px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ---------- AI 备课 ---------- */
.lesson-result {
  margin-top: 14px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.lesson-sec {
  margin-bottom: 12px;
}
.lesson-sec b {
  font-size: 13px;
}
.lesson-sec ul {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12.5px;
  line-height: 1.7;
}
.lesson-p {
  margin: 6px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
}
.rubric-tag {
  margin: 0 6px 4px 0;
}
.lesson-foot {
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
