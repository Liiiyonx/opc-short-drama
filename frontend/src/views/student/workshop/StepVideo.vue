<template>
  <section class="step-panel">
    <template v-if="!work">
      <el-empty description="还没有成片作品">
        <el-button type="primary" :disabled="!canCreate" @click="emit('create')">创建成片作品</el-button>
        <p v-if="!canCreate" class="hint">需要先完成分镜与配音</p>
      </el-empty>
    </template>

    <template v-else-if="work.status !== 'ready'">
      <el-alert
        v-if="work.status === 'failed'"
        type="error"
        :closable="false"
        show-icon
        title="上次合成失败，可直接重试；连续失败请检查后台 worker 与 ffmpeg"
      />
      <el-alert v-else-if="work.status === 'generating' && !polling" type="warning" :closable="false" show-icon title="任务正在后台处理中">
        <template #default>
          <span>稍后刷新查看结果；若长时间无进展，请确认 worker 已启动。</span>
          <el-button size="small" text type="primary" @click="emit('refresh')">刷新状态</el-button>
        </template>
      </el-alert>
      <el-alert type="info" :closable="false" show-icon title="成片合成说明" description="按分镜顺序拼图 + 烧录字幕；未上传素材图时使用占位图，可在分镜步骤的作品资产中上传图片。" />
      <el-button type="primary" :loading="saving || polling" @click="onGenerate">
        {{ polling ? '合成中…' : '合成成片' }}
      </el-button>
      <el-progress v-if="polling" :percentage="pollPercent" :stroke-width="10" striped striped-flow :duration="2" />
      <el-alert
        v-if="polling && slow"
        type="warning"
        :closable="false"
        title="处理时间较长：请确认后台 worker 已启动（仍会继续等待）"
      />
      <el-alert v-if="pollError" type="error" :closable="false" :title="pollError" />
    </template>

    <template v-else>
      <el-alert
        type="success"
        :closable="false"
        show-icon
        :title="`成片完成：${((meta.duration_ms || 0) / 1000).toFixed(1)} 秒${meta.placeholder ? '（占位图路线）' : ''}`"
      />
      <div class="video-wall" v-if="videoAssets.length">
        <div
          v-for="(asset, idx) in videoAssets"
          :key="asset.id"
          class="wall-item"
        >
          <span v-if="idx === videoAssets.length - 1" class="wall-badge">最新</span>
          <span v-else class="wall-badge old">历史版本</span>
          <AssetCard :asset="asset" />
        </div>
      </div>

      <el-divider content-position="left">发布参数包</el-divider>
      <div class="publish-box">
        <div class="publish-head">
          <el-button size="small" type="primary" :loading="publishGenerating" @click="onGeneratePublish">
            {{ publishParams ? '重新生成发布参数' : '生成发布参数' }}
          </el-button>
          <UsageChip :usage="publishUsage" />
          <span class="hint">按目标市场生成各平台标题 / 文案 / 话题标签 / 发布时间建议</span>
        </div>
        <template v-if="publishParams">
          <el-row :gutter="10" class="platform-row">
            <el-col v-for="platform in publishParams.platforms || []" :key="platform.name" :span="8">
              <el-card shadow="never" class="platform-card">
                <template #header>
                  <div class="platform-head">
                    <span class="platform-id">
                      <span class="platform-avatar" :style="{ background: avatarColor(platform.name) }">{{ platform.name.charAt(0) }}</span>
                      <span class="platform-name">{{ platform.name }}</span>
                    </span>
                    <el-button
                      size="small"
                      text
                      type="primary"
                      @click="copyText(`${platform.title}\n${platform.caption}\n${(platform.hashtags || []).join(' ')}`)"
                    >
                      复制
                    </el-button>
                  </div>
                </template>
                <p class="p-title">{{ platform.title }}</p>
                <p class="p-caption">{{ platform.caption }}</p>
                <div v-if="(platform.hashtags || []).length" class="p-tags">
                  <el-tag v-for="tag in platform.hashtags" :key="tag" size="small" round effect="plain" type="info">{{ tag }}</el-tag>
                </div>
                <p class="p-meta">🕐 {{ platform.best_time }}</p>
                <p v-if="platform.notes" class="p-note">{{ platform.notes }}</p>
              </el-card>
            </el-col>
          </el-row>
          <el-alert
            v-if="(publishParams.compliance_checklist || []).length"
            type="warning"
            :closable="false"
            title="发布前合规检查"
          >
            <template #default>
              <ul class="checklist">
                <li v-for="(item, idx) in publishParams.compliance_checklist" :key="idx">{{ item }}</li>
              </ul>
            </template>
          </el-alert>
          <p v-if="publishParams.resolution_note" class="p-meta">🎬 {{ publishParams.resolution_note }}</p>
        </template>
      </div>

      <el-divider content-position="left">数据复盘（发布后回填播放数据）</el-divider>
      <div class="review-box">
        <el-form :inline="true" size="small" class="review-form">
          <el-form-item label="平台">
            <el-select v-model="reviewForm.platform" style="width: 130px">
              <el-option v-for="p in ['TikTok', 'YouTube Shorts', 'ReelShort', 'Instagram Reels']" :key="p" :label="p" :value="p" />
            </el-select>
          </el-form-item>
          <el-form-item label="播放"><el-input-number v-model="reviewForm.stats.views" :min="0" :controls="false" style="width: 90px" /></el-form-item>
          <el-form-item label="点赞"><el-input-number v-model="reviewForm.stats.likes" :min="0" :controls="false" style="width: 80px" /></el-form-item>
          <el-form-item label="评论"><el-input-number v-model="reviewForm.stats.comments" :min="0" :controls="false" style="width: 80px" /></el-form-item>
          <el-form-item label="分享"><el-input-number v-model="reviewForm.stats.shares" :min="0" :controls="false" style="width: 80px" /></el-form-item>
          <el-form-item label="完播率%">
            <el-input-number v-model="reviewRatePct" :min="0" :max="100" :controls="false" style="width: 80px" />
          </el-form-item>
          <el-form-item label="均观秒"><el-input-number v-model="reviewForm.stats.avg_watch_seconds" :min="0" :controls="false" style="width: 80px" /></el-form-item>
          <el-form-item>
            <el-button type="primary" :loading="analyzeLoading" @click="runAnalyze">
              {{ analysisReport ? '重新生成复盘' : '生成数据复盘' }}
            </el-button>
            <el-button :disabled="!analysisReport" :loading="optimizeLoading" @click="runOptimize">
              {{ optimizePlan ? '重新生成建议' : '生成优化建议' }}
            </el-button>
          </el-form-item>
        </el-form>
        <p class="review-hint">把发布平台后台的数据填进来，AI 会生成复盘与下一轮迭代建议（对应五维能力中的「数据分析」）。</p>

        <template v-if="analysisReport">
          <div class="report-card">
            <div class="report-head">
              <span class="report-title">📊 复盘报告</span>
              <UsageChip :usage="analyzeUsage" />
            </div>
            <p class="report-summary">{{ analysisReport.summary }}</p>
            <p v-for="(m, i) in analysisReport.metrics_read || []" :key="'m' + i" class="report-line">📈 {{ m }}</p>
            <p v-for="(h, i) in analysisReport.highlights || []" :key="'h' + i" class="report-line ok">✓ {{ h }}</p>
            <p v-for="(iss, i) in analysisReport.issues || []" :key="'i' + i" class="report-line warn">△ {{ iss }}</p>
            <p class="report-verdict">结论：<b>{{ analysisReport.verdict }}</b></p>
          </div>
        </template>

        <template v-if="optimizePlan">
          <div class="report-card">
            <div class="report-head">
              <span class="report-title">🎯 下一轮迭代建议</span>
              <UsageChip :usage="optimizeUsage" />
            </div>
            <div v-for="(sug, i) in optimizePlan.suggestions || []" :key="'s' + i" class="sug-row">
              <el-tag size="small" :type="sug.priority === '高' ? 'danger' : sug.priority === '低' ? 'info' : 'warning'" class="sug-pri">{{ sug.priority }}</el-tag>
              <div class="sug-body">
                <b class="sug-area">{{ sug.area }}</b>
                <span>{{ sug.action }}</span>
                <small v-if="sug.expected">预期：{{ sug.expected }}</small>
              </div>
            </div>
            <p v-if="(optimizePlan.next_topics || []).length" class="report-line">🎬 下一部剧选题：{{ optimizePlan.next_topics.join("；") }}</p>
            <p v-if="(optimizePlan.learning_goals || []).length" class="report-line">🎓 建议补强：{{ optimizePlan.learning_goals.join("、") }}</p>
          </div>
        </template>
      </div>

      <el-divider content-position="left">AI 使用声明</el-divider>
      <el-form :model="declareForm" label-width="120px" class="declare-form">
        <el-form-item label="使用的智能体">
          <el-checkbox-group v-model="declareForm.agents_used">
            <el-checkbox label="script" border>剧本</el-checkbox>
            <el-checkbox label="storyboard" border>分镜</el-checkbox>
            <el-checkbox label="tts" border>配音</el-checkbox>
            <el-checkbox label="compose" border>合成</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="人工修改比例">
          <el-slider v-model="declareForm.human_edit_ratio" :min="0" :max="1" :step="0.05" show-input :format-tooltip="(v) => `${Math.round(v * 100)}%`" style="max-width: 320px" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="declareForm.note" type="textarea" :rows="2" maxlength="200" placeholder="说明人工介入的内容" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" :loading="declaring" @click="onDeclare">保存声明</el-button>
          <span v-if="declared" class="declared-tip">已保存</span>
        </el-form-item>
      </el-form>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { createPublishParams, fetchFileBlob, generateWork, invokeAgent, submitAiDeclare } from '../../../api/index.js'
import { useTaskPoll } from '../../../composables/useTaskPoll.js'

import AssetCard from '../../../components/AssetCard.vue'
import UsageChip from '../../../components/UsageChip.vue'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  storyboardWork: { type: Object, default: null },
  audioWork: { type: Object, default: null },
  scriptWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated', 'refresh'])

const saving = ref(false)
const declaring = ref(false)
const declared = ref(false)
const publishGenerating = ref(false)
const publishParams = ref(null)
const publishUsage = ref(null)

// 数据复盘（analyze → optimize 闭环）
const reviewForm = ref({
  platform: 'TikTok',
  stats: { views: 0, likes: 0, comments: 0, shares: 0, completion_rate: 0, avg_watch_seconds: 0 }
})
const reviewRatePct = ref(0)
const analysisReport = ref(null)
const analyzeUsage = ref(null)
const analyzeLoading = ref(false)
const optimizePlan = ref(null)
const optimizeUsage = ref(null)
const optimizeLoading = ref(false)

async function runAnalyze() {
  analyzeLoading.value = true
  try {
    const meta = props.work.meta_json || {}
    const data = await invokeAgent('analyze', {
      title: props.work.title.replace(/-成片$/, ''),
      platform: reviewForm.value.platform,
      target_market: (props.scriptWork && props.scriptWork.meta_json && props.scriptWork.meta_json.target_market) || '北美',
      duration_seconds: Math.round(((meta.duration_ms || 0) / 1000) * 10) / 10,
      stats: { ...reviewForm.value.stats, completion_rate: Math.round(reviewRatePct.value) / 100 }
    })
    analysisReport.value = data.result
    analyzeUsage.value = data.usage || null
    ElMessage.success('复盘报告已生成')
  } catch (error) {
    ElMessage.error(error.message || '复盘生成失败')
  } finally {
    analyzeLoading.value = false
  }
}

async function runOptimize() {
  optimizeLoading.value = true
  try {
    const data = await invokeAgent('optimize', {
      title: props.work.title.replace(/-成片$/, ''),
      target_market: (props.scriptWork && props.scriptWork.meta_json && props.scriptWork.meta_json.target_market) || '北美',
      analysis: analysisReport.value
    })
    optimizePlan.value = data.result
    optimizeUsage.value = data.usage || null
    ElMessage.success('优化建议已生成')
  } catch (error) {
    ElMessage.error(error.message || '建议生成失败')
  } finally {
    optimizeLoading.value = false
  }
}
const { status, slow, error: pollError, start, stop } = useTaskPoll()

const declareForm = ref({
  agents_used: ['script', 'storyboard', 'tts', 'compose'],
  human_edit_ratio: 0.3,
  note: ''
})

const canCreate = computed(() => props.storyboardWork && props.audioWork)
const polling = computed(() => status.value === 'running')
const pollPercent = computed(() => (status.value === 'success' ? 100 : 60))
const meta = computed(() => (props.work && props.work.meta_json) || {})
const videoAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => asset.kind === 'video')
})

async function loadPublishParams() {
  publishParams.value = null
  const assets = (props.detail && props.detail.assets) || []
  const asset = assets.filter((item) => item.kind === 'publish_params').pop()
  if (!asset) return
  try {
    const blob = await fetchFileBlob(asset.url)
    publishParams.value = JSON.parse(await blob.text())
  } catch {
    publishParams.value = null
  }
}

async function onGeneratePublish() {
  publishGenerating.value = true
  try {
    const payload = {}
    if (props.scriptWork) {
      payload.source_work_id = props.scriptWork.id
    }
    const data = await createPublishParams(props.work.id, payload)
    publishParams.value = data.result
    publishUsage.value = data.usage || null
    ElMessage.success('发布参数已生成')
    emit('refresh')
  } catch (error) {
    ElMessage.error(error.message || '生成失败')
  } finally {
    publishGenerating.value = false
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择复制')
  }
}

// 平台头像配色（按名称稳定取色）
const AVATAR_COLORS = ['#409eff', '#7c3aed', '#e6a23c', '#67c23a', '#f56c6c', '#13c2c2']
function avatarColor(name) {
  const sum = [...(name || '')].reduce((acc, ch) => acc + ch.charCodeAt(0), 0)
  return AVATAR_COLORS[sum % AVATAR_COLORS.length]
}

async function onGenerate() {
  saving.value = true
  try {
    const data = await generateWork(props.work.id, {
      storyboard_work_id: props.storyboardWork.id,
      audio_work_id: props.audioWork.id
    })
    emit('generated', data)
    if (data.session_id && data.async) {
      start(
        data.session_id,
        () => {
          emit('refresh')
        },
        3000
      )
    }
  } finally {
    saving.value = false
  }
}

async function onDeclare() {
  declaring.value = true
  try {
    await submitAiDeclare(props.work.id, { ...declareForm.value })
    declared.value = true
    ElMessage.success('AI 使用声明已保存')
  } catch (error) {
    ElMessage.error(error.message || '保存失败')
  } finally {
    declaring.value = false
  }
}

onBeforeUnmount(stop)
onMounted(loadPublishParams)
watch(() => [props.work && props.work.id, props.work && props.work.status], loadPublishParams)
</script>

<style scoped>
.step-panel {
  padding: 4px 0 8px;
}
.el-alert {
  margin-bottom: 12px;
}
.asset-list {
  margin: 12px 0;
}
.publish-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.publish-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.platform-row {
  margin-top: 4px;
}
.platform-card {
  margin-bottom: 10px;
}
.platform-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.platform-name {
  font-weight: 500;
  font-size: 13px;
}
.p-title {
  margin: 0 0 6px;
  font-weight: 500;
  font-size: 13px;
}
.p-caption {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.p-meta {
  margin: 0 0 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.p-note {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.checklist {
  margin: 4px 0 0;
  padding-left: 18px;
  font-size: 12px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.declare-form {
  max-width: 560px;
}
.declared-tip {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-color-success);
}

/* ---------- 视频预览墙（历史版本网格） ---------- */
.video-wall {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.wall-item {
  position: relative;
  min-width: 0;
}
.wall-badge {
  position: absolute;
  top: -8px;
  right: 10px;
  z-index: 2;
  font-size: 10px;
  line-height: 1;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--el-color-success);
  color: #fff;
  box-shadow: 0 2px 6px rgba(103, 194, 58, 0.4);
}
.wall-badge.old {
  background: var(--el-text-color-placeholder);
  box-shadow: none;
}
@media (max-width: 900px) {
  .video-wall {
    grid-template-columns: 1fr;
  }
}

/* ---------- 数据复盘 ---------- */
.review-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.review-form .el-form-item {
  margin-bottom: 6px;
}
.review-hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--el-text-color-secondary);
}
.report-card {
  border: 0.5px solid var(--el-border-color-lighter);
  border-radius: 10px;
  padding: 14px 16px;
  background: var(--el-fill-color-lighter);
}
.report-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.report-title {
  font-size: 13px;
  font-weight: 700;
}
.report-summary {
  margin: 0 0 8px;
  font-size: 13px;
  line-height: 1.7;
}
.report-line {
  margin: 5px 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}
.report-line.ok {
  color: var(--el-color-success);
}
.report-line.warn {
  color: var(--el-color-warning);
}
.report-verdict {
  margin: 10px 0 0;
  font-size: 13px;
  font-weight: 600;
}
.sug-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 7px 0;
  border-bottom: 0.5px dashed var(--el-border-color-lighter);
}
.sug-pri {
  flex-shrink: 0;
  margin-top: 1px;
}
.sug-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 12.5px;
  line-height: 1.6;
}
.sug-area {
  font-size: 12px;
}
.sug-body small {
  color: var(--el-text-color-secondary);
}
</style>
