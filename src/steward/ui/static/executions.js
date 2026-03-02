const i18n = {
  zh: {
    title: "执行结果中心",
    subtitle: "查看自动执行链路的真实状态、步骤细节与失败原因。",
    last_updated: "最后刷新：",
    refresh: "刷新结果",
    back_dashboard: "返回 Dashboard",
    metric_total: "最近分发",
    metric_running: "进行中",
    metric_succeeded: "成功",
    metric_failed: "失败",
    list_title: "执行记录",
    no_records: "暂无执行记录",
    loading: "加载中...",
    status_queued: "排队中",
    status_running: "执行中",
    status_retrying: "重试中",
    status_waiting: "等待中",
    status_succeeded: "成功",
    status_failed: "失败",
    status_unknown: "未知",
    summary_success: "计划共 {steps} 步，已完成 {done} 步，执行成功。",
    summary_failed: "执行失败：{reason}",
    summary_running: "正在执行第 {step}/{steps} 步。",
    summary_queued: "已入队，等待 worker 执行。",
    summary_waiting: "计划进入等待态，需外部事件触发后继续。",
    summary_retrying: "步骤失败后已进入重试流程。",
    summary_default: "执行状态：{status}",
    summary_unknown_reason: "未知原因",
    meta_plan: "计划",
    meta_dispatch: "分发",
    meta_intent: "意图",
    meta_trigger: "触发原因",
    meta_progress: "进度",
    meta_retry: "重试",
    meta_queued_at: "入队",
    meta_started_at: "开始",
    meta_finished_at: "结束",
    none: "-",
    step_title: "步骤 {step} · {connector}",
    step_detail_empty: "无额外细节",
    attempts_title: "步骤明细（{count}）",
    attempts_empty: "暂无步骤执行记录",
    step_error: "错误：{error}",
    step_duration: "耗时 {ms} ms",
    open_record: "打开记录",
    raw_detail: "查看原始返回",
    raw_error: "原始错误",
  },
  en: {
    title: "Execution Results",
    subtitle: "Inspect real execution status, step details, and failure reasons.",
    last_updated: "Last updated:",
    refresh: "Refresh",
    back_dashboard: "Back to Dashboard",
    metric_total: "Recent Dispatches",
    metric_running: "Running",
    metric_succeeded: "Succeeded",
    metric_failed: "Failed",
    list_title: "Execution Records",
    no_records: "No execution records.",
    loading: "Loading...",
    status_queued: "Queued",
    status_running: "Running",
    status_retrying: "Retrying",
    status_waiting: "Waiting",
    status_succeeded: "Succeeded",
    status_failed: "Failed",
    status_unknown: "Unknown",
    summary_success: "{done}/{steps} steps completed. Execution succeeded.",
    summary_failed: "Execution failed: {reason}",
    summary_running: "Executing step {step}/{steps}.",
    summary_queued: "Queued and waiting for worker dispatch.",
    summary_waiting: "Execution is waiting for an external trigger.",
    summary_retrying: "A failed step is being retried.",
    summary_default: "Execution status: {status}",
    summary_unknown_reason: "unknown reason",
    meta_plan: "Plan",
    meta_dispatch: "Dispatch",
    meta_intent: "Intent",
    meta_trigger: "Trigger",
    meta_progress: "Progress",
    meta_retry: "Retries",
    meta_queued_at: "Queued",
    meta_started_at: "Started",
    meta_finished_at: "Finished",
    none: "-",
    step_title: "Step {step} · {connector}",
    step_detail_empty: "No extra detail",
    attempts_title: "Step attempts ({count})",
    attempts_empty: "No step attempts yet.",
    step_error: "Error: {error}",
    step_duration: "Duration {ms} ms",
    open_record: "Open record",
    raw_detail: "Show raw output",
    raw_error: "Raw error",
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

function fmtNow() {
  return new Date().toLocaleTimeString(currentLang === "zh" ? "zh-CN" : "en-US", { hour12: false });
}

function fmtTime(isoText) {
  if (!isoText) {
    return t("none");
  }
  const date = new Date(isoText);
  if (Number.isNaN(date.getTime())) {
    return t("none");
  }
  return date.toLocaleString(currentLang === "zh" ? "zh-CN" : "en-US", { hour12: false });
}

function shortId(raw) {
  const value = String(raw || "");
  if (value.length <= 12) {
    return value || t("none");
  }
  return `${value.slice(0, 8)}...`;
}

function normalizeStatus(raw) {
  const value = String(raw || "").trim().toLowerCase();
  if (["queued", "running", "retrying", "waiting", "succeeded", "failed"].includes(value)) {
    return value;
  }
  return "unknown";
}

function statusLabel(status) {
  return t(`status_${status}`);
}

function statusClass(status) {
  if (status === "succeeded") {
    return "status-success";
  }
  if (status === "failed") {
    return "status-failed";
  }
  if (status === "running" || status === "retrying") {
    return "status-running";
  }
  if (status === "waiting") {
    return "status-waiting";
  }
  return "status-queued";
}

function latestFailedReason(item) {
  const attempts = Array.isArray(item?.attempts) ? item.attempts : [];
  for (let idx = attempts.length - 1; idx >= 0; idx -= 1) {
    const attempt = attempts[idx] || {};
    if (String(attempt.status || "").toLowerCase() === "failed") {
      return attempt.error_message || attempt.detail || item.last_error || "";
    }
  }
  return item.last_error || "";
}

function executionSummary(item, status) {
  if (item?.human_summary) {
    return String(item.human_summary);
  }
  const totalSteps = Number(item?.total_steps || 0);
  const doneSteps = Number(item?.succeeded_steps || 0);
  const currentStep = Math.max(1, Number(item?.current_step || 1));
  const reason = latestFailedReason(item) || t("summary_unknown_reason");

  if (status === "succeeded") {
    return t("summary_success", { steps: totalSteps, done: doneSteps });
  }
  if (status === "failed") {
    return t("summary_failed", { reason });
  }
  if (status === "running") {
    return t("summary_running", { step: currentStep, steps: Math.max(1, totalSteps) });
  }
  if (status === "queued") {
    return t("summary_queued");
  }
  if (status === "waiting") {
    return t("summary_waiting");
  }
  if (status === "retrying") {
    return t("summary_retrying");
  }
  return t("summary_default", { status: statusLabel(status) });
}

const titleEl = document.getElementById("page-title");
const subtitleEl = document.getElementById("page-subtitle");
const lastUpdatedEl = document.getElementById("last-updated");
const refreshBtn = document.getElementById("refresh-btn");
const backDashboardBtn = document.getElementById("back-dashboard-btn");
const langSwitchEl = document.getElementById("lang-switch");

const metricTotalTitleEl = document.getElementById("metric-total-title");
const metricRunningTitleEl = document.getElementById("metric-running-title");
const metricSucceededTitleEl = document.getElementById("metric-succeeded-title");
const metricFailedTitleEl = document.getElementById("metric-failed-title");

const metricTotalValueEl = document.getElementById("metric-total-value");
const metricRunningValueEl = document.getElementById("metric-running-value");
const metricSucceededValueEl = document.getElementById("metric-succeeded-value");
const metricFailedValueEl = document.getElementById("metric-failed-value");

const listTitleEl = document.getElementById("list-title");
const listCountEl = document.getElementById("list-count");
const emptyTextEl = document.getElementById("empty-text");
const executionListEl = document.getElementById("execution-list");

function applyI18n() {
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";

  titleEl.textContent = t("title");
  subtitleEl.textContent = t("subtitle");
  refreshBtn.textContent = t("refresh");
  backDashboardBtn.textContent = t("back_dashboard");

  metricTotalTitleEl.textContent = t("metric_total");
  metricRunningTitleEl.textContent = t("metric_running");
  metricSucceededTitleEl.textContent = t("metric_succeeded");
  metricFailedTitleEl.textContent = t("metric_failed");

  listTitleEl.textContent = t("list_title");
  emptyTextEl.textContent = t("no_records");
  lastUpdatedEl.textContent = `${t("last_updated")} --`;
}

async function fetchApi(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function renderMetrics(items) {
  const list = Array.isArray(items) ? items : [];
  const runningStatuses = new Set(["running", "queued", "retrying", "waiting"]);

  const runningCount = list.filter((item) => runningStatuses.has(normalizeStatus(item?.dispatch_status))).length;
  const succeededCount = list.filter((item) => normalizeStatus(item?.dispatch_status) === "succeeded").length;
  const failedCount = list.filter((item) => normalizeStatus(item?.dispatch_status) === "failed").length;

  metricTotalValueEl.textContent = String(list.length);
  metricRunningValueEl.textContent = String(runningCount);
  metricSucceededValueEl.textContent = String(succeededCount);
  metricFailedValueEl.textContent = String(failedCount);
}

function renderAttempt(item) {
  const status = normalizeStatus(item?.status);
  const stepIndex = Number(item?.step_index || 0) + 1;
  const connector = String(item?.connector_label || item?.connector_instance_id || "unknown");
  const fallbackTitle = t("step_title", { step: stepIndex, connector });
  const title = String(item?.step_label || fallbackTitle);
  const detail = String(item?.human_detail || item?.detail || "").trim() || t("step_detail_empty");
  const errorText = String(item?.human_error || item?.error_message || "").trim();
  const errorLine = errorText
    ? `<div class="attempt-error">${escapeHtml(t("step_error", { error: errorText }))}</div>`
    : "";
  const durationLine = item?.duration_ms
    ? `<div class="attempt-duration">${escapeHtml(t("step_duration", { ms: item.duration_ms }))}</div>`
    : "";
  const rawDetail = String(item?.detail || "").trim();
  const rawError = String(item?.error_message || "").trim();
  const showRawDetail = rawDetail && rawDetail !== detail;
  const showRawError = rawError && rawError !== errorText;
  const rawPanel = (showRawDetail || showRawError)
    ? `
      <details class="attempt-raw">
        <summary>${escapeHtml(t("raw_detail"))}</summary>
        <div class="attempt-raw-body">
          ${showRawDetail ? `<div>${escapeHtml(rawDetail)}</div>` : ""}
          ${showRawError ? `<div>${escapeHtml(t("raw_error"))}: ${escapeHtml(rawError)}</div>` : ""}
        </div>
      </details>
    `
    : "";
  const recordLink = item?.record_url
    ? `<a class="attempt-link" href="${escapeHtml(item.record_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(t("open_record"))}</a>`
    : "";

  return `
    <div class="attempt-item">
      <div class="attempt-head">
        <div class="attempt-title">${escapeHtml(title)}</div>
        <span class="badge ${statusClass(status)}">${escapeHtml(statusLabel(status))}</span>
      </div>
      <div class="attempt-meta">${escapeHtml(fmtTime(item?.created_at))}</div>
      <div class="attempt-detail">${escapeHtml(detail)}</div>
      ${errorLine}
      ${durationLine}
      ${recordLink}
      ${rawPanel}
    </div>
  `;
}

function renderExecutionCard(item) {
  const status = normalizeStatus(item?.dispatch_status);
  const summary = executionSummary(item, status);
  const progress = `${Number(item?.succeeded_steps || 0)}/${Number(item?.total_steps || 0)}`;
  const intentTitle = String(item?.intent_label || item?.intent || "unknown");
  const statusTitle = String(item?.dispatch_status_label || statusLabel(status));
  const triggerLabel = String(item?.trigger_reason_label || item?.trigger_reason || t("none"));
  const attempts = Array.isArray(item?.attempts) ? item.attempts : [];
  const attemptBody = attempts.length
    ? attempts.map((attempt) => renderAttempt(attempt)).join("")
    : `<p class="muted text-sm">${escapeHtml(t("attempts_empty"))}</p>`;
  const openFailed = status === "failed" ? " open" : "";

  return `
    <article class="execution-card">
      <div class="execution-head">
        <div class="execution-head-main">
          <div class="execution-title">${escapeHtml(intentTitle)}</div>
          <div class="execution-meta">
            ${escapeHtml(t("meta_plan"))} ${escapeHtml(item?.plan_id_short || shortId(item?.plan_id))}
            &middot;
            ${escapeHtml(t("meta_dispatch"))} ${escapeHtml(item?.dispatch_id_short || shortId(item?.dispatch_id))}
          </div>
        </div>
        <span class="badge ${statusClass(status)}">${escapeHtml(statusTitle)}</span>
      </div>

      <div class="execution-summary">${escapeHtml(summary)}</div>

      <div class="execution-grid">
        <div class="execution-kv">${escapeHtml(t("meta_progress"))}: ${escapeHtml(progress)}</div>
        <div class="execution-kv">${escapeHtml(t("meta_retry"))}: ${escapeHtml(item?.retry_count ?? 0)}</div>
        <div class="execution-kv">${escapeHtml(t("meta_trigger"))}: ${escapeHtml(triggerLabel)}</div>
        <div class="execution-kv">${escapeHtml(t("meta_queued_at"))}: ${escapeHtml(fmtTime(item?.queued_at))}</div>
        <div class="execution-kv">${escapeHtml(t("meta_started_at"))}: ${escapeHtml(fmtTime(item?.started_at))}</div>
        <div class="execution-kv">${escapeHtml(t("meta_finished_at"))}: ${escapeHtml(fmtTime(item?.finished_at))}</div>
      </div>

      <details class="attempts-panel"${openFailed}>
        <summary>${escapeHtml(t("attempts_title", { count: attempts.length }))}</summary>
        <div class="attempts-list">${attemptBody}</div>
      </details>
    </article>
  `;
}

function renderExecutions(items) {
  const list = Array.isArray(items) ? items : [];
  listCountEl.textContent = String(list.length);
  renderMetrics(list);

  if (!list.length) {
    emptyTextEl.classList.remove("hidden");
    executionListEl.innerHTML = "";
    return;
  }

  emptyTextEl.classList.add("hidden");
  executionListEl.innerHTML = list.map((item) => renderExecutionCard(item)).join("");
}

let refreshInFlight = false;

async function refreshAll() {
  if (refreshInFlight) {
    return;
  }
  refreshInFlight = true;
  refreshBtn.disabled = true;
  try {
    const payload = await fetchApi(`/api/v1/dashboard/executions?limit=50&lang=${encodeURIComponent(currentLang)}`);
    renderExecutions(payload?.items || []);
    lastUpdatedEl.textContent = `${t("last_updated")} ${fmtNow()}`;
  } catch (error) {
    emptyTextEl.classList.remove("hidden");
    emptyTextEl.textContent = `${t("no_records")} (${error instanceof Error ? error.message : "error"})`;
    executionListEl.innerHTML = "";
    renderMetrics([]);
  } finally {
    refreshBtn.disabled = false;
    refreshInFlight = false;
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
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) {
    refreshAll();
  }
});

applyI18n();
executionListEl.innerHTML = `<p class="muted text-sm">${escapeHtml(t("loading"))}</p>`;
refreshAll();
setInterval(() => {
  if (!document.hidden) {
    refreshAll();
  }
}, 15000);
