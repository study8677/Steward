const i18n = {
  zh: {
    title: "能力管理中心（信息源管理）",
    subtitle: "第一性原理：先选能力，再决定配置和启用。",
    last_updated: "最后刷新：",
    back_dashboard: "返回 Dashboard",
    refresh: "刷新能力状态",
    quick_nl_title: "自然语言快速配置",
    quick_nl_hint: "示例：启用 github mcp 和 gh-fix-ci skill。",
    integration_placeholder: "e.g. 启用 github mcp 和 playwright mcp, 启用 gh-fix-ci skill",
    btn_apply: "应用",
    btn_create_config: "保存 MCP 配置",
    custom_provider_title: "新增自定义 MCP Server",
    browser_title: "能力列表",
    tab_all: "全部",
    tab_mcp: "MCP",
    tab_skill: "Skill",
    search_placeholder: "搜索 capability id / 名称 / 描述",
    only_enabled: "只看已启用",
    only_needs_config: "只看待配置",
    metric_enabled: "已启用能力",
    metric_mcp: "MCP Servers",
    metric_skill: "Skills",
    metric_pending: "待补齐配置",
    waiting_action: "等待操作",
    waiting_config: "等待配置",
    loading: "加载中...",
    no_connectors: "暂无能力项",
    no_filtered: "当前筛选条件下没有能力项。",
    configured: "配置成功",
    configure_failed: "配置失败",
    applied: "已应用",
    apply_failed: "应用失败",
    saved: "已保存",
    save_failed: "保存失败",
    mcp_enabled: "已启用",
    mcp_disabled: "未启用",
    skill_installed: "已安装",
    skill_not_installed: "未安装",
    mcp_configured: "已配置",
    mcp_unconfigured: "待配置",
    btn_enable: "启用",
    btn_disable: "停用",
    btn_configure: "配置",
    btn_collapse: "收起配置",
    save_config: "保存配置",
    source_label: "source",
    command_label: "command",
    endpoint_label: "endpoint",
    transport_label: "transport",
    auth_env_label: "auth_env",
    display_name_label: "display_name",
    description_label: "description",
  },
  en: {
    title: "Capability Hub (Integrations)",
    subtitle: "First principles: choose capability first, then configure and enable.",
    last_updated: "Last updated:",
    back_dashboard: "Back to Dashboard",
    refresh: "Refresh",
    quick_nl_title: "Quick NL Config",
    quick_nl_hint: "Example: enable github mcp and gh-fix-ci skill.",
    integration_placeholder: "e.g. enable github mcp and playwright mcp, enable gh-fix-ci skill",
    btn_apply: "Apply",
    btn_create_config: "Save MCP Config",
    custom_provider_title: "Create Custom MCP Server",
    browser_title: "Capabilities",
    tab_all: "All",
    tab_mcp: "MCP",
    tab_skill: "Skills",
    search_placeholder: "Search capability id / name / description",
    only_enabled: "Enabled only",
    only_needs_config: "Needs config only",
    metric_enabled: "Enabled",
    metric_mcp: "MCP Servers",
    metric_skill: "Skills",
    metric_pending: "Needs Setup",
    waiting_action: "Waiting for action",
    waiting_config: "Waiting for configuration",
    loading: "Loading...",
    no_connectors: "No capability items.",
    no_filtered: "No capability items match current filters.",
    configured: "Configured.",
    configure_failed: "Failed to configure.",
    applied: "Applied.",
    apply_failed: "Failed to apply.",
    saved: "Saved.",
    save_failed: "Failed to save.",
    mcp_enabled: "Enabled",
    mcp_disabled: "Disabled",
    skill_installed: "Installed",
    skill_not_installed: "Not Installed",
    mcp_configured: "Configured",
    mcp_unconfigured: "Needs Config",
    btn_enable: "Enable",
    btn_disable: "Disable",
    btn_configure: "Configure",
    btn_collapse: "Collapse",
    save_config: "Save Config",
    source_label: "source",
    command_label: "command",
    endpoint_label: "endpoint",
    transport_label: "transport",
    auth_env_label: "auth_env",
    display_name_label: "display_name",
    description_label: "description",
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

const state = {
  filter: "all",
  query: "",
  onlyEnabled: false,
  onlyNeedsConfig: false,
  capabilities: [],
};

const pageTitleEl = document.getElementById("integrations-page-title");
const pageSubtitleEl = document.getElementById("integrations-page-subtitle");
const lastUpdatedEl = document.getElementById("integration-last-updated");
const backDashboardBtn = document.getElementById("back-dashboard-btn");
const refreshBtn = document.getElementById("refresh-integrations-btn");
const langSwitchEl = document.getElementById("lang-switch");

const quickNlTitleEl = document.getElementById("quick-nl-title");
const quickNlHintEl = document.getElementById("quick-nl-hint");
const nlIntegrationFormEl = document.getElementById("integration-form");
const integrationInputEl = document.getElementById("integration-text");
const integrationApplyBtn = document.getElementById("integration-apply-btn");
const nlIntegrationResultEl = document.getElementById("integration-result");

const customProviderTitleEl = document.getElementById("custom-provider-title");
const customProviderFormEl = document.getElementById("custom-provider-form");
const customProviderResultEl = document.getElementById("custom-provider-result");
const customProviderSubmitBtn = document.getElementById("custom-provider-submit-btn");

const browserTitleEl = document.getElementById("capability-browser-title");
const tabAllEl = document.getElementById("tab-all");
const tabMcpEl = document.getElementById("tab-mcp");
const tabSkillEl = document.getElementById("tab-skill");
const searchEl = document.getElementById("capability-search");
const onlyEnabledEl = document.getElementById("only-enabled");
const onlyNeedsConfigEl = document.getElementById("only-needs-config");
const onlyEnabledLabelEl = document.getElementById("only-enabled-label");
const onlyNeedsConfigLabelEl = document.getElementById("only-needs-config-label");
const emptyEl = document.getElementById("capability-empty");
const capabilityGridEl = document.getElementById("capability-grid");

const metricEnabledTitleEl = document.getElementById("metric-enabled-title");
const metricMcpTitleEl = document.getElementById("metric-mcp-title");
const metricSkillTitleEl = document.getElementById("metric-skill-title");
const metricPendingTitleEl = document.getElementById("metric-pending-title");
const metricEnabledValueEl = document.getElementById("metric-enabled-value");
const metricMcpValueEl = document.getElementById("metric-mcp-value");
const metricSkillValueEl = document.getElementById("metric-skill-value");
const metricPendingValueEl = document.getElementById("metric-pending-value");

function applyI18n() {
  document.documentElement.lang = currentLang === "zh" ? "zh-CN" : "en";

  pageTitleEl.textContent = t("title");
  pageSubtitleEl.textContent = t("subtitle");
  backDashboardBtn.textContent = t("back_dashboard");
  refreshBtn.textContent = t("refresh");

  quickNlTitleEl.textContent = t("quick_nl_title");
  quickNlHintEl.textContent = t("quick_nl_hint");
  integrationInputEl.placeholder = t("integration_placeholder");
  integrationApplyBtn.textContent = t("btn_apply");

  customProviderTitleEl.textContent = t("custom_provider_title");
  customProviderSubmitBtn.textContent = t("btn_create_config");

  browserTitleEl.textContent = t("browser_title");
  tabAllEl.textContent = t("tab_all");
  tabMcpEl.textContent = t("tab_mcp");
  tabSkillEl.textContent = t("tab_skill");
  searchEl.placeholder = t("search_placeholder");
  onlyEnabledLabelEl.textContent = t("only_enabled");
  onlyNeedsConfigLabelEl.textContent = t("only_needs_config");
  emptyEl.textContent = t("no_filtered");

  metricEnabledTitleEl.textContent = t("metric_enabled");
  metricMcpTitleEl.textContent = t("metric_mcp");
  metricSkillTitleEl.textContent = t("metric_skill");
  metricPendingTitleEl.textContent = t("metric_pending");

  lastUpdatedEl.textContent = `${t("last_updated")} --`;
  if (!customProviderResultEl.textContent.trim()) {
    customProviderResultEl.textContent = t("waiting_action");
  }
  if (!nlIntegrationResultEl.textContent.trim()) {
    nlIntegrationResultEl.textContent = t("waiting_config");
  }
}

async function fetchApi(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function mapCapabilities(snapshot) {
  const mcpServers = Array.isArray(snapshot?.mcp_servers) ? snapshot.mcp_servers : [];
  const skills = Array.isArray(snapshot?.skills) ? snapshot.skills : [];

  const mappedMcp = mcpServers.map((item) => {
    const configured = Boolean(item?.configured);
    return {
      kind: "mcp",
      id: String(item?.server || "").trim(),
      displayName: String(item?.display_name || item?.server || "").trim(),
      description: String(item?.description || "").trim(),
      enabled: Boolean(item?.enabled),
      configured,
      needsConfig: !configured,
      meta1: `transport: ${String(item?.transport || "stdio").trim()}`,
      meta2: String(item?.source_url || "").trim(),
      raw: item,
    };
  });

  const mappedSkills = skills.map((item) => {
    const installed = Boolean(item?.installed);
    const enabled = Boolean(item?.enabled);
    return {
      kind: "skill",
      id: String(item?.skill || "").trim(),
      displayName: String(item?.display_name || item?.skill || "").trim(),
      description: String(item?.description || "").trim(),
      enabled,
      installed,
      needsConfig: enabled && !installed,
      meta1: `source: ${String(item?.source || "-").trim() || "-"}`,
      meta2: "",
      raw: item,
    };
  });

  return [...mappedMcp, ...mappedSkills];
}

function updateMetrics(capabilities) {
  const enabled = capabilities.filter((item) => item.enabled).length;
  const mcpCount = capabilities.filter((item) => item.kind === "mcp").length;
  const skillCount = capabilities.filter((item) => item.kind === "skill").length;
  const pending = capabilities.filter((item) => item.needsConfig).length;

  metricEnabledValueEl.textContent = String(enabled);
  metricMcpValueEl.textContent = String(mcpCount);
  metricSkillValueEl.textContent = String(skillCount);
  metricPendingValueEl.textContent = String(pending);
}

function filteredCapabilities() {
  const query = state.query.toLowerCase();
  return state.capabilities.filter((item) => {
    if (state.filter !== "all" && item.kind !== state.filter) {
      return false;
    }
    if (state.onlyEnabled && !item.enabled) {
      return false;
    }
    if (state.onlyNeedsConfig && !item.needsConfig) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = `${item.id} ${item.displayName} ${item.description} ${item.meta1}`.toLowerCase();
    return haystack.includes(query);
  });
}

function renderCapabilityCard(item) {
  const key = `${item.kind}:${item.id}`;
  const enabledLabel = item.enabled ? t("mcp_enabled") : t("mcp_disabled");
  const enabledClass = item.enabled ? "health-ok" : "danger-badge";
  const toggleLabel = item.enabled ? t("btn_disable") : t("btn_enable");

  let subBadge = "";
  if (item.kind === "mcp") {
    const configured = Boolean(item?.configured);
    const label = configured ? t("mcp_configured") : t("mcp_unconfigured");
    const klass = configured ? "badge-soft" : "badge-warn";
    subBadge = `<span class="badge ${klass}">${escapeHtml(label)}</span>`;
  } else {
    const label = item.installed ? t("skill_installed") : t("skill_not_installed");
    const klass = item.installed ? "badge-soft" : "badge-warn";
    subBadge = `<span class="badge ${klass}">${escapeHtml(label)}</span>`;
  }

  const description = escapeHtml(item.description || "-");
  const meta1 = escapeHtml(item.meta1 || "");
  const meta2 = escapeHtml(item.meta2 || "");

  if (item.kind === "mcp") {
    const raw = item.raw || {};
    return `
      <article class="cap-card" data-kind="mcp" data-id="${encodeURIComponent(item.id)}">
        <div class="cap-head">
          <div>
            <span class="cap-type">MCP</span>
            <h3 class="cap-title">${escapeHtml(item.displayName || item.id)}</h3>
            <p class="cap-id">id: ${escapeHtml(item.id)}</p>
          </div>
          <div class="cap-badges">
            <span class="badge ${enabledClass}">${escapeHtml(enabledLabel)}</span>
            ${subBadge}
          </div>
        </div>
        <p class="cap-desc">${description}</p>
        <div class="cap-meta">${meta1}</div>
        ${meta2 ? `<div class="cap-meta">${meta2}</div>` : ""}
        <div class="cap-actions">
          <button type="button" class="btn btn-sm btn-secondary cap-toggle-btn" data-kind="mcp" data-id="${encodeURIComponent(item.id)}" data-enabled="${item.enabled ? "1" : "0"}">${escapeHtml(toggleLabel)}</button>
          <button type="button" class="btn btn-sm btn-primary cap-config-btn">${escapeHtml(t("btn_configure"))}</button>
        </div>
        <div class="cap-config hidden">
          <form class="cap-config-form" data-kind="mcp" data-id="${encodeURIComponent(item.id)}">
            <div class="form-grid">
              <label>${escapeHtml(t("display_name_label"))}<input type="text" name="display_name" value="${escapeHtml(raw.display_name || "")}" /></label>
              <label>${escapeHtml(t("transport_label"))}
                <select name="transport">
                  <option value="stdio" ${raw.transport === "stdio" ? "selected" : ""}>stdio</option>
                  <option value="http" ${raw.transport === "http" ? "selected" : ""}>http</option>
                </select>
              </label>
              <label>${escapeHtml(t("command_label"))}<input type="text" name="command" value="${escapeHtml(raw.command || "")}" /></label>
              <label>${escapeHtml(t("endpoint_label"))}<input type="text" name="endpoint" value="${escapeHtml(raw.endpoint || "")}" /></label>
              <label>${escapeHtml(t("auth_env_label"))}<input type="text" name="auth_env" value="${escapeHtml(raw.auth_env || "")}" /></label>
              <label class="full-width">${escapeHtml(t("description_label"))}<input type="text" name="description" value="${escapeHtml(raw.description || "")}" /></label>
            </div>
            <div class="item-actions mt-3">
              <button type="submit" class="btn btn-sm btn-primary">${escapeHtml(t("save_config"))}</button>
            </div>
          </form>
          <p class="status-msg cap-result" data-result-key="${escapeHtml(key)}"></p>
        </div>
      </article>
    `;
  }

  const raw = item.raw || {};
  return `
    <article class="cap-card" data-kind="skill" data-id="${encodeURIComponent(item.id)}">
      <div class="cap-head">
        <div>
          <span class="cap-type">Skill</span>
          <h3 class="cap-title">${escapeHtml(item.displayName || item.id)}</h3>
          <p class="cap-id">id: ${escapeHtml(item.id)}</p>
        </div>
        <div class="cap-badges">
          <span class="badge ${enabledClass}">${escapeHtml(enabledLabel)}</span>
          ${subBadge}
        </div>
      </div>
      <p class="cap-desc">${description}</p>
      <div class="cap-meta">${meta1}</div>
      <div class="cap-actions">
        <button type="button" class="btn btn-sm btn-secondary cap-toggle-btn" data-kind="skill" data-id="${encodeURIComponent(item.id)}" data-enabled="${item.enabled ? "1" : "0"}">${escapeHtml(toggleLabel)}</button>
        <button type="button" class="btn btn-sm btn-primary cap-config-btn">${escapeHtml(t("btn_configure"))}</button>
      </div>
      <div class="cap-config hidden">
        <form class="cap-config-form" data-kind="skill" data-id="${encodeURIComponent(item.id)}">
          <div class="form-grid">
            <label>${escapeHtml(t("display_name_label"))}<input type="text" name="display_name" value="${escapeHtml(raw.display_name || "")}" /></label>
            <label>${escapeHtml(t("source_label"))}<input type="text" name="source" value="${escapeHtml(raw.source || "")}" /></label>
            <label class="full-width">${escapeHtml(t("description_label"))}<input type="text" name="description" value="${escapeHtml(raw.description || "")}" /></label>
          </div>
          <div class="item-actions mt-3">
            <button type="submit" class="btn btn-sm btn-primary">${escapeHtml(t("save_config"))}</button>
          </div>
        </form>
        <p class="status-msg cap-result" data-result-key="${escapeHtml(key)}"></p>
      </div>
    </article>
  `;
}

function renderCapabilities() {
  const list = filteredCapabilities();
  emptyEl.classList.toggle("hidden", list.length > 0);
  if (!list.length) {
    capabilityGridEl.innerHTML = "";
    return;
  }
  capabilityGridEl.innerHTML = list.map((item) => renderCapabilityCard(item)).join("");
}

function updateActiveTabUi() {
  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.filter === state.filter);
  });
}

async function refreshState() {
  try {
    const snapshot = await fetchApi("/api/v1/integrations");
    state.capabilities = mapCapabilities(snapshot);
    updateMetrics(state.capabilities);
    renderCapabilities();
    updateActiveTabUi();
    lastUpdatedEl.textContent = `${t("last_updated")} ${fmtNow()}`;
  } catch (_) {
    capabilityGridEl.innerHTML = `<p class="muted text-sm">${escapeHtml(t("no_connectors"))}</p>`;
    lastUpdatedEl.textContent = `${t("last_updated")} --`;
  }
}

customProviderFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(customProviderFormEl);
  const server = String(form.get("server") || "").trim();
  if (!server) {
    return;
  }

  const transport = String(form.get("transport") || "stdio").trim();
  const entry = String(form.get("entry") || "").trim();
  const payload = {
    display_name: String(form.get("display_name") || "").trim(),
    transport,
    description: String(form.get("description") || "").trim(),
    auth_env: String(form.get("auth_env") || "").trim(),
  };
  if (transport === "http") {
    payload.endpoint = entry;
  } else {
    payload.command = entry;
  }

  customProviderResultEl.textContent = t("loading");
  customProviderSubmitBtn.disabled = true;
  try {
    const response = await fetch(`/api/v1/integrations/mcp/${encodeURIComponent(server)}/configure`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error("configure_failed");
    }
    customProviderResultEl.textContent = t("configured");
    customProviderFormEl.reset();
    await refreshState();
  } catch (_) {
    customProviderResultEl.textContent = t("configure_failed");
  } finally {
    customProviderSubmitBtn.disabled = false;
  }
});

nlIntegrationFormEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = String(integrationInputEl.value || "").trim();
  if (!text) {
    return;
  }

  nlIntegrationResultEl.textContent = t("loading");
  try {
    const response = await fetch("/api/v1/integrations/nl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      throw new Error("apply_failed");
    }
    nlIntegrationResultEl.textContent = t("applied");
    await refreshState();
  } catch (_) {
    nlIntegrationResultEl.textContent = t("apply_failed");
  }
});

capabilityGridEl.addEventListener("click", async (event) => {
  const target = event.target instanceof HTMLElement ? event.target : null;
  if (!target) {
    return;
  }

  const configButton = target.closest(".cap-config-btn");
  if (configButton instanceof HTMLElement) {
    const card = configButton.closest(".cap-card");
    const config = card?.querySelector(".cap-config");
    if (!(config instanceof HTMLElement)) {
      return;
    }
    const hidden = config.classList.toggle("hidden");
    configButton.textContent = hidden ? t("btn_configure") : t("btn_collapse");
    return;
  }

  const toggleButton = target.closest(".cap-toggle-btn");
  if (!(toggleButton instanceof HTMLElement)) {
    return;
  }
  const kind = String(toggleButton.dataset.kind || "").trim();
  const encodedId = String(toggleButton.dataset.id || "").trim();
  if (!kind || !encodedId) {
    return;
  }
  const id = decodeURIComponent(encodedId);
  const enabled = toggleButton.dataset.enabled === "1";
  const action = enabled ? "disable" : "enable";
  const endpointKind = kind === "mcp" ? "mcp" : "skills";

  toggleButton.disabled = true;
  try {
    const response = await fetch(
      `/api/v1/integrations/${endpointKind}/${encodeURIComponent(id)}/${action}`,
      { method: "POST" }
    );
    if (!response.ok) {
      throw new Error("toggle_failed");
    }
    await refreshState();
  } finally {
    toggleButton.disabled = false;
  }
});

capabilityGridEl.addEventListener("submit", async (event) => {
  const form = event.target instanceof HTMLFormElement ? event.target : null;
  if (!form || !form.classList.contains("cap-config-form")) {
    return;
  }
  event.preventDefault();

  const kind = String(form.dataset.kind || "").trim();
  const encodedId = String(form.dataset.id || "").trim();
  if (!kind || !encodedId) {
    return;
  }
  const id = decodeURIComponent(encodedId);
  const endpointKind = kind === "mcp" ? "mcp" : "skills";

  const payload = {};
  new FormData(form).forEach((value, key) => {
    const trimmed = String(value || "").trim();
    if (trimmed) {
      payload[key] = trimmed;
    }
  });

  const resultEl = form.parentElement?.querySelector("[data-result-key]");
  if (resultEl instanceof HTMLElement) {
    resultEl.textContent = t("loading");
  }

  try {
    const response = await fetch(
      `/api/v1/integrations/${endpointKind}/${encodeURIComponent(id)}/configure`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    );
    if (!response.ok) {
      throw new Error("save_failed");
    }
    if (resultEl instanceof HTMLElement) {
      resultEl.textContent = t("saved");
    }
    await refreshState();
  } catch (_) {
    if (resultEl instanceof HTMLElement) {
      resultEl.textContent = t("save_failed");
    }
  }
});

document.querySelectorAll(".tab-btn").forEach((button) => {
  button.addEventListener("click", () => {
    state.filter = String(button.dataset.filter || "all");
    updateActiveTabUi();
    renderCapabilities();
  });
});

searchEl.addEventListener("input", () => {
  state.query = String(searchEl.value || "").trim();
  renderCapabilities();
});

onlyEnabledEl.addEventListener("change", () => {
  state.onlyEnabled = Boolean(onlyEnabledEl.checked);
  renderCapabilities();
});

onlyNeedsConfigEl.addEventListener("change", () => {
  state.onlyNeedsConfig = Boolean(onlyNeedsConfigEl.checked);
  renderCapabilities();
});

refreshBtn.addEventListener("click", refreshState);

langSwitchEl.value = currentLang;
langSwitchEl.addEventListener("change", (event) => {
  currentLang = event.target.value;
  localStorage.setItem("steward_lang", currentLang);
  applyI18n();
  renderCapabilities();
  updateMetrics(state.capabilities);
  lastUpdatedEl.textContent = `${t("last_updated")} ${fmtNow()}`;
});

applyI18n();
refreshState();
