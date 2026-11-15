<template>
  <div class="workshop" v-loading="loading">
    <div class="workshop-head">
      <div>
        <h3 class="title">{{ chain.base || '创作工坊' }}</h3>
        <span class="sub">AI 创作流水线：剧本 → 分镜 → 翻译本地化（可选）→ 配音 → 字幕 → 成片，每步产物入库、可单步重跑</span>
      </div>
      <div>
        <el-button text type="primary" @click="openRunDrawer">运行记录</el-button>
        <el-button v-if="chain.works.script" text type="primary" @click="newDialog = true">新建剧集</el-button>
        <el-button @click="router.push('/student')">返回工作台</el-button>
      </div>

    <!-- 流水线运行记录（Dify 式可观测） -->
    <el-drawer v-model="runDrawer" title="流水线运行记录" size="520px">
      <div v-loading="runLoading">
        <div v-if="runSummary" class="run-summary">
          共 {{ runLogs.length }} 次调用 · 成功 {{ runSummary.success }} · 失败 {{ runSummary.failed }}
        </div>
        <el-empty v-if="!runLoading && !runLogs.length" description="本剧集还没有智能体调用记录" :image-size="70" />
        <el-collapse v-model="runOpen" class="run-collapse">
          <el-collapse-item v-for="log in runLogs" :key="log.id" :name="log.id">
            <template #title>
              <span class="run-title">
                <span class="run-agent">{{ AGENT_LABELS[log.agent_type] || log.agent_type }}</span>
                <el-tag size="small" :type="runStatusType(log.status)">{{ runStatusLabel(log.status) }}</el-tag>
                <span class="run-time">{{ formatRunTime(log.created_at) }}</span>
              </span>
            </template>
            <div class="run-body">
              <div v-if="log.error" class="run-error">⚠ {{ log.error }}</div>
              <div class="run-io-title">输入</div>
              <pre class="run-io">{{ compactJson(log.input_json) }}</pre>
              <div class="run-io-title">输出</div>
              <pre class="run-io">{{ log.status === "success" ? compactJson(log.output_json) : "—" }}</pre>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-drawer>
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
      <WorkSteps :steps="stepList" @select="scrollToStep" />

      <div class="panel-block" id="panel-script" :class="stepStateOf('script').cls">
        <h4 class="panel-title">
          1 · AI 剧本
          <span class="panel-state" :class="stepStateOf('script').cls">{{ stepStateOf('script').label }}</span>
        </h4>
        <StepScript :work="chain.works.script" :detail="details.script" @generated="onGenerated('script', $event)" />
      </div>

      <div class="panel-block" id="panel-storyboard" :class="stepStateOf('storyboard').cls">
        <h4 class="panel-title">
          2 · AI 分镜
          <span class="panel-state" :class="stepStateOf('storyboard').cls">{{ stepStateOf('storyboard').label }}</span>
        </h4>
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

      <div class="panel-block" id="panel-translate" :class="stepStateOf('translate').cls">
        <h4 class="panel-title">
          3 · 翻译本地化
          <span class="panel-state" :class="stepStateOf('translate').cls">{{ stepStateOf('translate').label }}</span>
        </h4>
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

      <div class="panel-block" id="panel-audio" :class="stepStateOf('audio').cls">
        <h4 class="panel-title">
          4 · AI 配音
          <span class="panel-state" :class="stepStateOf('audio').cls">{{ stepStateOf('audio').label }}</span>
        </h4>
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

      <div class="panel-block" id="panel-subtitle" :class="stepStateOf('subtitle').cls">
        <h4 class="panel-title">
          5 · 字幕
          <span class="panel-state" :class="stepStateOf('subtitle').cls">{{ stepStateOf('subtitle').label }}</span>
        </h4>
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

      <div class="panel-block" id="panel-video" :class="stepStateOf('video').cls">
        <h4 class="panel-title">
          6 · 成片
          <span class="panel-state" :class="stepStateOf('video').cls">{{ stepStateOf('video').label }}</span>
        </h4>
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
import { listAgentSessions } from '../../api/index.js'

const AGENT_LABELS = {
  script: '剧本生成',
  storyboard: '分镜',
  translate: '翻译本地化',
  tts: '配音',
  compose: '成片合成',
  publish: '发布参数'
}

// 流水线运行记录抽屉
const runDrawer = ref(false)
const runLoading = ref(false)
const runLogs = ref([])
const runOpen = ref([])

const runSummary = computed(() => {
  if (!runLogs.value.length) return null
  return {
    success: runLogs.value.filter((l) => l.status === 'success').length,
    failed: runLogs.value.filter((l) => l.status === 'failed').length
  }
})

async function openRunDrawer() {
  runDrawer.value = true
  runLoading.value = true
  runOpen.value = []
  try {
    const data = await listAgentSessions({ page_size: 100 })
    const chainIds = new Set(
      Object.values(chain.value.works)
        .filter((w) => w && w.id)
        .map((w) => w.id)
    )
    runLogs.value = (data.items || [])
      .filter((s) => chainIds.has(s.work_id))
      .sort((a, b) => b.id - a.id)
  } finally {
    runLoading.value = false
  }
}

function runStatusLabel(status) {
  return { success: '成功', failed: '失败', running: '运行中' }[status] || status
}

function runStatusType(status) {
  return { success: 'success', failed: 'danger', running: 'primary' }[status] || 'info'
}

function formatRunTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(5, 16)
}

function compactJson(obj) {
  if (!obj) return '—'
  try {
    return JSON.stringify(obj, null, 1).slice(0, 2000)
  } catch {
    return '—'
  }
}

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

// 步骤解锁条件（与各面板渲染条件一一对应）
const PREREQ = {
  script: () => true,
  storyboard: () => chain.value.works.script?.status === 'ready',
  translate: () => chain.value.works.storyboard?.status === 'ready',
  audio: () => chain.value.works.storyboard?.status === 'ready',
  subtitle: () => chain.value.works.audio?.status === 'ready',
  video: () =>
    chain.value.works.storyboard?.status === 'ready' &&
    chain.value.works.audio?.status === 'ready'
}

const stepList = computed(() => {
  let currentAssigned = false
  return STEP_DEFS.map((def) => {
    const work = chain.value.works[def.key]
    const unlocked = PREREQ[def.key]()
    let status
    if (work && work.status === 'ready') {
      status = 'success'
    } else if (work && work.status === 'generating') {
      status = 'generating'
    } else if (!unlocked) {
      status = 'locked'
    } else if (!currentAssigned && (!def.optional || work)) {
      // 首个可行动步骤高亮为「进行中」；可选步骤未创建时不占当前位
      status = 'current'
      currentAssigned = true
    } else {
      status = 'wait'
    }
    return { ...def, status }
  })
})

const STEP_STATE_LABELS = {
  success: { label: '已完成', cls: 'is-success' },
  generating: { label: '生成中…', cls: 'is-generating' },
  current: { label: '进行中', cls: 'is-current' },
  wait: { label: '待处理', cls: 'is-wait' },
  locked: { label: '未解锁', cls: 'is-locked' }
}

function stepStateOf(key) {
  const step = stepList.value.find((item) => item.key === key)
  return STEP_STATE_LABELS[step ? step.status : 'wait']
}

function scrollToStep(step) {
  const el = document.getElementById(`panel-${step.key}`)
  if (!el) return
  // 手写缓动滚动：不依赖 CSS smooth scrollIntoView（部分 WebView 内核不支持）
  const headerOffset = 76
  const targetY = Math.max(
    0,
    window.scrollY + el.getBoundingClientRect().top - headerOffset
  )
  animateScrollTo(targetY)
  // 点击反馈：目标面板短暂高亮
  el.classList.remove('flash')
  void el.offsetWidth
  el.classList.add('flash')
  setTimeout(() => el.classList.remove('flash'), 1300)
}

function animateScrollTo(targetY, duration = 450) {
  const startY = window.scrollY
  const delta = targetY - startY
  if (Math.abs(delta) < 2) return
  const startTime = performance.now()
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3)
  let moved = false
  let finished = false
  function frame(now) {
    if (finished) return
    moved = true
    const t = Math.min(1, (now - startTime) / duration)
    window.scrollTo(0, startY + delta * easeOutCubic(t))
    if (t < 1) requestAnimationFrame(frame)
    else finished = true
  }
  requestAnimationFrame(frame)
  // 看门狗：环境节流 rAF（如后台 WebView）时 140ms 内无帧则直接落位
  setTimeout(() => {
    if (!moved && !finished) {
      finished = true
      window.scrollTo(0, targetY)
    }
  }, 140)
}

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
.panel-block {
  background: var(--el-bg-color);
  border: 0.5px solid var(--el-border-color);
  border-left: 3px solid transparent;
  border-radius: var(--el-border-radius-base);
  padding: 16px 20px;
  margin-bottom: 16px;
  scroll-margin-top: 76px; /* sticky 顶栏偏移，锚点滚动停在标题下方 */
  transition: border-color 0.3s ease, opacity 0.3s ease;
}
.panel-block.is-success {
  border-left-color: var(--el-color-success);
}
.panel-block.is-generating,
.panel-block.is-current {
  border-left-color: var(--el-color-primary);
}
.panel-block.is-locked {
  opacity: 0.75;
}
.panel-block.flash {
  animation: panel-flash 1.3s ease;
}
@keyframes panel-flash {
  0% {
    background: var(--el-color-primary-light-9);
  }
  100% {
    background: var(--el-bg-color);
  }
}
.panel-title {
  margin: 0 0 12px;
  font-weight: 600;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.panel-state {
  font-size: 11px;
  font-weight: 500;
  line-height: 1;
  padding: 4px 9px;
  border-radius: 10px;
  flex-shrink: 0;
}
.panel-state.is-success {
  color: var(--el-color-success);
  background: var(--el-color-success-light-9);
}
.panel-state.is-generating,
.panel-state.is-current {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.panel-state.is-wait {
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
}
.panel-state.is-locked {
  color: var(--el-text-color-placeholder);
  background: var(--el-fill-color-lighter);
}

/* ---------- 运行记录抽屉 ---------- */
.run-summary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-bottom: 10px;
}
.run-collapse {
  border-top: none;
}
.run-title {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-width: 0;
}
.run-agent {
  font-size: 12.5px;
  font-weight: 600;
}
.run-time {
  margin-left: auto;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}
.run-body {
  padding: 0 4px;
}
.run-error {
  font-size: 12px;
  color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
  border-radius: 6px;
  padding: 7px 10px;
  margin-bottom: 8px;
}
.run-io-title {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin: 8px 0 4px;
}
.run-io {
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 11px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  max-height: 180px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
