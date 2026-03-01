<p align="center">
  <h1 align="center">🤖 Steward</h1>
  <p align="center">
    <strong>一个无感常驻、主动推进事务的协作 Agent。</strong><br>
    把高频噪音交给系统，把决策时间留给你。
  </p>
  <p align="center">
    <a href="./README_EN.md">English</a> · <a href="./agent.md">Agent Spec</a> · <a href="http://127.0.0.1:8000/dashboard">Dashboard</a>
  </p>
</p>

---

## 💡 为什么做 Steward

想象你在玩一款策略游戏——《钢铁雄心》或《文明》。你不想亲自管理"第一军团少了一支枪"，你想做的是**制定战略**，然后让系统根据战场态势自行执行。

现实工作中的你也是如此：

> **80% 的事务是低风险、可自动化的噪音。**
> 你的注意力应该只花在那 **20% 真正需要你判断的决策**上。

Steward 就是你的数字管家——它静默感知邮件、GitHub、日历、聊天等多源信号，主动识别并推进待办事项，**低风险的事情自动做完，只在关键决策时才打扰你**。

## ✨ 核心特性

| 特性 | 描述 |
|-----|------|
| 🔇 **无感常驻** | 7×24 后台运行，默认不弹窗，只在关键时刻打扰 |
| 🧠 **多源感知** | GitHub、邮件、日历、聊天、屏幕信号——统一接入的一等信号源 |
| ⚡ **自主执行** | 低风险任务自动完成，带审计记录和回滚能力 |
| 🛡️ **策略门禁** | 高风险/不可逆动作必须人工确认，安全底线不可配置绕过 |
| 📋 **定时简报** | 每 4 小时汇总一次，用自然语言告诉你"做了什么、等什么、需要你决定什么" |
| 🔌 **可插拔连接器** | Slack、Gmail、Google Calendar、MCP——通过统一 Connector 协议接入 |
| 🧩 **冲突仲裁** | 多任务竞争同一资源时，自动合并/串行/升级处理 |

## 📸 Dashboard 预览

<p align="center">
  <img src="docs/images/dashboard_overview.png" width="100%" alt="Dashboard 概览 — KPI 卡片、待确认计划、冲突工单">
</p>

<p align="center">
  <img src="docs/images/dashboard_connectors.png" width="100%" alt="连接器健康状态 & 自然语言输入">
</p>

<p align="center">
  <img src="docs/images/dashboard_brief.png" width="100%" alt="LLM 驱动的自然语言简报 & 运行日志">
</p>

## 🚀 快速开始

**只需要一行命令。**

```bash
git clone https://github.com/user/Steward.git
cd Steward
make start
```

终端会交互式引导你完成配置：

```
╔══════════════════════════════════════╗
║     🤖  Steward 一键启动向导        ║
╚══════════════════════════════════════╝

✅ Python: Python 3.14.2
✅ 虚拟环境已创建
✅ 依赖安装完成

📋 配置大模型 API（必填项）
  请选择大模型供应商：
  1) OpenAI   2) DeepSeek   3) NVIDIA NIM
  4) 智谱 GLM  5) Moonshot   6) 自定义 URL

  请输入 API Key: ▎

🚀 一切就绪！正在启动 Steward...
   Dashboard:  http://127.0.0.1:8000/dashboard
```

仅需填入一个 **API Key**，无需 Docker，无需手工编辑配置文件。

> 💡 **进阶用户**：如需使用 Postgres，设置环境变量 `STEWARD_DATABASE_URL` 并运行 `docker compose up -d && make upgrade`。

## 🏗️ 架构概览

```
信号源 (GitHub / 邮件 / 日历 / 屏幕 / MCP)
         │
         ▼
   ┌─────────────┐
   │  感知入口    │  ← Webhook / 轮询 / 屏幕传感器
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │ Context Space│  ← 跨源信号聚合、实体解析
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │  策略门禁    │  ← 风险评估、置信度、打扰预算
   └──────┬──────┘
          │
     ┌────┴────┐
     ▼         ▼
  自动执行   请求确认
     │         │
     ▼         ▼
   ┌─────────────┐
   │  简报 & 审计 │  ← 自然语言总结、完整决策轨迹
   └─────────────┘
```

## 🛠️ 技术栈

| 层 | 技术 |
|---|------|
| 语言 | Python 3.14 + asyncio |
| 服务层 | FastAPI + Uvicorn |
| 数据层 | SQLite（默认）/ PostgreSQL + SQLAlchemy + Alembic |
| 调度 | APScheduler（事件驱动优先，轮询兜底） |
| 模型 | OpenAI 兼容 API（任意供应商） |
| 可观测性 | structlog + OpenTelemetry + Prometheus |

## 📁 项目结构

```
steward/
├── api/              # FastAPI 路由（REST + Webhook）
├── core/             # 配置、日志、模型层
├── domain/           # 枚举、Schema、领域模型
├── infra/            # 数据库、迁移
├── connectors/       # GitHub / Email / Calendar / MCP 连接器
├── services/         # 核心业务逻辑（门禁、简报、冲突仲裁）
├── runtime/          # 调度器、状态机
├── macos/            # macOS 托盘 & 屏幕传感器
└── ui/               # Dashboard 前端
```

## 📖 深入了解

- **[agent.md](./agent.md)**：完整的设计规范（800+ 行），涵盖 Context Space、策略门禁、冲突仲裁、状态机、个性化学习等所有机制的第一性原理推导。

## 🤝 贡献

欢迎提交 Issue 和 PR。请先阅读 [agent.md](./agent.md) 了解设计理念。

```bash
make lint    # 代码检查
make test    # 运行测试
make format  # 代码格式化
```

## 📄 License

[MIT](./LICENSE)
