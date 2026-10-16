<template>
  <div class="page">
    <div class="head">
      <div>
        <h3 class="title">企业工作台</h3>
        <span class="sub">{{ companyName }} · 工单发布与成果遴选（P0 线下结算，平台仅存凭证）</span>
      </div>
      <div>
        <el-button type="primary" @click="openForm">发布工单</el-button>
        <el-button text @click="logout">退出登录</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <span>我的工单</span>
        <el-button size="small" text type="primary" @click="reload">刷新</el-button>
      </template>
      <el-table :data="orders" v-loading="loading" empty-text="还没有工单，点击「发布工单」开始">
        <el-table-column prop="title" label="工单标题" min-width="180" show-overflow-tooltip />
        <el-table-column label="预算" width="110">
          <template #default="{ row }">{{ (row.budget_cents / 100).toFixed(0) }} 元</template>
        </el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ STATUS_LABELS[row.status] || row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="openDetail(row)">详情 / 投标</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="formVisible" title="发布工单" width="600px">
      <el-form label-width="96px">
        <el-form-item label="工单标题">
          <el-input v-model="form.title" maxlength="80" placeholder="如：出海短剧《都市逆袭》定制需求" />
        </el-form-item>
        <el-form-item label="题材">
          <el-input v-model="form.genre" placeholder="如：逆袭 / 甜宠" style="width: 200px" />
        </el-form-item>
        <el-form-item label="目标市场">
          <el-select v-model="form.market" style="width: 200px">
            <el-option v-for="item in ['北美', '东南亚', '日韩', '欧洲', '中东', '拉美']" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="集数 / 语言">
          <el-input-number v-model="form.episodes" :min="1" :max="100" />
          <el-select v-model="form.lang" style="width: 150px; margin-left: 12px">
            <el-option label="en-US" value="en-US" />
            <el-option label="zh-CN" value="zh-CN" />
            <el-option label="ja-JP" value="ja-JP" />
          </el-select>
        </el-form-item>
        <el-form-item label="预算（元）">
          <el-input-number v-model="form.budgetYuan" :min="0" :step="500" />
        </el-form-item>
        <el-form-item label="交付要求">
          <el-input v-model="form.delivery" type="textarea" :rows="3" placeholder="交付格式、验收标准、时间要求" />
        </el-form-item>
        <el-form-item label="截止时间">
          <el-date-picker v-model="form.deadline" type="datetime" placeholder="可不设" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" title="发布后需教师审核通过才会出现在学生的工单大厅。" />
      <template #footer>
        <el-button type="primary" :loading="saving" :disabled="!form.title.trim()" @click="submitForm">提交审核</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" :title="current ? current.title : '工单详情'" size="640px">
      <template v-if="current">
        <el-descriptions :column="2" size="small" border>
          <el-descriptions-item label="状态">{{ STATUS_LABELS[current.status] || current.status }}</el-descriptions-item>
          <el-descriptions-item label="预算">{{ (current.budget_cents / 100).toFixed(0) }} 元</el-descriptions-item>
          <el-descriptions-item label="需求" :span="2">
            {{ formatRequirements(current.requirements_json) }}
          </el-descriptions-item>
          <el-descriptions-item v-if="current.verify_note" label="审核意见" :span="2">{{ current.verify_note }}</el-descriptions-item>
        </el-descriptions>

        <el-divider content-position="left">投标列表（{{ bids.length }}）</el-divider>
        <el-empty v-if="!bids.length" description="暂无投标" :image-size="60" />
        <div v-for="bid in bids" :key="bid.id" class="bid-card">
          <div class="bid-head">
            <b>{{ bid.bidder_name }}</b>
            <span class="bid-amount">报价 {{ (bid.amount_cents / 100).toFixed(0) }} 元</span>
            <el-tag size="small" :type="bid.status === 'won' ? 'success' : bid.status === 'lost' ? 'info' : 'warning'">
              {{ BID_LABELS[bid.status] || bid.status }}
            </el-tag>
            <el-button
              v-if="bid.status === 'active' && (current.status === 'bidding' || current.status === 'published')"
              size="small"
              type="primary"
              @click="doAward(bid)"
            >定标</el-button>
          </div>
          <p class="bid-proposal">{{ bid.proposal || '（未填写方案）' }}</p>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { awardOrder, createOrder, getOrder, listOrders } from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'

const STATUS_LABELS = {
  draft: '草稿 / 待修改',
  pending_review: '待审核',
  published: '已发布',
  bidding: '投标中',
  awarded: '已定标',
  closed: '已关闭',
  cancelled: '已取消'
}
const BID_LABELS = { active: '有效', won: '中标', lost: '未中', withdrawn: '撤回' }

const router = useRouter()
const userStore = useUserStore()

const orders = ref([])
const loading = ref(false)
const saving = ref(false)
const formVisible = ref(false)
const detailVisible = ref(false)
const current = ref(null)
const bids = ref([])
const form = ref({ title: '', genre: '', market: '北美', episodes: 6, lang: 'en-US', budgetYuan: 3000, delivery: '', deadline: null })

const companyName = computed(() => {
  const profile = userStore.profile && userStore.profile.profile
  return (profile && profile.company_name) || (userStore.profile ? userStore.profile.username : '')
})

function statusType(status) {
  if (status === 'published' || status === 'bidding') return 'success'
  if (status === 'awarded') return 'warning'
  if (status === 'pending_review') return 'info'
  return 'info'
}

function formatTime(value) {
  if (!value) return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function formatRequirements(req) {
  if (!req) return '-'
  return Object.entries(req)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${value}`)
    .join('；')
}

async function reload() {
  loading.value = true
  try {
    const data = await listOrders()
    orders.value = data.items
  } catch (error) {
    ElMessage.error(error.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function openForm() {
  form.value = { title: '', genre: '', market: '北美', episodes: 6, lang: 'en-US', budgetYuan: 3000, delivery: '', deadline: null }
  formVisible.value = true
}

async function submitForm() {
  saving.value = true
  try {
    const requirements = {
      genre: form.value.genre,
      market: form.value.market,
      episodes: form.value.episodes,
      lang: form.value.lang,
      delivery: form.value.delivery
    }
    await createOrder({
      title: form.value.title.trim(),
      requirements,
      budget_cents: Math.round(form.value.budgetYuan * 100),
      deadline: form.value.deadline ? new Date(form.value.deadline).toISOString().slice(0, 19) : null,
      submit: true
    })
    ElMessage.success('工单已提交审核')
    formVisible.value = false
    await reload()
  } catch (error) {
    ElMessage.error(error.message || '发布失败')
  } finally {
    saving.value = false
  }
}

async function openDetail(row) {
  current.value = row
  detailVisible.value = true
  try {
    const data = await getOrder(row.id)
    bids.value = data.bids
  } catch (error) {
    ElMessage.error(error.message || '加载投标失败')
  }
}

async function doAward(bid) {
  try {
    await ElMessageBox.confirm(
      `确认选择「${bid.bidder_name}」的投标（${(bid.amount_cents / 100).toFixed(0)} 元）定标？`,
      '定标确认',
      { type: 'warning' }
    )
    await awardOrder(current.value.id, bid.id)
    ElMessage.success('定标完成')
    await reload()
    await openDetail(current.value)
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.message || '定标失败')
    }
  }
}

function logout() {
  userStore.logout()
  router.push('/login')
}

onMounted(async () => {
  if (!userStore.profile) {
    await userStore.fetchMe()
  }
  await reload()
})
</script>

<style scoped>
.page {
  padding: 20px 24px 40px;
  max-width: 1080px;
  margin: 0 auto;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}
.title {
  margin: 0 0 4px;
  font-weight: 500;
}
.sub {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.bid-card {
  border: 0.5px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
  padding: 10px 14px;
  margin-bottom: 10px;
}
.bid-head {
  display: flex;
  align-items: center;
  gap: 12px;
}
.bid-amount {
  color: var(--el-color-danger);
  font-size: 13px;
}
.bid-proposal {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
</style>
