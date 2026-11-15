<template>
  <div class="share-page">
    <header class="share-head">
      <span class="logo">
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M9 7.5 16.5 12 9 16.5z" fill="#fff" />
        </svg>
      </span>
      <div>
        <h1 class="alias">{{ data.alias }}</h1>
        <p class="meta">
          {{ data.major || '专业未填' }} · {{ data.grade || '' }} 级 · 短剧出海创作作品集
        </p>
      </div>
    </header>

    <div class="ability-strip" v-if="works.length">
      <span class="strip-label">累计完成作品</span>
      <b class="strip-num">{{ works.length }}</b>
      <span class="strip-label">部 · 覆盖</span>
      <b class="strip-num">{{ typeCount }}</b>
      <span class="strip-label">个创作环节</span>
    </div>

    <div class="works-grid">
      <div v-for="work in works" :key="work.title + work.version" class="work-card">
        <div class="work-top">
          <el-tag size="small" effect="dark" class="type-tag">{{ work.type_label }}</el-tag>
          <span class="work-version">v{{ work.version }}</span>
        </div>
        <h3 class="work-title">{{ work.title }}</h3>
        <p class="work-date">{{ formatTime(work.created_at) }}</p>
      </div>
    </div>

    <el-empty v-if="loaded && !works.length" description="该学生暂无已完成的作品" />

    <footer class="share-foot">
      本页面由 <b>OPC 短剧出海平台</b> 生成 · 脱敏视图（不含联系方式）· 意向合作请联系学院教师对接
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getPublicPortfolio } from '../api/index.js'

const route = useRoute()
const data = ref({ alias: '', major: '', grade: '', works: [] })
const loaded = ref(false)
const error = ref('')

const works = computed(() => data.value.works || [])
const typeCount = computed(() => new Set(works.value.map((w) => w.type)).size)

function formatTime(value) {
  if (!value) return ''
  return String(value).replace('T', ' ').slice(0, 10)
}

onMounted(async () => {
  try {
    data.value = await getPublicPortfolio(route.params.token)
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loaded.value = true
  }
})
</script>

<style scoped>
.share-page {
  min-height: 100vh;
  background:
    radial-gradient(900px 450px at 110% -10%, rgba(124, 58, 237, 0.1), transparent 55%),
    radial-gradient(900px 450px at -10% 110%, rgba(64, 158, 255, 0.1), transparent 55%),
    var(--el-bg-color-page);
  padding: 40px 24px 60px;
  max-width: 1080px;
  margin: 0 auto;
}
.share-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 22px;
}
.logo {
  width: 52px;
  height: 52px;
  border-radius: 14px;
  background: var(--opc-gradient);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.logo svg {
  width: 26px;
  height: 26px;
}
.alias {
  margin: 0 0 4px;
  font-size: 26px;
  font-weight: 700;
}
.meta {
  margin: 0;
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.ability-strip {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 14px 18px;
  border-radius: 12px;
  background: var(--opc-gradient-soft);
  margin-bottom: 22px;
}
.strip-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.strip-num {
  font-size: 20px;
  font-weight: 700;
  color: var(--el-color-primary);
}
.works-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.work-card {
  border: 0.5px solid var(--el-border-color-lighter);
  border-radius: 12px;
  padding: 14px 16px;
  background: var(--el-bg-color);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}
.work-card:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}
.work-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.type-tag {
  border: none;
  background: var(--opc-gradient);
}
.work-version {
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
}
.work-title {
  margin: 0 0 8px;
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.work-date {
  margin: 0;
  font-size: 11.5px;
  color: var(--el-text-color-placeholder);
}
.share-foot {
  margin-top: 40px;
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
@media (max-width: 760px) {
  .works-grid {
    grid-template-columns: 1fr;
  }
}
</style>
