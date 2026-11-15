<template>
  <section class="step-panel">
    <template v-if="!work">
      <el-empty description="还没有配音作品">
        <el-button type="primary" @click="emit('create')">创建配音作品</el-button>
      </el-empty>
    </template>

    <template v-else-if="work.status !== 'ready'">
      <el-alert
        v-if="work.status === 'failed'"
        type="error"
        :closable="false"
        show-icon
        title="上次生成失败，可直接重试；连续失败请检查后台 worker 与 TTS 服务"
      />
      <el-alert
        v-else-if="work.status === 'generating' && !polling"
        type="warning"
        :closable="false"
        show-icon
        title="任务正在后台处理中"
      >
        <template #default>
          <span>稍后刷新查看结果；若长时间无进展，请确认 worker 已启动。</span>
          <el-button size="small" text type="primary" @click="emit('refresh')">刷新状态</el-button>
        </template>
      </el-alert>
      <el-form label-width="96px" class="gen-form">
        <el-form-item label="语言">
          <el-select v-model="lang" style="width: 200px">
            <el-option label="自动（跟随剧本市场）" value="auto" />
            <el-option v-for="item in LANGS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <span class="hint">{{ autoHint }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving || polling" @click="onGenerate">
            {{ polling ? '配音合成中…' : '生成配音' }}
          </el-button>
        </el-form-item>
      </el-form>
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
      <el-alert type="success" :closable="false" show-icon :title="`配音完成：${meta.lines || 0} 条台词，总时长 ${((meta.total_duration_ms || 0) / 1000).toFixed(1)} 秒`" />
      <UsageChip :usage="pollUsage" class="usage-row" />
      <div class="asset-list">
        <AssetCard v-for="asset in mediaAssets" :key="asset.id" :asset="asset" />
      </div>
      <el-button text type="primary" @click="regenerating = !regenerating">{{ regenerating ? '收起' : '重新配音' }}</el-button>
      <el-form v-if="regenerating" label-width="96px" class="gen-form">
        <el-form-item label="语言">
          <el-select v-model="lang" style="width: 200px">
            <el-option label="自动（跟随剧本市场）" value="auto" />
            <el-option v-for="item in LANGS" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
          <span class="hint">{{ autoHint }}</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" :loading="saving || polling" @click="onGenerate">重新生成</el-button>
        </el-form-item>
      </el-form>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { generateWork } from '../../../api/index.js'
import { useTaskPoll } from '../../../composables/useTaskPoll.js'

import AssetCard from '../../../components/AssetCard.vue'
import UsageChip from '../../../components/UsageChip.vue'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  storyboardWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated', 'refresh'])

// 语言默认「自动」：不传 lang，由后端沿 分镜→剧本 回溯目标市场推断
// （修复记录：原默认 zh-CN，北美短剧忘切语言会配出中文音色）
const LANGS = [
  { label: '中文（普通话）', value: 'zh-CN' },
  { label: '英语（美国）', value: 'en-US' },
  { label: '日语', value: 'ja-JP' },
  { label: '韩语', value: 'ko-KR' },
  { label: '西班牙语（墨西哥）', value: 'es-MX' },
  { label: '阿拉伯语（埃及）', value: 'ar-EG' },
  { label: '泰语', value: 'th-TH' },
  { label: '越南语', value: 'vi-VN' },
  { label: '印尼语', value: 'id-ID' },
  { label: '法语', value: 'fr-FR' },
  { label: '葡萄牙语（巴西）', value: 'pt-BR' },
  { label: '马来语', value: 'ms-MY' }
]
const lang = ref('auto')
const saving = ref(false)
const regenerating = ref(false)
const { status, slow, error: pollError, usage: pollUsage, start, stop } = useTaskPoll()

const polling = computed(() => status.value === 'running')
const pollPercent = computed(() => (status.value === 'success' ? 100 : 65))
const meta = computed(() => (props.work && props.work.meta_json) || {})
const mediaAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => ['audio', 'audio_merged', 'srt'].includes(asset.kind))
})
const autoHint = computed(() => {
  if (lang.value !== 'auto') return '已手动覆盖语言'
  const market = props.storyboardWork && props.storyboardWork.meta_json && props.storyboardWork.meta_json.target_market
  return market ? `跟随剧本目标市场「${market}」自动推断` : '按剧本目标市场自动推断'
})

async function onGenerate() {
  saving.value = true
  try {
    const payload = { storyboard_work_id: props.storyboardWork.id }
    if (lang.value && lang.value !== 'auto') {
      payload.lang = lang.value
    }
    const data = await generateWork(props.work.id, payload)
    emit('generated', data)
    if (data.session_id && data.async) {
      start(
        data.session_id,
        () => {
          emit('refresh')
        },
        2000
      )
    }  } finally {
    saving.value = false
  }
}

onBeforeUnmount(stop)
</script>

<style scoped>
.usage-row {
  margin: 0 0 10px;
}

.step-panel {
  padding: 4px 0 8px;
}
.gen-form {
  max-width: 520px;
}
.hint {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.asset-list {
  margin: 12px 0;
}
</style>
