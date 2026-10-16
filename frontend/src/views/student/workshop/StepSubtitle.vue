<template>
  <section class="step-panel">
    <template v-if="!work">
      <el-empty description="还没有字幕作品">
        <el-button type="primary" @click="emit('create')">创建字幕作品</el-button>
      </el-empty>
    </template>

    <template v-else-if="work.status !== 'ready'">
      <el-alert type="info" :closable="false" show-icon title="字幕来自配音时间轴" description="点击生成将从配音作品复制 SRT；下载后可由人工校轴，再作为文本资产上传（P1 支持在线校轴）。" />
      <el-button type="primary" :loading="saving" @click="onGenerate">生成字幕</el-button>
    </template>

    <template v-else>
      <el-alert type="success" :closable="false" show-icon title="字幕已生成" description="可下载 SRT 校对；校对后的版本可通过作品资产上传登记。" />
      <div class="asset-list">
        <AssetCard v-for="asset in srtAssets" :key="asset.id" :asset="asset" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { generateWork } from '../../../api/index.js'

import AssetCard from '../../../components/AssetCard.vue'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  audioWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated'])

const saving = ref(false)
const srtAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => asset.kind === 'srt')
})

async function onGenerate() {
  saving.value = true
  try {
    const data = await generateWork(props.work.id, { audio_work_id: props.audioWork.id })
    emit('generated', data)
  } finally {
    saving.value = false
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
</style>
