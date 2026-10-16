# 04 · API 设计

> V1.0 · 2026-10-16 · P0-MVP 端点清单

## 1. 统一规范

- 前缀 `/api/v1`，REST 风格，JSON。
- 鉴权：`Authorization: Bearer <jwt>`；access token 2 小时，refresh token 7 天。
- 统一包裹：`{"code": 0, "message": "ok", "data": ...}`；`code != 0` 即业务失败。
- 分页：`page`（默认 1）/ `page_size`（默认 20，max 100），返回 `{items, total, page, page_size}`。
- 角色鉴权按 `users.role` 走依赖注入（`deps.require_role("teacher")`）。

## 2. 错误码

| code | 含义 | HTTP |
|---|---|---|
| 0 | 成功 | 200 |
| 40001 | 参数错误 | 422 |
| 40101 | 未登录 / token 失效 | 401 |
| 40301 | 无权限 | 403 |
| 40401 | 资源不存在 | 404 |
| 40901 | 状态冲突（如任务已截止） | 409 |
| 42901 | 智能体配额超限 | 429 |
| 50001 | 服务器内部错误 | 500 |
| 50002 | LLM 网关错误（上游不可用/未配置密钥） | 502 |

## 3. 端点清单

### 3.1 认证
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /auth/login | 三端统一登录 `{username, password}` → `{access_token, refresh_token, user}` |
| POST | /auth/refresh | 刷新 access token |
| GET | /users/me | 当前用户信息 + 档案 |

### 3.2 智能体与流水线
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /agents/{type}/invoke | 调用智能体（type=script/storyboard/translate）。body 为该智能体输入契约；同步返回 `result` |
| POST | /agents/tts/invoke | 配音为异步任务，返回 `{task_id}` |
| GET | /agents/sessions/{id} | 查询会话产物与日志 |
| GET | /agents/sessions | 按 work_id / agent_type 过滤列表 |
| POST | /works/{id}/pipeline/run | 触发流水线某一步 `{step}`（脚本/分镜/配音/字幕/成片） |
| GET | /works/{id}/pipeline | 查询工坊各步骤状态与产物版本 |

### 3.3 作品
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /works | 创建作品（空稿，进入流水线） |
| GET | /works/{id} | 作品详情 + 版本链 + 资产列表 |
| GET | /works | 列表：owner / type / task_id 过滤 |
| POST | /works/{id}/versions | 基于某版本生成新版本（单步重跑入口） |
| POST | /works/{id}/assets | 上传 / 登记资产（人工上传素材） |
| GET | /works/{id}/assets/{asset_id}/url | 取存储预签名 URL |
| POST | /works/{id}/ai-declare | 提交 / 更新 AI 使用声明 |

### 3.4 实训任务与批改
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /tasks | 任务列表（学生：可接；教师：我发布的） |
| POST | /tasks | 教师发布任务 |
| GET | /tasks/{id} | 任务详情 + Rubric |
| POST | /tasks/{id}/submit | 学生提交交付物 |
| POST | /tasks/{id}/close | 教师截止任务 |
| POST | /works/{id}/review | 教师 Rubric 批改 → 触发能力快照 |
| GET | /works/{id}/review | 查看批改结果 |

### 3.5 工单
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /orders | 企业发布工单（status=draft） |
| GET | /orders | 工单大厅（学生：published；企业：我的；教师：待审核） |
| GET | /orders/{id} | 工单详情 |
| POST | /orders/{id}/verify | 教师/管理员审核 `{approved, note}` |
| POST | /orders/{id}/bid | 学生/团队投标 `{amount_cents, proposal}` |
| GET | /orders/{id}/bids | 投标列表（企业视角） |
| POST | /orders/{id}/award | 企业定标 `{bid_id}` |

### 3.6 能力图谱
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /ability/students/{id} | 个人五维能力 + 成长曲线（按快照聚合） |
| GET | /ability/classes/{id} | 班级能力分布 |

### 3.7 异步任务（音视频长任务）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /agents/tts/invoke | 入队，返回 `{task_id}` |
| GET | /tasks/{task_id} | 轮询 `{status, progress, result?, error?}` |

> P1 升级：SSE `/agents/stream/{session_id}` 推送生成进度。

### 3.8 管理（P1）
`/admin/users`、`/admin/courses`、`/admin/models`（模型与配额配置）、`/admin/agent-logs`（成本看板）。

## 4. 关键约束

1. 投标门槛：学生能力分达到课程阈值方可投标（P0 阈值由教师配置，默认 60）。
2. 企业发单需 `verify_status=approved`（人工审核营业执照后代管）。
3. 智能体 invoke 前必须过配额检查，超限返回 42901，并落 `agent_call_logs`（status=quota_exceeded）。
4. 所有写操作记录操作者；作品类接口校验 owner 或同任务教师权限。
