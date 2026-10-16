import { ref } from 'vue'

import { getTask } from '../api/index.js'

/**
 * 异步任务轮询：task_id 即 agent session id。
 * status: idle | running | success | failed
 *
 * 加固策略：
 * - slow：超过 slowAfterMs（默认 90s）仍未完成 → UI 可提示「处理时间较长」；
 * - 超过 maxMs（默认 10 分钟）停止轮询，判超时失败并给出「检查 worker」提示，
 *   避免 worker 未启动时前端无限静默轮询；
 * - 网络类错误仅计一次失败（fetch 错误），不会无限重试。
 */
export function useTaskPoll() {
  const status = ref('idle')
  const error = ref('')
  const result = ref(null)
  const slow = ref(false)
  let timer = null

  async function pollOnce(taskId) {
    const data = await getTask(taskId)
    if (data.status === 'success') {
      status.value = 'success'
      result.value = data.result
      return true
    }
    if (data.status === 'failed') {
      status.value = 'failed'
      error.value = data.error || '任务执行失败'
      return true
    }
    return false
  }

  async function start(taskId, onDone, interval = 2000, options = {}) {
    const { maxMs = 10 * 60 * 1000, slowAfterMs = 90 * 1000 } = options
    const startedAt = Date.now()
    status.value = 'running'
    error.value = ''
    result.value = null
    slow.value = false
    const loop = async () => {
      if (Date.now() - startedAt > maxMs) {
        stop()
        status.value = 'failed'
        slow.value = true
        error.value =
          '等待超时：任务可能仍在后台处理，也可能是后台 worker 未启动。' +
          '请确认 worker 运行后刷新本页查看最新状态。'
        if (onDone) {
          onDone(null, error.value)
        }
        return
      }
      if (!slow.value && Date.now() - startedAt > slowAfterMs) {
        slow.value = true
      }
      try {
        const finished = await pollOnce(taskId)
        if (finished) {
          if (onDone) {
            onDone(status.value === 'success' ? result.value : null, error.value)
          }
          return
        }
      } catch (err) {
        status.value = 'failed'
        error.value = err.message || '任务查询失败'
        if (onDone) {
          onDone(null, error.value)
        }
        return
      }
      timer = setTimeout(loop, interval)
    }
    loop()
  }

  function stop() {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  function reset() {
    stop()
    status.value = 'idle'
    error.value = ''
    result.value = null
    slow.value = false
  }

  return { status, slow, error, result, start, stop, reset }
}
