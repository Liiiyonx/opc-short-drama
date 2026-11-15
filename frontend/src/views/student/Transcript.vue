<template>
  <div class="page transcript">
    <div class="head no-print">
      <div>
        <h3 class="title">学习档案</h3>
        <span class="sub">可打印 / 导出 PDF（浏览器打印对话框中选择「另存为 PDF」）</span>
      </div>
      <div>
        <el-button type="primary" @click="print">打印 / 导出 PDF</el-button>
        <el-button @click="router.push('/student')">返回工作台</el-button>
      </div>
    </div>

    <div class="doc" v-loading="loading">
      <header class="doc-head">
        <h2>学习档案</h2>
        <p>{{ profile.username }} · {{ profile.major || '—' }} · {{ profile.grade || '—' }} 级</p>
        <p class="doc-sub">OPC 短剧出海平台 · 生成于 {{ today }}</p>
      </header>

      <section class="doc-sec">
        <h4>一、五维能力</h4>
        <div v-for="item in abilityLatest" :key="item.dimension" class="ab-line">
          <span class="ab-name">{{ item.dimension }}</span>
          <div class="ab-track">
            <div class="ab-fill" :style="{ width: item.score + '%' }"></div>
          </div>
          <span class="ab-score">{{ item.score }}</span>
        </div>
        <p v-if="!abilityLatest.length" class="doc-muted">暂无批改产出的能力评分。</p>
        <p class="doc-muted">共 {{ reviewCount }} 次作品获得教师批改。</p>
      </section>

      <section class="doc-sec">
        <h4>二、作品清单（{{ works.length }}）</h4>
        <table class="doc-table">
          <thead>
            <tr><th>标题</th><th>类型</th><th>状态</th><th>版本</th><th>创建时间</th></tr>
          </thead>
          <tbody>
            <tr v-for="w in works" :key="w.id">
              <td>{{ w.title }}</td>
              <td>{{ TYPE_LABELS[w.type] || w.type }}</td>
              <td>{{ STATUS_LABELS[w.status] || w.status }}</td>
              <td>v{{ w.version }}</td>
              <td>{{ formatTime(w.created_at) }}</td>
            </tr>
            <tr v-if="!works.length"><td colspan="5" class="doc-muted">暂无作品</td></tr>
          </tbody>
        </table>
      </section>

      <section class="doc-sec">
        <h4>三、AI 使用说明</h4>
        <p class="doc-muted">
          本档案所列作品在创作过程中使用了平台六大智能体（剧本生成 / 分镜 / 翻译本地化 /
          配音 / 成片合成 / 发布参数）辅助完成，每部作品的智能体使用记录与人工修改比例
          已随作品存档，教师可在批改视图中核查，体现「AI 辅助而非替代」的过程留痕。
        </p>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { getStudentAbility, listWorks } from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'

const TYPE_LABELS = {
  script: '剧本', storyboard: '分镜', translate: '翻译本地化',
  audio: '配音', subtitle: '字幕', video: '成片'
}
const STATUS_LABELS = { draft: '草稿', generating: '生成中', ready: '已完成', failed: '失败' }
const DIMENSIONS = ['内容创作', '跨文化沟通', '电商运营', 'AI工具应用', '数据分析']

const router = useRouter()
const userStore = useUserStore()
const loading = ref(false)
const abilityLatest = ref([])
const reviewCount = ref(0)
const works = ref([])

const profile = computed(() => userStore.profile || { username: '', major: '', grade: '' })
const today = new Date().toISOString().slice(0, 10)

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function print() {
  window.print()
}

onMounted(async () => {
  loading.value = true
  try {
    if (!userStore.profile) await userStore.fetchMe()
    const me = userStore.profile
    if (!me) return
    const [ability, worksData] = await Promise.all([
      getStudentAbility(me.id).catch(() => null),
      listWorks({ page: 1, page_size: 50 }).catch(() => null)
    ])
    if (ability) {
      abilityLatest.value = DIMENSIONS.filter((d) => ability.latest[d] !== undefined).map((d) => ({
        dimension: d,
        score: Math.round(ability.latest[d])
      }))
      reviewCount.value = ability.review_count || 0
    }
    if (worksData) works.value = worksData.items || []
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.title {
  margin: 0 0 4px;
  font-size: 20px;
  font-weight: 600;
}
.sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.doc {
  max-width: 800px;
  margin: 0 auto;
  background: var(--el-bg-color);
  border: 0.5px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 32px 40px;
}
.doc-head {
  text-align: center;
  border-bottom: 2px solid var(--el-border-color);
  padding-bottom: 14px;
  margin-bottom: 20px;
}
.doc-head h2 {
  margin: 0 0 6px;
  letter-spacing: 4px;
}
.doc-head p {
  margin: 0 0 2px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.doc-sub {
  font-size: 11.5px !important;
  color: var(--el-text-color-placeholder) !important;
}
.doc-sec {
  margin-bottom: 22px;
}
.doc-sec h4 {
  margin: 0 0 10px;
  font-size: 14px;
  border-left: 3px solid var(--el-color-primary);
  padding-left: 8px;
}
.ab-line {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 7px;
}
.ab-name {
  width: 84px;
  font-size: 12.5px;
  flex-shrink: 0;
}
.ab-track {
  flex: 1;
  height: 10px;
  border-radius: 5px;
  background: var(--el-fill-color-light);
  overflow: hidden;
}
.ab-fill {
  height: 100%;
  border-radius: 5px;
  background: var(--opc-gradient);
}
.ab-score {
  width: 34px;
  text-align: right;
  font-weight: 600;
  font-size: 12.5px;
}
.doc-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.doc-table th,
.doc-table td {
  border: 0.5px solid var(--el-border-color-lighter);
  padding: 7px 10px;
  text-align: left;
}
.doc-table th {
  background: var(--el-fill-color-light);
  font-weight: 600;
}
.doc-muted {
  font-size: 12.5px;
  color: var(--el-text-color-secondary);
  line-height: 1.7;
}

/* 打印：隐藏导航与按钮，文档铺满 */
@media print {
  .no-print {
    display: none !important;
  }
  .page {
    padding: 0 !important;
    max-width: none !important;
  }
  .doc {
    border: none;
    border-radius: 0;
    padding: 0;
  }
  .ab-fill {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }
}
</style>
