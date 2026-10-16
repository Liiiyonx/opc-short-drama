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
      <div class="asset-list">
        <AssetCard v-for="asset in videoAssets" :key="asset.id" :asset="asset" />
      </div>

      <el-divider content-position="left">发布参数包</el-divider>
      <div class="publish-box">
        <div class="publish-head">
          <el-button size="small" type="primary" :loading="publishGenerating" @click="onGeneratePublish">
            {{ publishParams ? '重新生成发布参数' : '生成发布参数' }}
          </el-button>
          <span class="hint">按目标市场生成各平台标题 / 文案 / 话题标签 / 发布时间建议</span>
        </div>
        <template v-if="publishParams">
          <el-row :gutter="10" class="platform-row">
            <el-col v-for="platform in publishParams.platforms || []" :key="platform.name" :span="8">
              <el-card shadow="never" class="platform-card">
                <template #header>
                  <div class="platform-head">
                    <span class="platform-name">{{ platform.name }}</span>
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
                <p class="p-meta">{{ (platform.hashtags || []).join(' ') }}</p>
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
import { createPublishParams, fetchFileBlob, generateWork, submitAiDeclare } from '../../../api/index.js'
import { useTaskPoll } from '../../../composables/useTaskPoll.js'

import AssetCard from '../../../components/AssetCard.vue'

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
</style>
