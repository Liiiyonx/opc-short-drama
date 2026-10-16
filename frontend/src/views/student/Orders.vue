<template>
  <div class="page">
    <div class="head">
      <div>
        <h3 class="title">工单大厅</h3>
        <span class="sub">企业真实需求，投标需五维能力均分 ≥ 60（能力数据缺失时不限制）</span>
      </div>
      <div>
        <el-button @click="router.push('/student')">返回工作台</el-button>
      </div>
    </div>

    <el-card shadow="never">
      <template #header>
        <span>可投工单</span>
        <el-button size="small" text type="primary" @click="reload">刷新</el-button>
      </template>
      <el-table :data="orders" v-loading="loading" empty-text="暂无已发布的工单">
        <el-table-column prop="title" label="工单" min-width="200" show-overflow-tooltip />
        <el-table-column label="需求" min-width="220">
          <template #default="{ row }">
            <span class="req-text">{{ formatRequirements(row.requirements_json) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算" width="110">
          <template #default="{ row }">{{ (row.budget_cents / 100).toFixed(0) }} 元</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'bidding' ? 'warning' : 'success'">
              {{ row.status === 'bidding' ? '投标中' : '已发布' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150">
          <template #default="{ row }">
            <el-button size="small" type="primary" @click="openBid(row)">投标</el-button>
            <el-button size="small" text @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="bidVisible" :title="`投标：${current ? current.title : ''}`" width="520px">
      <el-alert v-if="abilityAverage !== null" :type="abilityAverage >= 60 ? 'success' : 'error'" :closable="false"
        :title="`我的五维能力均分：${abilityAverage} 分`" class="bid-alert" />
      <el-form label-width="80px">
        <el-form-item label="报价（元）">
          <el-input-number v-model="bidForm.amountYuan" :min="1" :step="100" />
          <span class="hint">参考预算 {{ current ? (current.budget_cents / 100).toFixed(0) : 0 }} 元</span>
        </el-form-item>
        <el-form-item label="作品方案">
          <el-input v-model="bidForm.proposal" type="textarea" :rows="4" maxlength="500"
            placeholder="简述创作思路、团队配置与交付计划" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" :loading="submitting" :disabled="!canBid" @click="doBid">提交投标</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="detailVisible" :title="current ? current.title : '工单详情'" size="560px">
      <template v-if="current">
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="预算">{{ (current.budget_cents / 100).toFixed(0) }} 元</el-descriptions-item>
          <el-descriptions-item label="需求">{{ formatRequirements(current.requirements_json) }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ current.status }}</el-descriptions-item>
        </el-descriptions>
        <el-divider content-position="left">我的投标</el-divider>
        <el-empty v-if="!bids.length" description="我还没有投标该工单" :image-size="60" />
        <div v-for="bid in bids" :key="bid.id" class="my-bid">
          <span>报价 {{ (bid.amount_cents / 100).toFixed(0) }} 元</span>
          <el-tag size="small" :type="bid.status === 'won' ? 'success' : bid.status === 'lost' ? 'info' : 'warning'">
            {{ { active: '有效', won: '中标 🎉', lost: '未中', withdrawn: '撤回' }[bid.status] || bid.status }}
          </el-tag>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { bidOrder, getOrder, getStudentAbility, listOrders } from '../../api/index.js'
import { useUserStore } from '../../stores/user.js'

const router = useRouter()
const userStore = useUserStore()

const orders = ref([])
const loading = ref(false)
const submitting = ref(false)
const bidVisible = ref(false)
const detailVisible = ref(false)
const current = ref(null)
const bids = ref([])
const abilityAverage = ref(null)
const bidForm = ref({ amountYuan: 1000, proposal: '' })

const canBid = computed(() => abilityAverage.value === null || abilityAverage.value >= 60)

function formatRequirements(req) {
  if (!req) return '-'
  return Object.entries(req)
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => `${key}: ${value}`)
    .join('；')
}

async function loadAbility() {
  const me = userStore.profile
  if (!me) return
  try {
    const data = await getStudentAbility(me.id)
    const scores = Object.values(data.latest || {})
    abilityAverage.value = scores.length
      ? Math.round((scores.reduce((sum, score) => sum + score, 0) / scores.length) * 10) / 10
      : null
  } catch {
    abilityAverage.value = null
  }
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

async function openBid(row) {
  current.value = row
  bidForm.value = { amountYuan: Math.round(row.budget_cents / 100) || 1000, proposal: '' }
  await loadAbility()
  bidVisible.value = true
}

async function openDetail(row) {
  current.value = row
  detailVisible.value = true
  try {
    const data = await getOrder(row.id)
    bids.value = data.bids
  } catch {
    bids.value = []
  }
}

async function doBid() {
  submitting.value = true
  try {
    await bidOrder(current.value.id, {
      amount_cents: Math.round(bidForm.value.amountYuan * 100),
      proposal: bidForm.value.proposal || null
    })
    ElMessage.success('投标成功')
    bidVisible.value = false
    await reload()
  } catch (error) {
    ElMessage.error(error.message || '投标失败')
  } finally {
    submitting.value = false
  }
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
.req-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.bid-alert {
  margin-bottom: 14px;
}
.hint {
  margin-left: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.my-bid {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
}
</style>
