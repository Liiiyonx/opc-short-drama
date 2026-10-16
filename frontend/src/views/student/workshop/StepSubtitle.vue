<template>
  <section class="step-panel">
    <template v-if="!work">
      <el-empty description="还没有字幕作品">
        <el-button type="primary" @click="emit('create')">创建字幕作品</el-button>
      </el-empty>
    </template>

    <template v-else-if="work.status !== 'ready'">
      <el-alert type="info" :closable="false" show-icon title="字幕来自配音时间轴" description="点击生成将从配音作品复制 SRT；下载校对后可回传修订版，系统自动比对与 AI 原版的差异度。" />
      <el-button type="primary" :loading="saving" @click="onGenerate">生成字幕</el-button>
    </template>

    <template v-else>
      <el-alert type="success" :closable="false" show-icon title="字幕已生成" description="下载 SRT 校对后，在下方提交修订版：系统将自动计算与 AI 原版的差异度，作为「AI 辅助而非替代」的过程证据。" />
      <div class="asset-list">
        <AssetCard v-for="asset in srtAssets" :key="asset.id" :asset="asset" />
      </div>

      <el-divider content-position="left">人工校轴（初终稿比对）</el-divider>
      <div class="revision-box">
        <el-alert
          v-if="measuredRatio !== null"
          type="warning"
          :closable="false"
          show-icon
          :title="`最近一次校轴实测修改度：${(measuredRatio * 100).toFixed(1)}%`"
          description="该数值由系统比对学生修订版与 AI 原版自动计算，教师批改页可见。"
        />
        <el-button size="small" @click="revising = !revising">{{ revising ? '收起' : '提交校对版' }}</el-button>
        <template v-if="revising">
          <div class="upload-row">
            <input ref="fileInput" type="file" accept=".srt,.txt" style="display: none" @change="onFilePicked" />
            <el-button size="small" @click="fileInput.click()">选择本地 .srt 文件</el-button>
            <span class="hint">或直接在下方粘贴完整 SRT 内容</span>
          </div>
          <el-input
            v-model="revisedText"
            type="textarea"
            :rows="6"
            placeholder="粘贴校对后的完整 SRT 内容（保留时间轴格式）"
          />
          <div class="submit-row">
            <el-button type="primary" size="small" :loading="submitting" :disabled="!revisedText.trim()" @click="onSubmitRevision">
              提交修订并计算差异度
            </el-button>
            <span v-if="revisionResult" class="result-tip">
              实测修改度 {{ (revisionResult.measured_edit_ratio * 100).toFixed(1) }}%（相似度 {{ (revisionResult.similarity * 100).toFixed(1) }}%）
            </span>
          </div>
        </template>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { generateWork, submitRevision } from '../../../api/index.js'

import AssetCard from '../../../components/AssetCard.vue'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  audioWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated', 'refresh'])

const saving = ref(false)
const revising = ref(false)
const submitting = ref(false)
const revisedText = ref('')
const revisionResult = ref(null)
const fileInput = ref(null)

const srtAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => asset.kind === 'srt')
})

const measuredRatio = computed(() => {
  const declare = (props.work && props.work.ai_declare_json) || {}
  const value = declare.measured_edit_ratio
  return value === undefined || value === null ? null : value
})

function onFilePicked(event) {
  const file = event.target.files && event.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    revisedText.value = String(reader.result || '')
  }
  reader.readAsText(file, 'utf-8')
  event.target.value = ''
}

async function onGenerate() {
  saving.value = true
  try {
    const data = await generateWork(props.work.id, { audio_work_id: props.audioWork.id })
    emit('generated', data)
  } finally {
    saving.value = false
  }
}

async function onSubmitRevision() {
  submitting.value = true
  try {
    const data = await submitRevision(props.work.id, { kind: 'srt', content: revisedText.value })
    revisionResult.value = data
    ElMessage.success(`修订已保存：实测修改度 ${(data.measured_edit_ratio * 100).toFixed(1)}%`)
    emit('refresh')
  } catch (error) {
    ElMessage.error(error.message || '提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.step-panel {
  padding: 4px 0 8px;
}
.el-alert {
  margin-bottom: 12px;
}
.asset-list {
  margin-top: 12px;
}
.revision-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 640px;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.submit-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.result-tip {
  font-size: 12px;
  color: var(--el-color-success);
}
</style>
