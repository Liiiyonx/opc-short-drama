<template>
  <el-drawer v-model="visible" :title="`批改作品：${work ? work.title : ''}`" size="680px">
    <div v-loading="loading" class="review-body">
      <template v-if="work">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="作品类型">{{ TYPE_LABELS[work.type] || work.type }}</el-descriptions-item>
          <el-descriptions-item label="版本">v{{ work.version }}</el-descriptions-item>
          <el-descriptions-item label="AI 使用声明" :span="2">
            <span v-if="declare">
              智能体：{{ (declare.agents_used || []).join('、') || '未填' }}；
              人工修改比例：{{ declare.human_edit_ratio != null ? Math.round(declare.human_edit_ratio * 100) + '%' : '未填' }}
            </span>
            <span v-else class="muted">学生未填写 AI 使用声明</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="measuredRatio != null" label="实测修改度" :span="2">
            <el-tag type="warning" size="small">{{ Math.round(measuredRatio * 100) }}%</el-tag>
            <span class="muted" style="margin-left: 8px">
              系统比对「学生修订版 vs AI 原版」自动计算（字幕校轴等），与自报值可交叉核验
            </span>
          </el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">作品产物</el-divider>
        <AssetCard v-for="asset in assets" :key="asset.id" :asset="asset" />
        <el-empty v-if="!assets.length" description="暂无产物" :image-size="60" />

        <el-divider content-position="left">Rubric 评分</el-divider>
        <div v-for="criterion in criteria" :key="criterion.key" class="criterion-row">
          <div class="criterion-head">
            <span>{{ criterion.name }}</span>
            <small class="muted">{{ criterion.dimension }} · 权重 {{ Math.round((normalizedWeight(criterion) * 100)) }}%</small>
          </div>
          <el-slider v-model="scores[criterion.key]" :min="0" :max="100" show-input :format-tooltip="(v) => `${v} 分`" />
        </div>
        <div class="total-line">
          加权总分：<b>{{ totalScore }}</b> 分
          <el-tag v-if="existingReview" size="small" type="info" style="margin-left: 10px">
            此前已批改（{{ existingReview.rubric_score_json.total }} 分）
          </el-tag>
        </div>

        <el-form label-width="72px">
          <el-form-item label="评语">
            <el-input v-model="comment" type="textarea" :rows="3" maxlength="500" placeholder="给出改进建议" />
          </el-form-item>
        </el-form>

        <div class="submit-line">
          <el-button type="primary" :loading="saving" @click="submitReview">提交批改（触发能力快照）</el-button>
          <span v-if="lastResult" class="result-tip">
            已提交：加权总分 {{ lastResult.total }} 分，{{ lastResult.passed ? '达标' : '未达标' }}
          </span>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import AssetCard from './AssetCard.vue'
import { getWork, getWorkReview, reviewWork } from '../api/index.js'

const TYPE_LABELS = { script: '剧本', storyboard: '分镜', translate: '翻译本地化', audio: '配音', subtitle: '字幕', video: '成片' }

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  work: { type: Object, default: null },
  rubric: { type: Object, default: null }
})
const emit = defineEmits(['update:modelValue', 'done'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const loading = ref(false)
const saving = ref(false)
const assets = ref([])
const declare = ref(null)
const existingReview = ref(null)
const comment = ref('')
const scores = ref({})
const lastResult = ref(null)

const criteria = computed(() => (props.rubric && props.rubric.criteria) || [])

const measuredRatio = computed(() => {
  const value = declare.value && declare.value.measured_edit_ratio
  return value === undefined || value === null ? null : value
})

function normalizedWeight(criterion) {
  const totalWeight = criteria.value.reduce((sum, item) => sum + Number(item.weight || 0), 0) || 1
  return Number(criterion.weight || 0) / totalWeight
}

const totalScore = computed(() => {
  let total = 0
  for (const criterion of criteria.value) {
    total += (scores.value[criterion.key] || 0) * normalizedWeight(criterion)
  }
  return Math.round(total * 100) / 100
})

async function load() {
  if (!props.work) return
  loading.value = true
  lastResult.value = null
  comment.value = ''
  // 先按 Rubric 初始化默认分（80），加载失败也不会提交 0 分
  const initial = {}
  for (const criterion of criteria.value) {
    initial[criterion.key] = 80
  }
  scores.value = initial
  try {
    const detail = await getWork(props.work.id)
    assets.value = detail.assets || []
    declare.value = detail.work && detail.work.ai_declare_json
    try {
      const reviewData = await getWorkReview(props.work.id)
      existingReview.value = reviewData.latest
      if (reviewData.latest) {
        comment.value = reviewData.latest.comment || ''
        const items = reviewData.latest.rubric_score_json.items || {}
        const restored = {}
        for (const [key, value] of Object.entries(items)) {
          restored[key] = value.score
        }
        scores.value = restored
      }
    } catch {
      existingReview.value = null
    }
    // 恢复未覆盖的项到默认分
    for (const criterion of criteria.value) {
      if (scores.value[criterion.key] === undefined) {
        scores.value[criterion.key] = 80
      }
    }
  } catch (error) {
    ElMessage.error(error.message || '加载作品失败')
  } finally {
    loading.value = false
  }
}

async function submitReview() {
  saving.value = true
  try {
    const payload = {
      criterion_scores: criteria.value.map((criterion) => ({
        key: criterion.key,
        score: Number(scores.value[criterion.key] || 0)
      })),
      comment: comment.value || null
    }
    const data = await reviewWork(props.work.id, payload)
    lastResult.value = { total: data.total, passed: data.passed }
    ElMessage.success('批改完成，能力快照已更新')
    emit('done')
  } catch (error) {
    ElMessage.error(error.message || '提交失败')
  } finally {
    saving.value = false
  }
}

watch(() => props.modelValue, (value) => {
  if (value) {
    scores.value = {}
    load()
  }
})
</script>

<style scoped>
.review-body {
  min-height: 200px;
}
.criterion-row {
  margin-bottom: 6px;
}
.criterion-head {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 2px;
}
.muted {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.total-line {
  margin: 8px 0 14px;
  font-size: 14px;
}
.submit-line {
  display: flex;
  align-items: center;
  gap: 12px;
}
.result-tip {
  font-size: 13px;
  color: var(--el-color-success);
}
</style>
