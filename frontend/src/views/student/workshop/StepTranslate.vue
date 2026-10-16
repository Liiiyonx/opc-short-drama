<template>
  <section class="step-panel">
    <template v-if="!work">
      <el-empty description="还没有翻译作品（可选步骤：台词跨文化本地化）">
        <el-button type="primary" @click="emit('create')">创建翻译作品</el-button>
      </el-empty>
    </template>

    <template v-else-if="work.status !== 'ready'">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="翻译本地化：台词跨文化改写 + 文化禁忌标记"
        description="由商务英语能力维度主导：保留戏剧张力、俚语文化等价替换、逐行合规扫描。目标语言默认按剧本市场推断，可覆盖。"
      />
      <el-form label-width="110px" class="gen-form">
        <el-form-item label="目标语言">
          <el-select v-model="locale" style="width: 220px">
            <el-option v-for="item in LOCALES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="onGenerate">生成翻译</el-button>
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <el-alert
        type="success"
        :closable="false"
        show-icon
        :title="`翻译完成：${meta.lines || 0} 行台词 → ${localeLabel}${meta.notes ? `，${meta.notes} 条替换说明` : ''}${meta.flags ? `，${meta.flags} 条合规提示` : ''}`"
      />

      <el-table v-if="product.lines && product.lines.length" :data="product.lines" size="small" class="loc-table">
        <el-table-column prop="line_id" label="#" width="52" />
        <el-table-column label="原文" min-width="200">
          <template #default="{ row }">{{ sourceText(row.line_id) }}</template>
        </el-table-column>
        <el-table-column prop="translated" label="本地化" min-width="220" />
      </el-table>

      <template v-if="product.notes && product.notes.length">
        <el-divider content-position="left">跨文化替换说明</el-divider>
        <el-alert v-for="(note, idx) in product.notes" :key="idx" type="info" :closable="false" :title="note" class="note-item" />
      </template>

      <template v-if="product.compliance_flags && product.compliance_flags.length">
        <el-divider content-position="left">合规标记</el-divider>
        <el-table :data="product.compliance_flags" size="small">
          <el-table-column prop="line_id" label="行" width="52" />
          <el-table-column prop="issue" label="问题" min-width="180" />
          <el-table-column prop="suggestion" label="替代建议" min-width="180" />
          <el-table-column label="级别" width="90">
            <template #default="{ row }">
              <el-tag :type="severityType(row.severity)" size="small">{{ row.severity || 'medium' }}</el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <el-button text type="primary" class="retry-btn" @click="regenerating = !regenerating">
        {{ regenerating ? '收起' : '重新翻译' }}
      </el-button>
      <el-form v-if="regenerating" label-width="110px" class="gen-form">
        <el-form-item label="目标语言">
          <el-select v-model="locale" style="width: 220px">
            <el-option v-for="item in LOCALES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" :loading="saving" @click="onGenerate">重新生成</el-button>
        </el-form-item>
      </el-form>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchFileBlob, generateWork, getWork } from '../../../api/index.js'

const props = defineProps({
  work: { type: Object, default: null },
  detail: { type: Object, default: null },
  storyboardWork: { type: Object, default: null }
})
const emit = defineEmits(['create', 'generated'])

const LOCALES = [
  { label: '英语（美国）', value: 'en-US' },
  { label: '日语', value: 'ja-JP' },
  { label: '韩语', value: 'ko-KR' },
  { label: '泰语', value: 'th-TH' },
  { label: '越南语', value: 'vi-VN' },
  { label: '印尼语', value: 'id-ID' },
  { label: '阿拉伯语（埃及）', value: 'ar-EG' },
  { label: '西班牙语（墨西哥）', value: 'es-MX' }
]

const saving = ref(false)
const regenerating = ref(false)
const locale = ref('en-US')
const product = ref({})
const sourceLines = ref([])

const meta = computed(() => (props.work && props.work.meta_json) || {})
const localeLabel = computed(() => {
  const found = LOCALES.find((item) => item.value === (meta.value.target_locale || locale.value))
  return found ? found.label : meta.value.target_locale || '英语（美国）'
})

function severityType(severity) {
  if (severity === 'high') return 'danger'
  if (severity === 'low') return 'info'
  return 'warning'
}

function sourceText(lineId) {
  const found = sourceLines.value.find((item) => item.line_id === lineId)
  return found ? found.text : '—'
}

async function loadProduct() {
  product.value = {}
  if (!props.work || props.work.status !== 'ready') return
  const assets = (props.detail && props.detail.assets) || []
  const jsonAsset = assets.filter((asset) => asset.kind === 'json').pop()
  if (!jsonAsset) return
  try {
    const blob = await fetchFileBlob(jsonAsset.url)
    product.value = JSON.parse(await blob.text())
  } catch {
    product.value = {}
  }
}

async function loadSources() {
  // 原文展示：从分镜作品 json 产物提取（line_id=shot_no）
  if (!props.storyboardWork) return
  try {
    const detail = await getWork(props.storyboardWork.id)
    const jsonAsset = (detail.assets || []).filter((asset) => asset.kind === 'json').pop()
    if (!jsonAsset) return
    const blob = await fetchFileBlob(jsonAsset.url)
    const data = JSON.parse(await blob.text())
    sourceLines.value = (data.shots || [])
      .filter((shot) => shot.dialogue)
      .map((shot) => ({ line_id: shot.shot_no, text: shot.dialogue }))
  } catch {
    sourceLines.value = []
  }
}

async function onGenerate() {
  saving.value = true
  try {
    const payload = { storyboard_work_id: props.storyboardWork.id }
    if (locale.value) {
      payload.target_locale = locale.value
    }
    const data = await generateWork(props.work.id, payload)
    emit('generated', data)
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadProduct()
  loadSources()
})
watch(() => [props.work && props.work.id, props.work && props.work.status], () => {
  loadProduct()
  loadSources()
})
</script>

<style scoped>
.step-panel {
  padding: 4px 0 8px;
}
.el-alert {
  margin-bottom: 12px;
}
.gen-form {
  max-width: 540px;
}
.loc-table {
  margin: 12px 0;
}
.note-item {
  margin-bottom: 8px;
}
.retry-btn {
  margin-top: 8px;
}
</style>
