<template>
  <div class="workshop" v-loading="loading">
    <div class="workshop-head">
      <div>
        <h3 class="title">{{ chain.base || '创作工坊' }}</h3>
        <span class="sub">AI 创作流水线：剧本 → 分镜 → 翻译本地化（可选）→ 配音 → 字幕 → 成片，每步产物入库、可单步重跑</span>
      </div>
      <div>
        <el-button v-if="chain.works.script" text type="primary" @click="newDialog = true">新建剧集</el-button>
        <el-button @click="router.push('/student')">返回工作台</el-button>
      </div>
    </div>

    <el-dialog v-model="newDialog" title="新建剧集" width="420px">
      <el-form label-width="72px">
        <el-form-item label="剧名">
          <el-input v-model="newTitle" placeholder="如：外卖箱里的秘密" maxlength="50" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :disabled="!newTitle.trim()" @click="createChain">创建并进入</el-button>
      </template>
    </el-dialog>

    <template v-if="chain.works.script">
      <WorkSteps :steps="stepList" :active-index="activeIndex" />

      <div class="panel-block">
        <h4 class="panel-title">1 · AI 剧本</h4>
        <StepScript :work="chain.works.script" :detail="details.script" @generated="onGenerated('script', $event)" />
      </div>

      <div class="panel-block">
        <h4 class="panel-title">2 · AI 分镜</h4>
        <StepStoryboard
          v-if="chain.works.script.status === 'ready'"
          :work="chain.works.storyboard"
          :detail="details.storyboard"
          :script-work="chain.works.script"
          @create="createStepWork('storyboard')"
          @generated="onGenerated('storyboard', $event)"
        />
        <el-empty v-else description="完成剧本后解锁分镜" :image-size="60" />
      </div>

      <div class="panel-block">
        <h4 class="panel-title">3 · 翻译本地化 <el-tag size="small" type="info">可选</el-tag></h4>
        <StepTranslate
          v-if="chain.works.storyboard && chain.works.storyboard.status === 'ready'"
          :work="chain.works.translate"
          :detail="details.translate"
          :storyboard-work="chain.works.storyboard"
          @create="createStepWork('translate')"
          @generated="onGenerated('translate', $event)"
        />
        <el-empty v-else description="完成分镜后解锁翻译本地化" :image-size="60" />
      </div>

      <div class="panel-block">
        <h4 class="panel-title">4 · AI 配音</h4>
        <StepAudio
          v-if="chain.works.storyboard && chain.works.storyboard.status === 'ready'"
          :work="chain.works.audio"
          :detail="details.audio"
          :storyboard-work="chain.works.storyboard"
          @create="createStepWork('audio')"
          @generated="onGenerated('audio', $event)"
          @refresh="refreshAll"
        />
        <el-empty v-else description="完成分镜后解锁配音" :image-size="60" />
      </div>

      <div class="panel-block">
        <h4 class="panel-title">5 · 字幕</h4>
        <StepSubtitle
          v-if="chain.works.audio && chain.works.audio.status === 'ready'"
          :work="chain.works.subtitle"
          :detail="details.subtitle"
          :audio-work="chain.works.audio"
          @create="createStepWork('subtitle')"
          @generated="onGenerated('subtitle', $event)"
          @refresh="refreshAll"
        />
        <el-empty v-else description="完成配音后解锁字幕" :image-size="60" />
      </div>

      <div class="panel-block">
        <h4 class="panel-title">6 · 成片</h4>
        <StepVideo
          v-if="chain.works.storyboard && chain.works.storyboard.status === 'ready' && chain.works.audio && chain.works.audio.status === 'ready'"
          :work="chain.works.video"
          :detail="details.video"
          :storyboard-work="chain.works.storyboard"
          :audio-work="chain.works.audio"
          :script-work="chain.works.script"
          @create="createStepWork('video')"
          @generated="onGenerated('video', $event)"
          @refresh="refreshAll"
        />
        <el-empty v-else description="完成分镜与配音后解锁成片" :image-size="60" />
      </div>
    </template>

    <el-empty v-else description="从工作台「新建剧集」开始，或在作品列表选择一部作品进入工坊">
      <el-button type="primary" @click="newDialog = true">新建剧集</el-button>
    </el-empty>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import WorkSteps from '../../components/WorkSteps.vue'
import StepScript from './workshop/StepScript.vue'
import StepStoryboard from './workshop/StepStoryboard.vue'
import StepTranslate from './workshop/StepTranslate.vue'
import StepAudio from './workshop/StepAudio.vue'
import StepSubtitle from './workshop/StepSubtitle.vue'
import StepVideo from './workshop/StepVideo.vue'
import { useWorkStore } from '../../stores/work.js'

const STEP_DEFS = [
  { key: 'script', title: 'AI 剧本', desc: '题材/市场 → 分集大纲' },
  { key: 'storyboard', title: 'AI 分镜', desc: '剧本 → 镜头列表' },
  { key: 'translate', title: '翻译本地化', desc: '台词 → 跨文化改写', optional: true },
  { key: 'audio', title: 'AI 配音', desc: '台词 → 多语种音频' },
  { key: 'subtitle', title: '字幕', desc: 'SRT 时间轴' },
  { key: 'video', title: '成片', desc: '烧字幕合成 MP4' }
]

const STEP_SUFFIX = {
  script: '',
  storyboard: '-分镜',
  translate: '-翻译',
  audio: '-配音',
  subtitle: '-字幕',
  video: '-成片'
}

const route = useRoute()
const router = useRouter()
const workStore = useWorkStore()

const loading = ref(false)
const newDialog = ref(false)
const newTitle = ref('')
const chain = ref({
  base: '',
  works: { script: null, storyboard: null, translate: null, audio: null, subtitle: null, video: null }
})
const details = ref({})

const stepList = computed(() =>
  STEP_DEFS.map((def) => {
    const work = chain.value.works[def.key]
    let status = 'wait'
    if (work) {
      if (work.status === 'ready') {
        status = 'success'
      } else if (work.status === 'generating') {
        status = 'process'
      } else {
        status = 'process'
      }
    }
    return { ...def, status }
  })
)

const activeIndex = computed(() => {
  const idx = STEP_DEFS.findIndex((def) => {
    // 可选步骤未创建时不阻塞进度条
    if (def.optional && !chain.value.works[def.key]) return false
    const work = chain.value.works[def.key]
    return !work || work.status !== 'ready'
  })
  return idx === -1 ? STEP_DEFS.length : idx
})

function stripSuffix(title) {
  for (const suffix of Object.values(STEP_SUFFIX)) {
    if (suffix && title.endsWith(suffix)) {
      return title.slice(0, -suffix.length)
    }
  }
  return title
}

function reconstruct() {
  const all = workStore.works
  for (const [type, suffix] of Object.entries(STEP_SUFFIX)) {
    const matches = all.filter(
      (work) => work.type === type && work.title === chain.value.base + suffix
    )
    chain.value.works[type] = matches.length
      ? matches.reduce((a, b) => (a.id > b.id ? a : b))
      : null
  }
}

async function loadDetails() {
  details.value = {}
  for (const [type, work] of Object.entries(chain.value.works)) {
    if (work) {
      const detail = await workStore.getDetail(work.id)
      details.value[type] = detail
      chain.value.works[type] = detail.work
    }
  }
}

async function init() {
  loading.value = true
  try {
    await workStore.loadWorks({ page: 1, page_size: 100 })
    const anchorId = route.params.workId
    if (anchorId) {
      const anchor = workStore.works.find((work) => work.id === Number(anchorId))
      if (anchor) {
        chain.value.base = stripSuffix(anchor.title)
      }
    }
    if (chain.value.base) {
      reconstruct()
      await loadDetails()
    }
  } finally {
    loading.value = false
  }
}

async function createChain() {
  const base = newTitle.value.trim()
  const work = await workStore.createWork({ title: base, type: 'script' })
  chain.value.base = base
  chain.value.works.script = work
  chain.value.works.storyboard = null
  chain.value.works.translate = null
  chain.value.works.audio = null
  chain.value.works.subtitle = null
  chain.value.works.video = null
  newDialog.value = false
  newTitle.value = ''
  await loadDetails()
}

async function createStepWork(type) {
  const work = await workStore.createWork({
    title: chain.value.base + STEP_SUFFIX[type],
    type
  })
  chain.value.works[type] = work
  await loadDetails()
}

function onGenerated(type, payload) {
  if (payload && payload.work) {
    chain.value.works[type] = payload.work
  }
  refreshAll()
}

async function refreshAll() {
  await loadDetails()
}

onMounted(init)
</script>

<style scoped>
.workshop {
  padding: 20px 24px 40px;
  max-width: 1080px;
  margin: 0 auto;
}
.workshop-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.title {
  margin: 0;
  font-weight: 500;
}
.sub {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.panel-block {
  background: var(--el-bg-color);
  border: 0.5px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  padding: 16px 20px;
  margin-bottom: 16px;
}
.panel-title {
  margin: 0 0 12px;
  font-weight: 500;
  font-size: 14px;
}
</style>
