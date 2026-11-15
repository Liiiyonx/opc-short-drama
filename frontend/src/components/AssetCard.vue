<template>
  <div class="asset-card" :class="`k-${asset.kind}`">
    <div class="asset-head">
      <span class="asset-icon" v-html="meta.icon" aria-hidden="true"></span>
      <div class="asset-id">
        <span class="asset-name" :title="filename">{{ filename }}</span>
        <span class="asset-sub">{{ [meta.label, sizeText, durationText].filter(Boolean).join(' · ') }}</span>
      </div>
      <el-button size="small" text type="primary" @click="download">下载</el-button>
    </div>

    <div v-loading="loading" class="asset-body">
      <!-- 视频：圆角深底播放器 -->
      <video
        v-if="asset.kind === 'video' && objectUrl"
        :src="objectUrl"
        controls
        preload="metadata"
        class="media-video"
      ></video>

      <!-- 音频：内嵌播放器 -->
      <audio
        v-else-if="isAudioKind && objectUrl"
        :src="objectUrl"
        controls
        preload="metadata"
        class="media-audio"
      ></audio>

      <!-- 图片：缩略图 -->
      <img v-else-if="asset.kind === 'image' && objectUrl" :src="objectUrl" class="media-img" alt="资产图片" />

      <!-- SRT/文本：等宽预览 -->
      <pre v-else-if="isPlainText && text" class="plain-text">{{ text }}</pre>

      <!-- JSON：默认折叠（结构化数据已在上方可视化，原始文本按需展开） -->
      <el-collapse v-else-if="asset.kind === 'json'" v-model="jsonOpen" class="json-collapse">
        <el-collapse-item name="raw" title="原始 JSON">
          <pre v-if="text" class="plain-text json-raw">{{ text }}</pre>
          <div v-else class="json-loading">展开时加载…</div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { downloadFile, fetchFileBlob } from '../api/index.js'

const props = defineProps({
  asset: { type: Object, required: true }
})

// 类型元数据：标签 / 图标（Feather 线条风，继承芯片文字色）
const KIND_META = {
  json: {
    label: 'JSON',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
  },
  srt: {
    label: '字幕',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="16" x2="11" y2="16"/><line x1="13" y1="16" x2="18" y2="16"/><line x1="6" y1="12" x2="9" y2="12"/></svg>'
  },
  text: {
    label: '文本',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
  },
  image: {
    label: '图片',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
  },
  audio: {
    label: '音频',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/></svg>'
  },
  audio_merged: {
    label: '合并音轨',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/></svg>'
  },
  video: {
    label: '成片',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>'
  }
}

const FALLBACK_META = { label: '文件', icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>' }

const loading = ref(false)
const text = ref('')
const objectUrl = ref('')
const jsonOpen = ref([])

const meta = computed(() => KIND_META[props.asset.kind] || FALLBACK_META)
const isAudioKind = computed(() => ['audio', 'audio_merged'].includes(props.asset.kind))
const isPlainText = computed(() => ['text', 'srt'].includes(props.asset.kind))
const filename = computed(() => {
  const key = props.asset.storage_key || ''
  return key.split('/').pop() || key
})
const sizeText = computed(() => {
  const size = props.asset.size
  if (!size) return ''
  if (size >= 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(size / 1024))} KB`
})
const durationText = computed(() => {
  const ms = props.asset.duration_ms
  return ms ? `${(ms / 1000).toFixed(1)}s` : ''
})

async function loadText() {
  try {
    text.value = await (await fetchFileBlob(props.asset.url)).text()
  } catch (error) {
    ElMessage.error(`产物加载失败：${error.message}`)
  }
}

async function loadMedia() {
  try {
    const blob = await fetchFileBlob(props.asset.url)
    objectUrl.value = URL.createObjectURL(blob)
  } catch (error) {
    ElMessage.error(`产物加载失败：${error.message}`)
  }
}

function download() {
  downloadFile(props.asset.url, filename.value).catch((error) => {
    ElMessage.error(`下载失败：${error.message}`)
  })
}

onMounted(() => {
  loading.value = true
  const job = props.asset.kind === 'json'
    ? Promise.resolve() // JSON 懒加载：展开时再取
    : isPlainText.value
      ? loadText()
      : loadMedia()
  job.finally(() => {
    loading.value = false
  })
})

// JSON 折叠面板展开时才加载原始文本
watch(jsonOpen, (open) => {
  if (open.length && !text.value) loadText()
})
</script>

<style scoped>
.asset-card {
  border: 0.5px solid var(--el-border-color-lighter);
  border-radius: 10px;
  margin-bottom: 12px;
  overflow: hidden;
  background: var(--el-bg-color);
}
.asset-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  background: var(--el-fill-color-light);
}
.asset-icon {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.asset-icon :deep(svg) {
  width: 15px;
  height: 15px;
}
/* 类型配色芯片 */
.k-json .asset-icon {
  background: rgba(124, 58, 237, 0.12);
  color: #7c3aed;
}
.k-srt .asset-icon,
.k-text .asset-icon {
  background: rgba(64, 158, 255, 0.12);
  color: #409eff;
}
.k-image .asset-icon {
  background: rgba(230, 162, 60, 0.15);
  color: #e6a23c;
}
.k-audio .asset-icon,
.k-audio_merged .asset-icon {
  background: rgba(103, 194, 58, 0.15);
  color: #67c23a;
}
.k-video .asset-icon {
  background: rgba(245, 108, 108, 0.15);
  color: #f56c6c;
}
.asset-id {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.asset-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-sub {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.asset-body {
  padding: 12px;
}
.media-video {
  display: block;
  /* 竖屏 9:16 限高（一屏内看完），横屏限宽；两者自适应 */
  max-width: min(100%, 560px);
  max-height: 540px;
  width: auto;
  border-radius: 10px;
  background: #000;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
}
.media-audio {
  display: block;
  width: 100%;
  max-width: 480px;
}
.media-img {
  max-width: 260px;
  max-height: 300px;
  border-radius: 8px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}
.plain-text {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
}
.json-collapse {
  border-top: none;
  border-bottom: none;
}
.json-collapse :deep(.el-collapse-item__header) {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  height: 34px;
  border-bottom: none;
  background: transparent;
}
.json-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}
.json-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}
.json-raw {
  max-height: 260px;
}
.json-loading {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
