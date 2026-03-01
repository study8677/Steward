<p align="center">
  <h1 align="center">🤖 Steward</h1>
  <p align="center">
    <strong>An ambient, proactive agent that handles low-risk work automatically<br>and briefs you only when your judgment is needed.</strong>
  </p>
  <p align="center">
    <a href="./README.md">中文</a> · <a href="./agent.md">Agent Spec</a> · <a href="http://127.0.0.1:8000/dashboard">Dashboard</a>
  </p>
</p>

---

## 💡 Why Steward

Picture yourself playing a grand strategy game — *Hearts of Iron* or *Civilization*. You don't want to manage "the 1st Corps is missing a rifle." You want to **set the strategy** and let the system adapt and execute based on the situation.

Your real work life is the same:

> **80% of your tasks are low-risk, automatable noise.**
> Your attention should be reserved for the **20% that truly require your judgment**.

Steward is your digital chief of staff — it silently monitors emails, GitHub, calendars, chat, and more, proactively identifies and advances your to-dos. **Low-risk tasks get done automatically. You're only interrupted for decisions that matter.**

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🔇 **Ambient** | Runs 24/7 in the background, zero popups by default |
| 🧠 **Multi-Source Perception** | GitHub, email, calendar, chat, screen — all first-class signal sources |
| ⚡ **Autonomous Execution** | Low-risk tasks auto-completed with full audit trail and rollback capability |
| 🛡️ **Policy Gate** | High-risk / irreversible actions require explicit human approval — no override possible |
| 📋 **Periodic Briefs** | Every 4 hours: natural language summary of "what was done, what's pending, what needs your call" |
| 🔌 **Pluggable Connectors** | Slack, Gmail, Google Calendar, MCP — unified connector protocol |
| 🧩 **Conflict Arbiter** | When multiple plans compete for the same resource: auto merge / serialize / escalate |

## 📸 Dashboard Preview

<p align="center">
  <img src="docs/images/dashboard_overview.png" width="100%" alt="Dashboard Overview — KPI cards, pending plans, conflict tickets">
</p>

<p align="center">
  <img src="docs/images/dashboard_connectors.png" width="100%" alt="Connector Health & Natural Language Input">
</p>

<p align="center">
  <img src="docs/images/dashboard_brief.png" width="100%" alt="LLM-powered Natural Language Brief & Runtime Logs">
</p>

## 🚀 Quick Start

**One command. That's it.**

```bash
git clone https://github.com/user/Steward.git
cd Steward
make start
```

An interactive wizard walks you through setup:

```
╔══════════════════════════════════════╗
║     🤖  Steward Quick Start         ║
╚══════════════════════════════════════╝

✅ Python: Python 3.14.2
✅ Virtual environment created
✅ Dependencies installed

📋 Configure LLM API (required)
  Select your LLM provider:
  1) OpenAI   2) DeepSeek   3) NVIDIA NIM
  4) GLM      5) Moonshot   6) Custom URL

  Enter API Key: ▎

🚀 All set! Starting Steward...
   Dashboard:  http://127.0.0.1:8000/dashboard
```

Just one **API Key** — no Docker, no manual config editing.

> 💡 **Power users**: For PostgreSQL, set `STEWARD_DATABASE_URL` and run `docker compose up -d && make upgrade`.

## 🏗️ Architecture

```
Signal Sources (GitHub / Email / Calendar / Screen / MCP)
         │
         ▼
   ┌─────────────┐
   │  Perception  │  ← Webhooks / Polling / Screen Sensor
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │ Context Space│  ← Cross-source aggregation & entity resolution
   └──────┬──────┘
          │
          ▼
   ┌─────────────┐
   │ Policy Gate  │  ← Risk assessment, confidence, interruption budget
   └──────┬──────┘
          │
     ┌────┴────┐
     ▼         ▼
  Auto-exec  Ask User
     │         │
     ▼         ▼
   ┌─────────────┐
   │ Brief & Audit│  ← NL summaries, full decision trace
   └─────────────┘
```

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.14 + asyncio |
| API | FastAPI + Uvicorn |
| Data | SQLite (default) / PostgreSQL + SQLAlchemy + Alembic |
| Scheduling | APScheduler (event-driven first, polling as fallback) |
| Models | Any OpenAI-compatible API |
| Observability | structlog + OpenTelemetry + Prometheus |

## 📁 Project Structure

```
steward/
├── api/              # FastAPI routes (REST + Webhooks)
├── core/             # Config, logging, model layer
├── domain/           # Enums, schemas, domain models
├── infra/            # Database, migrations
├── connectors/       # GitHub / Email / Calendar / MCP connectors
├── services/         # Core logic (policy gate, briefs, conflict arbiter)
├── runtime/          # Scheduler, state machine
├── macos/            # macOS menu bar & screen sensor
└── ui/               # Dashboard frontend
```

## 📖 Learn More

- **[agent.md](./agent.md)**: The full design specification (800+ lines) — first-principles derivation of Context Space, Policy Gate, Conflict Arbiter, State Machine, personalized learning, and every other mechanism.

## 🤝 Contributing

Issues and PRs welcome. Please read [agent.md](./agent.md) first to understand the design philosophy.

```bash
make lint    # Code linting
make test    # Run tests
make format  # Code formatting
```

## 📄 License

[MIT](./LICENSE)
