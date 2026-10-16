<template>
  <section class="step-panel">
    <template v-if="work.status !== 'ready'">
      <el-form :model="form" label-width="96px" class="gen-form">
        <el-form-item label="题材">
          <el-select v-model="form.genre" placeholder="选择题材" filterable allow-create>
            <el-option v-for="item in GENRES" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标市场">
          <el-select v-model="form.target_market" placeholder="选择目标市场">
            <el-option v-for="item in MARKETS" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="集数">
          <el-input-number v-model="form.episodes" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="单集时长(分)">
          <el-input-number v-model="form.episode_minutes" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="风格">
          <el-input v-model="form.style" placeholder="如：逆袭/甜宠/悬疑（选填）" maxlength="20" />
        </el-form-item>
        <el-form-item label="锁定关键词">
          <el-select v-model="form.keywords" multiple filterable allow-create placeholder="输入后回车添加" style="width: 100%" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" :disabled="!canSubmit" @click="onGenerate">生成剧本</el-button>
        </el-form-item>
      </el-form>
    </template>

    <template v-else>
      <div class="result-head">
        <el-alert type="success" :closable="false" show-icon :title="`剧本已生成：${product.title || ''}`" :description="product.logline || ''" />
        <el-button text type="primary" @click="showForm = !showForm">{{ showForm ? '收起改写' : '多轮改写' }}</el-button>
      </div>
      <el-form v-if="showForm" :model="form" label-width="96px" class="gen-form">
        <el-form-item label="修改反馈">
          <el-input v-model="form.feedback" type="textarea" :rows="2" placeholder="描述希望调整的方向，如：第 2 集节奏太快、加强女主反转" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="small" :loading="saving" @click="onGenerate">按反馈重新生成</el-button>
        </el-form-item>
      </el-form>
      <el-collapse v-if="product.episodes && product.episodes.length">
        <el-collapse-item v-for="ep in product.episodes" :key="ep.ep" :title="`第 ${ep.ep} 集 · ${ep.title}`" :name="ep.ep">
          <p class="ep-outline">{{ ep.outline }}</p>
          <p v-for="(scene, idx) in ep.scenes" :key="idx" class="ep-scene">
            场景 {{ scene.scene }}｜{{ scene.location }}｜{{ (scene.characters || []).join('、') }}
            <br /><span class="dialogue">{{ (scene.dialogue || []).join(' / ') }}</span>
          </p>
        </el-collapse-item>
      </el-collapse>
      <div class="asset-list">
        <AssetCard v-for="asset in jsonAssets" :key="asset.id" :asset="asset" />
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { fetchFileBlob, generateWork } from '../../../api/index.js'

import AssetCard from '../../../components/AssetCard.vue'

const props = defineProps({
  work: { type: Object, required: true },
  detail: { type: Object, default: null }
})
const emit = defineEmits(['generated'])

const GENRES = ['逆袭', '甜宠', '悬疑', '战神', '豪门', '职场', '穿越', '家庭']
const MARKETS = ['北美', '东南亚', '日韩', '欧洲', '中东', '拉美']

const form = ref({
  genre: '',
  target_market: '北美',
  episodes: 20,
  episode_minutes: 2,
  style: '',
  keywords: [],
  feedback: ''
})
const saving = ref(false)
const showForm = ref(false)
const product = ref({})

const canSubmit = computed(() => form.value.genre && form.value.target_market)
const jsonAssets = computed(() => {
  const assets = (props.detail && props.detail.assets) || []
  return assets.filter((asset) => asset.kind === 'json')
})

async function loadProduct() {
  const asset = jsonAssets.value[0]
  if (!asset) {
    product.value = {}
    return
  }
  try {
    const text = await (await fetchFileBlob(asset.url)).text()
    product.value = JSON.parse(text)
    if (product.value.genre) {
      form.value.genre = product.value.genre
    }
  } catch {
    product.value = {}
  }
}

async function onGenerate() {
  saving.value = true
  try {
    const payload = { ...form.value }
    if (!payload.feedback) {
      delete payload.feedback
    }
    const data = await generateWork(props.work.id, payload)
    emit('generated', data)
  } finally {
    saving.value = false
  }
}

watch(() => props.detail, loadProduct, { immediate: false })
onMounted(loadProduct)
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
.ep-outline {
  margin: 0 0 8px;
  font-size: 13px;
}
.ep-scene {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.dialogue {
  color: var(--el-text-color-primary);
}
.asset-list {
  margin-top: 12px;
}
</style>
