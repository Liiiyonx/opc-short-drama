import { defineConfig, devices } from '@playwright/test'

// P0-06 浏览器级 E2E：四角色登录 + 学生工坊 + 管理健康页 + 移动端。
// 前置：demo 环境运行中（npm run dev 或 demo.ps1 start），演示账号已播种。
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  retries: 1,
  reporter: [['list'], ['json', { outputFile: 'e2e/report.json' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:5199',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure'
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    // iPhone 13 预设默认 webkit（未安装）——browserName 统一跑 chromium 内核
    { name: 'mobile', use: { ...devices['iPhone 13'], browserName: 'chromium' } }
  ]
})
