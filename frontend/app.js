/* ==========================================================================
   NEXUS V3 — Local Intelligence Workstation Logic
   Architecture: Vanilla JS & SSE streaming client for FastAPI + Ollama
   ========================================================================== */

(() => {
  "use strict";

  /* ========================================================================
     1. CONFIGURATION & CONSTANTS
     ======================================================================== */
  const BACKEND_URL = (window.location.protocol.startsWith("http") && (window.location.port === "8000" || window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"))
    ? window.location.origin
    : "http://127.0.0.1:8000";

  const DEFAULT_PROMPT = "You are NEXUS, a helpful local AI assistant. Be accurate, concise, and transparent when you are uncertain.";
  const THEMES = ["emerald", "violet", "ruby", "sapphire"];

  /* ========================================================================
     2. APPLICATION STATE
     ======================================================================== */
  const state = {
    // Backend health
    backendOnline: false,
    ollamaOnline: false,
    
    // Model Discovery
    models: [],
    selectedModel: "",

    // Settings
    settings: {
      system_prompt: DEFAULT_PROMPT,
      default_model: "",
    },

    // Session Management
    conversations: [],
    currentConversationId: null,
    messages: [],

    // Execution & Streaming
    isStreaming: false,

    // Active Theme
    currentTheme: localStorage.getItem("nexus_theme") || "emerald",
  };

  /* ========================================================================
     3. DOM SELECTORS
     ======================================================================== */
  const els = {
    // Ambient & Cursor
    ambientCursor: document.getElementById("ambientCursor"),

    // Boot
    bootScreen: document.getElementById("bootScreen"),
    bootStep1: document.getElementById("bootStep1"),
    bootStep2: document.getElementById("bootStep2"),
    bootStep3: document.getElementById("bootStep3"),
    bootStep4: document.getElementById("bootStep4"),
    bootProgressFill: document.getElementById("bootProgressFill"),
    bootErrorAction: document.getElementById("bootErrorAction"),
    bootErrorMsg: document.getElementById("bootErrorMsg"),
    bootRetryBtn: document.getElementById("bootRetryBtn"),

    // Sidebar
    sidebar: document.getElementById("sidebar"),
    sidebarScrim: document.getElementById("sidebarScrim"),
    mobileMenuBtn: document.getElementById("mobileMenuBtn"),
    sidebarCloseBtn: document.getElementById("sidebarCloseBtn"),
    newChatBtn: document.getElementById("newChatBtn"),
    convoSearchInput: document.getElementById("convoSearchInput"),
    searchClearBtn: document.getElementById("searchClearBtn"),
    convoList: document.getElementById("convoList"),
    convoEmptyState: document.getElementById("convoEmptyState"),
    backendLed: document.getElementById("backendLed"),
    ollamaLed: document.getElementById("ollamaLed"),
    sidebarSettingsBtn: document.getElementById("sidebarSettingsBtn"),

    // Topbar
    sessionTitleDisplay: document.getElementById("sessionTitleDisplay"),
    modelSelect: document.getElementById("modelSelect"),
    refreshModelsBtn: document.getElementById("refreshModelsBtn"),
    topbarSettingsBtn: document.getElementById("topbarSettingsBtn"),

    // Chat Viewport
    chatViewport: document.getElementById("chatViewport"),
    emptyState: document.getElementById("emptyState"),
    starterGrid: document.getElementById("starterGrid"),
    messagesFlow: document.getElementById("messagesFlow"),

    // Composer
    messageInput: document.getElementById("messageInput"),
    composerModelName: document.getElementById("composerModelName"),
    sendBtn: document.getElementById("sendBtn"),

    // Settings Drawer
    settingsScrim: document.getElementById("settingsScrim"),
    settingsDrawer: document.getElementById("settingsDrawer"),
    drawerCloseBtn: document.getElementById("drawerCloseBtn"),
    settingsSystemPrompt: document.getElementById("settingsSystemPrompt"),
    settingsDefaultModel: document.getElementById("settingsDefaultModel"),
    diagBackendLed: document.getElementById("diagBackendLed"),
    diagBackendVal: document.getElementById("diagBackendVal"),
    diagOllamaLed: document.getElementById("diagOllamaLed"),
    diagOllamaVal: document.getElementById("diagOllamaVal"),
    diagModelCount: document.getElementById("diagModelCount"),
    settingsSaveHint: document.getElementById("settingsSaveHint"),
    settingsResetBtn: document.getElementById("settingsResetBtn"),
    settingsSaveBtn: document.getElementById("settingsSaveBtn"),
    themeCards: document.querySelectorAll(".theme-card"),

    // Toast
    toastDeck: document.getElementById("toastDeck"),
  };

  /* ========================================================================
     4. TOAST NOTIFICATIONS
     ======================================================================== */
  function showToast(message, duration = 2400) {
    if (!els.toastDeck) return;
    const toast = document.createElement("div");
    toast.className = "toast-item";
    toast.textContent = message;
    els.toastDeck.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(8px)";
      toast.style.transition = "all 0.2s ease";
      setTimeout(() => toast.remove(), 200);
    }, duration);
  }

  /* ========================================================================
     5. SAFE MARKDOWN & CODE PARSER
     ======================================================================== */
  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderMarkdown(rawText) {
    if (!rawText) return "";

    const codeBlocks = [];
    let text = rawText.replace(/```([a-zA-Z0-9_.-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      const id = codeBlocks.length;
      codeBlocks.push({ lang: lang || "code", code: code.trim() });
      return `@@CODEBLOCK_${id}@@`;
    });

    text = escapeHtml(text);

    // Inline elements
    text = text.replace(/`([^`\n]+)`/g, '<code class="inline-code-token">$1</code>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    text = text.replace(/__(.*?)__/g, '<strong>$1</strong>');
    text = text.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
    text = text.replace(/_([^_\n]+)_/g, '<em>$1</em>');

    const lines = text.split("\n");
    let inList = false;
    let listType = "";
    let formattedHtml = "";

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.trim().startsWith("@@CODEBLOCK_")) {
        if (inList) { formattedHtml += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
        const blockId = line.trim().replace("@@CODEBLOCK_", "").replace("@@", "");
        const item = codeBlocks[Number(blockId)];
        if (item) {
          formattedHtml += `
            <div class="code-container">
              <div class="code-header">
                <span>${escapeHtml(item.lang)}</span>
                <button type="button" class="btn-copy-code" data-code="${escapeHtml(item.code)}">
                  <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                  <span>Copy</span>
                </button>
              </div>
              <pre><code>${escapeHtml(item.code)}</code></pre>
            </div>`;
        }
        continue;
      }

      if (line.startsWith("### ")) {
        if (inList) { formattedHtml += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
        formattedHtml += `<h3>${line.slice(4)}</h3>`;
        continue;
      }
      if (line.startsWith("## ")) {
        if (inList) { formattedHtml += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
        formattedHtml += `<h2>${line.slice(3)}</h2>`;
        continue;
      }
      if (line.startsWith("# ")) {
        if (inList) { formattedHtml += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
        formattedHtml += `<h1>${line.slice(2)}</h1>`;
        continue;
      }

      if (line.startsWith("&gt; ")) {
        if (inList) { formattedHtml += listType === "ul" ? "</ul>" : "</ol>"; inList = false; }
        formattedHtml += `<blockquote>${line.slice(5)}</blockquote>`;
        continue;
      }

      if (/^[-*]\s+/.test(line)) {
        if (!inList || listType !== "ul") {
          if (inList) formattedHtml += listType === "ul" ? "</ul>" : "</ol>";
          formattedHtml += "<ul>";
          inList = true;
          listType = "ul";
        }
        formattedHtml += `<li>${line.replace(/^[-*]\s+/, "")}</li>`;
        continue;
      }

      if (/^\d+\.\s+/.test(line)) {
        if (!inList || listType !== "ol") {
          if (inList) formattedHtml += listType === "ul" ? "</ul>" : "</ol>";
          formattedHtml += "<ol>";
          inList = true;
          listType = "ol";
        }
        formattedHtml += `<li>${line.replace(/^\d+\.\s+/, "")}</li>`;
        continue;
      }

      if (inList) {
        formattedHtml += listType === "ul" ? "</ul>" : "</ol>";
        inList = false;
      }

      if (line.trim()) {
        formattedHtml += `<p>${line}</p>`;
      }
    }

    if (inList) {
      formattedHtml += listType === "ul" ? "</ul>" : "</ol>";
    }

    return formattedHtml;
  }

  function attachCodeCopyHandlers(container) {
    container.querySelectorAll(".btn-copy-code").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.getAttribute("data-code") || "";
        navigator.clipboard.writeText(code).then(() => {
          const original = btn.innerHTML;
          btn.innerHTML = `<svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg><span>Copied</span>`;
          setTimeout(() => (btn.innerHTML = original), 1600);
        });
      });
    });
  }

  /* ========================================================================
     6. API CLIENT WRAPPER
     ======================================================================== */
  async function apiFetch(path, options = {}) {
    const res = await fetch(`${BACKEND_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (!res.ok) {
      let detail = "";
      try {
        const body = await res.json();
        detail = body.detail || body.message || JSON.stringify(body);
      } catch {
        detail = res.statusText;
      }
      throw new Error(detail || `HTTP Error ${res.status}`);
    }
    return res;
  }

  async function apiJson(path, options = {}) {
    const res = await apiFetch(path, options);
    return res.json();
  }

  /* ========================================================================
     7. THEME SYSTEM
     ======================================================================== */
  function applyTheme(themeName) {
    if (!THEMES.includes(themeName)) themeName = "emerald";
    state.currentTheme = themeName;
    document.documentElement.setAttribute("data-theme", themeName);
    localStorage.setItem("nexus_theme", themeName);

    els.themeCards.forEach((card) => {
      const isMatch = card.getAttribute("data-theme-id") === themeName;
      card.classList.toggle("active", isMatch);
    });
  }

  els.themeCards.forEach((card) => {
    card.addEventListener("click", () => {
      const themeId = card.getAttribute("data-theme-id");
      applyTheme(themeId);
      showToast(`Applied ${card.querySelector(".theme-name").textContent} theme.`);
    });
  });

  /* ========================================================================
     8. CURSOR TRACKING (Optimized via requestAnimationFrame)
     ======================================================================== */
  let mouseX = window.innerWidth / 2;
  let mouseY = window.innerHeight / 2;
  let rafPending = false;

  window.addEventListener("pointermove", (e) => {
    mouseX = e.clientX;
    mouseY = e.clientY;
    if (!rafPending) {
      rafPending = true;
      requestAnimationFrame(() => {
        document.documentElement.style.setProperty("--mouse-x", `${mouseX}px`);
        document.documentElement.style.setProperty("--mouse-y", `${mouseY}px`);
        rafPending = false;
      });
    }
  });

  /* ========================================================================
     9. HEALTH, STATUS & DIAGNOSTICS
     ======================================================================== */
  async function checkHealth() {
    try {
      const data = await apiJson("/api/health");
      state.backendOnline = data && data.backend === "running";
      state.ollamaOnline = data && data.ollama === "reachable";
      updateStatusUI();
    } catch {
      state.backendOnline = false;
      state.ollamaOnline = false;
      updateStatusUI();
    }
  }

  function updateStatusUI() {
    if (els.backendLed) els.backendLed.className = `node-led ${state.backendOnline ? "online" : "offline"}`;
    if (els.diagBackendLed) els.diagBackendLed.className = `diag-indicator-led ${state.backendOnline ? "online" : "offline"}`;
    if (els.diagBackendVal) els.diagBackendVal.textContent = state.backendOnline ? "Running (127.0.0.1:8000)" : "Unreachable";

    if (els.ollamaLed) els.ollamaLed.className = `node-led ${state.ollamaOnline ? "online" : "offline"}`;
    if (els.diagOllamaLed) els.diagOllamaLed.className = `diag-indicator-led ${state.ollamaOnline ? "online" : "offline"}`;
    if (els.diagOllamaVal) els.diagOllamaVal.textContent = state.ollamaOnline ? "Connected (127.0.0.1:11434)" : "Unreachable";
  }

  /* ========================================================================
     10. MODEL DISCOVERY & SELECTION
     ======================================================================== */
  async function fetchModels() {
    if (els.refreshModelsBtn) els.refreshModelsBtn.classList.add("spinning");
    try {
      const data = await apiJson("/api/models");
      state.models = Array.isArray(data.models) ? data.models : [];
      populateModelDropdowns();
      if (els.diagModelCount) els.diagModelCount.textContent = `${state.models.length} model(s) installed`;
    } catch (err) {
      state.models = [];
      populateModelDropdowns();
      if (els.diagModelCount) els.diagModelCount.textContent = "0 detected";
    } finally {
      if (els.refreshModelsBtn) {
        setTimeout(() => els.refreshModelsBtn.classList.remove("spinning"), 600);
      }
    }
  }

  function populateModelDropdowns() {
    // Topbar Model Selector
    if (state.models.length === 0) {
      if (els.modelSelect) els.modelSelect.innerHTML = `<option value="" disabled selected>No models installed in Ollama</option>`;
      state.selectedModel = "";
      if (els.composerModelName) els.composerModelName.textContent = "No model";
    } else {
      const defaultPref = state.settings.default_model;
      let target = state.selectedModel;
      if (!target || !state.models.includes(target)) {
        if (defaultPref && state.models.includes(defaultPref)) {
          target = defaultPref;
        } else {
          target = state.models[0];
        }
      }

      state.selectedModel = target;
      if (els.composerModelName) els.composerModelName.textContent = target;

      if (els.modelSelect) {
        els.modelSelect.innerHTML = state.models
          .map((m) => `<option value="${escapeHtml(m)}" ${m === target ? "selected" : ""}>${escapeHtml(m)}</option>`)
          .join("");
      }
    }

    // Settings Default Model Dropdown
    if (els.settingsDefaultModel) {
      els.settingsDefaultModel.innerHTML = `<option value="">(None - Auto select first available)</option>` +
        state.models.map((m) => `<option value="${escapeHtml(m)}" ${m === state.settings.default_model ? "selected" : ""}>${escapeHtml(m)}</option>`).join("");
    }

    updateSendButtonState();
  }

  if (els.modelSelect) {
    els.modelSelect.addEventListener("change", () => {
      state.selectedModel = els.modelSelect.value;
      if (els.composerModelName) els.composerModelName.textContent = state.selectedModel;
      updateSendButtonState();
    });
  }

  if (els.refreshModelsBtn) {
    els.refreshModelsBtn.addEventListener("click", async () => {
      await fetchModels();
      showToast("Model list refreshed.");
    });
  }

  /* ========================================================================
     11. SETTINGS MANAGEMENT
     ======================================================================== */
  async function loadSettings() {
    try {
      const data = await apiJson("/api/settings");
      state.settings.system_prompt = data.system_prompt || DEFAULT_PROMPT;
      state.settings.default_model = data.default_model || "";
      
      if (els.settingsSystemPrompt) els.settingsSystemPrompt.value = state.settings.system_prompt;
      if (state.settings.default_model && state.models.includes(state.settings.default_model)) {
        state.selectedModel = state.settings.default_model;
        populateModelDropdowns();
      }
    } catch {
      /* default to state defaults */
    }
  }

  function openSettings() {
    if (els.settingsSystemPrompt) els.settingsSystemPrompt.value = state.settings.system_prompt;
    if (els.settingsDefaultModel) els.settingsDefaultModel.value = state.settings.default_model || "";
    if (els.settingsSaveHint) els.settingsSaveHint.textContent = "";
    if (els.settingsScrim) els.settingsScrim.classList.add("show");
  }

  function closeSettings() {
    if (els.settingsScrim) els.settingsScrim.classList.remove("show");
  }

  if (els.sidebarSettingsBtn) els.sidebarSettingsBtn.addEventListener("click", openSettings);
  if (els.topbarSettingsBtn) els.topbarSettingsBtn.addEventListener("click", openSettings);
  if (els.drawerCloseBtn) els.drawerCloseBtn.addEventListener("click", closeSettings);
  if (els.settingsScrim) {
    els.settingsScrim.addEventListener("click", (e) => {
      if (e.target === els.settingsScrim) closeSettings();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && els.settingsScrim && els.settingsScrim.classList.contains("show")) {
      closeSettings();
    }
    if (e.altKey && e.key.toLowerCase() === "n") {
      e.preventDefault();
      createNewConversation();
    }
    if (e.altKey && e.key === ",") {
      e.preventDefault();
      openSettings();
    }
  });

  if (els.settingsResetBtn) {
    els.settingsResetBtn.addEventListener("click", () => {
      if (els.settingsSystemPrompt) els.settingsSystemPrompt.value = DEFAULT_PROMPT;
      if (els.settingsDefaultModel) els.settingsDefaultModel.value = "";
      if (els.settingsSaveHint) els.settingsSaveHint.textContent = "Reset to default guidelines.";
      setTimeout(() => { if (els.settingsSaveHint) els.settingsSaveHint.textContent = ""; }, 2000);
    });
  }

  if (els.settingsSaveBtn) {
    els.settingsSaveBtn.addEventListener("click", async () => {
      const payload = {
        system_prompt: els.settingsSystemPrompt ? els.settingsSystemPrompt.value.trim() : DEFAULT_PROMPT,
        default_model: els.settingsDefaultModel ? els.settingsDefaultModel.value || "" : "",
      };

      els.settingsSaveBtn.disabled = true;
      if (els.settingsSaveHint) els.settingsSaveHint.textContent = "Saving...";

      try {
        const updated = await apiJson("/api/settings", {
          method: "PUT",
          body: JSON.stringify(payload),
        });

        state.settings.system_prompt = updated.system_prompt;
        state.settings.default_model = updated.default_model;

        if (updated.default_model && state.models.includes(updated.default_model)) {
          state.selectedModel = updated.default_model;
          populateModelDropdowns();
        }

        if (els.settingsSaveHint) els.settingsSaveHint.textContent = "Settings saved.";
        showToast("Workstation settings updated.");
      } catch (err) {
        if (els.settingsSaveHint) els.settingsSaveHint.textContent = "Failed to save: " + err.message;
      } finally {
        els.settingsSaveBtn.disabled = false;
        setTimeout(() => { if (els.settingsSaveHint) els.settingsSaveHint.textContent = ""; }, 2500);
      }
    });
  }

  /* ========================================================================
     12. CONVERSATION MANAGEMENT
     ======================================================================== */
  async function loadConversations() {
    try {
      const convos = await apiJson("/api/conversations");
      state.conversations = Array.isArray(convos) ? convos : [];
      renderConversationList(els.convoSearchInput ? els.convoSearchInput.value : "");

      if (state.conversations.length > 0 && !state.currentConversationId) {
        selectConversation(state.conversations[0].id);
      } else if (state.conversations.length === 0) {
        showEmptyState();
      }
    } catch {
      state.conversations = [];
      renderConversationList();
      showEmptyState();
    }
  }

  function renderConversationList(searchTerm = "") {
    if (!els.convoList) return;
    const filter = searchTerm.trim().toLowerCase();
    const filtered = state.conversations.filter((c) =>
      (c.title || "New Conversation").toLowerCase().includes(filter)
    );

    els.convoList.innerHTML = "";
    if (els.convoEmptyState) els.convoEmptyState.hidden = filtered.length > 0;

    filtered.forEach((convo) => {
      const isActive = convo.id === state.currentConversationId;
      const item = document.createElement("div");
      item.className = `session-item ${isActive ? "active" : ""}`;
      item.setAttribute("data-id", convo.id);

      item.innerHTML = `
        <div class="session-item-main">
          <svg class="session-item-icon" viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span class="session-item-title">${escapeHtml(convo.title || "New Conversation")}</span>
        </div>
        <button class="session-delete-btn" title="Delete conversation" aria-label="Delete conversation">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
        </button>
      `;

      item.addEventListener("click", (e) => {
        if (e.target.closest(".session-delete-btn")) return;
        selectConversation(convo.id);
        closeMobileSidebar();
      });

      const delBtn = item.querySelector(".session-delete-btn");
      delBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        deleteConversation(convo.id);
      });

      els.convoList.appendChild(item);
    });
  }

  async function createNewConversation() {
    try {
      const newConvo = await apiJson("/api/conversations", {
        method: "POST",
        body: JSON.stringify({ title: "New Conversation" }),
      });

      state.conversations.unshift(newConvo);
      renderConversationList(els.convoSearchInput ? els.convoSearchInput.value : "");
      await selectConversation(newConvo.id);
      closeMobileSidebar();
      if (els.messageInput) els.messageInput.focus();
    } catch (err) {
      showToast("Could not create session: " + err.message);
    }
  }

  if (els.newChatBtn) els.newChatBtn.addEventListener("click", createNewConversation);

  async function selectConversation(convoId) {
    state.currentConversationId = convoId;
    renderConversationList(els.convoSearchInput ? els.convoSearchInput.value : "");

    try {
      const data = await apiJson(`/api/conversations/${encodeURIComponent(convoId)}`);
      if (els.sessionTitleDisplay) els.sessionTitleDisplay.textContent = data.title || "New Session";
      state.messages = Array.isArray(data.messages) ? data.messages : [];

      if (els.messagesFlow) els.messagesFlow.innerHTML = "";
      if (state.messages.length === 0) {
        showEmptyState();
      } else {
        hideEmptyState();
        state.messages.forEach((msg) => {
          appendMessageRow(msg.role, msg.content, msg.created_at);
        });
        scrollChatToBottom(false);
      }
    } catch (err) {
      showToast("Error loading session: " + err.message);
    }
  }

  async function deleteConversation(convoId) {
    try {
      await apiFetch(`/api/conversations/${encodeURIComponent(convoId)}`, {
        method: "DELETE",
      });

      state.conversations = state.conversations.filter((c) => c.id !== convoId);
      if (state.currentConversationId === convoId) {
        if (state.conversations.length > 0) {
          selectConversation(state.conversations[0].id);
        } else {
          state.currentConversationId = null;
          state.messages = [];
          if (els.sessionTitleDisplay) els.sessionTitleDisplay.textContent = "New Session";
          showEmptyState();
        }
      }
      renderConversationList(els.convoSearchInput ? els.convoSearchInput.value : "");
      showToast("Session removed.");
    } catch (err) {
      showToast("Delete failed: " + err.message);
    }
  }

  function showEmptyState() {
    if (els.messagesFlow) els.messagesFlow.innerHTML = "";
    if (els.emptyState) els.emptyState.hidden = false;
  }

  function hideEmptyState() {
    if (els.emptyState) els.emptyState.hidden = true;
  }

  /* Search Filter */
  if (els.convoSearchInput) {
    els.convoSearchInput.addEventListener("input", () => {
      const val = els.convoSearchInput.value;
      if (els.searchClearBtn) els.searchClearBtn.hidden = val.length === 0;
      renderConversationList(val);
    });
  }

  if (els.searchClearBtn) {
    els.searchClearBtn.addEventListener("click", () => {
      if (els.convoSearchInput) {
        els.convoSearchInput.value = "";
        els.convoSearchInput.focus();
      }
      els.searchClearBtn.hidden = true;
      renderConversationList();
    });
  }

  /* ========================================================================
     13. MESSAGE RENDERING & STREAMING
     ======================================================================== */
  function formatTimestamp(isoStr) {
    try {
      const d = isoStr ? new Date(isoStr) : new Date();
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return "";
    }
  }

  function appendMessageRow(role, content, timestampIso) {
    hideEmptyState();

    const wrapper = document.createElement("div");
    wrapper.className = `msg-wrapper ${role}`;

    const roleName = role === "assistant" ? "NEXUS INTELLIGENCE" : "OPERATOR";
    const timeFormatted = formatTimestamp(timestampIso);

    wrapper.innerHTML = `
      <div class="msg-header">
        <span class="msg-role-badge">
          ${role === "assistant" ? '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>' : '<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>'}
          <span>${roleName}</span>
        </span>
        <span class="msg-time">${timeFormatted}</span>
      </div>
      <div class="msg-card">${role === "assistant" ? renderMarkdown(content) : escapeHtml(content).replace(/\n/g, "<br>")}</div>
    `;

    if (role === "assistant") {
      attachCodeCopyHandlers(wrapper);
    }

    if (els.messagesFlow) els.messagesFlow.appendChild(wrapper);
    return wrapper;
  }

  function scrollChatToBottom(smooth = true) {
    if (!els.chatViewport) return;
    els.chatViewport.scrollTo({
      top: els.chatViewport.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
  }

  /* Starter Prompts */
  if (els.starterGrid) {
    els.starterGrid.querySelectorAll(".starter-tile").forEach((tile) => {
      tile.addEventListener("click", () => {
        const prompt = tile.getAttribute("data-prompt") || "";
        if (els.messageInput) {
          els.messageInput.value = prompt;
          autoGrowTextarea();
          updateSendButtonState();
          els.messageInput.focus();
        }
      });
    });
  }

  /* Composer input logic */
  function autoGrowTextarea() {
    if (!els.messageInput) return;
    els.messageInput.style.height = "auto";
    els.messageInput.style.height = Math.min(els.messageInput.scrollHeight, 180) + "px";
  }

  function updateSendButtonState() {
    if (!els.sendBtn || !els.messageInput) return;
    const hasText = els.messageInput.value.trim().length > 0;
    const hasModel = Boolean(state.selectedModel);
    els.sendBtn.disabled = !hasText || !hasModel || state.isStreaming;
  }

  if (els.messageInput) {
    els.messageInput.addEventListener("input", () => {
      autoGrowTextarea();
      updateSendButtonState();
    });

    els.messageInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSendMessage();
      }
    });
  }

  if (els.sendBtn) els.sendBtn.addEventListener("click", handleSendMessage);

  /* Send Execution & SSE Stream Reader */
  async function ensureConversation() {
    if (state.currentConversationId) return state.currentConversationId;
    const newConvo = await apiJson("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ title: "New Session" }),
    });
    state.conversations.unshift(newConvo);
    state.currentConversationId = newConvo.id;
    renderConversationList(els.convoSearchInput ? els.convoSearchInput.value : "");
    return newConvo.id;
  }

  async function handleSendMessage() {
    if (!els.messageInput) return;
    const userText = els.messageInput.value.trim();
    if (!userText || state.isStreaming) return;

    if (!state.selectedModel) {
      showToast("No model selected. Please select or install a model in Ollama.");
      return;
    }

    let convoId;
    try {
      convoId = await ensureConversation();
    } catch (err) {
      showToast("Failed to initialize session: " + err.message);
      return;
    }

    // Reset Composer
    els.messageInput.value = "";
    autoGrowTextarea();
    state.isStreaming = true;
    updateSendButtonState();

    // 1. User Message Row
    appendMessageRow("user", userText, new Date().toISOString());
    scrollChatToBottom(true);

    // 2. Assistant Message Container with Wave Loader
    const asstWrapper = document.createElement("div");
    asstWrapper.className = "msg-wrapper assistant";
    asstWrapper.innerHTML = `
      <div class="msg-header">
        <span class="msg-role-badge">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>
          <span>NEXUS INTELLIGENCE</span>
        </span>
        <span class="msg-time">${formatTimestamp()}</span>
      </div>
      <div class="msg-card">
        <div class="typing-dots"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>
      </div>
    `;
    if (els.messagesFlow) els.messagesFlow.appendChild(asstWrapper);
    scrollChatToBottom(true);

    const cardEl = asstWrapper.querySelector(".msg-card");
    let accumulated = "";
    let receivedFirstToken = false;

    try {
      const response = await fetch(`${BACKEND_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          conversation_id: convoId,
          message: userText,
          model: state.selectedModel,
        }),
      });

      if (!response.ok || !response.body) {
        let errMessage = response.statusText;
        try {
          const errJson = await response.json();
          errMessage = errJson.detail || errJson.message || errMessage;
        } catch { /* ignore */ }
        throw new Error(errMessage || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // keep remainder

        for (const rawLine of lines) {
          const line = rawLine.trim();
          if (!line.startsWith("data:")) continue;
          const jsonStr = line.slice(5).trim();
          if (!jsonStr) continue;

          let payload;
          try {
            payload = JSON.parse(jsonStr);
          } catch {
            continue;
          }

          if (payload.error) throw new Error(payload.error);
          if (payload.done) continue;

          if (typeof payload.content === "string") {
            if (!receivedFirstToken) {
              cardEl.innerHTML = "";
              receivedFirstToken = true;
            }
            accumulated += payload.content;
            cardEl.innerHTML = renderMarkdown(accumulated) + '<span class="stream-cursor"></span>';
            attachCodeCopyHandlers(asstWrapper);
            scrollChatToBottom(false);
          }
        }
      }

      // Cleanup stream cursor
      const cursor = cardEl.querySelector(".stream-cursor");
      if (cursor) cursor.remove();

      if (!accumulated) {
        cardEl.innerHTML = "<p><em>(No response received from local engine)</em></p>";
      } else {
        cardEl.innerHTML = renderMarkdown(accumulated);
        attachCodeCopyHandlers(asstWrapper);
      }

      // Auto Title first exchange
      const convo = state.conversations.find((c) => c.id === convoId);
      if (convo && (!convo.title || convo.title === "New Conversation" || convo.title === "New Session")) {
        const autoTitle = userText.slice(0, 32) + (userText.length > 32 ? "..." : "");
        convo.title = autoTitle;
        if (els.sessionTitleDisplay) els.sessionTitleDisplay.textContent = autoTitle;
        renderConversationList(els.convoSearchInput ? els.convoSearchInput.value : "");
      }

    } catch (err) {
      asstWrapper.classList.add("error");
      cardEl.innerHTML = `<p><strong>Execution Error:</strong> ${escapeHtml(err.message)}</p>`;
    } finally {
      state.isStreaming = false;
      updateSendButtonState();
      scrollChatToBottom(true);
      if (els.messageInput) els.messageInput.focus();
    }
  }

  /* ========================================================================
     14. MOBILE SIDEBAR DRAWER
     ======================================================================== */
  function openMobileSidebar() {
    if (els.sidebar) els.sidebar.classList.add("open");
    if (els.sidebarScrim) els.sidebarScrim.classList.add("show");
  }

  function closeMobileSidebar() {
    if (els.sidebar) els.sidebar.classList.remove("open");
    if (els.sidebarScrim) els.sidebarScrim.classList.remove("show");
  }

  if (els.mobileMenuBtn) els.mobileMenuBtn.addEventListener("click", openMobileSidebar);
  if (els.sidebarCloseBtn) els.sidebarCloseBtn.addEventListener("click", closeMobileSidebar);
  if (els.sidebarScrim) els.sidebarScrim.addEventListener("click", closeMobileSidebar);

  /* ========================================================================
     15. BOOT SEQUENCE INITIALIZATION
     ======================================================================== */
  function dismissBoot() {
    if (!els.bootScreen) return;
    els.bootScreen.classList.add("fade-out");
    setTimeout(() => {
      if (els.bootScreen) els.bootScreen.hidden = true;
    }, 400);
  }

  async function runBootSequence() {
    applyTheme(state.currentTheme);
    if (els.bootProgressFill) els.bootProgressFill.style.width = "25%";
    if (els.bootStep1) els.bootStep1.className = "boot-log-line done";
    if (els.bootStep2) els.bootStep2.className = "boot-log-line active";

    // Auto-dismiss safety timeout: UI is NEVER trapped in boot screen
    const safetyTimer = setTimeout(() => {
      dismissBoot();
    }, 1200);

    try {
      // Step 1: Health check
      await checkHealth();
      if (els.bootProgressFill) els.bootProgressFill.style.width = "50%";

      if (state.backendOnline) {
        if (els.bootStep2) els.bootStep2.className = "boot-log-line done";
        if (els.bootStep3) els.bootStep3.className = "boot-log-line active";
        if (els.bootProgressFill) els.bootProgressFill.style.width = "75%";

        // Step 2: Settings & Models
        await Promise.all([loadSettings(), fetchModels(), loadConversations()]);
        if (els.bootProgressFill) els.bootProgressFill.style.width = "100%";

        if (state.ollamaOnline) {
          if (els.bootStep3) els.bootStep3.className = "boot-log-line done";
          if (els.bootStep4) els.bootStep4.className = "boot-log-line done";
        } else {
          if (els.bootStep3) els.bootStep3.className = "boot-log-line error";
          if (els.bootStep4) els.bootStep4.className = "boot-log-line error";
        }
      } else {
        if (els.bootStep2) els.bootStep2.className = "boot-log-line error";
      }
    } catch {
      /* proceed to reveal UI */
    } finally {
      clearTimeout(safetyTimer);
      setTimeout(dismissBoot, 350);
      setInterval(checkHealth, 8000);
    }
  }

  if (els.bootRetryBtn) {
    els.bootRetryBtn.addEventListener("click", () => {
      if (els.bootErrorAction) els.bootErrorAction.hidden = true;
      if (els.bootProgressFill) els.bootProgressFill.style.width = "10%";
      runBootSequence();
    });
  }

  // Start Workstation
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runBootSequence);
  } else {
    runBootSequence();
  }
})();
