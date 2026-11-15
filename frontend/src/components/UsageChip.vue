<template>
  <span v-if="hasData" class="usage-chip" :title="tooltip">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z" />
    </svg>
    <span class="u-tokens">{{ totalTokens.toLocaleString() }} tokens</span>
    <span class="u-sep">·</span>
    <span class="u-cost">¥{{ costText }}</span>
    <span class="u-sep">·</span>
    <span class="u-duration">{{ durationText }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

/**
 * 成本透明芯片（参考 Langfuse 的 per-request 用量展示）：
 * 每次智能体调用的 tokens / 估算成本 / 耗时。tokens 为 0（如 ffmpeg 合成）时不渲染。
 */
const props = defineProps({
  usage: { type: Object, default: null }
})

const hasData = computed(() => {
  const u = props.usage
  return !!u && (Number(u.prompt_tokens || 0) + Number(u.completion_tokens || 0)) > 0
})

const totalTokens = computed(() =>
  Number(props.usage?.prompt_tokens || 0) + Number(props.usage?.completion_tokens || 0)
)

const costText = computed(() => {
  const cost = Number(props.usage?.cost_est || 0)
  return cost > 0 ? cost.toFixed(4) : '0'
})

const durationText = computed(() => {
  const ms = Number(props.usage?.duration_ms || 0)
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
})

const tooltip = computed(() => {
  const u = props.usage || {}
  const parts = []
  if (u.model) parts.push(`模型 ${u.model}`)
  if (u.prompt_tokens) parts.push(`输入 ${u.prompt_tokens} tokens`)
  if (u.completion_tokens) parts.push(`输出 ${u.completion_tokens} tokens`)
  parts.push('成本为按模型单价的估算值')
  return parts.join(' · ')
})
</script>

<style scoped>
.usage-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  line-height: 1;
  padding: 4px 9px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 0.5px solid var(--el-border-color-lighter);
  color: var(--el-text-color-secondary);
  cursor: default;
}
.usage-chip svg {
  width: 11px;
  height: 11px;
  color: var(--el-color-warning);
}
.u-tokens {
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}
.u-cost {
  color: var(--el-color-success);
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-weight: 600;
}
.u-sep {
  color: var(--el-border-color);
}
</style>
