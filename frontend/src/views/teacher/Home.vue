<template>
  <div class="page">
    <div class="head">
      <div>
        <h3 class="title">教师工作台</h3>
        <span class="sub">{{ username }} · 任务发布与 Rubric 批改</span>
      </div>
      <div>
        <el-button type="primary" @click="openForm">发布任务</el-button>
        <el-button text @click="logout">退出登录</el-button>
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
      <el-table :data="tasks" v-loading="loading" empty-text="还没有任务，点击「发布任务」开始">
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

import { closeTask, createTask, listCourses, listOrders, listTasks, verifyOrder } from '../../api/index.js'
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

function logout() {
  userStore.logout()
  router.push('/login')
}

onMounted(async () => {
  if (!userStore.profile) {
    await userStore.fetchMe()
  }
  await reload()
})
</script>

<style scoped>
.page {
  padding: 20px 24px 40px;
  max-width: 1080px;
  margin: 0 auto;
}
.head {
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
</style>
