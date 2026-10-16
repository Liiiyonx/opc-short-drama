import { ref } from 'vue'

import { getTask } from '../api/index.js'

/**
 * 异步任务轮询：task_id 即 agent session id。
 * status: idle | running | success | failed
 */
export function useTaskPoll() {
  const status = ref('idle')
  const error = ref('')
  const result = ref(null)
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

  async function start(taskId, onDone, interval = 2000) {
    status.value = 'running'
    error.value = ''
    result.value = null
    const loop = async () => {
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
  }

  return { status, error, result, start, stop, reset }
}
