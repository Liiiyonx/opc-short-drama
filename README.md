<div align="center">

# OPC 短剧出海 AI 集合智能体平台

**AI 赋能 · 一人成军** —— 电子商务与商务英语双专业联动的短剧出海产教融合平台

学生一人借助 10 个智能体独立承接短剧出海全流程（剧本 → 分镜 → 翻译 → 配音 → 成片 → 发布 → 数据复盘），教师通过平台教学与批改，成果由企业遴选买单。

[![CI](https://img.shields.io/badge/CI-pytest%20%2B%20build-blue)](.github/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Vue](https://img.shields.io/badge/Vue-3-4FC08D?logo=vuedotjs&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-异步-009688?logo=fastapi&logoColor=white)
![License](https://img.shields.io/badge/用途-教学演示-informational)

</div>

---

## ✨ 功能矩阵

**十智能体**（统一网关：契约校验 → 配额 → 会话 → 调用日志 → 成本估算）

| 智能体 | 职责 | 形态 |
|---|---|---|
| 剧本生成 | 题材/市场 → 分集大纲，支持多轮改写 | LLM 同步 |
| 分镜 | 剧本 → 镜头表（景别/运镜/英文画面提示词） | LLM 同步 |
| 翻译本地化 | 台词跨文化改写 + 俚语适配 + 合规标记 | LLM 同步 |
| 配音 | 多语种 TTS、角色音色映射、SRT 对齐 | Edge-TTS 异步 |
| 成片合成 | 图片序列 + 音轨 + 烧字幕 → MP4 | ffmpeg 异步 |
| 发布参数 | 各平台标题/文案/话题标签/发布时间建议 | LLM 同步 |
| 数据分析 | 回填播放数据 → 复盘报告（指标计算/归因/结论分级） | LLM 同步 |
| 优化建议 | 复盘 → 按优先级排序的可执行迭代建议 | LLM 同步 |
| 人才匹配 | 企业工单 → 学生脱敏排行（规则化可解释打分） | 规则引擎 |
| AI 备课 | 课程主题 → 教案草案（环节时间守恒/Rubric 建议） | LLM 同步 |

**三端 + 管理后台**

- **学生端**：六步创作工坊（版本链/单步重跑/异步进度）、AI 使用声明、人工修订差异度比对、数据复盘、实训任务、工单投标、作品集脱敏分享、学习档案导出
- **教师端**：任务发布（Rubric 编辑器）、批改 → 五维能力快照、能力预警、AI 备课、工单合规审核、AI 用量看板（成本/tokens/趋势）
- **企业端**：工单发布（资质审核）、投标定标状态机、AI 人才匹配
- **管理后台**：用户/课程管理
- **平台底座**：JWT 双 token、登录防爆破限流、每用户配额、成本全记账、arq 异步队列 + 超时清扫、流式文件 + Range、暗色模式、深度健康检查

## 🏗️ 架构

```
┌──────────────────────────────────────────────────────────┐
│  接入层：学生端 / 教师端 / 企业端 / 管理后台（Vue3 + EP）    │
├──────────────────────────────────────────────────────────┤
│  网关：JWT 鉴权 · 登录限流 · 配额 · 访问日志(X-Request-ID)  │
├──────────────────────────────────────────────────────────┤
│  业务层：教学管理 · 实训工作流 · 工单交易 · 能力图谱 · 分析  │
├──────────────────────────────────────────────────────────┤
│  智能体中枢：编排器（契约→配额→会话→日志→成本）             │
│   ┌────────┬────────┬────────┬────────┬────────┐        │
│   │剧本LLM │分镜LLM │翻译LLM │配音TTS │合成FFMPEG│        │
│   ├────────┼────────┼────────┼────────┼────────┤        │
│   │发布LLM │分析LLM │建议LLM │匹配规则 │备课LLM  │        │
│   └────────┴────────┴────────┴────────┴────────┘        │
├──────────────────────────────────────────────────────────┤
│  数据层：MySQL · Redis(arq) · MinIO/本地存储               │
├──────────────────────────────────────────────────────────┤
│  基础设施：单 VPS · Docker Compose · nginx · 每日备份      │
└──────────────────────────────────────────────────────────┘
```

## 🚀 快速开始（本地开发）

```bash
# 后端（Python 3.12）
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt -r requirements-dev.txt
cp ../.env.example .env                                  # 密钥见下方规约
python -m alembic upgrade head
python -m scripts.seed                                   # 演示数据（幂等）
uvicorn app.main:app --reload --port 8000

# 异步 worker（配音/成片；需 Redis 与 ffmpeg）
python -m arq app.workers.tasks.WorkerSettings

# 前端
cd ../frontend
npm install
npm run dev            # http://localhost:5173，/api 代理到 8000
```

**一键演示**（自动找解释器 / 加载密钥 / 迁移 / 健康检查）：

```bash
bash demo_up.sh           # 真实 AI 模式
bash demo_up.sh --mock    # 无密钥演示（全程离线，显式测试桩）
bash demo_down.sh         # 停止
# → http://127.0.0.1:5199
```

| 角色 | 账号 | 密码 |
|---|---|---|
| 学生 | student01 | student123 |
| 教师 | teacher01 | teacher123 |
| 企业 | enterprise01 | ent123456 |
| 管理员 | admin | admin123 |

> 登录页支持**演示账号一键填充**；15 分钟全流程演示脚本见 `docs/演示脚本.md`。

## 🧪 测试

```bash
cd backend
python -m pytest tests/ -q          # 55+ 用例：API 全流程 / 权限矩阵 / 配额 / 限流 / 分析
python -m scripts.e2e_api_test      # API 级端到端冒烟（35 断言，真实模式约 0.05 元）
python -m scripts.selfcheck         # 环境体检（含真实 LLM / Edge-TTS 调用）
python -m scripts.bench_api         # 非 AI 接口 P95 < 500ms 基准
```

推送自动触发 CI（`.github/workflows/ci.yml`：后端 pytest + 前端 build，LLM/TTS 走显式 mock）。

## 🚢 生产部署（单 VPS）

```bash
cp .env.example .env    # 填 LLM_API_KEY / JWT_SECRET / 各服务密码
bash deploy.sh          # docker compose 全栈：nginx + api + worker + mysql + redis + minio
bash deploy/backup.sh   # 数据备份（MySQL + MinIO，滚动保留 7 份，可配 cron）
```

安全基线：数据面端口不出公网、Redis 强制密码、`OPC_ENV=prod` 下弱 JWT 密钥拒绝启动、上传白名单 + 大小限制、登录失败限流。

## 📁 项目结构

```
├── backend/
│   ├── app/
│   │   ├── agents/          # 10 个智能体 + prompts/ + 编排器
│   │   ├── api/v1/          # REST 路由（auth/works/tasks/orders/analytics/portfolio/…）
│   │   ├── core/            # 配置(fail-fast) / 安全 / 限流 / 中间件
│   │   ├── models/          # 18 张表（SQLAlchemy 2.0 异步）
│   │   ├── services/        # LLM 网关 / TTS / 媒体 / 存储 / 能力 / 工单
│   │   └── workers/         # arq 异步任务
│   ├── tests/               # 55+ pytest 用例
│   ├── alembic/             # 迁移链
│   └── scripts/             # seed / selfcheck / bench_api / e2e_api_test
├── frontend/
│   ├── src/
│   │   ├── views/           # student / teacher / enterprise / admin / 公开页
│   │   ├── components/      # AppHeader / WorkSteps / AssetCard / UsageChip
│   │   ├── composables/     # useTaskPoll（异步轮询 + 超时兜底）
│   │   └── styles/          # 设计基座（品牌变量 / 暗色适配）
│   └── nginx.conf           # gzip + 静态缓存 + 反代
├── deploy/backup.sh         # 数据备份
├── docs/                    # 策划与设计文档（仓库唯一事实来源）
├── docker-compose.yml       # 生产编排
└── .github/workflows/ci.yml # CI
```

## 🗺️ Roadmap

- [ ] 半自动发布（平台 API 凭据接入后，当前为发布参数包）
- [ ] 素材库联动 + 分镜图生成
- [ ] 可视化编排画布（Dify 式）
- [ ] 用量按班级/课程聚合、产教数据看板
- [ ] CosyVoice 自托管音色

## 📖 文档索引

| 文档 | 内容 |
|---|---|
| docs/01 范围与路线图 | 做什么、不做什么、三期路线、验收标准 |
| docs/02 技术架构 | 选型与理由、模块划分、编排与部署 |
| docs/03 数据库设计 | 18 张表字段/索引/ER 关系 |
| docs/04 API 设计 | 统一规范、错误码、全端点清单 |
| docs/05 智能体设计 | 智能体契约、System Prompt、编排状态机 |
| docs/06 开发计划 | 排期、分工、里程碑 |
| docs/07 风险与合规 | 风险登记册、五条合规红线 |
| docs/演示脚本.md | 15 分钟全流程演示（含新功能） |
| docs/开发进度存档.md | 每步实质工作的开发日志 |

## 🔑 开发规约（必须遵守）

1. **密钥一律放项目外**：默认 `D:\VeriCall_data\secrets\opc_secrets.env`，严禁提交仓库；
2. **LLM 默认云端 DeepSeek**（OpenAI 兼容协议）；无密钥时明确报错，**不回退本地 Ollama**（`mock` 为显式测试桩）；
3. **金额一律用「分」**（bigint），禁止浮点存钱；
4. JSON 字段统一 `*_json` 命名；存储只存键值，文件本体走对象存储；
5. 每完成一部分实质工作，**立即追加** `docs/开发进度存档.md`。
