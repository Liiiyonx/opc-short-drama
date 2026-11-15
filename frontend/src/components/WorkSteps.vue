<template>
  <nav class="steps-nav" aria-label="创作步骤导航">
    <!-- 总进度 -->
    <div class="steps-progress">
      <div class="progress-caption">
        <span class="done-count">
          已完成 <b>{{ doneCount }}</b> / {{ steps.length }} 步
        </span>
        <span v-if="generatingStep" class="generating-hint">
          <i class="spin-dot"></i>「{{ generatingStep.title }}」生成中…
        </span>
      </div>
      <div class="progress-bar" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100">
        <div class="progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>

    <!-- 步骤轨道 -->
    <ol class="steps-track">
      <li
        v-for="(step, index) in steps"
        :key="step.key"
        class="step-item"
        :class="`is-${step.status}`"
        :aria-current="step.status === 'current' ? 'step' : undefined"
        @click="emit('select', step)"
      >
        <!-- 连接线（首步无） -->
        <span
          v-if="index > 0"
          class="step-connector"
          :class="{ done: steps[index - 1].status === 'success' }"
          aria-hidden="true"
        ></span>

        <!-- 状态节点 -->
        <span class="step-node">
          <template v-if="step.status === 'success'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
          </template>
          <template v-else-if="step.status === 'generating'">
            <svg class="spinning" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.2-8.56" /></svg>
          </template>
          <template v-else-if="step.status === 'locked'">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg>
          </template>
          <template v-else>
            <span v-html="TYPE_ICONS[step.key]"></span>
          </template>
          <i v-if="step.status === 'current'" class="current-halo" aria-hidden="true"></i>
        </span>

        <!-- 文案 -->
        <div class="step-meta">
          <div class="step-title-line">
            <span class="step-title">{{ step.title }}</span>
            <span v-if="step.optional" class="step-optional">可选</span>
          </div>
          <div class="step-desc">{{ step.desc }}</div>
          <div class="step-state">{{ STATE_LABELS[step.status] }}</div>
        </div>
      </li>
    </ol>
  </nav>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  steps: { type: Array, required: true }
})

const emit = defineEmits(['select'])

const STATE_LABELS = {
  success: '已完成',
  generating: '生成中',
  current: '进行中',
  wait: '待处理',
  locked: '未解锁'
}

// 各步骤类型图标（Feather 线条风，继承 currentColor）
const TYPE_ICONS = {
  script:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>',
  storyboard:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/></svg>',
  translate:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
  audio:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/></svg>',
  subtitle:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><line x1="6" y1="16" x2="12" y2="16"/><line x1="14" y1="16" x2="18" y2="16"/><line x1="6" y1="12" x2="9" y2="12"/></svg>',
  video:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>'
}

// 完成数：成功步骤 + 被跳过的可选步骤（可选未创建时状态为 wait，不计为未完成）
const doneCount = computed(
  () => props.steps.filter((s) => s.status === 'success' || (s.optional && s.status === 'wait')).length
)

const generatingStep = computed(() => props.steps.find((s) => s.status === 'generating'))

const progressPercent = computed(() =>
  Math.min(100, Math.round((doneCount.value / props.steps.length) * 100))
)
</script>

<style scoped>
.steps-nav {
  margin: 18px 0 24px;
  background: var(--el-bg-color);
  border: 0.5px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 16px 20px 6px;
}

/* ---------- 总进度 ---------- */

.steps-progress {
  margin-bottom: 18px;
}

.progress-caption {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.done-count b {
  color: var(--el-color-success);
  font-size: 15px;
  padding: 0 1px;
}

.generating-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--el-color-primary);
}

.spin-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid var(--el-color-primary-light-8);
  border-top-color: var(--el-color-primary);
  animation: rotate 0.9s linear infinite;
}

.progress-bar {
  height: 6px;
  border-radius: 3px;
  background: #eef0f4;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  background: var(--opc-gradient);
  transition: width 0.5s ease;
}

/* ---------- 步骤轨道 ---------- */

.steps-track {
  display: flex;
  list-style: none;
  margin: 0;
  padding: 0 0 14px;
  overflow-x: auto;
}

.step-item {
  position: relative;
  flex: 1 1 0;
  min-width: 118px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  cursor: pointer;
  padding: 0 4px;
}

.step-item:first-child .step-connector {
  display: none;
}

.step-connector {
  position: absolute;
  top: 21px;
  left: calc(-50% + 26px);
  width: calc(100% - 52px);
  height: 2px;
  background: #e4e7ed;
  transition: background 0.3s ease;
}

.step-connector.done {
  background: var(--el-color-success);
}

/* ---------- 状态节点 ---------- */

.step-node {
  position: relative;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  z-index: 1;
}

.step-node svg {
  width: 20px;
  height: 20px;
}

.step-item:hover .step-node {
  transform: translateY(-2px);
}

/* 已完成：实心绿 + 白勾 */
.is-success .step-node {
  background: var(--el-color-success);
  color: #fff;
  box-shadow: 0 4px 12px rgba(103, 194, 58, 0.35);
}

/* 生成中：主色环 + 旋转弧 */
.is-generating .step-node {
  background: var(--el-bg-color);
  border: 2px solid var(--el-color-primary);
  color: var(--el-color-primary);
  box-shadow: 0 0 0 5px var(--el-color-primary-light-9);
}

.spinning {
  animation: rotate 0.9s linear infinite;
}

/* 当前步骤：品牌渐变 + 呼吸光环 */
.is-current .step-node {
  background: var(--opc-gradient);
  color: #fff;
  box-shadow: 0 4px 14px rgba(64, 158, 255, 0.4);
}

.current-halo {
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 2px solid var(--el-color-primary-light-7);
  animation: halo 1.8s ease-out infinite;
  pointer-events: none;
}

/* 待处理：白底灰边 */
.is-wait .step-node {
  background: var(--el-bg-color);
  border: 2px solid var(--el-border-color);
  color: var(--el-text-color-placeholder);
}

.is-wait:hover .step-node {
  border-color: var(--el-color-primary-light-5);
  color: var(--el-color-primary);
}

/* 未解锁：虚线框 + 锁 */
.is-locked .step-node {
  background: var(--el-fill-color-lighter);
  border: 2px dashed var(--el-border-color);
  color: var(--el-text-color-placeholder);
}

/* ---------- 文案 ---------- */

.step-meta {
  margin-top: 8px;
}

.step-title-line {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}

.step-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.is-current .step-title {
  color: var(--el-color-primary);
}

.is-locked .step-title {
  color: var(--el-text-color-placeholder);
}

.step-optional {
  font-size: 10px;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 4px;
  background: var(--el-color-info-light-9);
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.step-desc {
  margin-top: 3px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 130px;
}

.is-locked .step-desc {
  color: var(--el-text-color-placeholder);
}

.step-state {
  margin-top: 5px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
}

.is-success .step-state {
  color: var(--el-color-success);
}

.is-generating .step-state,
.is-current .step-state {
  color: var(--el-color-primary);
}

@keyframes rotate {
  to {
    transform: rotate(360deg);
  }
}

@keyframes halo {
  0% {
    transform: scale(0.9);
    opacity: 0.9;
  }
  100% {
    transform: scale(1.35);
    opacity: 0;
  }
}
</style>
