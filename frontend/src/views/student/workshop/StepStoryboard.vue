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
        <el-alert
          type="success"
          :closable="false"
          show-icon
          :title="`分镜已生成：共 ${shots.length} 个镜头 · 约 ${totalDuration} 秒`"
        />
        <UsageChip :usage="usage" />
        <div class="head-actions">
          <el-button text type="primary" @click="copyAllPrompts">复制全部提示词</el-button>
          <el-button text type="primary" @click="regenerating = !regenerating">{{ regenerating ? '收起' : '换一集重生成' }}</el-button>
        </div>
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

      <!-- 镜头卡片：按场景分组（对标分镜脚本的阅读习惯） -->
      <section v-for="group in sceneGroups" :key="group.scene" class="scene-group">
        <div class="scene-head">
          <span class="scene-name">场景 {{ group.scene }}</span>
          <span class="scene-meta">{{ group.list.length }} 镜 · 约 {{ group.duration }}s</span>
        </div>

        <article v-for="shot in group.list" :key="shot.shot_no" class="shot-card">
          <div class="shot-head">
            <span class="shot-no">{{ String(shot.shot_no ?? 0).padStart(2, '0') }}</span>
            <div class="shot-tags">
              <el-tag size="small" effect="plain">{{ shot.shot_size || '景别' }}</el-tag>
              <el-tag size="small" effect="plain">{{ shot.camera_move || '运镜' }}</el-tag>
              <el-tag size="small" effect="plain" type="info">{{ shot.duration_sec || 0 }}s</el-tag>
            </div>
            <el-button
              v-if="shot.dialogue"
              size="small"
              text
              type="primary"
              class="copy-btn"
              @click="copy(shot.dialogue)"
            >复制台词</el-button>
          </div>

          <p v-if="shot.dialogue" class="shot-dialogue">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M10 8v6a4 4 0 0 1-4 4H5a1 1 0 0 1 0-2h1a2 2 0 0 0 2-2H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1zm11 0v6a4 4 0 0 1-4 4h-1a1 1 0 0 1 0-2h1a2 2 0 0 0 2-2h-4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h5a1 1 0 0 1 1 1z"/></svg>
            <span>{{ shot.dialogue }}</span>
          </p>

          <div class="shot-prompt">
            <div class="prompt-label">
              画面提示词
              <el-button size="small" text type="primary" @click="copy(shot.visual_prompt || '')">复制</el-button>
            </div>
            <pre class="prompt-text">{{ shot.visual_prompt || '—' }}</pre>
          </div>
        </article>
      </section>

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
import UsageChip from '../../../components/UsageChip.vue'

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
const usage = ref(null)

const episodeCount = computed(() => {
  const meta = (props.scriptWork && props.scriptWork.meta_json) || {}
  return meta.episodes || 1
})
const jsonAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => asset.kind === 'json')
})
const totalDuration = computed(() =>
  shots.value.reduce((sum, shot) => sum + (shot.duration_sec || 0), 0)
)

// 按场景分组（保持镜头顺序），供卡片分区展示
const sceneGroups = computed(() => {
  const map = new Map()
  for (const shot of shots.value) {
    const key = shot.scene ?? 1
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(shot)
  }
  return [...map.entries()].map(([scene, list]) => ({
    scene,
    list,
    duration: list.reduce((sum, shot) => sum + (shot.duration_sec || 0), 0)
  }))
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

function copyAllPrompts() {
  const all = shots.value
    .map((shot) => `${String(shot.shot_no ?? 0).padStart(2, '0')}: ${shot.visual_prompt || ''}`)
    .join('\n')
  if (!all) {
    ElMessage.warning('暂无可复制的提示词')
    return
  }
  copy(all)
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
    usage.value = data.usage || null
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
.head-actions {
  flex-shrink: 0;
  display: flex;
}
.asset-list {
  margin-top: 12px;
}

/* ---------- 场景分组 ---------- */

.scene-group {
  margin-bottom: 18px;
}
.scene-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 6px 2px 8px;
}
.scene-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  padding-left: 8px;
  border-left: 3px solid var(--el-color-primary);
  line-height: 1.2;
}
.scene-meta {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* ---------- 镜头卡片 ---------- */

.shot-card {
  border: 0.5px solid var(--el-border-color-lighter);
  border-radius: 10px;
  background: var(--el-bg-color);
  padding: 12px 14px;
  margin-bottom: 10px;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}
.shot-card:hover {
  border-color: var(--el-color-primary-light-5);
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.1);
}
.shot-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.shot-no {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
  background: var(--opc-gradient);
  border-radius: 7px;
  padding: 3px 7px;
  line-height: 1.2;
  flex-shrink: 0;
}
.shot-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.copy-btn {
  margin-left: auto;
}
.shot-dialogue {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin: 10px 0 0;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
  font-size: 13px;
  line-height: 1.6;
  color: var(--el-text-color-primary);
}
.shot-dialogue svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
  margin-top: 3px;
  color: var(--el-color-primary-light-3);
}
.shot-prompt {
  margin-top: 10px;
}
.prompt-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.prompt-text {
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
  line-height: 1.65;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
  padding: 9px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
