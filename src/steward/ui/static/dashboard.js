// I18n Data
const i18n = {
  zh: {
    title: "Steward Brief Hub",
    subtitle: "把高频噪音交给系统，把决策时间留给你。",
    last_updated: "最后刷新：",
    btn_integrations: "信息源管理",
    btn_refresh: "立即刷新",
    connectors: "连接器健康",
    tell_steward: "告诉 Steward (Cmd/Ctrl + K)",
    placeholder: "描述你当前要处理的真实事项。按 Enter 提交，Shift+Enter 换行",
    btn_send: "发送",
    latest_brief: "最新简报",
    runtime_logs: "运行日志",
    integrations_title: "信息源管理",
    integrations_subtitle: "配置外部信息源，扩充上下文边界",
    pending_plans: "待确认计划",
    conflicts: "冲突工单",
    waiting_input: "等待输入",
    no_brief: "暂无简报",
    no_logs: "暂无运行日志",
    no_pending: "暂无待确认计划",
    no_conflict: "当前无开放冲突",
    no_connectors: "暂无连接器状态",
    btn_confirm: "确认执行",
    btn_reject: "拒绝计划",
    test_success: "测试成功",
    test_failed: "测试失败",
    nl_config: "自然语言快速配置",
    btn_apply: "应用",
    kpi_decisions: "决策总数",
    kpi_waiting: "等待中",
    kpi_running: "执行中"
  },
  en: {
    title: "Steward Brief Hub",
    subtitle: "Focus on decisions. Leave the noise to the system.",
    last_updated: "Last updated: ",
    btn_integrations: "Integrations",
    btn_refresh: "Refresh Now",
    connectors: "Connector Health",
    tell_steward: "Tell Steward (Cmd/Ctrl + K)",
    placeholder: "Describe the task you want to handle. Press Enter to submit, Shift+Enter for new line.",
    btn_send: "Send",
    latest_brief: "Latest Brief",
    runtime_logs: "Runtime Logs",
    integrations_title: "Integrations Management",
    integrations_subtitle: "Configure external sources to expand context boundaries.",
    pending_plans: "Pending Clearances",
    conflicts: "Open Conflicts",
    waiting_input: "Waiting for input...",
    no_brief: "No brief available.",
    no_logs: "No runtime logs.",
    no_pending: "No pending plans.",
    no_conflict: "No open conflicts.",
    no_connectors: "No connector status.",
    btn_confirm: "Confirm",
    btn_reject: "Reject",
    test_success: "Test succeeded",
    test_failed: "Test failed",
    nl_config: "Quick NL Config",
    btn_apply: "Apply",
    kpi_decisions: "Decisions",
    kpi_waiting: "Waiting",
    kpi_running: "Running"
  }
};

let currentLang = localStorage.getItem('steward_lang') || 'zh';

function t(key) {
  return i18n[currentLang][key] || key;
}

function applyI18n() {
  document.querySelector('.hero-content h1').textContent = t('title');
  document.querySelector('.hero-content p').textContent = t('subtitle');
  document.getElementById('open-integrations-btn').textContent = t('btn_integrations');
  document.getElementById('refresh-btn').textContent = t('btn_refresh');

  const headers = document.querySelectorAll('article h2');
  if (headers.length >= 5) {
    headers[0].nextElementSibling.id === 'pending-badge' && (headers[0].textContent = t('pending_plans'));
    headers[1].nextElementSibling.id === 'conflict-badge' && (headers[1].textContent = t('conflicts'));
    headers[2].textContent = t('connectors');
    headers[3].textContent = t('tell_steward');
    headers[4].textContent = t('latest_brief');
    headers[5] && (headers[5].textContent = t('runtime_logs'));
  }

  document.getElementById('event-input').placeholder = t('placeholder');
  document.querySelector('#event-form .btn-primary').textContent = t('btn_send');
  document.querySelector('.drawer-header h2').textContent = t('integrations_title');
  document.querySelector('.drawer-header p').textContent = t('integrations_subtitle');
  document.querySelector('.quick-nl-config label').textContent = t('nl_config');
  document.querySelector('.quick-nl-config .btn').textContent = t('btn_apply');
}

// Ensure marked.js is available
if (typeof marked === 'undefined') {
  console.warn("marked.js failed to load. Falling back to plain text.");
}

// Core Elements
const refreshBtn = document.getElementById("refresh-btn");
const lastUpdatedEl = document.getElementById("last-updated");
const kpiCardsEl = document.getElementById("kpi-cards");
const connectorHealthEl = document.getElementById("connector-health");
const pendingListEl = document.getElementById("pending-list");
const pendingBadgeEl = document.getElementById("pending-badge");
const conflictListEl = document.getElementById("conflict-list");
const conflictBadgeEl = document.getElementById("conflict-badge");
const briefMarkdownEl = document.getElementById("brief-markdown");
const runtimeLogsEl = document.getElementById("runtime-logs");
const eventFormEl = document.getElementById("event-form");
const eventInputEl = document.getElementById("event-input");
const eventResultEl = document.getElementById("event-result");

// Drawer Elements
const overlayEl = document.getElementById("integrations-overlay");
const openDrawerBtn = document.getElementById("open-integrations-btn");
const closeDrawerBtn = document.getElementById("close-integrations-btn");
const langSwitchEl = document.getElementById("lang-switch");

let hasInitializedSnapshot = false;
let lastPendingPlanIds = new Set();
let lastConflictIds = new Set();

// --- Init ---
langSwitchEl.value = currentLang;
langSwitchEl.addEventListener('change', (e) => {
  currentLang = e.target.value;
  localStorage.setItem('steward_lang', currentLang);
  applyI18n();
  refreshAll();
});
applyI18n();

// --- Formatting ---
function fmtNow() {
  return new Date().toLocaleTimeString(currentLang === 'zh' ? 'zh-CN' : 'en-US', { hour12: false });
}

// --- Drawer Logic ---
openDrawerBtn.addEventListener('click', () => {
  overlayEl.classList.remove('hidden');
  document.body.style.overflow = 'hidden'; // prevent background scrolling
  if (typeof refreshProviders === 'function') refreshProviders();
});

function closeDrawer() {
  overlayEl.classList.add('hidden');
  document.body.style.overflow = '';
}

closeDrawerBtn.addEventListener('click', closeDrawer);
overlayEl.addEventListener('click', (e) => {
  if (e.target === overlayEl) closeDrawer();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !overlayEl.classList.contains('hidden')) {
    closeDrawer();
  }
});

// --- UI Utilities ---
// Auto-resizing textarea
eventInputEl.addEventListener('input', function () {
  this.style.height = 'auto';
  this.style.height = (this.scrollHeight) + 'px';
});

// Enter to submit (Shift+Enter for newline)
eventInputEl.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (this.value.trim()) eventFormEl.dispatchEvent(new Event('submit'));
  }
});

// Global Keyboard Shortcut: Cmd/Ctrl + K to focus input
document.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault();
    eventInputEl.focus();
  }

  // Y/N shortcuts for the first pending plan
  if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA' && overlayEl.classList.contains('hidden')) {
    const firstPendingBtnGroup = pendingListEl.querySelector('.list-item .item-actions');
    if (firstPendingBtnGroup) {
      if (e.key.toLowerCase() === 'y') {
        const confirmBtn = firstPendingBtnGroup.querySelector('.confirm');
        if (confirmBtn) confirmBtn.click();
      } else if (e.key.toLowerCase() === 'n') {
        const rejectBtn = firstPendingBtnGroup.querySelector('.reject');
        if (rejectBtn) rejectBtn.click();
      }
    }
  }
});

// --- Notifications ---
async function ensureNotificationPermission() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "default") {
    try { await Notification.requestPermission(); } catch (e) { }
  }
}

function notifyBrowser(title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") return;
  try { new Notification(title, { body }); } catch (e) { }
}

// --- Renderers ---
function renderKpis(overview) {
  const entries = [
    [t('pending_plans'), overview.plans_total ?? 0],
    [t('kpi_decisions'), overview.decisions_total ?? 0],
    [t('kpi_waiting'), overview.plans_waiting ?? 0],
    [t('kpi_running'), overview.plans_running ?? 0],
  ];

  kpiCardsEl.innerHTML = entries.map(([label, value]) => `
      <div class="kpi">
        <div class="label">${label}</div>
        <div class="value">${value}</div>
      </div>
    `).join("");
}

function renderConnectorHealth(items) {
  if (!items.length) {
    connectorHealthEl.innerHTML = `<p class="muted text-sm">${t('no_connectors')}</p>`;
    return;
  }
  connectorHealthEl.innerHTML = items.map(item => {
    const klass = item.healthy ? "health-ok" : "health-bad";
    const status = item.healthy ? "OK" : "ERR";
    return `
        <div class="health-chip ${klass}">
          <div class="item-title text-sm">${item.name}</div>
          <div class="item-meta" style="margin:0; font-size:0.75rem">${status} ${item.code ? `(${item.code})` : ''}</div>
        </div>
      `;
  }).join("");
}

async function handlePlanAction(planId, action) {
  const response = await fetch(`/api/v1/plans/${planId}/${action}`, { method: "POST" });
  if (!response.ok) throw new Error(`Action ${action} failed`);
}

function renderPending(items) {
  pendingBadgeEl.textContent = items.length;
  if (!items.length) {
    pendingListEl.innerHTML = `<p class="muted text-sm">${t('no_pending')}</p>`;
    return;
  }

  // Highlight the first one to signify keyboard shortcut availability
  pendingListEl.innerHTML = items.map((item, idx) => `
      <div class="list-item" style="${idx === 0 ? 'border-color: var(--primary); box-shadow: 0 0 0 1px var(--primary-soft);' : ''}" data-plan-id="${item.plan_id}">
        <div style="display:flex; justify-content:space-between;">
            <div class="item-title">Plan ${item.plan_id} ${idx === 0 ? '<span class="badge" style="background:var(--primary-soft); color:#fff; margin-left:8px; font-size:0.7rem;">[Y/N]</span>' : ''}</div>
            <div class="badge ${item.risk_level === 'high' ? 'danger-badge' : ''}">${item.risk_level}</div>
        </div>
        <div class="item-meta">${item.intent} &middot; ${item.state}</div>
        <div class="item-summary">${item.human_summary || "..."}</div>
        <div class="item-actions">
          <button class="btn btn-sm confirm" data-action="confirm">${t('btn_confirm')}</button>
          <button class="btn btn-sm reject" data-action="reject">${t('btn_reject')}</button>
        </div>
      </div>
    `).join("");

  pendingListEl.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const action = btn.dataset.action;
      const planId = btn.closest(".list-item")?.dataset.planId;
      if (!action || !planId) return;

      btn.disabled = true;
      try {
        await handlePlanAction(planId, action);
        await refreshAll();
      } catch (error) {
        alert(error.message);
      }
    });
  });
}

function renderConflicts(items) {
  conflictBadgeEl.textContent = items.length;
  if (!items.length) {
    conflictListEl.innerHTML = `<p class="muted text-sm">${t('no_conflict')}</p>`;
    return;
  }
  conflictListEl.innerHTML = items.map(item => `
      <div class="list-item" style="border-left: 3px solid var(--danger);">
        <div class="item-title">${item.conflict_id} <span class="badge danger-badge">${item.conflict_type}</span></div>
        <div class="item-meta" style="margin-bottom:4px;">Action: ${item.resolution}</div>
        <div class="item-meta" style="font-family:var(--font-mono); font-size:0.8rem;">${item.plan_a_id} vs ${item.plan_b_id}</div>
      </div>
    `).join("");
}

function maybeNotifySnapshot(snapshot) {
  const pendingItems = snapshot.pending_confirmations || [];
  const conflictItems = snapshot.open_conflicts || [];
  const pendingIds = new Set(pendingItems.map(i => String(i.plan_id)));
  const conflictIds = new Set(conflictItems.map(i => String(i.conflict_id)));

  if (!hasInitializedSnapshot) {
    lastPendingPlanIds = pendingIds;
    lastConflictIds = conflictIds;
    hasInitializedSnapshot = true;
    return;
  }

  const newPending = [...pendingIds].filter(id => !lastPendingPlanIds.has(id));
  const newConflicts = [...conflictIds].filter(id => !lastConflictIds.has(id));

  if (newPending.length > 0) notifyBrowser("Steward Clearance Required", `${newPending.length} new plans waiting.`);
  if (newConflicts.length > 0) notifyBrowser("Steward Conflict", `${newConflicts.length} new conflicts detected.`);

  lastPendingPlanIds = pendingIds;
  lastConflictIds = conflictIds;
}

function renderRuntimeLogs(items) {
  if (!items || !items.length) {
    runtimeLogsEl.innerHTML = `<p class="muted text-sm">${t('no_logs')}</p>`;
    return;
  }
  runtimeLogsEl.innerHTML = items.slice(0, 10).map(item => `
      <div class="list-item" style="padding:10px;">
        <div class="item-title text-sm">${item.title || "-"}</div>
        <div class="item-meta" style="font-size:0.75rem; margin-bottom:4px;">${item.timestamp} &middot; ${item.kind || "log"}</div>
        ${item.detail ? `<div class="muted text-xs" style="font-family:var(--font-mono); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.detail}</div>` : ''}
      </div>
    `).join("");
}

async function submitEvent(evt) {
  evt.preventDefault();
  const text = eventInputEl.value.trim();
  if (!text) return;

  const prevText = document.querySelector('#event-form .btn-primary').textContent;
  document.querySelector('#event-form .btn-primary').textContent = '...';
  document.querySelector('#event-form .btn-primary').disabled = true;

  try {
    const response = await fetch("/api/v1/events/ingest-nl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source_hint: "manual" }),
    });
    if (!response.ok) throw new Error("Inject failed");
    const data = await response.json();
    eventResultEl.textContent = `Action triggered! Plan: ${data.plan_id}`;
    eventFormEl.reset();
    eventInputEl.style.height = 'auto'; // reset height
    await refreshAll();
  } catch (err) {
    eventResultEl.textContent = "Error submitting event.";
  } finally {
    document.querySelector('#event-form .btn-primary').textContent = prevText;
    document.querySelector('#event-form .btn-primary').disabled = false;
    setTimeout(() => eventResultEl.textContent = t('waiting_input'), 3000);
  }
}

// --- Data Fetching ---
async function fetchApi(path) {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`HTTP error ${res.status}`);
  return res.json();
}

async function refreshAll() {
  try {
    // 1) 先加载并渲染 snapshot（快速数据库查询，不依赖 LLM）
    const snapshot = await fetchApi("/api/v1/dashboard/snapshot").catch(() => ({}));
    if (snapshot.overview) renderKpis(snapshot.overview);
    if (snapshot.connector_health) renderConnectorHealth(snapshot.connector_health);
    renderPending(snapshot.pending_confirmations || []);
    renderConflicts(snapshot.open_conflicts || []);
    renderRuntimeLogs(snapshot.recent_logs || []);
    maybeNotifySnapshot(snapshot);
    lastUpdatedEl.textContent = `${t('last_updated')} ${fmtNow()}`;

    // 2) 简报异步加载（LLM 串行调用较慢），不阻塞页面渲染
    briefMarkdownEl.innerHTML = `<span style="color:#888">⏳ ${t('brief_loading') || '正在生成简报...'}</span>`;
    fetchApi("/api/v1/briefs/latest").then(brief => {
      const briefText = brief?.markdown || "";
      if (typeof marked !== 'undefined' && briefText) {
        briefMarkdownEl.innerHTML = marked.parse(briefText);
      } else {
        briefMarkdownEl.textContent = briefText || t('no_brief');
      }
    }).catch(() => {
      briefMarkdownEl.textContent = t('no_brief') || '简报加载失败';
    });
  } catch (e) {
    console.error("Refresh failed", e);
  }
}

// Listeners
refreshBtn.addEventListener("click", refreshAll);
eventFormEl.addEventListener("submit", submitEvent);

// Init
ensureNotificationPermission();
refreshAll();
setInterval(refreshAll, 15000);

// --- Integrations (Drawer) Logic Appended ---
const customProviderFormEl = document.getElementById("custom-provider-form");
const customProviderResultEl = document.getElementById("custom-provider-result");
const nlIntegrationFormEl = document.getElementById('integration-form');
const nlIntegrationResultEl = document.getElementById('integration-result');
const integrationManageListEl = document.getElementById("integration-manage-list");
const integrationLastUpdatedEl = document.getElementById("integration-last-updated");

function builtinFields(provider) {
  if (provider === "slack") {
    return [{ key: "slack_signing_secret", label: "Slack signing secret", type: "password" }];
  }
  if (provider === "gmail") {
    return [
      { key: "gmail_pubsub_verification_token", label: "Gmail verification token", type: "password" },
      { key: "gmail_pubsub_topic", label: "Gmail topic", type: "text" },
    ];
  }
  if (provider === "google-calendar") {
    return [
      { key: "google_calendar_channel_token", label: "Calendar channel token", type: "password" },
      { key: "google_calendar_channel_ids", label: "Calendar channel ids (, separated)", type: "text" },
    ];
  }
  if (provider === "screen") {
    return [{ key: "screen_webhook_secret", label: "Screen webhook secret", type: "password" }];
  }
  return [];
}

function fieldTemplate(field) {
  return `
    <label>
      ${field.label}
      <input class="input-sm" type="${field.type}" name="${field.key}" />
    </label>
  `;
}

function renderProviders(items) {
  if (!items || !items.length) {
    integrationManageListEl.innerHTML = `<p class="muted text-sm">${t('no_connectors')}</p>`;
    return;
  }

  integrationManageListEl.innerHTML = items.map((item) => {
    const displayName = item.display_name || item.provider;
    let fields = [];
    if (item.provider_type !== "custom") {
      fields = builtinFields(item.provider);
    }
    const formFields = fields.map(f => fieldTemplate(f)).join("");
    const status = item.configured ? "Ready" : `Missing: ${(item.missing_fields || []).join(", ") || "config"}`;

    return `
      <div class="list-item" data-provider="${item.provider}">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div class="item-title">${displayName}</div>
          <div class="badge ${item.configured ? 'health-ok' : 'danger-badge'}">${status}</div>
        </div>
        <div class="muted text-xs mb-2">id: ${item.provider} | type: ${item.provider_type}</div>
        
        <form class="provider-config-form mt-3" data-provider="${item.provider}">
          <div class="form-grid">${formFields}</div>
          <div class="item-actions mt-3">
            <button type="submit" class="btn btn-sm btn-primary">Save Config</button>
            <button type="button" class="btn btn-sm btn-secondary test-btn" data-provider="${item.provider}">Run Test</button>
          </div>
        </form>
        <p class="status-msg provider-result" data-provider-result="${item.provider}"></p>
      </div>
    `;
  }).join("");

  integrationManageListEl.querySelectorAll("form.provider-config-form").forEach((form) => {
    form.addEventListener("submit", async (evt) => {
      evt.preventDefault();
      const provider = form.dataset.provider;
      const body = {};
      new FormData(form).forEach((val, key) => { if (val.trim()) body[key] = val.trim(); });

      const resultEl = integrationManageListEl.querySelector(`[data-provider-result="${provider}"]`);
      try {
        await fetch(`/api/v1/integrations/${provider}/configure`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
        resultEl.textContent = "Saved.";
        refreshProviders();
      } catch (e) {
        resultEl.textContent = "Failed to save.";
      }
    });
  });

  integrationManageListEl.querySelectorAll("button.test-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const provider = btn.dataset.provider;
      const resultEl = integrationManageListEl.querySelector(`[data-provider-result="${provider}"]`);
      try {
        const res = await fetch(`/api/v1/integrations/${provider}/test`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ summary: `Test ${provider}` }),
        });
        if (!res.ok) throw new Error("Test Failed");
        resultEl.textContent = t('test_success');
        refreshProviders();
      } catch (e) {
        resultEl.textContent = t('test_failed');
      }
    });
  });
}

function refreshProviders() {
  fetchApi("/api/v1/integrations").then(data => {
    renderProviders(data.providers || []);
    integrationLastUpdatedEl.textContent = fmtNow();
  }).catch(e => { });
}

customProviderFormEl.addEventListener("submit", (evt) => {
  evt.preventDefault();
  const form = new FormData(customProviderFormEl);
  const provider = form.get("provider")?.toString().trim();
  if (!provider) return;

  const payload = {
    display_name: form.get("display_name")?.toString().trim(),
    source: form.get("source")?.toString().trim() || "custom",
    webhook_secret: form.get("webhook_secret")?.toString().trim(),
    description: form.get("description")?.toString().trim()
  };

  fetch(`/api/v1/integrations/${encodeURIComponent(provider)}/configure`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
  }).then(() => {
    customProviderResultEl.textContent = "Configured.";
    customProviderFormEl.reset();
    refreshProviders();
  }).catch(() => { customProviderResultEl.textContent = "Failed to configure."; });
});

nlIntegrationFormEl.addEventListener("submit", async (evt) => {
  evt.preventDefault();
  const text = document.getElementById("integration-text").value.trim();
  if (!text) return;
  nlIntegrationResultEl.textContent = "...";
  try {
    const res = await fetch("/api/v1/integrations/nl", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error("Failed");
    nlIntegrationResultEl.textContent = "Applied.";
    refreshProviders();
  } catch (e) {
    nlIntegrationResultEl.textContent = "Error applying config.";
  }
});
