<template>
  <div class="asset-card">
    <div class="asset-head">
      <el-tag size="small" :type="tagType">{{ kindLabel }}</el-tag>
      <span class="asset-name">{{ filename }}</span>
      <el-button size="small" text type="primary" @click="download">下载</el-button>
    </div>
    <div v-loading="loading" class="asset-body">
      <pre v-if="isText" class="asset-text">{{ text }}</pre>
      <img v-else-if="asset.kind === 'image'" :src="objectUrl" class="asset-img" />
      <audio
        v-else-if="asset.kind === 'audio' || asset.kind === 'audio_merged'"
        :src="objectUrl"
        controls
        class="asset-media"
      />
      <video v-else-if="asset.kind === 'video'" :src="objectUrl" controls class="asset-media" />
      <span v-else class="asset-unknown">该类型暂不支持在线预览，请下载查看</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { downloadFile, fetchFileBlob } from '../api/index.js'

const props = defineProps({
  asset: { type: Object, required: true }
})

const KIND_LABELS = {
  text: '文本',
  json: '结构化产物',
  srt: '字幕',
  image: '图片',
  audio: '音频',
  audio_merged: '合并音轨',
  video: '成片'
}

const loading = ref(false)
const text = ref('')
const objectUrl = ref('')

const kindLabel = computed(() => KIND_LABELS[props.asset.kind] || props.asset.kind)
const isText = computed(() => ['text', 'json', 'srt'].includes(props.asset.kind))
const tagType = computed(() => {
  if (props.asset.kind === 'video') return 'success'
  if (props.asset.kind === 'image') return 'warning'
  return 'info'
})
const filename = computed(() => {
  const key = props.asset.storage_key || ''
  return key.split('/').pop() || key
})

async function load() {
  loading.value = true
  try {
    const blob = await fetchFileBlob(props.asset.url)
    if (isText.value) {
      text.value = await blob.text()
    } else {
      objectUrl.value = URL.createObjectURL(blob)
    }
  } catch (error) {
    ElMessage.error(`产物加载失败：${error.message}`)
  } finally {
    loading.value = false
  }
}

function download() {
  downloadFile(props.asset.url, filename.value).catch((error) => {
    ElMessage.error(`下载失败：${error.message}`)
  })
}

onMounted(load)
</script>

<style scoped>
.asset-card {
  border: 0.5px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  margin-bottom: 12px;
  overflow: hidden;
}
.asset-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
}
.asset-name {
  flex: 1;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.asset-body {
  padding: 12px;
}
.asset-text {
  margin: 0;
  max-height: 260px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.asset-img {
  max-width: 240px;
  max-height: 240px;
  border-radius: 4px;
}
.asset-media {
  width: 100%;
  max-width: 420px;
}
.asset-unknown {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
</style>
