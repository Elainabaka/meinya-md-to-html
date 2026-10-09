(function(){
"use strict";
const $ = id => document.getElementById(id);
const api = () => (window.pywebview && window.pywebview.api) || null;

/* ---------- giao dien vi/en ----------
   t(key, vars): chuoi theo ngon ngu hien tai; {ten} la bien thay vao.
   "vi" giu dung chu cu; moi khoa phai co ca "vi" lan "en" (test_i18n.py kiem tra). */
const I18N = {
  vi: {
    "tab.source": "Nguồn",
    "tab.mmTitle": "Soát tài liệu: đường dẫn, link, lệnh, cờ, tên có khớp code không",
    "btn.hide1": "Ẩn/hiện cột (Ctrl+1)",
    "btn.hide3": "Ẩn/hiện cột (Ctrl+3)",
    "theme.title": "Sáng / tối",
    "lang.title": "Ngôn ngữ giao diện",
    "src.dropHtml": "Kéo-thả <b>.md</b> vào đây",
    "src.dropSub": "hoặc dùng nút bên dưới",
    "src.add": "+ Thêm file",
    "src.folder": "Thư mục",
    "src.clear": "Xóa",
    "src.clearTitle": "Xóa hết danh sách",
    "src.recursive": "Quét thư mục con",
    "src.filter": "Lọc file… (Ctrl+K)",
    "src.empty": "Chưa có file .md nào.",
    "rm.title": "Bỏ file",
    "crumb.none": "Chưa chọn file",
    "status.ready": "Sẵn sàng.",
    "es.title": "Thả file .md để xem trước",
    "es.sub": "HTML được cache tự động cạnh file gốc — không cần bấm Convert.",
    "es.noPreview": "Không có file để xem trước",
    "es.noPreviewSub": "Các phát hiện này không thuộc file .md nào, nên không có trang xem trước.",
    "pv.zoomOut": "Thu nhỏ (Ctrl+-)",
    "pv.zoomIn": "Phóng to (Ctrl+=)",
    "pv.reload": "Render lại (F5)",
    "pv.open": "Mở HTML trong trình duyệt",
    "pv.zoomReset": "100% (Ctrl+0)",
    "btn.open": "Mở ↗",
    "opt.titleHint": "(1 file)",
    "ttl.options": "Tuỳ chọn",
    "ttl.findings": "Phát hiện",
    "opt.title": "Tiêu đề",
    "opt.titlePh": "Trống = lấy dòng # đầu",
    "opt.date": "Ngày",
    "opt.dateHint": "(trống = hôm nay)",
    "opt.noToc": "Tắt mục lục",
    "sec.cache": "Cache",
    "opt.cacheBeside": "Cạnh file gốc",
    "opt.cacheTool": "Trong thư mục tool",
    "opt.watch": "Tự cập nhật khi file đổi",
    "sec.export": "Xuất",
    "btn.export": "Xuất HTML…",
    "btn.exportAll": "Xuất tất cả…",
    "btn.reveal": "Mở thư mục file gốc",
    "btn.openFolder": "Mở thư mục xuất",
    "log.title": "Nhật ký",
    "log.expand": "mở",
    "log.collapse": "thu gọn",
    "mm.check": "Kiểm lại",
    "mm.changeRoot": "Đổi thư mục…",
    "mm.changeRootTitle": "Chọn thư mục khác để soát",
    "mm.filter": "Lọc tài liệu…",
    "mm.noRoot": "Chưa chọn thư mục",
    "mm.notChecked": "Chưa soát.",
    "mm.checking": "Đang soát…",
    "mm.busy": "Đang soát… {secs} giây (repo lớn có thể mất vài chục giây lần đầu)",
    "mm.checkedIn": "soát trong {secs}",
    "mm.outsideTail": "không thuộc tài liệu nào",
    "mm.at": "lúc {time}",
    "mm.checkFailed": "Không soát được.",
    "mm.openFailed": "Không mở được tài liệu.",
    "mm.noMatch": "Không có tài liệu khớp bộ lọc.",
    "mm.noDocs": "Chưa có tài liệu .md nào được soát.",
    "mm.countClean": "sạch",
    "mm.pickFirst": "Chọn một tài liệu bên trái để xem phát hiện",
    "mm.outside": "Chung · không thuộc tài liệu nào",
    "mm.outsideShort": "Chung",
    "mm.outsideCrumb": "Phát hiện không thuộc tài liệu nào",
    "mm.noMdPreview": "không có file .md để xem trước",
    "mm.line": "dòng {n}",
    "mm.notes": "Ghi nhận ({n})",
    "mm.noIssues": "Không có lỗi hay cảnh báo nào trong tài liệu này.",
    "mm.noFindings": "Không có phát hiện nào.",
    "mm.loadFailed": "Không lấy được phát hiện.",
    "mm.tier.error": "có lỗi",
    "mm.tier.warning": "có cảnh báo",
    "mm.tier.info": "chỉ ghi nhận",
    "mm.tier.clean": "sạch",
    "sev.error": "Lỗi",
    "sev.warning": "Cảnh báo",
    "sev.info": "Ghi nhận",
    "fx.suggestion": "Gợi ý: {s}",
    "fx.evidence": "Bằng chứng:",
    "p.doc1": "{n} tài liệu",
    "p.docN": "{n} tài liệu",
    "p.error1": "{n} lỗi",
    "p.errorN": "{n} lỗi",
    "p.warn1": "{n} cảnh báo",
    "p.warnN": "{n} cảnh báo",
    "p.note1": "{n} ghi nhận",
    "p.noteN": "{n} ghi nhận",
    "p.claim1": "{n} điều kiểm",
    "p.claimN": "{n} điều kiểm",
    "p.finding1": "{n} phát hiện",
    "p.findingN": "{n} phát hiện",
    "p.file1": "{n} file",
    "p.fileN": "{n} file",
    "unit.sec": "giây",
    "foot.count": "{n} file · {c} đã cache",
    "label.error": "Lỗi",
    "dot.cached": "Đã cache",
    "dot.updating": "Đang cập nhật…",
    "dot.pending": "Chờ render",
    "dot.missing": "File đã bị xoá/đổi tên",
    "dot.inline": "Chỉ xem tạm (không ghi được cache)",
    "badge.cacheTool": "cache trong tool",
    "badge.previewOnly": "chỉ xem tạm",
    "status.cacheTool": "File .html cạnh file gốc không phải của tool → cache: {out}",
    "status.inline": "Không ghi được cache (quyền thư mục?) — preview tạm trong bộ nhớ.",
    "status.cached": "đã cache · {size} · {when}",
    "when.updated": "vừa cập nhật",
    "when.current": "cache còn mới",
    "job.exporting": "Đang xuất",
    "job.caching": "Đang cache",
    "job.progress": "{kind} {done}/{total} — {current}",
    "what.export": "xuất",
    "what.cache": "cache",
    "job.cancelled": "Đã hủy {what}.",
    "job.errors": "{what}: {n} xong, {errs} lỗi (xem Nhật ký).",
    "job.done": "Xong {what} {files}.",
    "log.exported": "Đã xuất: {p}",
    "log.cached": "Cache: {p}",
    "log.error": "LỖI: {e}",
    "log.exportAll": "Bắt đầu xuất tất cả…",
    "log.added": "Đã thêm {files} kéo-thả.",
    "log.boot": "Meinya MD to HTML v{v} — cache tự động, không cần Convert.",
    "log.watch": "Tự cập nhật: {state}",
    "log.mm": "Mind Map: {docs}, {error}, {warning} ({secs}) — {root}",
    "log.mmErr": "Mind Map: {msg}",
    "state.on": "bật",
    "state.off": "tắt",
    "msg.noFile": "Chưa chọn file.",
    "msg.dropOnly": "Chỉ nhận file .md.",
    "msg.noOutput": "Chưa có thư mục xuất.",
    "msg.fileGone": "File đã bị xoá hoặc đổi tên: {name}",
    "err.backend": "backend chưa sẵn sàng",
    "err.generic": "Lỗi: {msg}",
    "err.preview": "Lỗi preview: {msg}",
    "err.addFile": "Lỗi thêm file: {msg}",
    "err.addFolder": "Lỗi thêm thư mục: {msg}",
    "err.export": "Xuất lỗi: {msg}",
    "err.open": "Mở lỗi: {msg}",
    "err.cache": "Lỗi đổi cache: {msg}",
    "err.drop": "Lỗi nhận file: {msg}",
    "err.mmOpen": "Lỗi mở tài liệu: {msg}",
    "err.chooseRoot": "Không chọn được thư mục: {msg}",
    "err.render": "Lỗi render.",
  },
  en: {
    "tab.source": "Source",
    "tab.mmTitle": "Check docs: paths, links, commands, flags, and whether names still match the code",
    "btn.hide1": "Show or hide column (Ctrl+1)",
    "btn.hide3": "Show or hide column (Ctrl+3)",
    "theme.title": "Light / dark",
    "lang.title": "Interface language",
    "src.dropHtml": "Drop <b>.md</b> files here",
    "src.dropSub": "or use the buttons below",
    "src.add": "+ Add files",
    "src.folder": "Folder",
    "src.clear": "Clear",
    "src.clearTitle": "Clear the whole list",
    "src.recursive": "Include subfolders",
    "src.filter": "Filter files… (Ctrl+K)",
    "src.empty": "No .md files yet.",
    "rm.title": "Remove file",
    "crumb.none": "No file selected",
    "status.ready": "Ready.",
    "es.title": "Drop a .md file to preview it",
    "es.sub": "HTML is cached automatically next to the source file — no Convert click needed.",
    "es.noPreview": "No file to preview",
    "es.noPreviewSub": "These findings do not belong to any .md file, so there is no preview page.",
    "pv.zoomOut": "Zoom out (Ctrl+-)",
    "pv.zoomIn": "Zoom in (Ctrl+=)",
    "pv.reload": "Re-render (F5)",
    "pv.open": "Open the HTML in the browser",
    "pv.zoomReset": "Reset to 100% (Ctrl+0)",
    "btn.open": "Open ↗",
    "opt.titleHint": "(1 file)",
    "ttl.options": "Options",
    "ttl.findings": "Findings",
    "opt.title": "Title",
    "opt.titlePh": "Empty = use the first # heading",
    "opt.date": "Date",
    "opt.dateHint": "(empty = today)",
    "opt.noToc": "Hide the table of contents",
    "sec.cache": "Cache",
    "opt.cacheBeside": "Next to the source file",
    "opt.cacheTool": "In the tool folder",
    "opt.watch": "Update automatically when a file changes",
    "sec.export": "Export",
    "btn.export": "Export HTML…",
    "btn.exportAll": "Export all…",
    "btn.reveal": "Show the source folder",
    "btn.openFolder": "Open the export folder",
    "log.title": "Log",
    "log.expand": "open",
    "log.collapse": "collapse",
    "mm.check": "Re-check",
    "mm.changeRoot": "Change folder…",
    "mm.changeRootTitle": "Choose another folder to check",
    "mm.filter": "Filter documents…",
    "mm.noRoot": "No folder selected",
    "mm.notChecked": "Not checked yet.",
    "mm.checking": "Checking…",
    "mm.busy": "Checking… {secs} s (a large repo can take tens of seconds the first time)",
    "mm.checkedIn": "checked in {secs}",
    "mm.outsideTail": "outside any document",
    "mm.at": "at {time}",
    "mm.checkFailed": "The check failed.",
    "mm.openFailed": "Could not open the document.",
    "mm.noMatch": "No documents match the filter.",
    "mm.noDocs": "No .md documents have been checked yet.",
    "mm.countClean": "clean",
    "mm.pickFirst": "Select a document on the left to see its findings",
    "mm.outside": "General · not in any document",
    "mm.outsideShort": "General",
    "mm.outsideCrumb": "Findings that are not in any document",
    "mm.noMdPreview": "no .md file to preview",
    "mm.line": "line {n}",
    "mm.notes": "Notes ({n})",
    "mm.noIssues": "This document has no errors or warnings.",
    "mm.noFindings": "No findings.",
    "mm.loadFailed": "Could not load the findings.",
    "mm.tier.error": "has errors",
    "mm.tier.warning": "has warnings",
    "mm.tier.info": "notes only",
    "mm.tier.clean": "clean",
    "sev.error": "Error",
    "sev.warning": "Warning",
    "sev.info": "Note",
    "fx.suggestion": "Suggestion: {s}",
    "fx.evidence": "Evidence:",
    "p.doc1": "{n} document",
    "p.docN": "{n} documents",
    "p.error1": "{n} error",
    "p.errorN": "{n} errors",
    "p.warn1": "{n} warning",
    "p.warnN": "{n} warnings",
    "p.note1": "{n} note",
    "p.noteN": "{n} notes",
    "p.claim1": "{n} check",
    "p.claimN": "{n} checks",
    "p.finding1": "{n} finding",
    "p.findingN": "{n} findings",
    "p.file1": "{n} file",
    "p.fileN": "{n} files",
    "unit.sec": "s",
    "foot.count": "{n} queued · {c} cached",
    "label.error": "Error",
    "dot.cached": "Cached",
    "dot.updating": "Updating…",
    "dot.pending": "Waiting to render",
    "dot.missing": "File deleted or renamed",
    "dot.inline": "Preview only (cache not writable)",
    "badge.cacheTool": "cache in tool folder",
    "badge.previewOnly": "preview only",
    "status.cacheTool": "The .html next to the source file was not made by this tool → cache: {out}",
    "status.inline": "Could not write the cache (folder permissions?) — preview kept in memory.",
    "status.cached": "cached · {size} · {when}",
    "when.updated": "just updated",
    "when.current": "cache is current",
    "job.exporting": "Exporting",
    "job.caching": "Caching",
    "job.progress": "{kind} {done}/{total} — {current}",
    "what.export": "export",
    "what.cache": "caching",
    "job.cancelled": "Cancelled {what}.",
    "job.errors": "{what}: {n} done, {errs} failed (see Log).",
    "job.done": "Finished {what}: {files}.",
    "log.exported": "Exported: {p}",
    "log.cached": "Cached: {p}",
    "log.error": "ERROR: {e}",
    "log.exportAll": "Starting export of all files…",
    "log.added": "Added {files} by drag and drop.",
    "log.boot": "MD to HTML v{v} — caches automatically, no Convert needed.",
    "log.watch": "Auto-update: {state}",
    "log.mm": "Mind Map: {docs}, {error}, {warning} ({secs}) — {root}",
    "log.mmErr": "Mind Map: {msg}",
    "state.on": "on",
    "state.off": "off",
    "msg.noFile": "No file selected.",
    "msg.dropOnly": "Only .md files are accepted.",
    "msg.noOutput": "No export folder yet.",
    "msg.fileGone": "File deleted or renamed: {name}",
    "err.backend": "the backend is not ready yet",
    "err.generic": "Error: {msg}",
    "err.preview": "Preview error: {msg}",
    "err.addFile": "Could not add files: {msg}",
    "err.addFolder": "Could not add the folder: {msg}",
    "err.export": "Export error: {msg}",
    "err.open": "Open error: {msg}",
    "err.cache": "Could not change the cache: {msg}",
    "err.drop": "Could not take the dropped files: {msg}",
    "err.mmOpen": "Could not open the document: {msg}",
    "err.chooseRoot": "Could not choose the folder: {msg}",
    "err.render": "Render error.",
  }
};
let uiLang = "vi";
function t(key, vars){
  const row = I18N[uiLang] || I18N.vi;
  let s = row[key];
  if(s === undefined) s = I18N.en[key];
  if(s === undefined) s = I18N.vi[key];
  if(s === undefined) return key;
  if(vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
  return s;
}
// So luong: "1 file" hoac "3 files" (tieng Anh); tieng Viet khong doi.
function plural(base, n){ return t(base + (Number(n) === 1 ? "1" : "N"), { n: n }); }
function detectLang(){ return (navigator.language || "").toLowerCase().startsWith("vi") ? "vi" : "en"; }
// Gan chu cho cac phan tu tinh (data-i18n, data-i18n-html, data-i18n-title, data-i18n-placeholder).
function applyStatic(){
  document.documentElement.lang = uiLang;
  document.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach(el => { el.innerHTML = t(el.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-title]").forEach(el => { el.title = t(el.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
}

const state = {
  files: [], sel: -1, settings: {}, cacheMode: "beside", watch: true,
  zoom: 1, lastRev: -1, shownRev: -1, shownIndex: -1, scrollY: {},
  busy: false, filter: "", inline: false,
  mode: "src", mmDocs: [], mmSel: "", mmFilter: "", mmRoot: "", mmBusy: false, mmWasBusy: false, mmOutside: null,
};

async function call(name, ...args){
  const a = api();
  if(!a) throw new Error(t("err.backend"));
  return a[name](...args);
}

/* ---------- ui helpers ---------- */
function log(msg){
  const el = $("log");
  el.textContent += msg + "\n";
  el.scrollTop = el.scrollHeight;
}
function status(msg){ $("status").textContent = msg; }
function setBadge(kind, text){
  const b = $("prevBadge");
  if(!text){ b.hidden = true; b.textContent = ""; b.className = "badge"; return; }
  b.hidden = false; b.textContent = text; b.className = "badge " + (kind || "");
}
function toast(msg, opts){
  opts = opts || {};
  const box = document.createElement("div");
  box.className = "toast " + (opts.kind || "");
  const tx = document.createElement("span"); tx.className = "tx"; tx.textContent = msg;
  box.appendChild(tx);
  if(opts.action){
    const b = document.createElement("button");
    b.textContent = opts.action.label;
    b.onclick = () => { box.remove(); opts.action.fn(); };
    box.appendChild(b);
  }
  $("toasts").appendChild(box);
  setTimeout(() => box.remove(), opts.sticky ? 12000 : 4200);
}
function setEmpty(on){
  $("emptyState").classList.toggle("hide", !on);
  $("preview").style.visibility = on ? "hidden" : "visible";
}
function fmtKB(n){ n = Number(n)||0; return n >= 1024*1024 ? (n/1048576).toFixed(1)+" MB" : Math.max(1, Math.round(n/1024)) + " KB"; }

/* ---------- settings ---------- */
function settings(){
  return {
    title: $("optTitle").value.trim(),
    eyebrow: $("optEyebrow").value.trim() || "Tài liệu kỹ thuật",
    lang: $("optLang").value,
    date: $("optDate").value.trim(),
    no_toc: $("optNoToc").checked,
  };
}
function applySettings(s){
  s = s || {};
  if(s.eyebrow) $("optEyebrow").value = s.eyebrow;
  if(s.lang) $("optLang").value = s.lang;
  if(s.date) $("optDate").value = s.date;
  $("optNoToc").checked = !!s.no_toc;
}
let settingsTimer = null;
function onSettingsChanged(){
  clearTimeout(settingsTimer);
  settingsTimer = setTimeout(async () => {
    state.settings = settings();
    await showPreview(state.sel);
  }, 350);
}

/* ---------- file list ---------- */
function parentName(p){
  const parts = String(p||"").replace(/\\/g, "/").split("/");
  return parts.length > 1 ? parts[parts.length - 2] : "";
}
function renderList(){
  const ul = $("fileList");
  ul.innerHTML = "";
  const dirs = new Set(state.files.map(f => parentName(f.path)));
  const multiDir = dirs.size > 1;
  let shown = 0;
  state.files.forEach((f, i) => {
    if(state.filter && !f.name.toLowerCase().includes(state.filter)) return;
    shown++;
    const li = document.createElement("li");
    if(i === state.sel) li.className = "sel";
    const dot = document.createElement("span");
    dot.className = "dot " + (f.state || "pending");
    dot.title = ({fresh:t("dot.cached"), rendered:t("dot.cached"), stale:t("dot.updating"), pending:t("dot.pending"),
      missing:t("dot.missing"), error:(f.msg || t("label.error")), inline:t("dot.inline")})[f.state] || "";
    const nm = document.createElement("span"); nm.className = "nm"; nm.textContent = f.name; nm.title = f.path;
    li.append(dot, nm);
    if(multiDir){
      const d = document.createElement("span"); d.className = "dir"; d.textContent = parentName(f.path);
      li.appendChild(d);
    }
    const rm = document.createElement("button");
    rm.className = "rm"; rm.textContent = "×"; rm.title = t("rm.title");
    rm.onclick = async ev => {
      ev.stopPropagation();
      await call("remove_file", i);
      if(state.sel > i) state.sel--;
      if(state.sel === i){ state.sel = Math.min(i, state.files.length - 2); }
      await refresh({ preview: true });
    };
    li.appendChild(rm);
    li.onclick = () => select(i);
    ul.appendChild(li);
  });
  $("fileCount").textContent = state.files.length;
  $("listEmpty").style.display = (state.files.length && shown) ? "none" : "";
  updateFoot();
}
function updateFoot(){
  if(state.mode === "mm"){ $("queueFoot").textContent = state.mmRoot || "—"; return; }
  const total = state.files.length;
  const cached = state.files.filter(f => f.state === "fresh" || f.state === "rendered").length;
  $("queueFoot").textContent = total ? t("foot.count", { n: total, c: cached }) : "—";
}

/* ---------- preview ---------- */
async function showPreview(i, force){
  if(i < 0 || i >= state.files.length){
    state.shownIndex = -1; setEmpty(true); setBadge("", "");
    $("prevName").textContent = "—"; $("prevStats").textContent = "";
    $("crumb").textContent = t("crumb.none"); $("crumb").title = "";
    return;
  }
  let r;
  try { r = await call("preview_info", i, settings()); }
  catch(e){ toast(t("err.preview", { msg: e.message }), {kind:"err"}); return; }
  if(!r.ok){ setBadge("err", r.error || t("label.error")); setEmpty(false); status(r.error || t("err.render")); return; }
  state.inline = !!r.inline;
  const f = state.files[i] || {};
  f.state = r.inline ? "inline" : (r.fallback ? "fresh" : (r.state || "fresh"));
  f.revision = r.revision;
  f.out = r.out; f.fallback = r.fallback;
  $("prevName").textContent = r.name;
  $("prevStats").textContent = r.stats ? "· " + r.stats : "";
  $("crumb").textContent = r.path; $("crumb").title = r.path;
  const frame = $("preview");
  if(r.inline){
    if(force || frame.srcdoc !== r.html){ frame.removeAttribute("src"); frame.srcdoc = r.html; }
  } else if(force || frame.getAttribute("src") !== r.url){
    frame.src = r.url;
  }
  state.shownIndex = i;
  const bumped = Number(r.revision) > state.shownRev;
  state.shownRev = Number(r.revision) || 0;
  setEmpty(false);
  if(r.fallback && !r.inline){
    setBadge("warn", t("badge.cacheTool"));
    status(t("status.cacheTool", { out: r.out }));
  } else if(r.inline){
    setBadge("warn", t("badge.previewOnly"));
    status(t("status.inline"));
  } else {
    setBadge("", "");
    status(t("status.cached", { size: fmtKB(f.out_size || f.size), when: (force || bumped) ? t("when.updated") : t("when.current") }));
  }
  renderList();
}
async function select(i){
  state.sel = i;
  renderList();
  if(i >= 0 && state.files[i]) status(state.files[i].path || "");
  await showPreview(i);
}

/* ---------- refresh / boot ---------- */
async function refresh(opts){
  opts = opts || {};
  let st;
  try { st = await call("initial_state"); }
  catch(e){ return; }
  state.files = st.files || [];
  state.settings = st.settings || {};
  state.cacheMode = st.cache_mode || "beside";
  state.watch = !!st.watch;
  state.lastRev = Number(st.revision) || 0;
  applySettings(state.settings);
  $("cmBeside").checked = state.cacheMode !== "tool";
  $("cmTool").checked = state.cacheMode === "tool";
  $("optWatch").checked = state.watch;
  $("ver").textContent = "v" + (st.version || "2.2.0");
  if(opts.selectLast && state.files.length) state.sel = state.files.length - 1;
  if(state.sel >= state.files.length) state.sel = state.files.length - 1;
  if(state.sel < 0 && state.files.length && !opts.selectLast) state.sel = state.files.length - 1;
  renderList();
  if(opts.preview === false){ setEmpty(state.sel < 0); }
  else await showPreview(state.sel);
}
window.__mdRefresh = async function(){ await refresh({ selectLast: true }); };

/* ---------- poll: live update + job progress ---------- */
function updateJob(job){
  const running = !!job.running;
  $("prog").hidden = !running;
  if(running){
    const pct = job.total ? Math.round((job.done || 0) / job.total * 100) : 0;
    $("progBar").style.width = pct + "%";
    status(t("job.progress", {
      kind: job.kind === "export" ? t("job.exporting") : t("job.caching"),
      done: job.done || 0, total: job.total || 0, current: job.current || "" }));
    state.busy = true;
    return;
  }
  if(!state.busy) return;
  state.busy = false;
  $("progBar").style.width = "0%";
  if(job.finished){
    const n = (job.outputs || []).length, errs = (job.errors || []).length;
    const what = t(job.kind === "export" ? "what.export" : "what.cache");
    if(job.cancelled) toast(t("job.cancelled", { what: what }), {kind:"err"});
    else if(errs) toast(t("job.errors", { what: what, n: n, errs: errs }), {kind:"err"});
    else toast(t("job.done", { what: what, files: plural("p.file", n) }), {kind:"ok"});
    (job.outputs || []).forEach(o => log(job.kind === "export" ? t("log.exported", { p: o }) : t("log.cached", { p: o })));
    (job.errors || []).forEach(e => log(t("log.error", { e: e })));
  }
  state.lastRev = -1;
}
async function poll(){
  if(!api()) return;
  let st;
  try { st = await call("watch_poll"); } catch(e){ return; }
  updateJob(st.job || {});
  const rev = Number(st.revision) || 0;
  if(rev === state.lastRev) return;
  state.lastRev = rev;
  (st.files || []).forEach((f, i) => { if(state.files[i]) Object.assign(state.files[i], f); });
  renderList();
  if(state.sel < 0 || !state.files[state.sel]) return;
  const f = state.files[state.sel];
  if(f.state === "missing"){ status(t("msg.fileGone", { name: f.name })); return; }
  if(state.shownIndex === state.sel && Number(f.revision || 0) !== state.shownRev){
    await showPreview(state.sel);
  }
}

/* ---------- actions ---------- */
async function doAdd(){
  try { await call("add_files"); await refresh({ selectLast: true }); }
  catch(e){ toast(t("err.addFile", { msg: e.message }), {kind:"err"}); }
}
async function doFolder(){
  try { await call("add_folder", $("optRec").checked); await refresh({ selectLast: true }); }
  catch(e){ toast(t("err.addFolder", { msg: e.message }), {kind:"err"}); }
}
async function doClear(){
  try { await call("clear_files"); state.sel = -1; await refresh({ preview:true }); }
  catch(e){ toast(t("err.generic", { msg: e.message }), {kind:"err"}); }
}
async function doExport(){
  if(state.sel < 0){ toast(t("msg.noFile"), {kind:"err"}); return; }
  try {
    const r = await call("export_current", state.sel, settings());
    if(r.cancelled) return;
    if(!r.ok){ toast(t("err.export", { msg: r.error || "" }), {kind:"err"}); return; }
    log(t("log.exported", { p: r.path }));
    toast(t("log.exported", { p: r.path }), {kind:"ok", action:{label: t("btn.open"), fn:() => call("open_in_browser", state.sel, settings()).catch(()=>{})}});
  } catch(e){ toast(t("err.export", { msg: e.message }), {kind:"err"}); }
}
async function doExportAll(){
  try {
    const r = await call("export_all", settings());
    if(r.cancelled) return;
    if(!r.ok){ toast(t("err.export", { msg: r.error || "" }), {kind:"err"}); return; }
    log(t("log.exportAll"));
  } catch(e){ toast(t("err.export", { msg: e.message }), {kind:"err"}); }
}
async function doOpen(){
  if(state.sel < 0){ toast(t("msg.noFile"), {kind:"err"}); return; }
  try {
    const r = await call("open_in_browser", state.sel, settings());
    if(!r.ok) toast(t("err.open", { msg: r.error || "" }), {kind:"err"});
  } catch(e){ toast(t("err.open", { msg: e.message }), {kind:"err"}); }
}
async function doReveal(){
  if(state.sel < 0){ toast(t("msg.noFile"), {kind:"err"}); return; }
  try { await call("reveal", state.sel); }
  catch(e){ toast(t("err.generic", { msg: e.message }), {kind:"err"}); }
}
async function doOpenOutput(){
  try {
    const r = await call("open_output");
    if(!r.ok) toast(r.error || t("msg.noOutput"), {kind:"err"});
  } catch(e){ toast(t("err.generic", { msg: e.message }), {kind:"err"}); }
}

/* ---------- zoom ---------- */
function setZoom(z){
  state.zoom = Math.min(2, Math.max(0.6, Math.round(z * 100) / 100));
  const f = $("preview");
  f.style.zoom = state.zoom;
  f.style.width = (100 / state.zoom) + "%";
  f.style.height = (100 / state.zoom) + "%";
  $("btnZoomReset").textContent = Math.round(state.zoom * 100) + "%";
}

/* ---------- theme ---------- */
function applyTheme(t){
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("mdhtml.theme", t); } catch(e){}
}

/* ---------- columns ---------- */
function initColumns(){
  const root = document.documentElement;
  try {
    const w1 = localStorage.getItem("mdhtml.w1"); if(w1) root.style.setProperty("--w1", w1);
    const w2 = localStorage.getItem("mdhtml.w2"); if(w2) root.style.setProperty("--w2", w2);
  } catch(e){}
  function drag(splitId, side, cssVar, storeKey, min, max){
    const el = $(splitId);
    el.addEventListener("mousedown", e => {
      e.preventDefault();
      const startX = e.clientX;
      const cur = parseInt(getComputedStyle(root).getPropertyValue(cssVar)) || 296;
      el.classList.add("drag");
      const move = ev => {
        let w = side === "left" ? cur + (ev.clientX - startX) : cur - (ev.clientX - startX);
        w = Math.max(min, Math.min(max, w));
        root.style.setProperty(cssVar, w + "px");
      };
      const up = () => {
        el.classList.remove("drag");
        document.removeEventListener("mousemove", move);
        document.removeEventListener("mouseup", up);
        try { localStorage.setItem(storeKey, getComputedStyle(root).getPropertyValue(cssVar).trim()); } catch(e2){}
      };
      document.addEventListener("mousemove", move);
      document.addEventListener("mouseup", up);
    });
    el.addEventListener("dblclick", () => {
      root.style.removeProperty(cssVar);
      try { localStorage.removeItem(storeKey); } catch(e2){}
    });
  }
  drag("split1", "left", "--w1", "mdhtml.w1", 220, 460);
  drag("split2", "right", "--w2", "mdhtml.w2", 230, 460);
}
function toggleCol(colId, splitId){
  const col = $(colId), split = $(splitId);
  col.classList.toggle("hide");
  split.classList.toggle("hide", col.classList.contains("hide"));
}

/* ---------- drag & drop (fallback text + native path qua __mdRefresh) ---------- */
function initDrop(){
  const dz = $("dropzone");
  ["dragenter","dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave","drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", async e => {
    const items = [...(e.dataTransfer.files || [])].filter(f => /\.md$/i.test(f.name));
    if(!items.length){ toast(t("msg.dropOnly"), {kind:"err"}); return; }
    const reads = items.map(f => new Promise(res => {
      const r = new FileReader();
      r.onload = () => res({ name: f.name, text: String(r.result || "") });
      r.onerror = () => res(null);
      r.readAsText(f, "utf-8");
    }));
    const payload = (await Promise.all(reads)).filter(Boolean);
    if(!payload.length) return;
    try {
      const r = await call("add_dropped_files", payload);
      const n = (r && r.added) || 0;
      if(n) log(t("log.added", { files: plural("p.file", n) }));
      await refresh({ selectLast: n > 0 });
    } catch(err){ toast(t("err.drop", { msg: err.message }), {kind:"err"}); }
  });
}

/* ---------- mind map: soat tai lieu (luong nen, backend trong api.py) ---------- */
const MM_SEV_KEY = {error:"sev.error", warning:"sev.warning", info:"sev.info"};
const MM_TIER_KEY = {error:"mm.tier.error", warning:"mm.tier.warning", info:"mm.tier.info", clean:"mm.tier.clean"};
let mmTimer = null;

function fmtSec(n){
  const s = (Number(n) || 0).toFixed(1);
  return (uiLang === "vi" ? s.replace(".", ",") : s) + " " + t("unit.sec");
}
function clockText(ts){
  return new Date((Number(ts) || 0) * 1000).toLocaleTimeString(uiLang === "vi" ? "vi-VN" : "en-GB", {hour:"2-digit", minute:"2-digit"});
}
function mmCountText(d){
  if(d.tier === "clean") return t("mm.countClean");
  const parts = [];
  if(d.error) parts.push(plural("p.error", d.error));
  if(d.warning) parts.push(plural("p.warn", d.warning));
  if(!parts.length && d.info) parts.push(plural("p.note", d.info));
  return parts.join(" · ");
}
function evidenceText(e){
  const parts = [];
  if(e.rev) parts.push("commit " + e.rev + (e.date ? " · " + e.date : ""));
  else if(e.date) parts.push(e.date);
  if(e.path) parts.push(e.line ? e.path + ":" + e.line : e.path);
  if(e.note) parts.push(e.note);
  if(e.text) parts.push("“" + e.text + "”");
  return parts.join(" — ") || String(e.kind || "");
}
function findingCard(f, showPath){
  const card = document.createElement("div");
  card.className = "fx sev-" + f.severity;
  const head = document.createElement("div"); head.className = "fx-head";
  const sev = document.createElement("span"); sev.className = "fx-sev";
  sev.textContent = MM_SEV_KEY[f.severity] ? t(MM_SEV_KEY[f.severity]) : f.severity;
  const loc = document.createElement("span"); loc.className = "fx-loc";
  const where = [];
  if(showPath && f.path) where.push(f.path);
  if(f.line) where.push(t("mm.line", { n: f.line }));
  loc.textContent = where.join(" · ");
  const rule = document.createElement("span"); rule.className = "fx-rule";
  rule.textContent = f.rule; rule.title = f.rule;
  head.append(sev, loc, rule);
  const msg = document.createElement("div"); msg.className = "fx-msg"; msg.textContent = f.message;
  card.append(head, msg);
  if(f.suggestion){
    const sug = document.createElement("div"); sug.className = "fx-sug";
    sug.textContent = t("fx.suggestion", { s: f.suggestion });
    card.appendChild(sug);
  }
  if(f.evidence && f.evidence.length){
    const box = document.createElement("div"); box.className = "fx-ev";
    box.textContent = t("fx.evidence");
    f.evidence.forEach(e => {
      const line = document.createElement("div");
      line.textContent = "· " + evidenceText(e);
      box.appendChild(line);
    });
    card.appendChild(box);
  }
  return card;
}
function noteLine(text){
  const n = document.createElement("div"); n.className = "mm-none"; n.textContent = text;
  return n;
}

const MM_OUTSIDE = "@outside";     // khoa cua nhom 'Chung' (khong phai duong dan that)
function outsideLabel(){ return t("mm.outside"); }
let mmChain = Promise.resolve();

// Dong danh sach Mind Map theo thu tu hien thi: nhom 'Chung' truoc, roi tai lieu (da loc).
function mmRows(){
  const q = state.mmFilter;
  const rows = [];
  if(state.mmOutside && (!q || outsideLabel().toLowerCase().includes(q))) rows.push({ key: MM_OUTSIDE, outside: true });
  state.mmDocs.forEach(d => {
    if(q && !d.path.toLowerCase().includes(q) && !(d.title || "").toLowerCase().includes(q)) return;
    rows.push({ key: d.path, outside: false, doc: d });
  });
  return rows;
}

// Moi lan chon di qua mot hang doi tuan tu: chon nhanh lien tiep thi ban sau thang, khong dan xen.
function mmPick(key, isDoc){
  state.mmSel = key;
  mmRenderList();
  mmChain = mmChain.then(() => (isDoc ? mmDoOpen(key) : mmDoOutside()));
  return mmChain;
}

function mmMove(delta){
  const rows = mmRows();
  if(!rows.length) return;
  let i = rows.findIndex(r => r.key === state.mmSel);
  i = i < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, i + delta));
  const row = rows[i];
  if(row.key === state.mmSel) return;
  mmPick(row.key, !row.outside);
  const li = $("mmList").children[i];
  if(li && li.scrollIntoView) li.scrollIntoView({ block: "nearest" });
}

// Tieu de/mo ta o khung xem truoc. Khong truyen gi thi dung chu mac dinh cua ngon ngu hien tai.
function setEmptyText(title, sub){
  $("esTitle").textContent = title || t("es.title");
  $("esSub").textContent = sub || t("es.sub");
}

// Bang phat hien trong cot phai. showPath: hien duong dan file (dung cho nhom 'Chung').
function mmFillPanel(title, sub, findings, showPath, emptyText){
  const box = $("mmFindings"), info = $("mmInfo"), infoBox = $("mmInfoBox"), infoBtn = $("btnMMInfo");
  box.innerHTML = ""; info.innerHTML = "";
  $("mmDocName").textContent = title;
  $("mmDocSub").textContent = sub;
  const main = findings.filter(f => f.severity !== "info");
  const infos = findings.filter(f => f.severity === "info");
  if(!main.length) box.appendChild(noteLine(emptyText));
  main.forEach(f => box.appendChild(findingCard(f, showPath)));
  const label = open => `${t("mm.notes", { n: infos.length })} ${open ? "▾" : "▸"}`;
  infoBox.hidden = !infos.length;
  infoBtn.textContent = label(false);
  info.hidden = true;
  infos.forEach(f => info.appendChild(findingCard(f, showPath)));
  infoBtn.onclick = () => { info.hidden = !info.hidden; infoBtn.textContent = label(!info.hidden); };
}

function setMode(mode){
  if(state.mode === mode) return;
  state.mode = mode;
  $("tabSrc").classList.toggle("on", mode === "src");
  $("tabMM").classList.toggle("on", mode === "mm");
  $("srcBody").hidden = mode === "mm";
  $("fileCount").hidden = mode === "mm";
  $("mmBody").hidden = mode !== "mm";
  $("mmCount").hidden = mode !== "mm";
  $("optsTtl").textContent = t(mode === "mm" ? "ttl.findings" : "ttl.options");
  $("optsBody").hidden = mode === "mm";
  $("mmPanel").hidden = mode !== "mm";
  // Nhat ky nhuong cho bang phat hien: an khi dang o Mind Map de bang co du chieu cao.
  $("logHead").hidden = mode === "mm";
  $("log").hidden = mode === "mm";
  if(mode === "mm"){ mmStart(false); return; }
  clearTimeout(mmTimer); mmTimer = null;
  setEmptyText();
  updateFoot();
}

function mmPaint(st, err){
  state.mmRoot = st.root || "";
  state.mmBusy = !!st.running;
  const root = $("mmRoot");
  root.textContent = state.mmRoot || t("mm.noRoot");
  root.title = state.mmRoot;
  $("btnMMCheck").disabled = state.mmBusy;
  $("mmBusy").hidden = !state.mmBusy;
  if(state.mmBusy){
    const secs = st.started ? Math.max(0, Math.round(Date.now() / 1000 - st.started)) : 0;
    $("mmBusyTxt").textContent = t("mm.busy", { secs: secs });
  }
  const errText = state.mmBusy ? "" : (err || st.error || "");
  $("mmErr").hidden = !errText;
  $("mmErr").textContent = errText;
  const sum = st.summary;
  if(state.mmBusy) $("mmSum").textContent = t("mm.checking");
  else if(sum){
    const parts = [plural("p.doc", sum.docs), plural("p.error", sum.error), plural("p.warn", sum.warning),
      t("mm.checkedIn", { secs: fmtSec(sum.seconds) })];
    if(sum.outside) parts.push(plural("p.finding", sum.outside) + " " + t("mm.outsideTail"));
    let line = parts.join(" · ");
    if(st.checked_at) line += " · " + t("mm.at", { time: clockText(st.checked_at) });
    $("mmSum").textContent = line;
  }
  else $("mmSum").textContent = errText ? "" : t("mm.notChecked");
  if(state.mmBusy) state.mmWasBusy = true;
  else if(state.mmWasBusy){
    state.mmWasBusy = false;
    if(sum) log(t("log.mm", { docs: plural("p.doc", sum.docs), error: plural("p.error", sum.error),
      warning: plural("p.warn", sum.warning), secs: fmtSec(sum.seconds), root: state.mmRoot }));
    else if(errText) log(t("log.mmErr", { msg: errText }));
  }
  state.mmDocs = st.docs || [];
  state.mmOutside = st.outside || null;
  $("mmCount").textContent = state.mmDocs.length;
  mmRenderList();
  updateFoot();
}

function mmRenderList(){
  const ul = $("mmList");
  ul.innerHTML = "";
  const rows = mmRows();
  rows.forEach(row => {
    const d = row.doc || null;
    const d2 = row.outside ? state.mmOutside : d;      // nhom 'Chung' dung so dem rieng
    const li = document.createElement("li");
    li.className = (row.key === state.mmSel ? "sel" : "") + (row.outside ? " mm-grp" : "");
    const dot = document.createElement("span");
    dot.className = "dot tier-" + d2.tier;
    dot.title = MM_TIER_KEY[d2.tier] ? t(MM_TIER_KEY[d2.tier]) : "";
    const nm = document.createElement("span"); nm.className = "nm";
    nm.textContent = row.outside ? outsideLabel() : d.path;
    nm.title = row.outside ? outsideLabel() : d.path + (d.title ? " — " + d.title : "");
    const cnt = document.createElement("span"); cnt.className = "mm-cnt";
    cnt.textContent = mmCountText(d2);
    li.append(dot, nm, cnt);
    li.onclick = () => mmPick(row.key, !row.outside);
    ul.appendChild(li);
  });
  const empty = $("mmEmpty");
  empty.hidden = rows.length > 0 || state.mmBusy;
  empty.textContent = state.mmDocs.length ? t("mm.noMatch") : t("mm.noDocs");
}

async function mmPoll(err){
  clearTimeout(mmTimer);
  let st;
  try { st = await call("mindmap_status"); }
  catch(e){ st = { running: false, docs: [], summary: null, root: state.mmRoot, error: e.message }; }
  mmPaint(st, err);
  if(st.running) mmTimer = setTimeout(() => mmPoll(), 700);
}

async function mmStart(force){
  let err = "";
  try {
    const r = await call("mindmap_start", state.sel, "", !!force, uiLang);
    if(!r.ok) err = r.error || t("mm.checkFailed");
  } catch(e){ err = e.message; }
  await mmPoll(err);
}

// Chay trong hang doi tuan tu (mmPick). Sau moi await kiem tra van con dang chon, neu khong thi bo.
async function mmDoOpen(path){
  if(state.mmSel !== path) return;
  let r;
  try { r = await call("mindmap_open", path); }
  catch(e){ toast(t("err.mmOpen", { msg: e.message }), {kind:"err"}); return; }
  if(state.mmSel !== path) return;
  if(!r.ok){ toast(r.error || t("mm.openFailed"), {kind:"err"}); return; }
  await refresh({ preview: false });
  if(state.mmSel !== path) return;
  setEmptyText();
  await select(r.index);
  if(state.mmSel !== path) return;
  await mmShowFindings(path);
}

async function mmShowFindings(path){
  let r;
  try { r = await call("mindmap_findings", path); }
  catch(e){ r = { ok: false, error: e.message }; }
  if(state.mmSel !== path) return;
  if(!r.ok){ mmFillPanel(path, "", [], false, r.error || t("mm.loadFailed")); return; }
  const d = r.doc;
  const sub = [plural("p.claim", d.claims), plural("p.error", d.error), plural("p.warn", d.warning), plural("p.note", d.info)].join(" · ");
  mmFillPanel(d.title || d.name, `${d.path} · ${sub}`, r.findings, false, t("mm.noIssues"));
}

// Nhom 'Chung': khong co file de xem truoc, nen khung xem truoc hien loi nhan thay vi tai lieu cu.
async function mmDoOutside(){
  if(state.mmSel !== MM_OUTSIDE) return;
  setEmptyText(t("es.noPreview"), t("es.noPreviewSub"));
  setEmpty(true);
  setBadge("", "");
  $("prevName").textContent = t("mm.outsideShort");
  $("prevStats").textContent = "";
  $("crumb").textContent = t("mm.outsideCrumb");
  $("crumb").title = "";
  let r;
  try { r = await call("mindmap_outside"); }
  catch(e){ r = { ok: false, error: e.message }; }
  if(state.mmSel !== MM_OUTSIDE) return;
  const g = state.mmOutside || { count: 0 };
  if(!r.ok){ mmFillPanel(outsideLabel(), "", [], true, r.error || t("mm.loadFailed")); return; }
  mmFillPanel(outsideLabel(), `${plural("p.finding", g.count)} · ${t("mm.noMdPreview")}`,
    r.findings, true, t("mm.noFindings"));
}

/* ---------- ngon ngu giao dien ---------- */
// Dat ngon ngu: chu tinh, nut VI/EN, va Mind Map soat lai bang ngon ngu moi.
// persist=true khi nguoi dung doi (luu vao state, Lang cua trang xuat theo); false khi tu doan luc khoi dong.
async function setLang(lang, persist){
  uiLang = lang === "en" ? "en" : "vi";
  applyStatic();
  try { await call("set_ui_lang", uiLang, !!persist); } catch(e){}
  refreshLabels();
  if(persist){
    $("optLang").value = uiLang;      // Lang cua trang xuat theo ngon ngu giao dien (co the doi o Tuy chon)
    onSettingsChanged();
  }
  if(state.mode === "mm"){
    await mmStart(false);
    if(state.mmSel === MM_OUTSIDE) await mmDoOutside();
    else if(state.mmSel) await mmShowFindings(state.mmSel);
  }
}

// Ghi lai chu cua phan tu co noi dung dong (khong nam trong data-i18n).
function refreshLabels(){
  $("btnLang").textContent = uiLang.toUpperCase();
  $("optsTtl").textContent = t(state.mode === "mm" ? "ttl.findings" : "ttl.options");
  $("logToggle").textContent = $("colOpts").classList.contains("log-collapsed") ? t("log.expand") : t("log.collapse");
  $("mmBusyTxt").textContent = t("mm.checking");
  if(!state.mmSel) $("mmDocName").textContent = t("mm.pickFirst");
  setEmptyText();
  if(state.shownIndex < 0 && !state.mmSel){
    $("crumb").textContent = t("crumb.none");
    status(t("status.ready"));
  }
  renderList();
  updateFoot();
  if(state.mode === "mm") mmRenderList();
}

/* ---------- events ---------- */
function initEvents(){
  $("btnAdd").onclick = doAdd;
  $("btnFolder").onclick = doFolder;
  $("btnClear").onclick = doClear;
  $("btnExport").onclick = doExport;
  $("btnExportAll").onclick = doExportAll;
  $("btnReveal").onclick = doReveal;
  $("btnOpenFolder").onclick = doOpenOutput;
  $("btnOpen").onclick = doOpen;
  $("btnReload").onclick = () => showPreview(state.sel, true);
  $("btnZoomIn").onclick = () => setZoom(state.zoom + 0.1);
  $("btnZoomOut").onclick = () => setZoom(state.zoom - 0.1);
  $("btnZoomReset").onclick = () => setZoom(1);
  $("btnTheme").onclick = () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  $("btnLang").onclick = () => setLang(uiLang === "vi" ? "en" : "vi", true);
  $("btnHide1").onclick = () => toggleCol("colFiles", "split1");
  $("btnHide3").onclick = () => toggleCol("colOpts", "split2");
  $("logHead").onclick = () => {
    const col = $("colOpts");
    col.classList.toggle("log-collapsed");
    $("logToggle").textContent = col.classList.contains("log-collapsed") ? t("log.expand") : t("log.collapse");
  };
  ["optTitle","optEyebrow","optDate"].forEach(id => $(id).addEventListener("input", onSettingsChanged));
  ["optLang","optNoToc"].forEach(id => $(id).addEventListener("change", onSettingsChanged));
  ["cmBeside","cmTool"].forEach(id => $(id).addEventListener("change", async e => {
    if(!e.target.checked) return;
    try { await call("set_options", e.target.value, null); state.cacheMode = e.target.value; await refresh(); }
    catch(err){ toast(t("err.cache", { msg: err.message }), {kind:"err"}); }
  }));
  $("optWatch").addEventListener("change", async e => {
    try { await call("set_options", null, e.target.checked); state.watch = e.target.checked; log(t("log.watch", { state: e.target.checked ? t("state.on") : t("state.off") })); }
    catch(err){ toast(t("err.generic", { msg: err.message }), {kind:"err"}); }
  });
  $("filter").addEventListener("input", e => { state.filter = e.target.value.trim().toLowerCase(); renderList(); });
  $("tabSrc").onclick = () => setMode("src");
  $("tabMM").onclick = () => setMode("mm");
  $("btnMMCheck").onclick = () => mmStart(true);
  $("btnMMRoot").onclick = async () => {
    let r;
    try { r = await call("mindmap_choose_root"); }
    catch(e){ return mmPoll(t("err.chooseRoot", { msg: e.message })); }
    if(r.cancelled) return;
    await mmPoll(r.ok ? "" : (r.error || ""));
  };
  $("mmFilter").addEventListener("input", e => { state.mmFilter = e.target.value.trim().toLowerCase(); mmRenderList(); });

  document.addEventListener("keydown", e => {
    const mod = e.ctrlKey || e.metaKey;
    const tag = (e.target && e.target.tagName) || "";
    const inField = tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA";
    const k = e.key.toLowerCase();
    if(mod && k === "o"){ e.preventDefault(); e.shiftKey ? doFolder() : doAdd(); return; }
    if(mod && k === "e"){ e.preventDefault(); e.shiftKey ? doExportAll() : doExport(); return; }
    if(mod && k === "k"){ e.preventDefault(); $("filter").focus(); $("filter").select(); return; }
    if(mod && (e.key === "=" || e.key === "+")){ e.preventDefault(); setZoom(state.zoom + 0.1); return; }
    if(mod && e.key === "-"){ e.preventDefault(); setZoom(state.zoom - 0.1); return; }
    if(mod && e.key === "0"){ e.preventDefault(); setZoom(1); return; }
    if(mod && e.key === "1"){ e.preventDefault(); toggleCol("colFiles", "split1"); return; }
    if(mod && e.key === "3"){ e.preventDefault(); toggleCol("colOpts", "split2"); return; }
    if(e.key === "F5"){ e.preventDefault(); showPreview(state.sel, true); return; }
    if(e.key === "Escape" && e.target === $("filter")){
      $("filter").value = ""; state.filter = ""; renderList(); $("filter").blur(); return;
    }
    if(!inField && (e.key === "ArrowDown" || e.key === "ArrowUp")){
      if(state.mode === "mm"){ e.preventDefault(); mmMove(e.key === "ArrowDown" ? 1 : -1); return; }
      if(!state.files.length) return;
      e.preventDefault();
      const i = Math.max(0, Math.min(state.files.length - 1, state.sel + (e.key === "ArrowDown" ? 1 : -1)));
      select(i);
    }
  });
}

/* ---------- iframe scroll bridge ---------- */
function initFrame(){
  const frame = $("preview");
  frame.addEventListener("load", () => {
    const y = state.scrollY[state.shownIndex] || 0;
    if(!y) return;
    try { frame.contentWindow.postMessage({ t: "mdhtml:scroll", y: y }, "*"); } catch(e){}
  });
  window.addEventListener("message", e => {
    const d = e.data || {};
    if(d.t === "mdhtml:at" && state.shownIndex >= 0){
      state.scrollY[state.shownIndex] = Number(d.y) || 0;
    }
  });
}

/* ---------- boot ---------- */
window.addEventListener("pywebviewready", async () => {
  initColumns();
  initEvents();
  initDrop();
  initFrame();
  let saved = null;
  try { saved = localStorage.getItem("mdhtml.theme"); } catch(e){}
  applyTheme(saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  setZoom(1);
  const st0 = await call("initial_state").catch(() => null);
  await setLang((st0 && st0.ui_lang) || detectLang(), false);
  await refresh({ preview: true });
  log(t("log.boot", { v: (st0 && st0.version) || "2.2.0" }));
  setInterval(poll, 1200);
});
})();
