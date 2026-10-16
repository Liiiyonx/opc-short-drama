<template>
  <div class="page" v-loading="loading">
    <div class="head">
      <div>
        <h3 class="title">{{ task ? task.title : '任务详情' }}</h3>
        <span class="sub">
          {{ task ? STATUS_LABELS[task.status] || task.status : '' }}
          <template v-if="task && task.deadline"> · 截止 {{ formatTime(task.deadline) }}</template>
          · 提交 {{ submissions.length }} 份
        </span>
      </div>
      <div>
        <el-button @click="router.push('/teacher')">返回任务列表</el-button>
      </div>
    </div>

    <el-alert v-if="task && task.brief" type="info" :closable="false" :title="task.brief" class="brief" />

    <el-card v-if="task" shadow="never" class="rubric-card">
      <template #header>评分量规 Rubric（达标分 {{ (task.rubric_json || {}).pass_score || 60 }}）</template>
      <el-table :data="(task.rubric_json || {}).criteria || []" size="small">
        <el-table-column prop="name" label="评分项" min-width="150" />
        <el-table-column prop="dimension" label="能力维度" width="130" />
        <el-table-column label="权重" width="90">
          <template #default="{ row }">{{ Math.round(normalizedWeight(row) * 100) }}%</template>
        </el-table-column>
        <el-table-column prop="description" label="评分要点" min-width="200" show-overflow-tooltip />
      </el-table>
    </el-card>

    <el-card shadow="never">
      <template #header>提交列表</template>
      <el-table :data="submissions" empty-text="还没有学生提交">
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="expand-body">
              <div v-for="work in row.works" :key="work.id" class="work-line">
                <el-tag size="small">{{ TYPE_LABELS[work.type] || work.type }}</el-tag>
                <span class="work-title">{{ work.title }}</span>
                <el-tag size="small" :type="work.status === 'ready' ? 'success' : 'info'">{{ work.status }}</el-tag>
                <el-button size="small" type="primary" @click="openReview(work)">批改此作品</el-button>
              </div>
              <el-empty v-if="!row.works.length" description="提交中没有作品" :image-size="50" />
              <p v-if="row.note" class="note">学生留言：{{ row.note }}</p>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="submitter_name" label="学生" width="140" />
        <el-table-column label="提交作品" min-width="240">
          <template #default="{ row }">
            <span v-for="work in row.works" :key="work.id" class="work-chip">{{ TYPE_LABELS[work.type] || work.type }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'reviewed' ? 'success' : 'warning'">
              {{ SUB_LABELS[row.status] || row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ formatTime(row.submitted_at) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <ReviewDrawer
      v-model="drawerVisible"
      :work="reviewTarget"
      :rubric="task ? task.rubric_json : null"
      @done="reload"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import ReviewDrawer from '../../components/ReviewDrawer.vue'
import { getTaskDetail, listSubmissions } from '../../api/index.js'

const TYPE_LABELS = { script: '剧本', storyboard: '分镜', audio: '配音', subtitle: '字幕', video: '成片' }
const STATUS_LABELS = { draft: '草稿', published: '进行中', closed: '已截止' }
const SUB_LABELS = { submitted: '待批改', reviewed: '已批改', returned: '已退回' }

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const task = ref(null)
const submissions = ref([])
const drawerVisible = ref(false)
const reviewTarget = ref(null)

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function normalizedWeight(criterion) {
  const criteria = (task.value && task.value.rubric_json && task.value.rubric_json.criteria) || []
  const total = criteria.reduce((sum, item) => sum + Number(item.weight || 0), 0) || 1
  return Number(criterion.weight || 0) / total
}

async function reload() {
  loading.value = true
  try {
    const taskId = Number(route.params.taskId)
    const detail = await getTaskDetail(taskId)
    task.value = detail.task
    const data = await listSubmissions(taskId)
    submissions.value = data.items
  } catch (error) {
    ElMessage.error(error.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openReview(work) {
  reviewTarget.value = work
  drawerVisible.value = true
}

onMounted(reload)
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
  margin-bottom: 14px;
}
.title {
  margin: 0 0 4px;
  font-weight: 500;
}
.sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.brief {
  margin-bottom: 14px;
}
.rubric-card {
  margin-bottom: 14px;
}
.expand-body {
  padding: 8px 16px;
}
.work-line {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
}
.work-title {
  flex: 1;
  font-size: 13px;
}
.note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 8px 0 0;
}
.work-chip {
  display: inline-block;
  margin-right: 6px;
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
  font-size: 12px;
}
</style>
