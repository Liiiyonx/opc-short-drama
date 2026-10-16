# OPC 短剧出海 AI 集合智能体平台

> "AI 赋能 · 一人成军" —— 电子商务与商务英语双专业联动的 OPC 短剧出海产教融合创新实践

- 建设单位：福州理工学院 经济贸易学院
- 形态：**三端（学生 / 教师 / 企业）+ 一中枢（Agent Orchestrator）+ 八智能体**
- 核心叙事：学生一人借助智能体矩阵，独立承接短剧出海全流程商业订单（一人成军）
- 当前阶段：**P0-MVP 全链路完成（2026-10-16）**：三端闭环（学生创作工坊 / 教师任务批改与能力快照 / 企业工单遴选）+ 智能体矩阵（剧本/分镜/翻译本地化/配音/成片合成/发布参数）+ arq 异步 + 一键部署脚本

## 目录结构

```
OPC短剧出海AI集合智能体平台/
├── docs/                      # 策划与设计文档（本仓库唯一事实来源）
│   ├── 01-范围与路线图.md      # 全景、MVP 砍单、P0/P1/P2、验收标准
│   ├── 02-技术架构.md          # 选型、模块划分、编排与部署
│   ├── 03-数据库设计.md        # 表结构、索引、ER 关系
│   ├── 04-API设计.md           # 接口规范与端点清单
│   ├── 05-智能体设计.md        # 八大智能体契约、Prompt 草案、编排状态机
│   ├── 06-开发计划.md          # 8 周排期、分工、里程碑
│   ├── 07-风险与合规.md        # 风险登记册、合规红线
│   └── 开发进度存档.md          # 每完成一部分实质工作立即追加
├── backend/                   # FastAPI 后端（Python 3.11+）
│   └── app/{core,db,models,schemas,api,agents,services,workers}
├── frontend/                  # Vue 3 + Element Plus 三端前端
├── docs/演示脚本.md            # 15 分钟全流程演示脚本（三端四智能体）
├── deploy.sh                  # 一键部署（docker compose 全栈）
├── docker-compose.yml         # nginx + api + worker + mysql + redis + minio
└── .env.example               # 配置模板（不含任何真实密钥）
```

## 快速开始（开发环境）

```bash
# 后端
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -r requirements.txt
cp ../.env.example .env        # 按需修改；密钥见下方规约
python -m alembic upgrade head # 初始化数据库
python -m scripts.seed         # 演示数据（幂等）
uvicorn app.main:app --reload --port 8000

# 异步任务 worker（配音/成片合成走 arq + Redis，需另开终端；依赖 Redis 与 ffmpeg）
cd backend
python -m arq app.workers.tasks.WorkerSettings

# 前端
cd frontend
npm install
npm run dev                    # http://localhost:5173，/api 代理到 8000
```

## 开发规约（必须遵守）

1. **密钥一律放项目外**：默认 `D:\VeriCall_data\secrets\opc_secrets.env`，bash 中
   `set -a; source <文件>; set +a` 后再启动服务；严禁把密钥提交进仓库（.env 已在 .gitignore）。
2. **LLM 默认云端 DeepSeek**（OpenAI 兼容协议，`LLM_BASE_URL/LLM_API_KEY/LLM_MODEL_DEFAULT`）；
   无密钥时给明确报错并提示 source secrets，**不回退本地 Ollama**。
3. **金额一律用「分」**（bigint），禁止浮点存钱。
4. JSON 字段统一 `*_json` 命名；存储只存键值，文件本体走对象存储。
5. 每完成一部分实质工作，**立即追加** `docs/开发进度存档.md`。

## 文档索引

| 文档 | 内容 |
|---|---|
| 01 范围与路线图 | 做什么、不做什么、三期路线、验收标准 |
| 02 技术架构 | 技术选型与理由、目录结构、智能体编排、部署形态 |
| 03 数据库设计 | 17 张核心表字段/索引/ER 关系 |
| 04 API 设计 | 统一规范、错误码、全端点清单 |
| 05 智能体设计 | 八大智能体输入输出契约、System Prompt 草案 |
| 06 开发计划 | 8 周排期到周、分工、里程碑 |
| 07 风险与合规 | 风险登记册、五条合规红线 |
