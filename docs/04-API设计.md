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

### 3.3 作品与资产（W3 已实现）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /works | 创建作品 `{title, type, task_id?}`，初始 draft |
| GET | /works | 我的作品列表（type 过滤、分页） |
| GET | /works/{id} | 详情：作品 + 资产（含 URL）+ 子版本链 |
| POST | /works/{id}/generate | 生成 / 重生成。script：剧本参数；storyboard：`{source_work_id, episode}`；audio：`{storyboard_work_id, lang?, voice_map?}`（异步）；subtitle：`{audio_work_id}`（同步复制 SRT）；video：`{storyboard_work_id, audio_work_id}`（异步）。首次生成原地升级 draft→ready，再次生成创建 parent 链新版本（异步类型不建版本链，P1 项） |
| POST | /works/{id}/assets | multipart 上传文件资产（file + kind） |
| POST | /works/{id}/text-assets | 登记文本资产 `{kind: text/json/srt, content}` |
| GET | /works/{id}/assets | 资产列表（含访问 URL） |
| POST | /works/{id}/ai-declare | 提交 AI 使用声明 `{agents_used, human_edit_ratio, note}` |
| GET | /files/{key} | 流式读取存储文件（需登录；local 后端读盘，minio 代理下载） |

### 3.4 实训任务与批改（W6 已实现）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /tasks | 任务列表（学生：已发布可接；教师：我发布的；admin：全部） |
| POST | /tasks | 教师发布任务 `{title, brief, course_id?, deadline?, team_rule, rubric?, publish}`；rubric 权重自动归一化，维度须为五维之一 |
| GET | /tasks/{id} | 任务详情 + Rubric（学生视角附 my_submission） |
| POST | /tasks/{id}/submit | 学生提交 `{work_ids, note}`；校验归属/截止，回写 works.task_id |
| POST | /tasks/{id}/close | 教师截止任务 |
| GET | /tasks/{id}/submissions | 提交列表（教师视角，含学生与作品明细） |
| POST | /works/{id}/review | 教师 Rubric 批改 `{criterion_scores, comment}` → 逐维落能力快照 |
| GET | /works/{id}/review | 查看批改结果（最新 + 历史） |
| GET | /courses | 课程列表（任务绑定用） |

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

### 3.6 能力图谱（W6 已实现）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /ability/students/{id} | 个人五维能力（latest 快照聚合）+ 成长曲线（history） |
| GET | /ability/classes/{id} | 班级能力分布（各维最新分均值） |

### 3.7 异步任务（音视频长任务）
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /agents/tts/invoke | 入队，返回 `{task_id}` |
| GET | /agent-tasks/{task_id} | 轮询 `{status, result?, error?}`（task_id 即 agent_sessions.id） |

> 命名说明：异步轮询原定 `/tasks/{id}`，因与 §3.4 教学任务路由冲突，W6 起重命名为 `/agent-tasks/{id}`。
>
> 异步智能体（tts / compose）经作品 generate 入口入队后返回 `session_id`，
> 由 arq worker（`python -m arq app.workers.tasks.WorkerSettings`）执行，
> 前端轮询 `GET /agent-tasks/{session_id}`：running → success / failed。P1 升级 SSE。
>
> 超时兜底（2026-10-16 优化轮）：running 超过 `AGENT_TASK_TIMEOUT_SECONDS`（默认 1800s）
> 的会话在三处被自动判失败并回落作品状态——API 启动 / worker 启动 / 轮询 GET 惰性触发；
> 失败响应带 `error` 说明与 `work_id`，前端据此刷新并提示。

> P1 升级：SSE `/agents/stream/{session_id}` 推送生成进度。

### 3.8 管理（P1）
`/admin/users`、`/admin/courses`、`/admin/models`（模型与配额配置）、`/admin/agent-logs`（成本看板）。

## 4. 关键约束

1. 投标门槛：学生能力分达到课程阈值方可投标（P0 阈值由教师配置，默认 60）。
2. 企业发单需 `verify_status=approved`（人工审核营业执照后代管）。
3. 智能体 invoke 前必须过配额检查，超限返回 42901，并落 `agent_call_logs`（status=quota_exceeded）。
4. 所有写操作记录操作者；作品类接口校验 owner 或同任务教师权限。
