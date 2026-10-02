(function detectFlexGap() {
  var flex = document.createElement("div");
  flex.style.position = "absolute";
  flex.style.visibility = "hidden";
  flex.style.display = "flex";
  flex.style.flexDirection = "column";
  flex.style.rowGap = "1px";
  flex.appendChild(document.createElement("div"));
  flex.appendChild(document.createElement("div"));
  document.body.appendChild(flex);
  var supported = flex.scrollHeight === 1;
  flex.parentNode.removeChild(flex);
  if (supported) document.documentElement.classList.add("supports-flex-gap");
})();

var $ = function(selector) { return document.querySelector(selector); };
var IMPORT_LIBRARY_KEY = "kdf:imported-decks:v1";
var COLORS = ["#0f6e56", "#b07514", "#b6442a", "#6b3d6e", "#1f5d99", "#2f8f4f", "#08423a", "#9d3a1e"];
var BATCH = 40;
var renderLimit = BATCH;
var searchTimer = null;
var activePronunciation = null;

function stopPronunciation() {
  var current = activePronunciation;
  if (!current) return;
  activePronunciation = null;
  clearTimeout(current.timer);
  current.audio.onended = current.audio.onerror = current.audio.onplaying = null;
  current.audio.pause();
  current.audio.removeAttribute("src");
  current.audio.load();
  current.button.classList.remove("playing");
  current.button.setAttribute("aria-pressed", "false");
  current.button.textContent = "▶ " + (current.button.getAttribute("data-audio-label") || "播放发音");
}

function playPronunciation(src, button) {
  var sameButton = activePronunciation && activePronunciation.button === button;
  stopPronunciation();
  if (sameButton) return;
  if (typeof Audio === "undefined") {
    notify("当前环境不支持音频播放", "error");
    return;
  }
  // One player, created only on a user click. Never preload the entire deck.
  var current = { audio: new Audio(), button: button, timer: null };
  activePronunciation = current;
  button.textContent = "■ 停止发音";
  button.classList.add("playing");
  button.setAttribute("aria-pressed", "true");
  function failed(error) {
    if (activePronunciation !== current) return;
    stopPronunciation();
    notify(error && error.name === "NotAllowedError"
      ? "播放被浏览器阻止，请再次点击发音按钮"
      : "音频无法播放，请检查音频文件是否完整并重试", "error");
  }
  current.audio.onended = function() {
    if (activePronunciation === current) stopPronunciation();
  };
  current.audio.onerror = failed;
  current.audio.onplaying = function() { clearTimeout(current.timer); };
  current.timer = setTimeout(failed, 15000);
  try {
    current.audio.src = src;
    var playback = current.audio.play();
    if (playback && typeof playback.catch === "function") playback.catch(failed);
  } catch (error) { failed(error); }
}

function audioButton(side) {
  if (!side || !side.audio) return "";
  var label = side.audioLabel || "播放发音";
  return "<button type=\"button\" class=\"audio-button\" data-stop data-audio=\"" + esc(side.audio) +
    "\" data-audio-label=\"" + esc(label) + "\" aria-label=\"" + esc(label + " " + (side.primary || "")) + "\" aria-pressed=\"false\">▶ " + esc(label) + "</button>";
}

var app = {
  catalog: { decks: [] },
  importedDecks: {},
  deckData: null,
  cards: [],
  categories: new Map(),
  childCategories: new Map(),
  profile: {},
  ui: { categoryId: "all", sectionId: "all", query: "", status: "all" },
  allFlipped: false
};

function esc(value) {
  return String(value == null ? "" : value).replace(/[&<>"']/g, function(char) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" }[char];
  });
}

function fmtMath(html) {
  var strip = function(group) {
    return group[0] === "(" && group[group.length - 1] === ")" ? group.slice(1, -1) : group;
  };
  return html
    .replace(/\^(\([^()]*\)|[A-Za-z0-9+\-−]+)/g, function(match, group) { return "<sup>" + strip(group) + "</sup>"; })
    .replace(/_(\([^()]*\)|[A-Za-z0-9+\-−]+)/g, function(match, group) { return "<sub>" + strip(group) + "</sub>"; });
}

function getDeckIdFromUrl() {
  try { return new URLSearchParams(location.search).get("deck"); }
  catch (error) { return null; }
}

function setDeckIdInUrl(deckId) {
  try {
    var url = new URL(location.href);
    url.searchParams.set("deck", deckId);
    history.replaceState({}, "", url);
  } catch (error) {}
}

function profileKey() { return "kdf:profile:" + app.deckData.deck.id; }
function uiKey() { return "kdf:ui:" + app.deckData.deck.id; }
function saveProfile() { localStorage.setItem(profileKey(), JSON.stringify(app.profile)); }
function saveUi() { localStorage.setItem(uiKey(), JSON.stringify(app.ui)); }
function cardState(cardId) { return app.profile[cardId] || {}; }
function categoryLabel(category) { return (category && (category.label || category.name)) || "未分类"; }
function isImageVocabulary(card) { return card && card.type === "image-vocabulary"; }

function frontText(card) {
  var front = (card && card.front) || {};
  return isImageVocabulary(card) && front.primary ? front.primary : (front.prompt || front.primary || front.translation || "未命名卡片");
}

function frontTranslation(card) {
  var front = (card && card.front) || {};
  if (isImageVocabulary(card)) return front.prompt || "";
  return front.prompt && front.primary && front.prompt !== front.primary ? front.primary : (front.translation || "");
}

function backText(card) {
  var back = (card && card.back) || {};
  return back.primary || back.answer || back.definition || back.translation || "";
}

function backTranslation(card) {
  var back = (card && card.back) || {};
  return back.translation || back.explanation || "";
}

function backPhonetic(card) { return (card && card.back && card.back.phonetic) || ""; }

function categoryColor(categoryId) {
  var roots = Array.from(app.categories.values()).filter(function(category) { return !category.parentId; });
  var current = app.categories.get(categoryId);
  var rootId = (current && current.parentId) || categoryId;
  var index = roots.findIndex(function(category) { return category.id === rootId; });
  return COLORS[(index < 0 ? 0 : index) % COLORS.length];
}

function nowIso() { return new Date().toISOString(); }

function notify(message, tone) {
  var toast = $("#toast");
  toast.textContent = message;
  toast.className = "toast " + (tone || "success");
  toast.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(function() { toast.hidden = true; }, 4200);
}

function showExport(title, content) {
  $("#exportTitle").textContent = title;
  $("#exportText").value = content;
  $("#exportPreview").hidden = false;
  $("#exportPreview").setAttribute("aria-hidden", "false");
  $("#exportText").focus();
  $("#exportText").select();
}

function closeExport() {
  $("#exportPreview").hidden = true;
  $("#exportPreview").setAttribute("aria-hidden", "true");
}

var scriptLoads = {};
function loadScript(src) {
  if (scriptLoads[src]) return scriptLoads[src];
  scriptLoads[src] = new Promise(function(resolve, reject) {
    var script = document.createElement("script");
    script.src = src;
    script.onload = function() { resolve(); };
    script.onerror = function() {
      scriptLoads[src] = null;
      reject(new Error("无法加载卡组脚本：" + src));
    };
    document.head.appendChild(script);
  });
  return scriptLoads[src];
}

function validateDeck(payload) {
  var errors = [];
  var warnings = [];
  if (!payload || typeof payload !== "object") errors.push("文件不是 JSON 对象");
  if (!payload || payload.schemaVersion !== "kdf/1.0") errors.push("仅支持 schemaVersion 为 kdf/1.0 的卡组");
  if (!payload || !payload.deck || typeof payload.deck !== "object") errors.push("缺少 deck 元数据");
  ["id", "title", "version", "defaultCardType"].forEach(function(field) {
    if (!payload || !payload.deck || !String(payload.deck[field] || "").trim()) errors.push("deck." + field + " 必填");
  });
  if (!payload || !Array.isArray(payload.categories)) errors.push("categories 必须是数组");
  if (!payload || !Array.isArray(payload.cards) || !payload.cards.length) errors.push("cards 必须是非空数组");
  var categoryIds = new Set();
  (payload && payload.categories ? payload.categories : []).forEach(function(category) {
    if (!category || !category.id || !category.name) errors.push("分类必须具有 id 和 name");
    if (category && categoryIds.has(category.id)) errors.push("分类 ID 重复：" + category.id);
    if (category && category.id) categoryIds.add(category.id);
  });
  var cardIds = new Set();
  var published = 0;
  (payload && payload.cards ? payload.cards : []).forEach(function(card) {
    if (!card || !card.id || !card.type || !card.status || !card.front || !card.back) {
      errors.push("每张卡必须包含 id、type、status、front、back");
    }
    if (card && cardIds.has(card.id)) errors.push("卡片 ID 重复：" + card.id);
    if (card && card.id) cardIds.add(card.id);
    if (card && card.categoryId && !categoryIds.has(card.categoryId)) errors.push("卡片 " + card.id + " 指向不存在的分类");
    if (card && card.status === "published") published += 1;
  });
  if (!published) warnings.push("该卡组没有 published 卡；导入后不会在学习区显示卡片。");
  return {
    valid: !errors.length,
    errors: errors,
    warnings: warnings,
    cardCount: payload && payload.cards ? payload.cards.length : 0,
    publishedCount: published
  };
}

function loadImportedDecks() {
  try { app.importedDecks = JSON.parse(localStorage.getItem(IMPORT_LIBRARY_KEY) || "{}"); }
  catch (error) { app.importedDecks = {}; }
}

function saveImportedDecks() {
  localStorage.setItem(IMPORT_LIBRARY_KEY, JSON.stringify(app.importedDecks));
}

function catalogEntries() {
  var bundled = app.catalog.decks.map(function(entry) {
    return Object.assign({}, entry, { source: "bundled" });
  });
  var imported = Object.keys(app.importedDecks).map(function(id) {
    var record = app.importedDecks[id];
    return {
      id: id,
      source: "local",
      importedAt: record.importedAt,
      title: record.deck && record.deck.deck ? record.deck.deck.title : id
    };
  });
  return bundled.concat(imported);
}

function loadCatalog() {
  if (!window.__KDF_CATALOG__) throw new Error("缺少内置卡组目录");
  app.catalog = window.__KDF_CATALOG__;
  loadImportedDecks();
}

function findCatalogDeck(deckId) {
  var decks = app.catalog.decks || [];
  var found = decks.filter(function(deck) { return deck.id === deckId; })[0];
  if (found) return found;
  found = decks.filter(function(deck) { return deck.featured; })[0];
  return found || decks[0];
}

function getDeckPayload(deckId) {
  if (app.importedDecks[deckId]) {
    return Promise.resolve(app.importedDecks[deckId].deck);
  }
  if (window.__KDF_DECKS__ && window.__KDF_DECKS__[deckId]) {
    return Promise.resolve(window.__KDF_DECKS__[deckId]);
  }
  var entry = findCatalogDeck(deckId);
  if (!entry) return Promise.reject(new Error("卡组目录为空"));
  if (!entry.script) return Promise.reject(new Error("无法加载卡组：" + entry.id));
  return loadScript(entry.script).then(function() {
    if (!window.__KDF_DECKS__ || !window.__KDF_DECKS__[entry.id]) {
      throw new Error("无法加载卡组：" + entry.id);
    }
    return window.__KDF_DECKS__[entry.id];
  });
}

function migrateLegacyCfaProfile() {
  if (app.deckData.deck.id !== "cfa-level-1" || Object.keys(app.profile).length) return;
  try {
    var old = JSON.parse(localStorage.getItem("cfa_l1_flash_v2") || "{}");
    if (!Object.keys(old).length) return;
    var next = {};
    Object.keys(old).forEach(function(cardId) {
      var state = old[cardId] || {};
      var priority = state.pr == null ? (state.fl ? 1 : 0) : state.pr;
      next[cardId] = {
        status: state.s === "k" ? "known" : state.s === "u" ? "learning" : null,
        priority: priority,
        note: state.n || ""
      };
    });
    app.profile = next;
    saveProfile();
  } catch (error) {}
}

function loadDeck(deckId) {
  stopPronunciation();
  return getDeckPayload(deckId).then(function(payload) {
    var result = validateDeck(payload);
    if (!result.valid) throw new Error(result.errors.join("；"));
    app.deckData = payload;
    app.cards = payload.cards.filter(function(card) { return card.status === "published"; });
    app.categories = new Map(payload.categories.map(function(category) { return [category.id, category]; }));
    app.childCategories = new Map();
    payload.categories.forEach(function(category) {
      if (!category.parentId) return;
      var list = app.childCategories.get(category.parentId) || [];
      list.push(category);
      app.childCategories.set(category.parentId, list);
    });
    try { app.profile = JSON.parse(localStorage.getItem(profileKey()) || "{}"); }
    catch (error) { app.profile = {}; }
    try { app.ui = Object.assign({}, app.ui, JSON.parse(localStorage.getItem(uiKey()) || "{}")); }
    catch (error) {}
    migrateLegacyCfaProfile();
    if (app.ui.categoryId !== "all" && !app.categories.has(app.ui.categoryId)) app.ui.categoryId = "all";
    if (app.ui.sectionId !== "all" && !app.categories.has(app.ui.sectionId)) app.ui.sectionId = "all";
    setDeckIdInUrl(payload.deck.id);
    applyDeckBrand();
  });
}

function applyDeckBrand() {
  var deck = app.deckData.deck;
  var accent = (deck.theme && deck.theme.accent) || "#0f6e56";
  document.title = deck.title + " · 知识闪卡";
  $("#deckTitle").textContent = deck.title;
  $("#deckDescription").textContent = deck.description || "可导入、可复习、可迁移的知识闪卡。";
  $("#deckBadge").textContent = deck.defaultCardType;
  $("#deckAccent").style.background = accent;
  document.documentElement.style.setProperty("--accent", accent);
}

function renderDeckPicker() {
  var select = $("#deckPicker");
  select.innerHTML = catalogEntries().map(function(entry) {
    var selected = entry.id === app.deckData.deck.id ? " selected" : "";
    var title = entry.id === app.deckData.deck.id ? app.deckData.deck.title : (entry.title || entry.id);
    var suffix = entry.source === "local" ? " · 本地" : "";
    return "<option value=\"" + esc(entry.id) + "\"" + selected + ">" + esc(title) + suffix + "</option>";
  }).join("");
}

function rootCategories() {
  return Array.from(app.categories.values()).filter(function(category) {
    return !category.parentId;
  }).sort(function(a, b) {
    return (a.sortOrder || 0) - (b.sortOrder || 0);
  });
}

function renderCategories() {
  var categories = [{ id: "all", label: "全部分类" }].concat(rootCategories().map(function(category) {
    return { id: category.id, label: categoryLabel(category) };
  }));
  $("#topics").innerHTML = categories.map(function(category) {
    return "<button class=\"chip" + (category.id === app.ui.categoryId ? " active" : "") + "\" data-category=\"" + esc(category.id) + "\">" + esc(category.label) + "</button>";
  }).join("");
  $("#topics").querySelectorAll("[data-category]").forEach(function(button) {
    button.addEventListener("click", function() {
      app.ui.categoryId = button.getAttribute("data-category");
      app.ui.sectionId = "all";
      saveUi();
      renderCategories();
      renderSections();
      renderLimit = BATCH;
      render();
    });
  });
  $("#filterCategory").innerHTML = categories.map(function(category) {
    return "<option value=\"" + esc(category.id) + "\">" + esc(category.label) + "</option>";
  }).join("");
  $("#filterCategory").value = app.ui.categoryId;
}

function renderSections() {
  var sections = app.ui.categoryId === "all" ? [] : (app.childCategories.get(app.ui.categoryId) || []);
  var wrap = $("#sections");
  if (!sections.length) { wrap.hidden = true; wrap.innerHTML = ""; return; }
  wrap.hidden = false;
  var choices = [{ id: "all", label: "全部模块" }].concat(sections.map(function(section) {
    return { id: section.id, label: categoryLabel(section) };
  }));
  wrap.innerHTML = choices.map(function(section) {
    return "<button class=\"chip section" + (section.id === app.ui.sectionId ? " active" : "") + "\" data-section=\"" + esc(section.id) + "\">" + esc(section.label) + "</button>";
  }).join("");
  wrap.querySelectorAll("[data-section]").forEach(function(button) {
    button.addEventListener("click", function() {
      app.ui.sectionId = button.getAttribute("data-section");
      saveUi();
      renderSections();
      renderLimit = BATCH;
      render();
    });
  });
}

function filteredCards() {
  var query = app.ui.query.trim().toLowerCase();
  return app.cards.filter(function(card) {
    if (app.ui.categoryId !== "all" && card.categoryId !== app.ui.categoryId) return false;
    if (app.ui.sectionId !== "all" && card.sectionId !== app.ui.sectionId) return false;
    var state = cardState(card.id);
    if (app.ui.status === "known" && state.status !== "known") return false;
    if (app.ui.status === "learning" && state.status !== "learning") return false;
    if (app.ui.status === "unseen" && state.status) return false;
    if (app.ui.status === "starred" && !state.priority) return false;
    if (app.ui.status === "noted" && !(state.note || "").trim()) return false;
    if (!query) return true;
    var back = card.back || {};
    var haystack = [frontText(card), frontTranslation(card), backText(card), backTranslation(card),
      back.phonetic, back.homophone, back.explanation, back.example].concat(card.tags || []);
    return haystack.join(" ").toLowerCase().indexOf(query) !== -1;
  });
}

function renderCard(card, number) {
  var state = cardState(card.id);
  var category = app.categories.get(card.categoryId);
  var stars = [1, 2, 3].map(function(level) {
    return "<button class=\"star" + (state.priority >= level ? " on" : "") + "\" data-priority=\"" + level + "\" aria-label=\"设置 " + level + " 星优先级\">★</button>";
  }).join("");
  var image = card.front && card.front.image
    ? "<img class=\"card-image\" src=\"" + esc(card.front.image) + "\" alt=\"" + esc(frontText(card)) + "\">"
    : "";
  var frontExtra = frontTranslation(card) ? "<div class=\"translation\">" + fmtMath(esc(frontTranslation(card))) + "</div>" : "";
  var frontPhonetic = card.front && card.front.phonetic ? "<div class=\"translation phonetic\">" + esc(card.front.phonetic) + "</div>" : "";
  var phonetic = backPhonetic(card) ? "<div class=\"translation\">" + esc(backPhonetic(card)) + "</div>" : "";
  var backExtra = backTranslation(card) ? "<div class=\"translation answer-translation\">" + fmtMath(esc(backTranslation(card))) + "</div>" : "";
  var example = card.back && card.back.example ? "<div class=\"example\">" + esc(card.back.example) + "</div>" : "";
  var homophone = card.back && card.back.homophone ? "<div class=\"mnemonic\"><span class=\"detail-label\">谐音提示</span>" + esc(card.back.homophone) + "</div>" : "";
  var explanation = card.back && card.back.explanation && card.back.explanation !== backTranslation(card)
    ? "<div class=\"example mnemonic\"><span class=\"detail-label\">" + (homophone ? "记忆句" : "解释") + "</span>" + esc(card.back.explanation) + "</div>" : "";
  var element = document.createElement("article");
  element.className = "card" + (app.allFlipped ? " flipped" : "");
  element.innerHTML =
    "<div class=\"face front\"><div class=\"meta\"><span class=\"tag\" style=\"background:" + categoryColor(card.categoryId) + "\">" + esc(categoryLabel(category)) + "</span><span class=\"num\">#" + number + "</span><span class=\"stars\">" + stars + "</span><span class=\"type\">" + esc(card.type) + "</span></div><div class=\"term\">" + fmtMath(esc(frontText(card))) + "</div>" + frontExtra + frontPhonetic + audioButton(card.front) + image + "<div class=\"hint\">点击翻转查看答案</div></div>" +
    "<div class=\"face back\"><div class=\"meta\"><span class=\"tag\" style=\"background:" + categoryColor(card.categoryId) + "\">" + esc(categoryLabel(category)) + "</span><span class=\"type\">" + esc(card.type) + "</span></div><div class=\"definition\">" + fmtMath(esc(backText(card))) + "</div>" + phonetic + backExtra + homophone + explanation + example + audioButton(card.back) +
    "<div class=\"actions\" data-stop><button class=\"sbtn" + (state.status === "known" ? " on known" : "") + "\" data-status=\"known\">已掌握</button><button class=\"sbtn" + (state.status === "learning" ? " on learning" : "") + "\" data-status=\"learning\">学习中</button></div>" +
    "<label class=\"note-wrap\" data-stop><span>笔记</span><textarea class=\"note\" placeholder=\"添加本卡笔记…\">" + esc(state.note || "") + "</textarea></label></div>";
  element.addEventListener("click", function(event) {
    if (!event.target.closest("[data-stop]") && !event.target.closest(".star")) element.classList.toggle("flipped");
  });
  element.querySelectorAll("[data-audio]").forEach(function(button) {
    button.addEventListener("click", function(event) {
      event.stopPropagation();
      playPronunciation(button.getAttribute("data-audio"), button);
    });
  });
  element.querySelectorAll(".star").forEach(function(button) {
    button.addEventListener("click", function(event) {
      event.stopPropagation();
      var level = Number(button.getAttribute("data-priority"));
      var current = cardState(card.id);
      app.profile[card.id] = Object.assign({}, current, { priority: current.priority === level ? 0 : level });
      saveProfile();
      render();
    });
  });
  element.querySelectorAll("[data-status]").forEach(function(button) {
    button.addEventListener("click", function(event) {
      event.stopPropagation();
      var status = button.getAttribute("data-status");
      var current = cardState(card.id);
      app.profile[card.id] = Object.assign({}, current, { status: current.status === status ? null : status });
      saveProfile();
      render();
    });
  });
  element.querySelector(".note").addEventListener("input", function(event) {
    var current = cardState(card.id);
    app.profile[card.id] = Object.assign({}, current, { note: event.target.value });
    saveProfile();
    updateStats();
  });
  return element;
}

function updateStats() {
  var known = app.cards.filter(function(card) { return cardState(card.id).status === "known"; }).length;
  var learning = app.cards.filter(function(card) { return cardState(card.id).status === "learning"; }).length;
  var percent = app.cards.length ? Math.round((known / app.cards.length) * 100) : 0;
  $("#known").textContent = "已掌握 " + known;
  $("#learning").textContent = "学习中 " + learning;
  $("#progressFill").style.width = percent + "%";
  $("#progressText").textContent = percent + "%";
}

function render() {
  stopPronunciation();
  var list = filteredCards();
  renderLimit = Math.min(Math.max(renderLimit, BATCH), list.length);
  var deck = $("#deck");
  deck.innerHTML = "";
  var fragment = document.createDocumentFragment();
  list.slice(0, renderLimit).forEach(function(card, index) {
    fragment.appendChild(renderCard(card, index + 1));
  });
  deck.appendChild(fragment);
  $("#count").textContent = list.length + " / " + app.cards.length + " 张";
  $("#empty").hidden = Boolean(list.length);
  $("#loadMore").hidden = renderLimit >= list.length;
  updateStats();
}

function showError(error) {
  $("#deck").innerHTML = "<div class=\"error\"><h2>无法加载卡组</h2><p>" + esc(error.message || String(error)) + "</p></div>";
}

function openManager() {
  var manager = $("#manager");
  manager.hidden = false;
  manager.setAttribute("aria-hidden", "false");
  renderManagerLibrary();
  $("#closeManager").focus();
}

function closeManager() {
  var manager = $("#manager");
  manager.hidden = true;
  manager.setAttribute("aria-hidden", "true");
  $("#manageDecks").focus();
}

function setSettingsOpen(open) {
  document.body.classList.toggle("settings-open", open);
  $("#settingsToggle").setAttribute("aria-expanded", String(open));
  $("#settingsToggle").textContent = open ? "收起" : "设置";
}

function renderManagerLibrary() {
  var rows = catalogEntries().map(function(entry) {
    var current = entry.id === app.deckData.deck.id;
    var info = entry.source === "local" ? app.importedDecks[entry.id].deck : null;
    var title = (info && info.deck && info.deck.title) || entry.title || entry.id;
    var count = info && info.cards ? info.cards.length : null;
    var meta = entry.source === "local" ? ("本地导入 · " + count + " 张") : "内置卡组";
    return "<div class=\"library-row\"><div><strong>" + esc(title) + "</strong><small>" + esc(meta) + "</small></div><div class=\"library-actions\"><button class=\"text-btn\" data-open-deck=\"" + esc(entry.id) + "\"" + (current ? " disabled" : "") + ">" + (current ? "当前" : "打开") + "</button>" + (entry.source === "local" ? "<button class=\"text-btn danger\" data-delete-deck=\"" + esc(entry.id) + "\">删除</button>" : "") + "</div></div>";
  }).join("") || "<p class=\"muted\">尚无卡组。</p>";
  $("#libraryList").innerHTML = rows;
  $("#libraryList").querySelectorAll("[data-open-deck]").forEach(function(button) {
    button.addEventListener("click", function() {
      switchDeck(button.getAttribute("data-open-deck")).then(closeManager);
    });
  });
  $("#libraryList").querySelectorAll("[data-delete-deck]").forEach(function(button) {
    button.addEventListener("click", function() {
      deleteImportedDeck(button.getAttribute("data-delete-deck"));
    });
  });
}

function switchDeck(deckId) {
  $("#deck").innerHTML = "<div class=\"loading\">正在切换卡组…</div>";
  return loadDeck(deckId).then(function() {
    renderDeckPicker();
    renderCategories();
    renderSections();
    renderLimit = BATCH;
    render();
  }).catch(showError);
}

function parsePastedJson(raw) {
  var text = String(raw || "").trim();
  if (!text) throw new Error("请先粘贴 JSON 内容");
  return JSON.parse(text);
}

function importDeckFromText(raw) {
  var payload = parsePastedJson(raw);
  var result = validateDeck(payload);
  if (!result.valid) throw new Error(result.errors.join("；"));
  var id = payload.deck.id;
  var existing = app.importedDecks[id];
  if (existing && !confirm("本地已有“" + payload.deck.title + "”。是否覆盖本地副本？")) return Promise.resolve();
  app.importedDecks[id] = { importedAt: nowIso(), deck: payload };
  saveImportedDecks();
  renderDeckPicker();
  renderManagerLibrary();
  var notice = result.warnings.length
    ? "已导入 " + payload.deck.title + "，但：" + result.warnings.join(" ")
    : "已导入 " + payload.deck.title + "（" + result.cardCount + " 张卡）";
  notify(notice, result.warnings.length ? "warning" : "success");
  return switchDeck(id);
}

function ankiSide(side) {
  if (!side) return "";
  return [side.prompt, side.primary, side.phonetic, side.translation, side.definition, side.answer, side.homophone, side.explanation, side.example]
    .filter(Boolean)
    .map(function(value) { return String(value).replace(/\r?\n/g, "<br>"); })
    .join("<br>");
}

function exportDeckJson() {
  showExport("KDF JSON", JSON.stringify(app.deckData, null, 2));
  notify("已生成 KDF JSON，请选中文本后手动复制");
}

function exportAnkiTsv() {
  var header = ["Front", "Back", "Tags"];
  var rows = [header].concat(app.deckData.cards.filter(function(card) {
    return card.status === "published";
  }).map(function(card) {
    return [ankiSide(card.front), ankiSide(card.back), (card.tags || []).join(" ")];
  }));
  var text = rows.map(function(row) {
    return row.map(function(value) { return "\"" + String(value).replace(/"/g, "\"\"") + "\""; }).join("\t");
  }).join("\n");
  showExport("Anki TSV", text);
  notify("已生成 Anki TSV，请选中文本后手动复制");
}

function exportProfile() {
  var packageData = {
    format: "kdf-profile/1.0",
    deckId: app.deckData.deck.id,
    exportedAt: nowIso(),
    profile: app.profile
  };
  showExport("学习档案 JSON", JSON.stringify(packageData, null, 2));
  notify("已生成学习档案，请选中文本后手动复制");
}

function restoreProfileFromText(raw) {
  var data = parsePastedJson(raw);
  if (!data || data.format !== "kdf-profile/1.0" || data.deckId !== app.deckData.deck.id || !data.profile || typeof data.profile !== "object") {
    throw new Error("学习档案不属于当前卡组或格式不正确");
  }
  if (!confirm("恢复会覆盖当前卡组现有的学习进度、星标和笔记。是否继续？")) return;
  app.profile = data.profile;
  saveProfile();
  render();
  notify("学习档案已恢复");
}

function deleteImportedDeck(deckId) {
  var record = app.importedDecks[deckId];
  if (!record || !confirm("删除本地副本“" + record.deck.deck.title + "”？不会删除原始文件。")) return;
  delete app.importedDecks[deckId];
  saveImportedDecks();
  renderDeckPicker();
  renderManagerLibrary();
  if (app.deckData.deck.id === deckId) switchDeck(app.catalog.decks[0].id);
  notify("本地导入卡组已删除");
}

function bindEvents() {
  document.addEventListener("visibilitychange", function() {
    if (document.hidden) stopPronunciation();
  });
  window.addEventListener("pagehide", stopPronunciation);
  $("#deckPicker").addEventListener("change", function(event) {
    switchDeck(event.target.value);
    if (window.matchMedia("(max-width: 760px)").matches) setSettingsOpen(false);
  });
  $("#settingsToggle").addEventListener("click", function() {
    setSettingsOpen(!document.body.classList.contains("settings-open"));
  });
  $("#search").addEventListener("input", function(event) {
    var value = event.target.value;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function() {
      app.ui.query = value;
      saveUi();
      renderLimit = BATCH;
      render();
    }, 200);
  });
  $("#filterStatus").addEventListener("change", function(event) {
    app.ui.status = event.target.value;
    saveUi();
    renderLimit = BATCH;
    render();
  });
  $("#filterCategory").addEventListener("change", function(event) {
    app.ui.categoryId = event.target.value;
    app.ui.sectionId = "all";
    saveUi();
    renderCategories();
    renderSections();
    renderLimit = BATCH;
    render();
  });
  $("#flipAll").addEventListener("click", function() {
    app.allFlipped = !app.allFlipped;
    $("#flipAll").textContent = app.allFlipped ? "隐藏释义" : "显示释义";
    document.querySelectorAll(".card").forEach(function(card) {
      card.classList.toggle("flipped", app.allFlipped);
    });
  });
  $("#shuffle").addEventListener("click", function() {
    app.cards = app.cards.slice().sort(function() { return Math.random() - 0.5; });
    renderLimit = BATCH;
    render();
  });
  $("#reset").addEventListener("click", function() {
    if (!confirm("清除当前卡组的学习进度、优先级和笔记？此操作不可恢复。")) return;
    app.profile = {};
    saveProfile();
    render();
  });
  $("#loadMore").addEventListener("click", function() {
    renderLimit += BATCH;
    render();
  });
  $("#theme").addEventListener("click", function() {
    if (document.documentElement.hasAttribute("data-theme-dark")) {
      document.documentElement.removeAttribute("data-theme-dark");
      $("#theme").textContent = "切换深色";
    } else {
      document.documentElement.setAttribute("data-theme-dark", "");
      $("#theme").textContent = "切换浅色";
    }
  });
  $("#manageDecks").addEventListener("click", openManager);
  $("#closeManager").addEventListener("click", closeManager);
  $("#manager").addEventListener("click", function(event) {
    if (event.target === $("#manager")) closeManager();
  });
  $("#closeExport").addEventListener("click", closeExport);
  $("#exportPreview").addEventListener("click", function(event) {
    if (event.target === $("#exportPreview")) closeExport();
  });
  document.addEventListener("keydown", function(event) {
    if (event.key === "Escape") {
      closeManager();
      closeExport();
      setSettingsOpen(false);
    }
  });
  $("#importDeckPaste").addEventListener("click", function() {
    importDeckFromText($("#importDeckText").value).then(function() {
      $("#importDeckText").value = "";
    }).catch(function(error) {
      notify(error.message || String(error), "error");
    });
  });
  $("#restoreProfilePaste").addEventListener("click", function() {
    try {
      restoreProfileFromText($("#importDeckText").value);
      $("#importDeckText").value = "";
    } catch (error) {
      notify(error.message || String(error), "error");
    }
  });
  $("#exportDeckJson").addEventListener("click", exportDeckJson);
  $("#exportAnki").addEventListener("click", exportAnkiTsv);
  $("#exportProfile").addEventListener("click", exportProfile);
}

function boot() {
  try {
    $("#manager").hidden = true;
    $("#manager").setAttribute("aria-hidden", "true");
    loadCatalog();
    var requestedDeckId = getDeckIdFromUrl();
    var configuredDefault = app.catalog.defaultDeckId;
    var hasConfigured = configuredDefault && app.catalog.decks.some(function(deck) { return deck.id === configuredDefault; });
    var cfa = app.catalog.decks.filter(function(deck) { return deck.id === "cfa-level-1"; })[0];
    var defaultDeckId = hasConfigured ? configuredDefault : ((cfa && cfa.id) || (app.catalog.decks[0] && app.catalog.decks[0].id));
    var availableDeckIds = {};
    catalogEntries().forEach(function(entry) { availableDeckIds[entry.id] = true; });
    var startId = requestedDeckId && availableDeckIds[requestedDeckId] ? requestedDeckId : defaultDeckId;
    loadDeck(startId).then(function() {
      bindEvents();
      renderDeckPicker();
      $("#search").value = app.ui.query;
      $("#filterStatus").value = app.ui.status;
      renderCategories();
      renderSections();
      render();
    }).catch(showError);
  } catch (error) {
    showError(error);
  }
}

boot();
