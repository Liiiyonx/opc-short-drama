<template>
  <section class="step-panel">
    <template v-if="!work">
      <el-empty description="还没有分镜作品">
        <el-button type="primary" @click="emit('create')">创建分镜作品</el-button>
      </el-empty>
    </template>

    <template v-else-if="work.status !== 'ready'">
      <el-form label-width="96px" class="gen-form">
        <el-form-item label="选择集数">
          <el-select v-model="episode" style="width: 160px">
            <el-option v-for="n in episodeCount" :key="n" :label="`第 ${n} 集`" :value="n" />
          </el-select>
        </el-form-item>
        <el-form-item label="风格提示">
          <el-input v-model="styleHint" placeholder="如：写实/动漫（选填）" maxlength="20" style="width: 240px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onGenerate">生成分镜</el-button>
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <div class="result-head">
        <el-alert type="success" :closable="false" show-icon :title="`分镜已生成：共 ${shots.length} 个镜头`" />
        <el-button text type="primary" @click="regenerating = !regenerating">{{ regenerating ? '收起' : '换一集重生成' }}</el-button>
      </div>
      <el-form v-if="regenerating" label-width="96px" class="gen-form">
        <el-form-item label="选择集数">
          <el-select v-model="episode" style="width: 160px">
            <el-option v-for="n in episodeCount" :key="n" :label="`第 ${n} 集`" :value="n" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" :loading="saving" @click="onGenerate">重新生成</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="shots" size="small" border max-height="420">
        <el-table-column prop="shot_no" label="镜号" width="60" />
        <el-table-column prop="scene" label="场景" width="60" />
        <el-table-column prop="shot_size" label="景别" width="80" />
        <el-table-column prop="camera_move" label="运镜" width="80" />
        <el-table-column prop="dialogue" label="台词" min-width="140" show-overflow-tooltip />
        <el-table-column prop="duration_sec" label="时长(s)" width="70" />
        <el-table-column label="画面提示词" min-width="200">
          <template #default="{ row }">
            <span class="prompt">{{ row.visual_prompt }}</span>
            <el-button size="small" text type="primary" @click="copy(row.visual_prompt)">复制</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="asset-list">
        <AssetCard v-for="asset in jsonAssets" :key="asset.id" :asset="asset" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { fetchFileBlob, generateWork } from '../../../api/index.js'

import AssetCard from '../../../components/AssetCard.vue'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  scriptWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated'])

const episode = ref(1)
const styleHint = ref('')
const saving = ref(false)
const regenerating = ref(false)
const shots = ref([])

const episodeCount = computed(() => {
  const meta = (props.scriptWork && props.scriptWork.meta_json) || {}
  return meta.episodes || 1
})
const jsonAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => asset.kind === 'json')
})

async function loadShots() {
  const asset = jsonAssets.value[0]
  if (!asset) {
    shots.value = []
    return
  }
  try {
    const text = await (await fetchFileBlob(asset.url)).text()
    shots.value = JSON.parse(text).shots || []
  } catch {
    shots.value = []
  }
}

function copy(text) {
  navigator.clipboard.writeText(text).then(
    () => ElMessage.success('已复制'),
    () => ElMessage.warning('复制失败，请手动选择')
  )
}

async function onGenerate() {
  saving.value = true
  try {
    const payload = {
      source_work_id: props.scriptWork.id,
      episode: episode.value
    }
    if (styleHint.value) {
      payload.style_hint = styleHint.value
    }
    const data = await generateWork(props.work.id, payload)
    emit('generated', data)
  } finally {
    saving.value = false
  }
}

watch(() => props.detail, loadShots, { immediate: false })
onMounted(loadShots)
</script>

<style scoped>
.step-panel {
  padding: 4px 0 8px;
}
.gen-form {
  max-width: 520px;
}
.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.result-head .el-alert {
  flex: 1;
}
.prompt {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.asset-list {
  margin-top: 12px;
}
</style>
