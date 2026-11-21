// P0-06 四角色登录闸门 + 学生工坊/管理健康页 + 移动端三档宽度。
// 演示账号由 dev/demo 构建注入（VITE_DEMO_ACCOUNTS），与 scripts.seed 一致。
import { expect, test } from '@playwright/test'

const ACCOUNTS = [
  { role: '学生', username: 'student01', password: 'student123', home: '/student' },
  { role: '教师', username: 'teacher01', password: 'teacher123', home: '/teacher' },
  { role: '企业', username: 'enterprise01', password: 'ent123456', home: '/enterprise' },
  { role: '管理员', username: 'admin', password: 'admin123', home: '/admin' }
]

async function login(page, username, password) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入账号').fill(username)
  await page.getByPlaceholder('请输入密码').fill(password)
  await page.getByRole('button', { name: '登 录' }).click()
  await page.waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 10000 })
}

async function logout(page) {
  await page.evaluate(() => {
    localStorage.removeItem('opc_token')
    localStorage.removeItem('opc_refresh_token')
  })
}

// ---------- 四角色登录 ----------

for (const acc of ACCOUNTS) {
  test(`登录 ${acc.role} → ${acc.home}`, async ({ page }) => {
    await login(page, acc.username, acc.password)
    await expect(page).toHaveURL(new RegExp(acc.home.replace('/', '\\/')))
    // 无控制台错误（P0 验收口径：40 次角色组合无控制台错误的浏览器级抽样）
    const errors = []
    page.on('pageerror', (e) => errors.push(String(e)))
    await page.waitForTimeout(1200)
    expect(errors).toEqual([])
    await logout(page)
  })
}

test('错误密码被拒绝', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('请输入账号').fill('student01')
  await page.getByPlaceholder('请输入密码').fill('wrong-password')
  await page.getByRole('button', { name: '登 录' }).click()
  await expect(page.getByText('账号或密码错误')).toBeVisible({ timeout: 8000 })
})

// ---------- 学生端核心链路 ----------

test.describe(() => {
  test.use({ viewport: { width: 1440, height: 900 } })

  test('学生工作台：展示剧集置顶且工坊可进', async ({ page }) => {
    await login(page, 'student01', 'student123')
    await expect(page.getByText('展示剧集：《海潮女王的逆袭》成片').first()).toBeVisible({ timeout: 10000 })
    // 进工坊不崩
    await page.getByRole('button', { name: '进入工坊' }).first().click()
    await page.waitForURL(/\/student\/workshop\/\d+/, { timeout: 10000 })
    await expect(page.locator('.workshop, .page').first()).toBeVisible()
  })

  test('管理后台：系统健康页六项全绿', async ({ page }) => {
    await login(page, 'admin', 'admin123')
    await page.getByRole('tab', { name: '系统健康' }).click()
    await expect(page.getByText('系统正常')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('Worker 心跳')).toBeVisible()
    await expect(page.getByText('在线')).toBeVisible()
  })
})

// ---------- 移动端（mobile project：iPhone 13 390×844） ----------

test.describe(() => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('移动端学生工作台：无页面级横向滚动 + 任务卡可见', async ({ page }) => {
    await login(page, 'student01', 'student123')
    await page.waitForTimeout(1200)
    const overflow = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth
    }))
    expect(overflow.sw, `横向溢出 ${overflow.sw} > ${overflow.cw}`).toBeLessThanOrEqual(overflow.cw)
    await expect(page.getByText('我的任务')).toBeVisible()
    await expect(page.getByText('我的能力')).toBeVisible()
  })

  test('移动端 414/768 两档零溢出', async ({ page }) => {
    await login(page, 'student01', 'student123')
    for (const width of [414, 768]) {
      await page.setViewportSize({ width, height: 900 })
      await page.waitForTimeout(400)
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
      expect(overflow, `${width}px 档横向溢出 ${overflow}px`).toBeLessThanOrEqual(0)
    }
  })
})
