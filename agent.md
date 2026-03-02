# Steward

一个无感感知上下文、主动推进事务、只在关键决策点打扰用户的协作 Agent。An ambient proactive agent that handles low-risk work automatically and briefs users only when their judgment is needed.

## 项目灵感

它的核心灵感来自策略游戏。像《钢铁雄心》《文明》这类游戏里，玩家通常不想关心“第一军团少了一支枪”或“骑兵向右移动了一格”这类微观细节；真正想要做的是制定更高层级的战略目标，再由系统根据局势变化自行调整和执行。
Steward 想解决的正是这一问题：它能够无感感知上下文，主动识别并推进当前应处理的事项，优先自行完成可自动化、低风险的事务，仅在真正涉及方向判断与关键决策时才请求用户介入。

## 核心机制

Steward 的关键不在于替用户做所有事，而在于将“上下文感知—任务识别—自主推进—关键汇报”组织成一个持续运行的闭环。它会根据当前目标、历史上下文与环境状态，主动判断哪些事务可以直接执行，哪些事项需要进一步确认，并把用户的注意力尽可能保留给真正重要的决策。

## 上下文信号源（增量 v0.1）

Steward 将上下文感知定义为多源融合，不局限于单一应用。屏幕与 GitHub、邮件、聊天软件等数据源同级，都是一等信号源。

- API / Webhook：GitHub、邮件、日历、聊天软件等结构化事件。
- Skill / MCP：来自社区或自建 skill 的能力，通过统一适配层接入。
- 屏幕信号：当前工作界面的视觉上下文（例如窗口、文本片段、任务迹象）。
- 本地环境：文件变更、命令执行、项目状态等运行时上下文。

## 工作上下文聚合器（Context Space，增量 v0.5）

Steward 不采用“事件线性堆叠”作为主路径，而是先将乱序、异构事件归拢到工作上下文空间（Context Space）后再生成任务。

1. 事件事实层（Event Log）：保存不可变的原始 `ContextEvent`。
2. 上下文空间层（Context Space）：按当前聚焦的项目、目标、承诺进行跨源聚合。
3. 任务层（Task Queue）：仅接收达到证据阈值的候选任务。

### Context Space 归拢规则（增量 v0.5）

- 强锚点优先：`repo + issue_id`、`thread_id`、`calendar_topic` 命中时直接并入同一空间。
- 时间窗对齐：在限定窗口（例如 30-90 分钟）内做跨源关联。
- 实体重叠打分：`person/repo/issue/file` 重叠越高，合并分越高。
- 屏幕仅作证据：屏幕信号可提升置信度，但默认不单独触发高风险任务。
- 阈值生成任务：只有当空间证据分达到阈值才输出 `TaskCandidate`。

## Context Space 实体解析（顶级 LLM 推理，增量 v0.8）

Steward 在 Context Space 路由上采用“受限工作台”策略：不让 LLM 在全量历史中自由聚类，而是只在有限候选集中做判别。

1. 全量不丢：Context Space 全量保留，不以“超过 48 小时不活跃”直接淘汰。
2. 分层召回：后端先召回最多 `50` 个候选（Pinned + 近期活跃 + 实体检索命中）。
3. 精排上屏：将高分候选压缩到 `8-12` 个再交给顶级推理模型做多项选择。
4. 多项选择题式路由：要求模型只输出 `Space ID` 或 `NEW`。
5. 置信度门禁：若模型置信度低于阈值，进入 `NEW` 候选并在简报中请用户确认。
6. NEW 前复活检查：创建 `NEW` 前，必须对 `dormant/parked/archived` 做一次复活匹配。

### Prompt 设计范式（增量 v0.8）

```text
[系统设定]
你是一个情报分析师，你的目标是判断新事件属于哪个当前活跃的上下文空间（Context Space），还是需要新开辟一个空间。

[当前活跃的 Context Spaces 列表]
Space 1: [Focus: Stewardship README 更新] [Entities: README, 架构设计, 状态机] [Status: Active]
Space 2: [Focus: 前端 Dashboard 崩溃] [Entities: Dashboard, React, Bug, 老板] [Status: Waiting fixing]
Space 3: [Focus: 订今晚的机票] [Entities: 携程, 航班, 行程] [Status: Dormant]

[新到事件]
来源: 微信, 内容: "前端的那个 bug 进展如何？"

[任务]
请推理该事件属于哪个 Space 的追踪范围？输出 Space ID，或输出 NEW 创建新空间。
```

### 路由输出约束（增量 v0.8）

- 仅允许输出：`SPACE_<id>` 或 `NEW`。
- 必须附带 `confidence`（0-1）与一行 `reason`（可审计）。
- 不允许输出自由文本任务清单，避免模型越权。

## 模型接入方式（API，增量 v1.3）

Steward 的模型部署方式采用 API 接入，不采用本地自托管推理服务。

1. 接入方式：通过外部模型 API 调用推理能力（路由、摘要、计划辅助）。
2. 凭据管理：API Key 仅通过环境变量或密钥管理服务注入，不写入仓库。
3. 稳定性：配置超时、重试、回退模型，避免单点失败导致主流程阻塞。
4. 成本控制：按任务类型选择模型档位，优先使用满足质量要求的最低成本模型。
5. 可观测性：记录 API 延迟、错误率、tokens 使用量，并纳入告警。

## 平台适配与技术路线（Python-First，增量 v1.5）

Steward 采用“macOS 首发，跨平台扩展”的路线，核心引擎使用 Python。

1. 平台阶段：
- Phase 1（当前）：macOS 优先适配与常驻运行。
- Phase 2（后续）：Windows 桌面适配。
- Phase 3（后续）：移动端（iOS/Android）以简报审批与状态查看为主。

2. 技术选型（Python-first）：
- 语言与运行时：`Python 3.14 + asyncio`。
- 服务层：`FastAPI`（本地控制面、Webhook 接入、Dashboard API）。
- 数据层：`Postgres + SQLAlchemy + Alembic`。
- 调度：事件驱动优先，`APScheduler/cron` 兜底。
- 可观测性：结构化日志 + `OpenTelemetry/Prometheus`。

3. 平台能力抽象：
- 核心层（跨平台）：Perception、Context Space、Policy Gate、Conflict Arbiter、State Machine。
- 适配层（平台相关）：通知、系统权限、开机自启、系统集成。
- 建议目录：`platform/adapters/macos`、`platform/adapters/windows`、`platform/adapters/mobile-client`。

4. macOS 首发建议：
- 常驻方式：`launchd`。
- 系统通知与能力桥接：通过 macOS 平台适配器实现（与核心逻辑隔离）。
- 先实现“后台运行 + 定时简报 + 确认动作入口”闭环，再扩展更多系统集成。

5. 可行性结论：
- Python 方案可行且匹配当前架构复杂度，具备快速迭代与跨平台扩展优势。

## 本地开发启动（macOS，增量 v1.6）

Steward 当前默认采用项目级独立虚拟环境 `.venv`，避免污染系统 Python 依赖。

1. 初始化环境：
- 运行 `make bootstrap`（会创建 `.venv`、安装 `uv` 到该虚拟环境、同步依赖、安装 pre-commit）。
- 首次初始化会自动生成 `config/model.yaml`（来自 `config/model.example.yaml` 模板）。

2. 检查环境：
- 运行 `make doctor`，确认 Python/uv 可用；若未安装 Docker Desktop，会提示但不阻断非数据库开发。

3. 配置模型（必填）：
- 编辑 `config/model.yaml`，至少填写 `model.api_key`（或配置 `model.api_key_env` 并提供对应环境变量）。
- 未完成模型配置时，服务会在启动阶段直接失败（不再提供“未配置模型也可运行”的路径）。

4. 启动本地依赖：
- 完整真实执行模式建议：`docker compose up -d`（同时启动 Postgres + Redis）。
- Docker 不是必须；也可使用本机/远程 Postgres、Redis，并通过环境变量配置。
- 初始化数据库：`make upgrade`。

5. 启动 API 服务：
- 运行 `make run`，默认监听 `127.0.0.1:8000`。
- Dashboard 页面：`http://127.0.0.1:8000/dashboard`。

6. 启动执行 Worker（真实自动执行必需）：
- 运行 `make worker`（对应命令 `steward-worker`）。
- 当 `STEWARD_EXECUTION_ENABLED=true` 时，`gate_result=auto` 将进入 Celery 队列异步执行。

7. 质量与测试：
- 运行 `make lint`（ruff + mypy + 模块注释守卫）。
- 运行 `make test`（pytest）。

8. 多渠道感官接入（Webhook）：
- 邮件：`POST /api/v1/webhooks/email`
- 聊天：`POST /api/v1/webhooks/chat`
- 日历：`POST /api/v1/webhooks/calendar`
- 屏幕传感器：`POST /api/v1/webhooks/screen`
- MCP 桥接：`POST /api/v1/webhooks/mcp/{server}`
- 可选安全头：`x-steward-webhook-token`（当环境变量配置了对应 secret 时必填）。

9. 真实 Provider 适配器（签名/字段校验 + 反压）：
- Slack：`POST /api/v1/webhooks/providers/slack`（`X-Slack-Request-Timestamp` + `X-Slack-Signature`）。
- GitHub：`POST /api/v1/webhooks/providers/github`（`X-Hub-Signature-256` + `X-GitHub-Event` + `X-GitHub-Delivery`）。
- Gmail（Pub/Sub push）：`POST /api/v1/webhooks/providers/gmail`（`Authorization: Bearer <token>` 可选强校验）。
- Google Calendar：`POST /api/v1/webhooks/providers/google-calendar`（`X-Goog-Channel-Token` 校验）。
- 反压策略：Provider 维度并发上限、速率窗口、dedup TTL（由 `STEWARD_WEBHOOK_BACKPRESSURE_*` 配置）。

9.1 GitHub issue 自动回复（Agent 化，增量）：
- 规划阶段不再使用固定模板字符串，改为通过模型生成 `add_issue_comment.body`。
- 回复生成输入包含：issue 标题/正文/最近评论 + 本地仓库上下文（README/README_CN/agent）。
- 输出约束：中英双语、包含“问题理解 + 当前能力 + 下一步建议”。
- 防循环策略：`issue_comment` 事件只跳过“当前 token 对应账号自己发出的评论”，用户评论仍可触发处理。

9.2 密钥管理约束（发布前检查）：
- `.env`、真实 token、真实 webhook secret 禁止入库。
- `.env.example` 仅保留变量占位与示例值。
- `config/integrations.runtime.json` 若包含真实密钥，需轮换后再处理发布。

10. macOS 托盘壳层（Menu Bar）：
- 已提供命令：`steward-menubar`。
- 启动前确认后端服务已运行在 `http://127.0.0.1:8000`（可通过 `STEWARD_MENUBAR_BASE_URL` 覆盖）。
- 托盘可直接查看待确认计划并一键 `confirm/reject`。
- 托盘会在“新增待确认计划 / 新增冲突 / 后端连接异常恢复”时触发 macOS 系统通知（需系统通知权限）。

11. Dashboard 浏览器弹窗：
- 打开 `http://127.0.0.1:8000/dashboard` 后，浏览器会请求通知权限。
- 授权后，页面轮询检测到“新增待确认计划 / 新增冲突”会触发浏览器通知。
- “待确认计划”卡片会调用模型生成一句人话摘要（将执行什么 + 主要风险），便于快速确认/拒绝。

12. 本地屏幕传感器（跨平台）：
- 启动命令：`steward-screen-sensor`。
- 该传感器会根据当前系统自动选择实现（macOS / Windows / Linux），周期读取前台应用/窗口标题，并上报到 `/api/v1/webhooks/screen`。
- 可选环境变量：
  - `STEWARD_SCREEN_SENSOR_BASE_URL`（默认 `http://127.0.0.1:8000`）
  - `STEWARD_SCREEN_SENSOR_INTERVAL_SECONDS`（默认 `8`）
  - `STEWARD_SCREEN_SENSOR_HTTP_TIMEOUT_SECONDS`（默认 `35`，用于等待后端处理与模型路由）
  - `STEWARD_SCREEN_WEBHOOK_TOKEN`（若配置了 screen webhook secret，需同步设置）
  - `STEWARD_SCREEN_SENSOR_PLATFORM`（可选，手动指定 `darwin|windows|linux`）
- 权限/依赖注意：
  - macOS：首次运行若提示无权限，请在系统设置中为终端/运行器授予“辅助功能（Accessibility）”权限。
  - Linux：默认使用 `xprop`，回退 `xdotool`；Wayland 场景通常需要 X11 bridge（存在 `DISPLAY`）。

13. 能力管理中心（MCP + Skill，第一性原理）：
- Dashboard 提供“能力管理中心”，支持自定义 MCP Server、按项配置 Skill、以及自然语言批量启停。
- 主入口 API：`GET /api/v1/integrations`、`POST /api/v1/integrations/nl`、`POST /api/v1/integrations/mcp/{server}/configure|enable|disable`、`POST /api/v1/integrations/skills/{skill}/configure|enable|disable`。
- 兼容层 API：`/api/v1/skills/*` 仍保留，但仅作为 facade，状态与 integrations 共用同一来源。
- 所有变更写入 `config/integrations.runtime.json` 并立即生效（含 `config/custom_providers/mcp_servers/skills`）。

14. 自然语言提交事件：
- Dashboard 的“自然语言提交事件”只需输入一句话，不再要求手工填写 source_ref/entities。
- 后端接口：`POST /api/v1/events/ingest-nl`，会先结构化再进入统一执行闭环。

15. 运行日志后台界面：
- Dashboard 新增“运行日志”面板，展示最近事件与决策流（事件入链、门禁判定、状态迁移）。
- 也可直接调用接口：`GET /api/v1/dashboard/logs`。
- 完整快照接口仍为：`GET /api/v1/dashboard/snapshot`（含 `recent_logs`）。

16. 执行结果中心（双语 + 记录可打开）：
- Dashboard 新增入口：`/dashboard/executions`，聚合展示 dispatch + step attempts。
- 执行结果接口支持语言参数：`GET /api/v1/dashboard/executions?limit=50&lang=zh|en`。
- 页面优先展示人话摘要（状态、触发原因、步骤说明、失败原因），原始返回折叠展示。
- 对 `manual.record_note` 步骤新增记录读取接口：`GET /api/v1/dashboard/records/{filename}`，可直接打开保存的 markdown 记录。

## 执行运行时与嵌入式改造（增量 v1.7）

本增量将“计划与执行”从同步占位链路升级为可恢复、可重试、可审计的真实执行链路，并在当前仓库内完成嵌入（非另起项目）。

1. 执行运行时：
- 引入 `Celery + Redis` 异步执行底座。
- `Action Runner` 从“同步直接执行”改为“门禁后分发到队列”。
- 新增 worker 启动命令：`steward-worker`（`make worker`）。

2. 数据模型增量：
- `action_plans` 新增 `execution_status/current_step/last_error/dispatch_id`。
- 新增 `execution_dispatches`、`execution_attempts`，记录分发与步骤尝试。
- 新增 `connector_specs`、`connector_instances`、`connector_sync_states`，承载声明式连接器运行时状态。

3. 规划层嵌入：
- 将 `third_party/superpowers` 作为规划/执行规范资产来源。
- 在 `src/steward/planning/` 中新增 `SuperpowersAssets`、`PlanCompiler`、`ExecutionPolicy`。
- 约束：superpowers 只提供规则文本，不直接执行外部动作。

4. 连接器运行时：
- 新增 `src/steward/connectors_runtime/`，采用声明式 `config/connectors/*.yaml` 做动作契约校验。
- 未真实实现能力不得进入自动执行路径；不再允许 `noop/placeholder` 执行。

## 路线图（增量 v1.7 -> v1.8）

1. Phase A（已完成）：
- Celery/Redis 执行链路接入。
- 执行审计表与分发状态落库。

2. Phase B（已完成）：
- Superpowers 规划资产嵌入。
- Plan 编译与执行策略校验落地。

3. Phase C（进行中）：
- 将更多 connector 的 pull/push 逻辑统一迁移到声明式运行时。
- 增强 connector state/cursor 的增量同步策略。

4. Phase D（计划中）：
- 执行层压测与故障注入（重试风暴、队列积压、外部 API 限流）。
- Dashboard 已增加执行结果页面（步骤级明细、人话摘要、中英文双语、记录打开入口）。
- 后续继续补齐执行队列深度、失败重试趋势等聚合可视化。

5. Phase E（计划中）：
- 发布切换策略与回滚剧本固化（分 connector 灰度启用）。
- 补齐生产环境告警阈值与 SLO 基线。

## Context Space 生命周期与退化防护（增量 v0.9）

为防止状态爆炸与空间碎片化，Steward 对 Context Space 采用显式生命周期管理。

1. 生命周期状态：`active -> dormant -> parked -> archived`（均可被复活）。
2. Pin 机制：存在截止时间、未完成承诺、WAITING 依赖的空间必须 `pinned`，优先进入候选集。
3. 复活优先：新事件到来时，先匹配历史空间并尝试复活，再允许创建 `NEW`。
4. 防碎片规则：若新建空间与历史空间高相似，自动合并或改为复活旧空间。
5. 归档不等于遗忘：`archived` 仅降低召回优先级，不从知识库删除。

### 推荐复活触发条件（增量 v0.9）

- 命中强锚点：`repo/issue/thread_id/goal_id`。
- 命中承诺语义：如“PRD 好了吗”“上次那个 bug 怎么样”。
- 命中到期窗口：`due_at` 临近时自动提升该空间召回权重。

## 双层决策规则（增量 v0.1）

Steward 的规则分为两层，避免“感知即执行”或“过度打扰”：

1. 触发层（Trigger Layer）：任何信号源都可以触发候选任务或候选动作（包括屏幕信号）。
2. 执行层（Execution Layer）：系统基于风险、置信度、策略门禁决定自动执行、进入简报、或请求用户确认。

## 打扰预算（增量 v0.1）

- 默认打扰预算：`10 次/天`。
- 用户可按个人偏好调整预算（例如按工作日/周末、会议时段动态调整）。
- 打扰预算主要用于控制实时中断；未触发中断的事项会进入定时简报。

## 高风险自动动作门禁（增量 v0.1）

高风险动作允许自动执行，但必须通过更严格门禁。建议最小门禁如下：

1. 用户显式开启高风险自动执行策略。
2. 达到高置信度阈值（例如 `>= 0.92`）。
3. 满足多源交叉验证（至少两个独立信号源一致，屏幕可作为其中之一）。
4. 动作可回滚，或提供短暂撤销窗口。
5. 动作类型在白名单内，且有完整审计记录。
6. 绝对不可逆动作必须人工确认，禁止静默自动执行（不可配置绕过）。

### 动作可逆性语义约定（Reversibility，增量 v0.6）

- `reversible`：可完全回滚，允许在门禁通过后自动执行。
- `undo_window`：不可完全回滚，但支持有限撤销窗口；仅在窗口内可撤销。
- `irreversible`：绝对不可逆，必须人工点击确认后执行，禁止静默自动执行。

## 无感常驻后台（增量 v0.2）

Steward 默认以常驻后台运行模式工作，目标是“持续在线、低打扰、可追责”。

- 常驻后台：7x24 运行，异常退出自动拉起。
- 无感优先：默认不弹窗，只有命中执行层打断条件时才实时提醒。
- 批量汇报：常规事项进入定时简报，减少上下文切换成本。

## 执行框架（增量 v0.2）

在“感知 -> Context Space -> 候选任务”之后，执行侧采用统一流水线：

1. Perception Inbox：接收所有候选任务与候选动作。
2. Planner：将候选任务转为可执行 ActionPlan（可多步）。
3. Conflict Arbiter：检测资源冲突与语义冲突，输出合并/串行/重规划/升级策略。
4. Policy Gate：基于风险、置信度、多源一致性与打扰预算进行执行判定。
5. Action Runner：调用 GitHub / 邮件 / 聊天 / skill / 本地工具执行动作。
6. Verifier：执行后校验结果，不一致则告警、重试或回滚。
7. Audit & Brief：记录决策依据与执行轨迹，汇总为简报。

## 简报示例（增量 v1.4）

以下示例展示“定时简报”作为用户与 Steward 的主要交互界面：

```md
Steward Brief | 2026-03-01 18:30 (Asia/Shanghai)
周期：14:30 - 18:30
打扰预算：2 / 10（今日）
整体状态：稳定（无关键故障）

1) 已自动完成（3）
- [Low][Reversible] GitHub Issue #128 已补充复现步骤并打上 `needs-triage`。
- [Low][Reversible] 邮件线程 “会议纪要” 已归档并提取 2 条待办。
- [Low][Reversible] Context Space `SPACE_17` 与 `SPACE_23` 已自动合并（重复空间）。

2) 正在等待（2）
- [Waiting] PR #42 等待 reviewer 回复，超时阈值：2026-03-02 10:00。
- [Waiting] 供应商报价邮件等待对方回执，已设置 24h 超时提醒。

3) 冲突与风险（1）
- [Conflicted][Medium] 两个计划都尝试修改 `github:issue:42` 状态。
  建议：采用 `serialize`（先执行 Plan A，再重规划 Plan B）。

4) 需要你确认（2）
- [High][Irreversible] 是否发送对外承诺邮件《PRD 本周五交付》？
  选项：`确认发送` | `改成草稿` | `取消`
- [Medium] 是否将 “前端崩溃修复” 优先级从 P2 提升至 P1？
  选项：`提升` | `保持`

5) 能力安装建议（不绕过打扰预算）
- 检测到缺少 Jira 连接器，是否一键授权安装？
  选项：`授权安装` | `稍后提醒` | `忽略`

6) 个性化反馈入口
- 你本周期手动确认率较高（4/5），建议保持当前打扰预算 `10`。
- 你可反馈：`太打扰` / `太保守` / `刚好`，Steward 将用于后续个性化调优。
```

### 简报交互原则（增量 v1.4）

- 高风险且不可逆动作必须出现在“需要你确认”分区。
- 能力安装建议默认只出现在定时简报，不触发实时打断。
- 冲突项必须展示冲突对象、建议策略与可选动作。
- 每条建议都应给出可执行选项，避免只给结论不给操作。

## 等待态轻量架构（Postgres 状态机 + Webhook/事件总线，增量 v0.7）

Steward 对 `WAITING` 任务采用“落库挂起 + 事件恢复”机制，减少常驻计算开销并支持跨天等待。

1. 进入 `WAITING`：`ActionPlan` 落库后释放执行进程，注册 `resume_trigger` 规则。
2. 事件到达：Perception 收到 Webhook/总线事件后，先标准化为 `match_key`。
3. 精准匹配：查询等待表，命中 `state='WAITING'` 且 `match_key` 匹配的任务。
4. 恢复执行：命中后原子迁移 `WAITING -> GATED -> RUNNING`。
5. 超时兜底：轻量 Cron 扫描 `wait_timeout_at`，超时任务回到 `GATED` 做升级处理。

### 推荐数据表（增量 v0.7）

1. `action_plans`：状态机主表（`state`, `wait_timeout_at`, `version`）。
2. `waiting_triggers`：等待触发器（`plan_id`, `match_key`, `status`, `expires_at`）。
3. `events`：事件事实表（`source`, `event_type`, `match_key`, `dedup_key`）。

### 匹配与调度约束（增量 v0.7）

- `match_key` 必须可索引，避免全表扫描。
- 状态迁移必须事务化，避免重复唤醒。
- Cron 仅做兜底，不替代事件驱动。

## 冲突检测与解决（增量 v1.2）

当多个 Context Space 或 ActionPlan 对同一资源提出竞争性操作时，Steward 通过 `Conflict Arbiter` 进行冲突治理。

1. 双阶段检测：
- Plan-time：`Planner` 生成 `ActionPlan` 后立即做冲突检测。
- Commit-time：执行前再次检测，防止并发写入导致脏冲突。

2. 冲突类型：
- 资源冲突：两个计划同时操作同一 `resource_key`（如同一 Issue 状态）。
- 语义冲突：两条简报建议在目标上互斥（如“关闭 Issue”与“保持开放并继续跟进”）。

3. 解决策略（按顺序尝试）：
- `merge`：可兼容操作进行合并执行。
- `serialize`：同一资源的写操作串行化。
- `replan`：冲突失败方基于最新状态重规划。
- `escalate`：不可合并且高风险/不可逆时进入人工确认。

4. 安全约束：
- `irreversible` 冲突不得自动决议，必须人工确认。
- 升级到人工确认时，输出单一冲突卡片，避免双重矛盾简报。

## 运行策略（增量 v0.2）

为实现“无感”，Steward 采用以下默认运行策略（可配置）：

- 默认打扰预算：`10 次/天`（用户可改）。
- 简报窗口：默认每 `4 小时` 汇总一次（可调整）。
- 兜底轮询周期：默认 `5 分钟`（事件驱动优先，轮询仅兜底）。
- 高风险自动执行撤销窗口：默认 `60 秒`（若动作支持撤销）。
- 静默时段：会议中或专注时段仅允许最高优先级打断。
- 个性化调优：预算与优先级可基于用户反馈做渐进式学习（不突破安全硬约束）。

### 屏幕信号降噪策略（增量 v0.5）

- 事件化采集：只采集窗口切换、错误提示、选中文本、符号跳转等高价值信号。
- 窗口聚合：按 30-90 秒滑动窗口聚合屏幕变化，避免逐帧入队。
- 去重限流：相同摘要在短时间内不重复写入。
- 前台优先：仅处理当前前台相关应用，后台窗口默认忽略。

## 稳定性与安全底线（增量 v0.2）

- 幂等执行：同一动作具备去重键，避免重复执行。
- 故障恢复：任务队列支持重试与死信队列（DLQ）。
- 游标持久化：各信号源增量同步状态可恢复。
- 最小权限：连接器按最小 scope 授权，默认只读起步。
- 审计可追溯：每次自动执行都记录输入信号、判定路径、动作结果。

## 可观测性与运维（增量 v1.1）

Steward 除审计日志外，还需要系统级可观测性，用于运行监控、故障告警和用户状态可见。

1. 指标监控（Metrics）：
- Context Space 数量与增长趋势（按状态分桶：active/dormant/parked/archived）。
- Gate 通过率（`auto|brief|confirm|blocked` 占比）与变化趋势。
- LLM 路由延迟（P50/P95/P99）与失败率。
- WAITING 队列规模、平均等待时长、超时率。
- 自动执行成功率、回滚率、重试率。
- 冲突率（每百个计划中的冲突数）与冲突解决耗时。

2. 告警机制（Alerts）：
- 死信队列（DLQ）堆积超过阈值触发告警。
- 连接器健康检查连续失败触发告警并自动降级。
- LLM 延迟或错误率持续超阈值触发告警。
- Context Space 增长异常（疑似状态爆炸）触发告警。

3. 用户可见 Dashboard：
- 运行总览：当前状态、吞吐、延迟、错误。
- 任务总览：NEW/WAITING/RUNNING/CONFLICTED/SUCCEEDED 数量。
- 风险与门禁：不同 gate_result 占比、人工确认占比。
- 个性化效果：打扰预算利用率、反馈采纳率、策略更新记录。
- 解释与追踪：最近 N 次关键决策的判定路径与证据。

### 观测 SLO 建议（增量 v1.1）

- 事件入库到路由完成 P95 < 3s。
- WAITING 超时处理延迟 P95 < 60s。
- 日常误告警率 < 5%。
- Dashboard 数据新鲜度延迟 < 30s。

## 用户反馈闭环与个性化（增量 v1.0）

Steward 将用户反馈视为一等输入，形成“决策 -> 反馈 -> 策略更新 -> 下次决策”的持续学习闭环。

1. 反馈采集：对每次自动执行、优先级调整、安装建议记录显式反馈。
2. 在线学习：关键负反馈（例如否决自动执行）可立即影响同类决策门槛。
3. 离线学习：每日批处理更新个性化偏好（预算、优先级、路由偏好）。
4. 安全优先：学习结果不能绕过不可逆动作的人工确认规则。

### 三个核心学习规则（增量 v1.0）

1. 用户否决自动执行：
- 将该样本写入负反馈集，降低同类 Action 的自动执行分。
- 连续命中阈值后，将同类动作从 `auto` 降级为 `confirm`。
- 不直接删除能力，只调整自治等级与触发阈值。

2. 用户手动提升优先级：
- 提取相似特征（来源、意图、实体类型、对方角色、截止时间）。
- 为相似任务增加优先级先验分，缩短进入简报/提醒的延迟。
- 采用衰减机制，避免一次性操作永久放大。

3. 打扰预算长期用不完：
- 计算预算利用率与反馈质量（是否“打扰得值”）。
- 连续低利用率时，按小步长自动下调预算或合并提醒窗口。
- 连续高价值确认时，可小步上调预算上限（仍受 floor/ceiling 限制）。

### 学习防护栏（增量 v1.0）

- 先影子后生效：新策略先 shadow 观察，再逐步生效。
- 最小样本门槛：样本数不足不更新策略。
- 可解释可回滚：每次策略更新可追溯、可一键回退。
- 不可逆保护：`irreversible` 动作永不被个性化学习改为静默执行。

## 核心数据模型（增量 v0.3）

以下为最小可实现模型，优先保证统一、可审计、可扩展：

1. `ContextEvent`
- `event_id`：全局唯一 ID。
- `source`：`github|email|chat|calendar|screen|local`。
- `source_ref`：原始来源引用（如 message_id、issue_id）。
- `occurred_at`：事件发生时间。
- `actor`：事件相关人或系统主体。
- `summary`：标准化摘要。
- `confidence`：感知置信度（0-1）。
- `raw_ref`：原始数据定位引用（不要求保存全文）。

2. `ContextSpace`
- `space_id`：上下文空间 ID。
- `focus_type`：`project|goal|commitment`。
- `focus_ref`：聚焦对象引用（如 repo、issue、目标 ID）。
- `entity_set`：关联实体集合（人、仓库、议题、文件等）。
- `evidence_events`：支撑该空间的事件 ID 列表。
- `space_score`：空间置信评分（0-1）。
- `state`：`active|dormant|parked|archived`。
- `is_pinned`：是否置顶保活。
- `pin_reason`：置顶原因（deadline、open_commitment、waiting_dependency）。
- `due_at`：承诺或目标截止时间（可为空）。
- `open_commitments_count`：未完成承诺数量。
- `last_reactivated_at`：最近一次复活时间（可为空）。

3. `TaskCandidate`
- `task_id`：候选任务 ID。
- `derived_from`：`ContextSpace` 或事件簇 ID。
- `intent`：任务意图（回复、跟进、审批、安排等）。
- `priority`：优先级（P0-P3）。
- `risk_level`：`low|medium|high`。
- `impact_score`：影响评分（0-100）。
- `urgency_score`：紧急评分（0-100）。
- `blocking_on`：是否依赖外部回复/外部系统结果（可为空）。

4. `ActionPlan`
- `plan_id`：执行计划 ID。
- `task_id`：关联任务 ID。
- `steps`：可执行步骤列表。
- `rollback`：回滚步骤或撤销策略。
- `reversibility`：`reversible|undo_window|irreversible`。
- `requires_confirmation`：是否需要用户确认。
- `wait_condition`：进入挂起态的条件（如“等待对方回复”）。
- `resume_trigger`：恢复执行触发器（新回复、状态更新、人工唤醒）。
- `wait_timeout_at`：挂起超时时间。
- `on_wait_timeout`：超时策略（提醒、升级、关闭）。
- `expires_at`：计划过期时间。

5. `DecisionLog`
- `decision_id`：决策 ID。
- `plan_id`：关联执行计划 ID。
- `gate_result`：`auto|brief|confirm|blocked`。
- `state_from`：状态迁移起点。
- `state_to`：状态迁移终点。
- `reason`：判定原因（规则命中、阈值、预算情况）。
- `executed_at`：执行时间。
- `outcome`：`succeeded|failed|rolled_back`。

6. `WaitingTrigger`
- `trigger_id`：触发器 ID。
- `plan_id`：关联 `ActionPlan`。
- `match_key`：事件匹配键（例如 `github:issue:42:updated`）。
- `trigger_status`：`active|consumed|expired`。
- `expires_at`：触发器过期时间。

7. `FeedbackEvent`
- `feedback_id`：反馈 ID。
- `decision_id`：关联 `DecisionLog`。
- `plan_id`：关联 `ActionPlan`。
- `feedback_type`：`approve|reject|edit_priority|snooze|accept_install|decline_install`。
- `old_value`：反馈前值（可为空）。
- `new_value`：反馈后值（可为空）。
- `note`：用户补充说明（可为空）。
- `created_at`：反馈时间。

8. `UserPreferenceProfile`
- `user_id`：用户 ID。
- `interruption_budget_target`：个性化预算目标值。
- `interruption_budget_floor`：预算下限。
- `interruption_budget_ceiling`：预算上限。
- `priority_profile`：优先级偏好参数（按任务特征）。
- `autonomy_profile`：自治等级偏好参数（按动作类型）。
- `updated_at`：最近更新时间。

9. `MetricSnapshot`
- `metric_id`：指标记录 ID。
- `metric_name`：指标名（如 `gate_pass_rate_auto`）。
- `metric_labels`：标签（source/model/connector 等）。
- `value`：指标值。
- `window`：统计窗口（1m/5m/1h/1d）。
- `captured_at`：采样时间。

10. `AlertEvent`
- `alert_id`：告警 ID。
- `alert_type`：`dlq_backlog|healthcheck_failure|llm_latency|space_growth_anomaly`。
- `severity`：`info|warning|critical`。
- `status`：`firing|acknowledged|resolved`。
- `trigger_value`：触发值。
- `threshold`：阈值。
- `created_at`：告警时间。
- `resolved_at`：恢复时间（可为空）。

11. `PlanEffect`
- `effect_id`：效果记录 ID。
- `plan_id`：关联 `ActionPlan`。
- `resource_key`：资源键（如 `github:issue:42`）。
- `operation`：目标操作（如 `set_status:closed`）。
- `expected_version`：并发校验版本（ETag/updated_at）。
- `reversibility`：`reversible|undo_window|irreversible`。

12. `ConflictCase`
- `conflict_id`：冲突 ID。
- `plan_a_id`：冲突计划 A。
- `plan_b_id`：冲突计划 B。
- `conflict_type`：`resource|semantic`。
- `resolution`：`merge|serialize|replan|escalate`。
- `status`：`open|resolved|dropped`。
- `resolved_by`：`system|user`。
- `created_at`：冲突发现时间。
- `resolved_at`：冲突解决时间（可为空）。

## 策略配置样例（增量 v0.3）

```yaml
policy:
  interruption_budget_per_day: 10
  brief_window_hours: 4
  fallback_polling_minutes: 5
  waiting_default_timeout_hours: 24
  waiting_timeout_action: remind_then_escalate
  quiet_hours:
    enabled: true
    rule: meeting_or_focus_only_p0

risk:
  high_risk_auto_enabled: true
  high_risk_confidence_threshold: 0.92
  require_multi_source_count: 2
  require_rollback_or_undo_window: true
  undo_window_seconds: 60

actions:
  high_risk_whitelist:
    - internal_status_transition
    - schedule_internal_meeting
  irreversible_actions:
    - external_commitment_send
    - payment_or_contract_change
    - delete_external_record
  forbid_silent_execution_for_irreversible: true
  require_manual_click_for_irreversible: true
  always_require_confirmation:
    - external_commitment_send
    - payment_or_contract_change

model:
  deployment_mode: api
  api:
    provider: configurable
    base_url: "https://api.example.com/v1"
    model_router: "top-reasoning-model"
    model_default: "balanced-general-model"
    model_fallback: "fast-fallback-model"
    api_key_env: "STEWARD_MODEL_API_KEY"
    timeout_ms: 12000
    max_retries: 2
    retry_backoff_ms: 500
    circuit_breaker_failures: 5
    circuit_breaker_cooldown_seconds: 30

integration:
  runtime_file: config/integrations.runtime.json
  capability_catalog_file: config/skills_catalog.yaml
  compatibility:
    keep_legacy_provider_webhooks: true
    expose_legacy_skills_api: true
  defaults:
    new_mcp_enabled: false
    new_skill_enabled: false

runtime:
  waiting_engine:
    backend: postgres
    resume_match_mode: indexed_match_key
    timeout_scan_interval_seconds: 60
  event_ingest:
    mode: webhook_first
    bus_fallback_enabled: true

conflict:
  enabled: true
  detect_at_plan_time: true
  detect_at_commit_time: true
  default_resolution_order: [merge, serialize, replan, escalate]
  lock_ttl_seconds: 120
  semantic_conflict_check_for_brief: true
  auto_escalate_on_irreversible_conflict: true

routing:
  context_space_router:
    mode: llm_multiple_choice
    allow_unbounded_space_store: true
    recency_window_hours: 48
    retrieval_candidates_max: 50
    llm_candidates_max: 12
    always_include_pinned: true
    run_resurrection_before_new: true
    output_schema: strict_space_id_or_new
    min_confidence: 0.70

lifecycle:
  context_space:
    states: [active, dormant, parked, archived]
    dormant_after_hours: 48
    parked_after_days: 7
    archive_after_days: 30
    auto_pin_if_open_commitment: true
    auto_pin_if_waiting_dependency: true
    resurrection_enabled: true
    resurrection_similarity_threshold: 0.78

learning:
  enabled: true
  mode: assisted
  min_samples_for_adaptation: 5
  decay_half_life_days: 30
  safe_apply_after_shadow_days: 7
  never_override_irreversible_rules: true
  feedback_loop:
    reject_auto_to_confirm: true
    reject_auto_threshold: 2
    promote_confirm_to_auto_threshold: 5
  priority_personalization:
    enabled: true
    similarity_key: [source, intent, entity_type, counterpart_role]
    manual_priority_boost_weight: 0.25
    max_auto_boost_level: 1
  interruption_budget_auto_tune:
    enabled: true
    target_utilization: 0.75
    floor: 6
    ceiling: 16
    step_per_day: 1
    freeze_on_negative_feedback_spike: true

observability:
  enabled: true
  metrics:
    export_interval_seconds: 15
    retention_days: 30
    track:
      - context_space_count_by_state
      - context_space_growth_rate
      - gate_pass_rate
      - llm_router_latency_p95
      - llm_router_error_rate
      - waiting_queue_size
      - waiting_timeout_rate
      - action_success_rate
      - rollback_rate
  alerts:
    dlq_backlog_threshold: 100
    connector_healthcheck_consecutive_failures: 3
    llm_latency_p95_ms_threshold: 3000
    llm_error_rate_threshold: 0.05
    context_space_growth_anomaly_zscore: 3.0
  dashboard:
    enabled: true
    refresh_seconds: 15
    include_user_view: true
    include_ops_view: true
    show_recent_decisions_count: 50
```

## Skill / MCP 能力接口规范（增量 v1.0）

Steward 当前将外部能力统一抽象为 Capability，落地为两类：`mcp_server` 与 `skill`。

1. 统一标识：MCP 使用 `server`，Skill 使用 `skill`，都采用规范化 id。
2. 统一状态：能力状态字段统一为 `enabled`；MCP 额外包含 `configured`，Skill 包含本机检测字段 `installed`。
3. 统一写入：`configure_*` 接口只写运行时配置，不直接执行外部安装命令。
4. 统一门禁：无论来自 Skill 还是 MCP，执行动作都必须经过 `Policy Gate`。
5. 统一审计：外部能力动作都进入 `DecisionLog`。

## Skill 与 MCP 配置（增量 v1.0）

Steward 的能力配置采用单一真相源设计，不再维护多套状态文件。

1. 主入口：Dashboard“能力管理中心”与 `/api/v1/integrations/*`。
2. 单一状态源：`IntegrationConfigService` 统一管理 `legacy provider + mcp + skill`。
3. 持久化：`config/integrations.runtime.json`（`config/custom_providers/mcp_servers/skills`）。
4. 能力目录：`config/skills_catalog.yaml` 会合并进内置 MCP/Skill 目录。
5. 兼容层：`/api/v1/skills/*` 保留以兼容旧调用，但不再维护独立状态。

## Skill / MCP 生命周期管理（增量 v1.0）

当前实现提供“配置、启用、停用”的显式生命周期管理；自动安装/升级/回滚仍是后续规划。

1. 创建或更新：
   - `POST /api/v1/integrations/mcp/{server}/configure`
   - `POST /api/v1/integrations/skills/{skill}/configure`
2. 启用或停用：
   - `POST /api/v1/integrations/mcp/{server}/enable|disable`
   - `POST /api/v1/integrations/skills/{skill}/enable|disable`
3. 批量自然语言操作：`POST /api/v1/integrations/nl`（例如“启用 github mcp 和 gh-fix-ci skill”）。
4. 状态回显：`GET /api/v1/integrations` 返回完整能力快照。
5. 旧接口映射：`/api/v1/skills/install|toggle|uninstall` 映射到同一 integrations 状态写入。

### 规划项（未默认启用）

- 自动安装与版本升级。
- 健康失败自动回滚。
- 能力市场与签名验证。

## 执行状态机（增量 v0.3）

`NEW -> PLANNED -> GATED -> RUNNING -> (WAITING | CONFLICTED | SUCCEEDED | FAILED | ROLLED_BACK)`

- `NEW`：收到候选任务。
- `PLANNED`：生成执行计划。
- `GATED`：通过执行层门禁判定。
- `RUNNING`：动作执行中。
- `WAITING`：挂起等待外部回复或外部系统结果，不占用实时打扰预算。
- `WAITING -> RUNNING`：收到 `resume_trigger` 或人工恢复后继续执行。
- `WAITING -> GATED`：超过 `wait_timeout_at` 重新进入门禁判定（简报提醒、升级处理或继续等待）。
- `RUNNING|GATED -> CONFLICTED`：检测到资源冲突或语义冲突。
- `CONFLICTED -> GATED`：冲突经 `merge/serialize/replan/escalate` 处理后重新进入门禁判定。
- `SUCCEEDED|FAILED|ROLLED_BACK`：结束态并写入审计。
