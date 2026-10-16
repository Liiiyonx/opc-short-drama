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
import { computed, onBeforeUnmount, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { generateWork, submitAiDeclare } from '../../../api/index.js'
import { useTaskPoll } from '../../../composables/useTaskPoll.js'

import AssetCard from '../../../components/AssetCard.vue'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  storyboardWork: { type: Object, default: null },
  audioWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated', 'refresh'])

const saving = ref(false)
const declaring = ref(false)
const declared = ref(false)
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
.declare-form {
  max-width: 560px;
}
.declared-tip {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-color-success);
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
