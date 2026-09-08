const $ = selector => document.querySelector(selector);
const IMPORT_LIBRARY_KEY = "kdf:imported-decks:v1";
const MAX_IMPORT_BYTES = 20 * 1024 * 1024;
const COLORS = ["#0f6e56", "#b07514", "#b6442a", "#6b3d6e", "#1f5d99", "#2f8f4f", "#08423a", "#9d3a1e"];
const BATCH = 40;
let renderLimit = BATCH;

const app = {
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

function esc(value) { return String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[char])); }
function fmtMath(html) { const strip = group => group[0] === "(" && group[group.length - 1] === ")" ? group.slice(1, -1) : group; return html.replace(/\^(\([^()]*\)|[A-Za-z0-9+\-−]+)/g, (match, group) => `<sup>${strip(group)}</sup>`).replace(/_(\([^()]*\)|[A-Za-z0-9+\-−]+)/g, (match, group) => `<sub>${strip(group)}</sub>`); }
function getDeckIdFromUrl() { return new URLSearchParams(location.search).get("deck"); }
function setDeckIdInUrl(deckId) { const url = new URL(location.href); url.searchParams.set("deck", deckId); history.replaceState({}, "", url); }
function profileKey() { return `kdf:profile:${app.deckData.deck.id}`; }
function uiKey() { return `kdf:ui:${app.deckData.deck.id}`; }
function saveProfile() { localStorage.setItem(profileKey(), JSON.stringify(app.profile)); }
function saveUi() { localStorage.setItem(uiKey(), JSON.stringify(app.ui)); }
function cardState(cardId) { return app.profile[cardId] || {}; }
function categoryLabel(category) { return category?.label || category?.name || "未分类"; }
function isImageVocabulary(card) { return card?.type === "image-vocabulary"; }
function frontText(card) {
  const front = card.front || {};
  // Picture-vocabulary cards keep their image clean while still showing the target English word.
  return isImageVocabulary(card) && front.primary ? front.primary : (front.prompt || front.primary || front.translation || "未命名卡片");
}
function frontTranslation(card) {
  const front = card.front || {};
  if (isImageVocabulary(card)) return front.prompt || "";
  return front.prompt && front.primary && front.prompt !== front.primary ? front.primary : front.translation || "";
}
function backText(card) { const back = card.back || {}; return back.primary || back.answer || back.definition || back.translation || ""; }
function backTranslation(card) { const back = card.back || {}; return back.translation || back.explanation || ""; }
function backPhonetic(card) { return card.back?.phonetic || ""; }
function categoryColor(categoryId) { const roots = [...app.categories.values()].filter(category => !category.parentId); const current = app.categories.get(categoryId); const rootId = current?.parentId || categoryId; const index = roots.findIndex(category => category.id === rootId); return COLORS[(index < 0 ? 0 : index) % COLORS.length]; }
function nowIso() { return new Date().toISOString(); }

function notify(message, tone = "success") {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast ${tone}`;
  toast.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => { toast.hidden = true; }, 4200);
}

function downloadBlob(filename, content, type) {
  const blob = content instanceof Blob ? content : new Blob([content], { type });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 2000);
}

function sanitizeFilename(value) { return String(value || "kdf-deck").replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, "-").slice(0, 80); }

function validateDeck(payload) {
  const errors = [];
  const warnings = [];
  if (!payload || typeof payload !== "object") errors.push("文件不是 JSON 对象");
  if (payload?.schemaVersion !== "kdf/1.0") errors.push("仅支持 schemaVersion 为 kdf/1.0 的卡组");
  if (!payload?.deck || typeof payload.deck !== "object") errors.push("缺少 deck 元数据");
  for (const field of ["id", "title", "version", "defaultCardType"]) if (!String(payload?.deck?.[field] || "").trim()) errors.push(`deck.${field} 必填`);
  if (!Array.isArray(payload?.categories)) errors.push("categories 必须是数组");
  if (!Array.isArray(payload?.cards) || !payload.cards.length) errors.push("cards 必须是非空数组");
  const categoryIds = new Set();
  for (const category of payload?.categories || []) {
    if (!category?.id || !category?.name) errors.push("分类必须具有 id 和 name");
    if (categoryIds.has(category?.id)) errors.push(`分类 ID 重复：${category.id}`);
    categoryIds.add(category?.id);
  }
  const cardIds = new Set();
  let published = 0;
  for (const card of payload?.cards || []) {
    if (!card?.id || !card?.type || !card?.status || !card?.front || !card?.back) errors.push("每张卡必须包含 id、type、status、front、back");
    if (cardIds.has(card?.id)) errors.push(`卡片 ID 重复：${card.id}`);
    cardIds.add(card?.id);
    if (card?.categoryId && !categoryIds.has(card.categoryId)) errors.push(`卡片 ${card.id} 指向不存在的分类`);
    if (card?.status === "published") published += 1;
  }
  if (!published) warnings.push("该卡组没有 published 卡；导入后不会在学习区显示卡片。");
  return { valid: !errors.length, errors, warnings, cardCount: payload?.cards?.length || 0, publishedCount: published };
}

function loadImportedDecks() {
  try { app.importedDecks = JSON.parse(localStorage.getItem(IMPORT_LIBRARY_KEY) || "{}"); }
  catch { app.importedDecks = {}; }
}
function saveImportedDecks() { localStorage.setItem(IMPORT_LIBRARY_KEY, JSON.stringify(app.importedDecks)); }
function catalogEntries() {
  const bundled = app.catalog.decks.map(entry => ({...entry, source: "bundled"}));
  const imported = Object.entries(app.importedDecks).map(([id, record]) => ({id, source: "local", importedAt: record.importedAt, title: record.deck.deck.title}));
  return [...bundled, ...imported];
}

async function loadCatalog() {
  const response = await fetch("./deck-catalog.json");
  if (!response.ok) throw new Error("无法加载内置卡组目录");
  app.catalog = await response.json();
  loadImportedDecks();
}

async function getDeckPayload(deckId) {
  if (app.importedDecks[deckId]) return app.importedDecks[deckId].deck;
  const entry = app.catalog.decks.find(deck => deck.id === deckId) || app.catalog.decks.find(deck => deck.featured) || app.catalog.decks[0];
  if (!entry) throw new Error("卡组目录为空");
  const response = await fetch(entry.path);
  if (!response.ok) throw new Error(`无法加载卡组：${entry.id}`);
  return response.json();
}

function migrateLegacyCfaProfile() {
  if (app.deckData.deck.id !== "cfa-level-1" || Object.keys(app.profile).length) return;
  try {
    const old = JSON.parse(localStorage.getItem("cfa_l1_flash_v2") || "{}");
    if (!Object.keys(old).length) return;
    app.profile = Object.fromEntries(Object.entries(old).map(([cardId, state]) => [cardId, { status: state.s === "k" ? "known" : state.s === "u" ? "learning" : null, priority: state.pr ?? (state.fl ? 1 : 0), note: state.n || "" }]));
    saveProfile();
  } catch (error) { console.warn("无法迁移旧 CFA 学习状态", error); }
}

async function loadDeck(deckId) {
  const payload = await getDeckPayload(deckId);
  const result = validateDeck(payload);
  if (!result.valid) throw new Error(result.errors.join("；"));
  app.deckData = payload;
  app.cards = payload.cards.filter(card => card.status === "published");
  app.categories = new Map(payload.categories.map(category => [category.id, category]));
  app.childCategories = new Map();
  payload.categories.forEach(category => { if (!category.parentId) return; const list = app.childCategories.get(category.parentId) || []; list.push(category); app.childCategories.set(category.parentId, list); });
  app.profile = JSON.parse(localStorage.getItem(profileKey()) || "{}");
  app.ui = {...app.ui, ...JSON.parse(localStorage.getItem(uiKey()) || "{}")};
  migrateLegacyCfaProfile();
  if (app.ui.categoryId !== "all" && !app.categories.has(app.ui.categoryId)) app.ui.categoryId = "all";
  if (app.ui.sectionId !== "all" && !app.categories.has(app.ui.sectionId)) app.ui.sectionId = "all";
  setDeckIdInUrl(payload.deck.id);
  applyDeckBrand();
}

function applyDeckBrand() {
  const deck = app.deckData.deck;
  document.title = `${deck.title} · 知识闪卡`;
  $("#deckTitle").textContent = deck.title;
  $("#deckDescription").textContent = deck.description || "可导入、可复习、可迁移的知识闪卡。";
  $("#deckBadge").textContent = deck.defaultCardType;
  $("#deckAccent").style.background = deck.theme?.accent || "#0f6e56";
  document.documentElement.style.setProperty("--accent", deck.theme?.accent || "#0f6e56");
}

function renderDeckPicker() {
  const select = $("#deckPicker");
  select.innerHTML = catalogEntries().map(entry => `<option value="${esc(entry.id)}"${entry.id === app.deckData.deck.id ? " selected" : ""}>${esc(entry.id === app.deckData.deck.id ? app.deckData.deck.title : (entry.title || entry.id))}${entry.source === "local" ? " · 本地" : ""}</option>`).join("");
}
function rootCategories() { return [...app.categories.values()].filter(category => !category.parentId).sort((a, b) => (a.sortOrder || 0) - (b.sortOrder || 0)); }
function renderCategories() {
  const categories = [{id: "all", label: "全部分类"}, ...rootCategories().map(category => ({id: category.id, label: categoryLabel(category)}))];
  $("#topics").innerHTML = categories.map(category => `<button class="chip${category.id === app.ui.categoryId ? " active" : ""}" data-category="${esc(category.id)}">${esc(category.label)}</button>`).join("");
  $("#topics").querySelectorAll("[data-category]").forEach(button => button.addEventListener("click", () => { app.ui.categoryId = button.dataset.category; app.ui.sectionId = "all"; saveUi(); renderCategories(); renderSections(); renderLimit = BATCH; render(); }));
  $("#filterCategory").innerHTML = categories.map(category => `<option value="${esc(category.id)}">${esc(category.label)}</option>`).join("");
  $("#filterCategory").value = app.ui.categoryId;
}
function renderSections() {
  const sections = app.ui.categoryId === "all" ? [] : (app.childCategories.get(app.ui.categoryId) || []);
  const wrap = $("#sections");
  if (!sections.length) { wrap.hidden = true; wrap.innerHTML = ""; return; }
  wrap.hidden = false;
  const choices = [{id: "all", label: "全部模块"}, ...sections.map(section => ({id: section.id, label: categoryLabel(section)}))];
  wrap.innerHTML = choices.map(section => `<button class="chip section${section.id === app.ui.sectionId ? " active" : ""}" data-section="${esc(section.id)}">${esc(section.label)}</button>`).join("");
  wrap.querySelectorAll("[data-section]").forEach(button => button.addEventListener("click", () => { app.ui.sectionId = button.dataset.section; saveUi(); renderSections(); renderLimit = BATCH; render(); }));
}
function filteredCards() {
  const query = app.ui.query.trim().toLowerCase();
  return app.cards.filter(card => {
    if (app.ui.categoryId !== "all" && card.categoryId !== app.ui.categoryId) return false;
    if (app.ui.sectionId !== "all" && card.sectionId !== app.ui.sectionId) return false;
    const state = cardState(card.id);
    if (app.ui.status === "known" && state.status !== "known") return false;
    if (app.ui.status === "learning" && state.status !== "learning") return false;
    if (app.ui.status === "unseen" && state.status) return false;
    if (app.ui.status === "starred" && !state.priority) return false;
    if (app.ui.status === "noted" && !(state.note || "").trim()) return false;
    return !query || [frontText(card), frontTranslation(card), backText(card), backTranslation(card), ...(card.tags || [])].join(" ").toLowerCase().includes(query);
  });
}
function renderCard(card, number) {
  const state = cardState(card.id);
  const category = app.categories.get(card.categoryId);
  const stars = [1, 2, 3].map(level => `<button class="star${state.priority >= level ? " on" : ""}" data-priority="${level}" aria-label="设置 ${level} 星优先级">★</button>`).join("");
  const element = document.createElement("article");
  element.className = `card${app.allFlipped ? " flipped" : ""}`;
  element.innerHTML = `<div class="face front"><div class="meta"><span class="tag" style="background:${categoryColor(card.categoryId)}">${esc(categoryLabel(category))}</span><span class="num">#${number}</span><span class="stars">${stars}</span><span class="type">${esc(card.type)}</span></div><div class="term">${fmtMath(esc(frontText(card)))}</div>${frontTranslation(card) ? `<div class="translation">${fmtMath(esc(frontTranslation(card)))}</div>` : ""}${card.front?.image ? `<img class="card-image" src="${esc(card.front.image)}" alt="${esc(frontText(card))}">` : ""}<div class="hint">点击翻转查看答案</div></div><div class="face back"><div class="meta"><span class="tag" style="background:${categoryColor(card.categoryId)}">${esc(categoryLabel(category))}</span><span class="type">${esc(card.type)}</span></div><div class="definition">${fmtMath(esc(backText(card)))}</div>${backPhonetic(card) ? `<div class="translation">${esc(backPhonetic(card))}</div>` : ""}${backTranslation(card) ? `<div class="translation answer-translation">${fmtMath(esc(backTranslation(card)))}</div>` : ""}${card.back?.example ? `<div class="example">${esc(card.back.example)}</div>` : ""}<div class="actions" data-stop><button class="sbtn${state.status === "known" ? " on known" : ""}" data-status="known">已掌握</button><button class="sbtn${state.status === "learning" ? " on learning" : ""}" data-status="learning">学习中</button></div><label class="note-wrap" data-stop><span>笔记</span><textarea class="note" placeholder="添加本卡笔记…">${esc(state.note || "")}</textarea></label></div>`;
  element.addEventListener("click", event => { if (!event.target.closest("[data-stop]") && !event.target.closest(".star")) element.classList.toggle("flipped"); });
  element.querySelectorAll(".star").forEach(button => button.addEventListener("click", event => { event.stopPropagation(); const level = Number(button.dataset.priority); const current = cardState(card.id); app.profile[card.id] = {...current, priority: current.priority === level ? 0 : level}; saveProfile(); render(); }));
  element.querySelectorAll("[data-status]").forEach(button => button.addEventListener("click", event => { event.stopPropagation(); const status = button.dataset.status; const current = cardState(card.id); app.profile[card.id] = {...current, status: current.status === status ? null : status}; saveProfile(); render(); }));
  element.querySelector(".note").addEventListener("input", event => { const current = cardState(card.id); app.profile[card.id] = {...current, note: event.target.value}; saveProfile(); updateStats(); });
  return element;
}
function updateStats() { const known = app.cards.filter(card => cardState(card.id).status === "known").length; const learning = app.cards.filter(card => cardState(card.id).status === "learning").length; const percent = app.cards.length ? Math.round((known / app.cards.length) * 100) : 0; $("#known").textContent = `已掌握 ${known}`; $("#learning").textContent = `学习中 ${learning}`; $("#progressFill").style.width = `${percent}%`; $("#progressText").textContent = `${percent}%`; }
function render() { const list = filteredCards(); renderLimit = Math.min(Math.max(renderLimit, BATCH), list.length); const deck = $("#deck"); deck.innerHTML = ""; const fragment = document.createDocumentFragment(); list.slice(0, renderLimit).forEach((card, index) => fragment.appendChild(renderCard(card, index + 1))); deck.appendChild(fragment); $("#count").textContent = `${list.length} / ${app.cards.length} 张`; $("#empty").hidden = Boolean(list.length); $("#loadMore").hidden = renderLimit >= list.length; updateStats(); }
function showError(error) { $("#deck").innerHTML = `<div class="error"><h2>无法加载卡组</h2><p>${esc(error.message || String(error))}</p><p>请使用本地 HTTP 服务打开项目，而不是 file:// 直接双击。</p></div>`; }

function openManager() {
  const manager = $("#manager");
  manager.hidden = false;
  manager.setAttribute("aria-hidden", "false");
  renderManagerLibrary();
  $("#closeManager").focus();
}
function closeManager() {
  const manager = $("#manager");
  manager.hidden = true;
  manager.setAttribute("aria-hidden", "true");
  $("#manageDecks").focus();
}
function renderManagerLibrary() {
  const rows = catalogEntries().map(entry => {
    const current = entry.id === app.deckData.deck.id;
    const info = entry.source === "local" ? app.importedDecks[entry.id].deck : null;
    const title = info?.deck?.title || entry.title || entry.id;
    const count = info?.cards?.length;
    return `<div class="library-row"><div><strong>${esc(title)}</strong><small>${entry.source === "local" ? `本地导入 · ${count} 张` : "内置卡组"}</small></div><div class="library-actions"><button class="text-btn" data-open-deck="${esc(entry.id)}"${current ? " disabled" : ""}>${current ? "当前" : "打开"}</button>${entry.source === "local" ? `<button class="text-btn danger" data-delete-deck="${esc(entry.id)}">删除</button>` : ""}</div></div>`;
  }).join("") || "<p class=muted>尚无卡组。</p>";
  $("#libraryList").innerHTML = rows;
  $("#libraryList").querySelectorAll("[data-open-deck]").forEach(button => button.addEventListener("click", async () => { await switchDeck(button.dataset.openDeck); closeManager(); }));
  $("#libraryList").querySelectorAll("[data-delete-deck]").forEach(button => button.addEventListener("click", () => deleteImportedDeck(button.dataset.deleteDeck)));
}
async function switchDeck(deckId) { $("#deck").innerHTML = "<div class=\"loading\">正在切换卡组…</div>"; try { await loadDeck(deckId); renderDeckPicker(); renderCategories(); renderSections(); renderLimit = BATCH; render(); } catch (error) { showError(error); } }

async function parseImportFile(file) {
  if (!file) return;
  if (file.size > MAX_IMPORT_BYTES) throw new Error("导入文件超过 20 MB 上限");
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".json")) return JSON.parse(await file.text());
  if (lower.endsWith(".zip")) {
    if (!window.JSZip) throw new Error("ZIP 支持未加载，请刷新页面后重试");
    const zip = await JSZip.loadAsync(await file.arrayBuffer());
    const deckFile = Object.values(zip.files).find(item => /(^|\/)deck\.json$/i.test(item.name));
    if (!deckFile) throw new Error("ZIP 中未找到 deck.json");
    return JSON.parse(await deckFile.async("string"));
  }
  throw new Error("请选择 KDF .json 或包含 deck.json 的 .zip 卡组包");
}

async function importDeck(file) {
  const payload = await parseImportFile(file);
  const result = validateDeck(payload);
  if (!result.valid) throw new Error(result.errors.join("；"));
  const id = payload.deck.id;
  const existing = app.importedDecks[id];
  if (existing && !confirm(`本地已有“${payload.deck.title}”。是否覆盖本地副本？`)) return;
  app.importedDecks[id] = { importedAt: nowIso(), deck: payload };
  saveImportedDecks();
  renderDeckPicker(); renderManagerLibrary();
  const notice = result.warnings.length ? `已导入 ${payload.deck.title}，但：${result.warnings.join(" ")}` : `已导入 ${payload.deck.title}（${result.cardCount} 张卡）`;
  notify(notice, result.warnings.length ? "warning" : "success");
  await switchDeck(id);
}

function exportDeckJson() { const name = `${sanitizeFilename(app.deckData.deck.id)}.kdf.json`; downloadBlob(name, JSON.stringify(app.deckData, null, 2), "application/json;charset=utf-8"); notify("已导出 KDF JSON 卡组"); }
function ankiSide(side) { return [side?.prompt, side?.primary, side?.translation, side?.definition, side?.answer, side?.explanation].filter(Boolean).map(value => String(value).replace(/\r?\n/g, "<br>")).join("<br>"); }
function exportAnkiTsv() {
  const lines = [["Front", "Back", "Tags"], ...app.deckData.cards.filter(card => card.status === "published").map(card => [ankiSide(card.front), ankiSide(card.back), (card.tags || []).join(" ")])].map(row => row.map(value => `"${String(value).replace(/"/g, '""')}"`).join("\t"));
  downloadBlob(`${sanitizeFilename(app.deckData.deck.id)}-anki.tsv`, lines.join("\n"), "text/tab-separated-values;charset=utf-8"); notify("已导出 Anki TSV");
}
async function exportDeckPackage() {
  if (!window.JSZip) throw new Error("ZIP 支持未加载，请刷新页面后重试");
  const zip = new JSZip();
  zip.file("deck.json", JSON.stringify(app.deckData, null, 2));
  zip.file("manifest.json", JSON.stringify({ format: "kdf-package/1.0", deckId: app.deckData.deck.id, deckVersion: app.deckData.deck.version, exportedAt: nowIso(), files: ["deck.json"] }, null, 2));
  const blob = await zip.generateAsync({type: "blob"});
  downloadBlob(`${sanitizeFilename(app.deckData.deck.id)}.kdf.zip`, blob, "application/zip"); notify("已导出 KDF 卡组包");
}
function exportProfile() { const packageData = { format: "kdf-profile/1.0", deckId: app.deckData.deck.id, exportedAt: nowIso(), profile: app.profile }; downloadBlob(`${sanitizeFilename(app.deckData.deck.id)}-learning-profile.json`, JSON.stringify(packageData, null, 2), "application/json;charset=utf-8"); notify("已导出学习档案"); }
async function restoreProfile(file) {
  if (!file || file.size > MAX_IMPORT_BYTES) throw new Error("学习档案文件无效或超过 20 MB");
  const data = JSON.parse(await file.text());
  if (data?.format !== "kdf-profile/1.0" || data.deckId !== app.deckData.deck.id || !data.profile || typeof data.profile !== "object") throw new Error("学习档案不属于当前卡组或格式不正确");
  if (!confirm("恢复会覆盖当前卡组现有的学习进度、星标和笔记。是否继续？")) return;
  app.profile = data.profile; saveProfile(); render(); notify("学习档案已恢复");
}
function deleteImportedDeck(deckId) {
  const record = app.importedDecks[deckId];
  if (!record || !confirm(`删除浏览器本地副本“${record.deck.deck.title}”？不会删除你电脑上的原始文件。`)) return;
  delete app.importedDecks[deckId]; saveImportedDecks(); renderDeckPicker(); renderManagerLibrary();
  if (app.deckData.deck.id === deckId) switchDeck(app.catalog.decks[0].id);
  notify("本地导入卡组已删除");
}

function bindEvents() {
  $("#deckPicker").addEventListener("change", event => switchDeck(event.target.value));
  $("#search").addEventListener("input", event => { app.ui.query = event.target.value; saveUi(); renderLimit = BATCH; render(); });
  $("#filterStatus").addEventListener("change", event => { app.ui.status = event.target.value; saveUi(); renderLimit = BATCH; render(); });
  $("#filterCategory").addEventListener("change", event => { app.ui.categoryId = event.target.value; app.ui.sectionId = "all"; saveUi(); renderCategories(); renderSections(); renderLimit = BATCH; render(); });
  $("#flipAll").addEventListener("click", () => { app.allFlipped = !app.allFlipped; $("#flipAll").textContent = app.allFlipped ? "隐藏释义" : "显示释义"; document.querySelectorAll(".card").forEach(card => card.classList.toggle("flipped", app.allFlipped)); });
  $("#shuffle").addEventListener("click", () => { app.cards = [...app.cards].sort(() => Math.random() - 0.5); renderLimit = BATCH; render(); });
  $("#reset").addEventListener("click", () => { if (!confirm("清除当前卡组的学习进度、优先级和笔记？此操作不可恢复。")) return; app.profile = {}; saveProfile(); render(); });
  $("#loadMore").addEventListener("click", () => { renderLimit += BATCH; render(); });
  $("#theme").addEventListener("click", () => { document.documentElement.toggleAttribute("data-theme-dark"); $("#theme").textContent = document.documentElement.hasAttribute("data-theme-dark") ? "切换浅色" : "切换深色"; });
  $("#manageDecks").addEventListener("click", openManager);
  $("#closeManager").addEventListener("click", closeManager);
  $("#manager").addEventListener("click", event => { if (event.target === $("#manager")) closeManager(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape") closeManager(); });
  $("#importDeckFile").addEventListener("change", async event => { try { await importDeck(event.target.files[0]); } catch (error) { notify(error.message || String(error), "error"); } finally { event.target.value = ""; } });
  $("#exportDeckJson").addEventListener("click", exportDeckJson);
  $("#exportDeckPackage").addEventListener("click", async () => { try { await exportDeckPackage(); } catch (error) { notify(error.message || String(error), "error"); } });
  $("#exportAnki").addEventListener("click", exportAnkiTsv);
  $("#exportProfile").addEventListener("click", exportProfile);
  $("#restoreProfileFile").addEventListener("change", async event => { try { await restoreProfile(event.target.files[0]); } catch (error) { notify(error.message || String(error), "error"); } finally { event.target.value = ""; } });
}
async function boot() {
  try {
    // 管理层必须按需打开；没有有效 URL 参数时始终从内置 CFA 卡组进入。
    $("#manager").hidden = true;
    $("#manager").setAttribute("aria-hidden", "true");
    await loadCatalog();
    const requestedDeckId = getDeckIdFromUrl();
    const defaultDeckId = app.catalog.decks.find(deck => deck.id === "cfa-level-1")?.id || app.catalog.decks[0]?.id;
    const availableDeckIds = new Set(catalogEntries().map(entry => entry.id));
    await loadDeck(requestedDeckId && availableDeckIds.has(requestedDeckId) ? requestedDeckId : defaultDeckId);
    bindEvents();
    renderDeckPicker();
    $("#search").value = app.ui.query;
    $("#filterStatus").value = app.ui.status;
    renderCategories();
    renderSections();
    render();
  } catch (error) {
    showError(error);
  }
}
boot();
