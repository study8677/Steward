const i18n = {
  zh: {
    title: "Steward Brief Hub",
    subtitle: "把高频噪音交给系统，把决策时间留给你。",
    language_switch: "语言切换",
    last_updated: "最后刷新：",
    btn_integrations: "信息源管理",
    btn_refresh: "立即刷新",
    btn_send: "发送",
    connectors: "连接器健康",
    tell_steward: "告诉 Steward (Cmd/Ctrl + K)",
    input_hint: "Enter 提交，Shift+Enter 换行。使用 Cmd/Ctrl + K 快速聚焦。",
    placeholder: "描述你当前要处理的真实事项。按 Enter 提交，Shift+Enter 换行",
    latest_brief: "最新简报",
    brief_view_now: "立即查看简报",
    brief_loading: "正在生成简报...",
    brief_frequency: "频率",
    brief_content_level: "内容层级",
    brief_save: "保存",
    brief_saved: "简报设置已更新",
    brief_save_failed: "简报设置更新失败",
    brief_waiting: "等待设置",
    brief_load_failed: "简报加载失败",
    level_simple: "简单",
    level_medium: "中等",
    level_rich: "丰富",
    runtime_logs: "运行日志",
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
    kpi_decisions: "决策总数",
    kpi_waiting: "等待中",
    kpi_running: "执行中",
    kpi_total: "计划总量",
    kpi_queue: "队列深度",
    status_ok: "正常",
    status_err: "异常",
    shortcut_hint: "[Y/N]",
    plan_label: "计划 {id}",
    plan_action_failed: "计划操作失败",
    event_submitting: "提交中...",
    event_submit_success: "已触发动作，计划：{id}",
    event_submit_failed: "提交事件失败",
    loading: "加载中...",
    conflict_action_label: "建议动作",
    conflict_relation: "{a} vs {b}",
    log_kind_default: "日志",
    notify_pending_title: "Steward 待确认",
    notify_pending_body: "新增 {count} 个待确认计划",
    notify_conflict_title: "Steward 冲突提醒",
    notify_conflict_body: "新增 {count} 个冲突工单",
  },
  en: {
    title: "Steward Brief Hub",
    subtitle: "Focus on decisions. Leave the noise to the system.",
    language_switch: "Language switch",
    last_updated: "Last updated:",
    btn_integrations: "Integrations",
    btn_refresh: "Refresh Now",
    btn_send: "Send",
    connectors: "Connector Health",
    tell_steward: "Tell Steward (Cmd/Ctrl + K)",
    input_hint: "Press Enter to submit, Shift+Enter for new line. Use Cmd/Ctrl + K to focus quickly.",
    placeholder: "Describe the task you want to handle. Press Enter to submit, Shift+Enter for new line.",
    latest_brief: "Latest Brief",
    brief_view_now: "View Brief Now",
    brief_loading: "Generating brief...",
    brief_frequency: "Frequency",
    brief_content_level: "Detail Level",
    brief_save: "Save",
    brief_saved: "Brief settings updated",
    brief_save_failed: "Failed to update brief settings",
    brief_waiting: "Waiting for settings",
    brief_load_failed: "Failed to load brief",
    level_simple: "Simple",
    level_medium: "Medium",
    level_rich: "Rich",
    runtime_logs: "Runtime Logs",
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
    kpi_decisions: "Decisions",
    kpi_waiting: "Waiting",
    kpi_running: "Running",
    kpi_total: "Total Plans",
    kpi_queue: "Queue Depth",
    status_ok: "OK",
    status_err: "ERR",
    shortcut_hint: "[Y/N]",
    plan_label: "Plan {id}",
    plan_action_failed: "Failed to update plan",
    event_submitting: "Submitting...",
    event_submit_success: "Action triggered, plan: {id}",
    event_submit_failed: "Error submitting event.",
    loading: "Loading...",
    conflict_action_label: "Action",
    conflict_relation: "{a} vs {b}",
    log_kind_default: "log",
    notify_pending_title: "Steward Clearance Required",
    notify_pending_body: "{count} new plans waiting",
    notify_conflict_title: "Steward Conflict",
    notify_conflict_body: "{count} new conflicts detected",
  },
};

let currentLang = localStorage.getItem("steward_lang") || "zh";

function t(key, vars = {}) {
  const table = i18n[currentLang] || i18n.zh;
  const template = table[key] || key;
  return template.replace(/\{(\w+)\}/g, (_, token) => {
    const value = vars[token];
    return value === undefined || value === null ? "" : String(value);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function sanitizeMarkdownForRendering(markdownText) {
  return String(markdownText ?? "")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function isEditableTarget(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    target.isContentEditable
  );
}

if (typeof marked === "undefined") {
  console.warn("marked.js failed to load. Falling back to plain text.");
}

const refreshBtn = document.getElementById("refresh-btn");
const lastUpdatedEl = document.getElementById("last-updated");
const kpiCardsEl = document.getElementById("kpi-cards");
const connectorHealthEl = document.getElementById("connector-health");
const pendingListEl = document.getElementById("pending-list");
const pendingBadgeEl = document.getElementById("pending-badge");
const conflictListEl = document.getElementById("conflict-list");
const conflictBadgeEl = document.getElementById("conflict-badge");
const briefMarkdownEl = document.getElementById("brief-markdown");
const briefViewBtn = document.getElementById("brief-view-btn");
const briefFrequencyEl = document.getElementById("brief-frequency-hours");
const briefContentLevelEl = document.getElementById("brief-content-level");
const briefSettingsSaveBtn = document.getElementById("brief-settings-save-btn");
const briefSettingsStatusEl = document.getElementById("brief-settings-status");
const runtimeLogsEl = document.getElementById("runtime-logs");
const eventFormEl = document.getElementById("event-form");
const eventInputEl = document.getElementById("event-input");
const eventResultEl = document.getElementById("event-result");
const eventSubmitBtn = eventFormEl.querySelector("button[type='submit']");
const eventInputHintEl = document.getElementById("event-input-hint");

const openDrawerBtn = document.getElementById("open-integrations-btn");
const langSwitchEl = document.getElementById("lang-switch");

let hasInitializedSnapshot = false;
let lastPendingPlanIds = new Set();
let lastConflictIds = new Set();
let briefSettingsLoaded = false;
let refreshInFlight = false;
let briefRequestId = 0;

function applyI18n() {
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";

  document.querySelector(".hero-content h1").textContent = t("title");
  document.querySelector(".hero-content p").textContent = t("subtitle");
  document.getElementById("pending-title").textContent = t("pending_plans");
  document.getElementById("conflict-title").textContent = t("conflicts");
  document.getElementById("connectors-title").textContent = t("connectors");
  document.getElementById("tell-title").textContent = t("tell_steward");
  document.getElementById("brief-title").textContent = t("latest_brief");
  briefViewBtn.textContent = t("brief_view_now");
  document.getElementById("logs-title").textContent = t("runtime_logs");

  openDrawerBtn.textContent = t("btn_integrations");
  refreshBtn.textContent = t("btn_refresh");
  eventSubmitBtn.textContent = t("btn_send");
  briefSettingsSaveBtn.textContent = t("brief_save");
  langSwitchEl.setAttribute("aria-label", t("language_switch"));

  eventInputEl.placeholder = t("placeholder");
  eventInputHintEl.textContent = t("input_hint");
  document.getElementById("brief-frequency-label").textContent = t("brief_frequency");
  document.getElementById("brief-content-level-label").textContent = t("brief_content_level");
  document.querySelector('#brief-content-level option[value="simple"]').textContent = t("level_simple");
  document.querySelector('#brief-content-level option[value="medium"]').textContent = t("level_medium");
  document.querySelector('#brief-content-level option[value="rich"]').textContent = t("level_rich");

  lastUpdatedEl.textContent = `${t("last_updated")} --`;
  if (!eventResultEl.textContent.trim()) {
    eventResultEl.textContent = t("waiting_input");
  }
}

function fmtNow() {
  return new Date().toLocaleTimeString(currentLang === "zh" ? "zh-CN" : "en-US", { hour12: false });
}

eventInputEl.addEventListener("input", function onInput() {
  this.style.height = "auto";
  this.style.height = `${this.scrollHeight}px`;
});

eventInputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (eventInputEl.value.trim()) {
      eventFormEl.requestSubmit();
    }
  }
});

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    eventInputEl.focus();
    return;
  }

  if (!isEditableTarget(event.target)) {
    const firstPendingBtnGroup = pendingListEl.querySelector(".list-item .item-actions");
    if (!firstPendingBtnGroup) {
      return;
    }

    const key = event.key.toLowerCase();
    if (key === "y") {
      firstPendingBtnGroup.querySelector(".confirm")?.click();
    } else if (key === "n") {
      firstPendingBtnGroup.querySelector(".reject")?.click();
    }
  }
});

function attachNotificationPermissionOnFirstIntent() {
  if (!("Notification" in window) || Notification.permission !== "default") {
    return;
  }

  const handler = async () => {
    try {
      await Notification.requestPermission();
    } catch (_) {
      // ignore
    }
  };

  ["click", "keydown", "touchstart"].forEach((eventName) => {
    document.addEventListener(eventName, handler, { once: true, passive: true });
  });
}

function notifyBrowser(title, body) {
  if (!("Notification" in window) || Notification.permission !== "granted") {
    return;
  }
  try {
    new Notification(title, { body });
  } catch (_) {
    // ignore
  }
}

async function fetchApi(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`HTTP error ${response.status}`);
  }
  return response.json();
}

async function refreshBriefSettings(force = false) {
  if (briefSettingsLoaded && !force) {
    return;
  }

  try {
    const data = await fetchApi("/api/v1/briefs/settings");
    briefFrequencyEl.value = String(data?.frequency_hours || "4");
    briefContentLevelEl.value = data?.content_level || "medium";
    briefSettingsStatusEl.textContent = t("brief_waiting");
    briefSettingsLoaded = true;
  } catch (_) {
    briefSettingsStatusEl.textContent = t("brief_save_failed");
  }
}

async function saveBriefSettings() {
  const frequencyHours = Number(briefFrequencyEl.value || 4);
  const contentLevel = String(briefContentLevelEl.value || "medium");
  briefSettingsSaveBtn.disabled = true;
  briefSettingsStatusEl.textContent = t("loading");

  try {
    const response = await fetch("/api/v1/briefs/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        frequency_hours: frequencyHours,
        content_level: contentLevel,
      }),
    });
    if (!response.ok) {
      throw new Error("save_failed");
    }

    const data = await response.json();
    briefFrequencyEl.value = String(data?.frequency_hours || frequencyHours);
    briefContentLevelEl.value = String(data?.content_level || contentLevel);
    briefSettingsStatusEl.textContent = t("brief_saved");
    briefSettingsLoaded = true;
    await refreshAll();
  } catch (_) {
    briefSettingsStatusEl.textContent = t("brief_save_failed");
  } finally {
    briefSettingsSaveBtn.disabled = false;
  }
}

function renderKpis(overview) {
  const entries = [
    [t("kpi_total"), overview?.plans_total ?? 0],
    [t("kpi_decisions"), overview?.decisions_total ?? 0],
    [t("kpi_waiting"), overview?.plans_waiting ?? 0],
    [t("kpi_running"), overview?.plans_running ?? 0],
    [t("kpi_queue"), overview?.queue_depth ?? 0],
  ];

  kpiCardsEl.innerHTML = entries
    .map(([label, value]) => {
      const safeLabel = escapeHtml(label);
      const safeValue = escapeHtml(value);
      return `
        <div class="kpi">
          <div class="label">${safeLabel}</div>
          <div class="value">${safeValue}</div>
        </div>
      `;
    })
    .join("");
}

function renderConnectorHealth(items) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) {
    connectorHealthEl.innerHTML = `<p class="muted text-sm">${escapeHtml(t("no_connectors"))}</p>`;
    return;
  }

  connectorHealthEl.innerHTML = list
    .map((item) => {
      const klass = item?.healthy ? "health-ok" : "health-bad";
      const status = item?.healthy ? t("status_ok") : t("status_err");
      const name = escapeHtml(item?.name || "-");
      const code = item?.code ? ` (${escapeHtml(item.code)})` : "";
      return `
        <div class="health-chip ${klass}">
          <div class="item-title text-sm">${name}</div>
          <div class="item-meta health-meta">${escapeHtml(status)}${code}</div>
        </div>
      `;
    })
    .join("");
}

async function handlePlanAction(planId, action) {
  const response = await fetch(`/api/v1/plans/${encodeURIComponent(planId)}/${encodeURIComponent(action)}`, {
    method: "POST",
  });
  if (!response.ok) {
    throw new Error(t("plan_action_failed"));
  }
}

function renderPending(items) {
  const list = Array.isArray(items) ? items : [];
  pendingBadgeEl.textContent = String(list.length);

  if (!list.length) {
    pendingListEl.innerHTML = `<p class="muted text-sm">${escapeHtml(t("no_pending"))}</p>`;
    return;
  }

  pendingListEl.innerHTML = list
    .map((item, idx) => {
      const planIdText = String(item?.plan_id || "-");
      const planId = encodeURIComponent(planIdText);
      const riskLevel = String(item?.risk_level || "unknown");
      const intent = escapeHtml(item?.intent || "-");
      const state = escapeHtml(item?.state || "-");
      const executionStatus = escapeHtml(item?.execution_status || "pending_confirmation");
      const summary = escapeHtml(item?.human_summary || "...");
      const primaryClass = idx === 0 ? " primary-item" : "";
      const riskBadge = riskLevel.toLowerCase() === "high" ? "danger-badge" : "";
      const shortcut = idx === 0 ? `<span class="badge shortcut-badge">${escapeHtml(t("shortcut_hint"))}</span>` : "";
      return `
        <div class="list-item${primaryClass}" data-plan-id="${planId}">
          <div class="item-head">
            <div class="item-title">${escapeHtml(t("plan_label", { id: planIdText }))} ${shortcut}</div>
            <div class="badge ${riskBadge}">${escapeHtml(riskLevel)}</div>
          </div>
          <div class="item-meta">${intent} &middot; ${state} &middot; ${executionStatus}</div>
          <div class="item-summary">${summary}</div>
          <div class="item-actions">
            <button type="button" class="btn btn-sm confirm" data-action="confirm">${escapeHtml(t("btn_confirm"))}</button>
            <button type="button" class="btn btn-sm reject" data-action="reject">${escapeHtml(t("btn_reject"))}</button>
          </div>
        </div>
      `;
    })
    .join("");

  pendingListEl.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      const encodedPlanId = button.closest(".list-item")?.dataset.planId;
      if (!action || !encodedPlanId) {
        return;
      }

      button.disabled = true;
      try {
        await handlePlanAction(decodeURIComponent(encodedPlanId), action);
        await refreshAll();
      } catch (error) {
        eventResultEl.textContent = error instanceof Error ? error.message : t("plan_action_failed");
      } finally {
        button.disabled = false;
      }
    });
  });
}

function renderConflicts(items) {
  const list = Array.isArray(items) ? items : [];
  conflictBadgeEl.textContent = String(list.length);

  if (!list.length) {
    conflictListEl.innerHTML = `<p class="muted text-sm">${escapeHtml(t("no_conflict"))}</p>`;
    return;
  }

  conflictListEl.innerHTML = list
    .map((item) => {
      const conflictId = escapeHtml(item?.conflict_id || "-");
      const conflictType = escapeHtml(item?.conflict_type || "-");
      const resolution = escapeHtml(item?.resolution || "-");
      const relation = escapeHtml(
        t("conflict_relation", {
          a: item?.plan_a_id || "-",
          b: item?.plan_b_id || "-",
        })
      );
      return `
        <div class="list-item conflict-item">
          <div class="item-title">${conflictId} <span class="badge danger-badge">${conflictType}</span></div>
          <div class="item-meta tight">${escapeHtml(t("conflict_action_label"))}: ${resolution}</div>
          <div class="item-meta mono">${relation}</div>
        </div>
      `;
    })
    .join("");
}

function maybeNotifySnapshot(snapshot) {
  const pendingItems = snapshot?.pending_confirmations || [];
  const conflictItems = snapshot?.open_conflicts || [];

  const pendingIds = new Set(pendingItems.map((item) => String(item.plan_id)));
  const conflictIds = new Set(conflictItems.map((item) => String(item.conflict_id)));

  if (!hasInitializedSnapshot) {
    hasInitializedSnapshot = true;
    lastPendingPlanIds = pendingIds;
    lastConflictIds = conflictIds;
    return;
  }

  const newPending = [...pendingIds].filter((id) => !lastPendingPlanIds.has(id));
  const newConflicts = [...conflictIds].filter((id) => !lastConflictIds.has(id));

  if (newPending.length > 0) {
    notifyBrowser(
      t("notify_pending_title"),
      t("notify_pending_body", { count: newPending.length })
    );
  }
  if (newConflicts.length > 0) {
    notifyBrowser(
      t("notify_conflict_title"),
      t("notify_conflict_body", { count: newConflicts.length })
    );
  }

  lastPendingPlanIds = pendingIds;
  lastConflictIds = conflictIds;
}

function renderRuntimeLogs(items) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) {
    runtimeLogsEl.innerHTML = `<p class="muted text-sm">${escapeHtml(t("no_logs"))}</p>`;
    return;
  }

  runtimeLogsEl.innerHTML = list
    .slice(0, 10)
    .map((item) => {
      const title = escapeHtml(item?.title || "-");
      const timestamp = escapeHtml(item?.timestamp || "-");
      const kind = escapeHtml(item?.kind || t("log_kind_default"));
      const detail = item?.detail
        ? `<div class="muted text-xs log-detail">${escapeHtml(item.detail)}</div>`
        : "";
      return `
        <div class="list-item log-item">
          <div class="item-title text-sm">${title}</div>
          <div class="item-meta log-meta-row">${timestamp} &middot; ${kind}</div>
          ${detail}
        </div>
      `;
    })
    .join("");
}

async function submitEvent(event) {
  event.preventDefault();
  const text = eventInputEl.value.trim();
  if (!text) {
    return;
  }

  const prevText = eventSubmitBtn.textContent;
  eventSubmitBtn.textContent = t("event_submitting");
  eventSubmitBtn.disabled = true;
  eventResultEl.textContent = t("loading");

  try {
    const response = await fetch("/api/v1/events/ingest-nl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source_hint: "manual" }),
    });
    if (!response.ok) {
      throw new Error("ingest_failed");
    }

    const data = await response.json();
    eventResultEl.textContent = t("event_submit_success", { id: data.plan_id });
    eventFormEl.reset();
    eventInputEl.style.height = "auto";
    await refreshAll();
  } catch (_) {
    eventResultEl.textContent = t("event_submit_failed");
  } finally {
    eventSubmitBtn.textContent = prevText;
    eventSubmitBtn.disabled = false;
    window.setTimeout(() => {
      eventResultEl.textContent = t("waiting_input");
    }, 3000);
  }
}

function renderBriefMarkdown(briefText) {
  if (!briefText) {
    briefMarkdownEl.textContent = t("no_brief");
    return;
  }

  if (typeof marked === "undefined") {
    briefMarkdownEl.textContent = briefText;
    return;
  }

  try {
    const safeMarkdown = sanitizeMarkdownForRendering(briefText);
    briefMarkdownEl.innerHTML = marked.parse(safeMarkdown);
  } catch (_) {
    briefMarkdownEl.textContent = briefText;
  }
}

async function refreshLatestBrief() {
  const currentBriefRequest = ++briefRequestId;
  briefMarkdownEl.innerHTML = `<span class="loading-hint">⏳ ${escapeHtml(t("brief_loading"))}</span>`;
  try {
    const brief = await fetchApi("/api/v1/briefs/latest");
    if (currentBriefRequest !== briefRequestId) {
      return;
    }
    const briefText = brief?.markdown || "";
    renderBriefMarkdown(briefText);
  } catch (_) {
    if (currentBriefRequest !== briefRequestId) {
      return;
    }
    briefMarkdownEl.textContent = t("brief_load_failed");
  }
}

async function refreshAll() {
  if (refreshInFlight) {
    return;
  }

  refreshInFlight = true;
  refreshBtn.disabled = true;
  try {
    await refreshBriefSettings();
    const snapshot = await fetchApi("/api/v1/dashboard/snapshot").catch(() => ({}));
    renderKpis(snapshot?.overview || {});
    renderConnectorHealth(snapshot?.connector_health || []);
    renderPending(snapshot?.pending_confirmations || []);
    renderConflicts(snapshot?.open_conflicts || []);
    renderRuntimeLogs(snapshot?.recent_logs || []);
    maybeNotifySnapshot(snapshot);
    lastUpdatedEl.textContent = `${t("last_updated")} ${fmtNow()}`;

    await refreshLatestBrief();
  } catch (error) {
    console.error("Refresh failed", error);
  } finally {
    refreshInFlight = false;
    refreshBtn.disabled = false;
  }
}

langSwitchEl.value = currentLang;
langSwitchEl.addEventListener("change", (event) => {
  currentLang = event.target.value;
  localStorage.setItem("steward_lang", currentLang);
  applyI18n();
  refreshAll();
});

refreshBtn.addEventListener("click", refreshAll);
briefViewBtn.addEventListener("click", async () => {
  briefViewBtn.disabled = true;
  try {
    await refreshLatestBrief();
    lastUpdatedEl.textContent = `${t("last_updated")} ${fmtNow()}`;
  } finally {
    briefViewBtn.disabled = false;
  }
});
eventFormEl.addEventListener("submit", submitEvent);
briefSettingsSaveBtn.addEventListener("click", saveBriefSettings);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshAll();
  }
});

applyI18n();
attachNotificationPermissionOnFirstIntent();
refreshAll();
setInterval(() => {
  if (!document.hidden) {
    refreshAll();
  }
}, 15000);
