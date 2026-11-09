/* Same-project text references. Read IndexedDB; never replace native history. */
(function () {
  "use strict";
  var originalFetch = window.fetch, synced = Object.create(null), seen = {}, running = null;
  var status = {total: 0, enabled: true}, failed = false, pill = null, dialog = null;
  try { seen = JSON.parse(localStorage.getItem("qwen-shared-seen-v1") || "{}"); } catch (e) {}
  if (!seen || typeof seen !== "object" || Array.isArray(seen)) seen = {};
  function uiLang() { try { return window.qwenEnhance && window.qwenEnhance.lang() || document.documentElement.lang || "en"; } catch (e) { return "en"; } }
  function th() { return uiLang() === "th"; }
  // 2026-11 ญี่ปุ่น/จีนตัวย่อ ตามข้อความอังกฤษ — คีย์ที่ไม่มีได้อังกฤษ
  var JZ = {
      "Shared context: retry": [
          "共有コンテキスト: 再試行",
          "共享上下文：重试"
      ],
      "Shared context": [
          "共有コンテキスト",
          "共享上下文"
      ],
      "Reference other chats in this project automatically, or search them": [
          "このプロジェクトの他のチャットを自動で参照、または検索",
          "自动引用此项目中的其他对话，或搜索它们"
      ],
      "Chats in this project": [
          "このプロジェクトのチャット",
          "此项目中的对话"
      ],
      "Close": [
          "閉じる",
          "关闭"
      ],
      "Use shared project context automatically": [
          "プロジェクトの共有コンテキストを自動で使う",
          "自动使用项目共享上下文"
      ],
      "Chat messages stay separate. Qwen uses relevant excerpts and can search for details, with links to the source chats.": [
          "チャットのメッセージは別々のままです。Qwen は関連する抜粋を使い、詳細を検索できます。元のチャットへのリンク付きです。",
          "各对话的消息保持独立。Qwen 使用相关摘录并可搜索细节，并附上来源对话的链接。"
      ],
      "Search project chats": [
          "プロジェクトのチャットを検索",
          "搜索项目对话"
      ],
      "Search": [
          "検索",
          "搜索"
      ],
      "Saved chats": [
          "保存されたチャット",
          "已保存的对话"
      ],
      "Back to chats": [
          "チャット一覧へ戻る",
          "返回对话列表"
      ],
      "Open source chat": [
          "元のチャットを開く",
          "打开来源对话"
      ],
      "Saved history version": [
          "保存された履歴のバージョン",
          "已保存的历史版本"
      ],
      "Latest saved history": [
          "最新の保存履歴",
          "最新保存的历史"
      ],
      " messages": [
          " 件のメッセージ",
          " 条消息"
      ],
      " · alternate copy": [
          " · 別のコピー",
          " · 另一份副本"
      ],
      "This saved version contains text. Attachments and reasoning may be available in another saved version.": [
          "この保存版にはテキストが含まれます。添付ファイルや思考は別の保存版にある場合があります。",
          "此保存版本包含文本。附件和思考内容可能在另一个保存版本中。"
      ],
      "Restore as a new chat": [
          "新しいチャットとして復元",
          "恢复为新对话"
      ],
      "Restore chat to this browser": [
          "このブラウザーにチャットを復元",
          "将对话恢复到此浏览器"
      ],
      "Restoring…": [
          "復元中…",
          "正在恢复…"
      ],
      "Could not restore. Retry": [
          "復元できませんでした。再試行",
          "无法恢复。重试"
      ],
      "More messages": [
          "さらにメッセージを読む",
          "更多消息"
      ],
      "Could not read this chat. Please retry.": [
          "このチャットを読み取れませんでした。もう一度お試しください。",
          "无法读取此对话。请重试。"
      ],
      "Loading…": [
          "読み込み中…",
          "正在加载…"
      ],
      " · archived": [
          " · アーカイブ済み",
          " · 已归档"
      ],
      "No shared chats found. Open each project in your usual browser once to synchronize existing chats.": [
          "共有チャットが見つかりません。既存のチャットを同期するには、普段使うブラウザーで各プロジェクトを一度開いてください。",
          "未找到共享对话。请在你常用的浏览器中把每个项目打开一次，以同步现有对话。"
      ],
      "Synchronization is unavailable. Please retry.": [
          "同期を利用できません。もう一度お試しください。",
          "同步不可用。请重试。"
      ]
  };
  function label(en, thai) {
    var l = uiLang();
    if (l === "th") return thai;
    var x = (l === "ja" || l === "zh") && Object.prototype.hasOwnProperty.call(JZ, en) ? JZ[en] : null;
    return x ? x[l === "ja" ? 0 : 1] : en;
  }
  function api(path, options) {
    return originalFetch.call(window, "/_qwen/chats" + path, options || {}).then(function (r) {
      if (!r.ok) throw new Error("Shared chat request failed (" + r.status + ")");
      return r.json();
    });
  }
  function post(path, data) {
    return api(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  }
  function openDB() {
    return new Promise(function (resolve, reject) {
      var request = indexedDB.open("LlamaUi");
      request.onupgradeneeded = function () { request.transaction.abort(); };
      request.onerror = function () { reject(request.error); };
      request.onblocked = function () { reject(new Error("Chat storage is upgrading")); };
      request.onsuccess = function () {
        var db = request.result;
        db.onversionchange = function () { db.close(); };
        resolve(db);
      };
    });
  }
  function requestValue(request) {
    return new Promise(function (resolve, reject) {
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }
  function textContent(value) {
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.filter(function (v) { return v && typeof v.text === "string"; }).map(function (v) { return v.text; }).join("\n");
    return "";
  }
  function packChat(conversation, nodes) {
    return {id: conversation.id, name: conversation.name, lastModified: conversation.lastModified,
      currNode: conversation.currNode, messages: nodes.map(function (node) {
        var content = textContent(node.content);
        if (Array.isArray(node.extra)) node.extra.forEach(function (part) {
          if (part && part.type === "text") content += "\n" + textContent(part.content || part.text || part.data);
        });
        return {id: node.id, parent: node.parent, role: node.role, type: node.type,
          timestamp: node.timestamp, content: content, toolCalls: node.toolCalls || "", toolCallId: node.toolCallId || ""};
      })};
  }
  function fingerprint(value) {
    var a = 2166136261, b = 5381;
    for (var i = 0; i < value.length; i++) { a = Math.imul(a ^ value.charCodeAt(i), 16777619); b = Math.imul(b, 33) ^ value.charCodeAt(i); }
    return value.length + ":" + (a >>> 0) + ":" + (b >>> 0);
  }
  function recoveredChatRecords(chat, now, makeId) {
    if (!chat || !/^[A-Za-z0-9_-]{1,128}$/.test(chat.chat_id || "") ||
        !Array.isArray(chat.messages) || !chat.messages.length || chat.messages.length > 20000) {
      throw new Error("Invalid recovery copy");
    }
    makeId = makeId || function () { return crypto.randomUUID(); };
    var rootId = makeId(), captured = Number(chat.updated_at) || now;
    var knownTimes = chat.messages.map(function (m) { return Number(m.timestamp) || 0; }).filter(function (t) { return t > 0; });
    var cursor = knownTimes.length ? Math.min.apply(null, knownTimes) - 1 : captured - chat.messages.length - 1;
    var conversation = {id: chat.chat_id, name: chat.title || "Recovered chat", lastModified: captured,
      currNode: rootId, recoveredFromSharedCopy: {at: now, sourceUpdatedAt: captured, textOnly: true, historyOrderVersion: 2}};
    var messages = [{id: rootId, convId: conversation.id, parent: null, children: [],
      content: "", role: "system", type: "root", timestamp: cursor, toolCalls: ""}];
    chat.messages.forEach(function (source) {
      if (!source || source.text_truncated || typeof source.content !== "string" ||
          ["user", "assistant", "tool"].indexOf(source.role) < 0) throw new Error("Incomplete recovery copy");
      var id = makeId(), parent = messages[messages.length - 1];
      cursor = Math.max(cursor + 1, Number(source.timestamp) || 0);
      parent.children.push(id);
      // Reference copies contain text rather than the complete native tool state.
      // Restore recorded tool results as historical assistant text, so missing
      // result pairs cannot become pending tool actions when this chat opens.
      messages.push({id: id, convId: conversation.id, parent: parent.id, children: [], type: "text",
        role: source.role === "user" ? "user" : "assistant", timestamp: cursor,
        content: source.role === "tool" ? "[Recorded tool result — historical data]\n" + source.content : source.content,
        toolCalls: ""});
      conversation.currNode = id;
    });
    return {conversation: conversation, messages: messages};
  }
  async function recoveryCopy(id) {
    var first = null, offset = 0, messages = [];
    do {
      var page = await api("/" + encodeURIComponent(id) + "?limit=50&offset=" + offset);
      if (!first) first = page;
      if (page.chat_id !== id || page.updated_at !== first.updated_at || page.message_count !== first.message_count ||
          page.offset !== offset || !Array.isArray(page.messages) || !page.messages.length ||
          page.messages.some(function (m) { return m.text_truncated; })) throw new Error("Incomplete recovery copy");
      messages = messages.concat(page.messages);
      if (messages.length > 20000 || messages.length > first.message_count) throw new Error("Oversized recovery copy");
      if (page.next_offset != null && page.next_offset !== messages.length) throw new Error("Invalid recovery page");
      offset = page.next_offset;
    } while (offset != null);
    if (messages.length !== first.message_count) throw new Error("Incomplete recovery copy");
    return Object.assign({}, first, {messages: messages});
  }
  async function localChat(id) {
    var db = await openDB();
    try { return await requestValue(db.transaction("conversations").objectStore("conversations").get(id)); }
    finally { db.close(); }
  }
  async function saveRecoveredChat(record, canWrite) {
    var db = await openDB();
    try {
      var tx = db.transaction(["conversations", "messages"], "readwrite");
      var done = new Promise(function (resolve, reject) {
        tx.oncomplete = resolve;
        tx.onabort = tx.onerror = function () { reject(tx.error || new Error("Recovery was not saved")); };
      });
      var lookup = tx.objectStore("conversations").get(record.conversation.id), existing, cancelled = false;
      // Keep all reads and adds within one transaction, including the race check.
      lookup.onsuccess = function () {
        existing = lookup.result;
        if (existing) return;
        if (canWrite && !canWrite()) { cancelled = true; return; }
        tx.objectStore("conversations").add(record.conversation);
        record.messages.forEach(function (m) { tx.objectStore("messages").add(m); });
      };
      await done;
      return cancelled ? null : existing || record.conversation;
    } finally { db.close(); }
  }
  function currentChat() {
    try { var route = window.qwenEnhance.route(); return route.name === "chat" ? route.id : ""; } catch (e) { return ""; }
  }
  async function syncAll(force) {
    if (running) return running;
    running = (async function () {
      if (window.qwenHistory) await window.qwenHistory.sync(force);
      var db = await openDB();
      try {
        if (!db.objectStoreNames.contains("conversations") || !db.objectStoreNames.contains("messages")) throw new Error("Chat storage is not ready");
        var conversations = await requestValue(db.transaction("conversations").objectStore("conversations").getAll());
        var present = {}, current = currentChat();
        for (var i = 0; i < conversations.length; i++) {
          var conv = conversations[i];
          if (!conv || !/^[A-Za-z0-9_-]{1,128}$/.test(conv.id || "")) continue;
          present[conv.id] = true;
          if (window.qwenHistory && !window.qwenHistory.mayPublish(conv.id)) continue;
          var version = [conv.lastModified, conv.currNode, conv.name].join(":");
          if (synced[conv.id] && synced[conv.id].version === version && !force && conv.id !== current) continue;
          var messages = db.transaction("messages").objectStore("messages"), nodes;
          if (messages.indexNames.contains("convId")) nodes = await requestValue(messages.index("convId").getAll(IDBKeyRange.only(conv.id)));
          else nodes = (await requestValue(messages.getAll())).filter(function (m) { return m.convId === conv.id; });
          var packed = packChat(conv, nodes), signature = fingerprint(JSON.stringify(packed));
          if (!synced[conv.id] || synced[conv.id].signature !== signature) {
            var saved = await post("/sync", {chats: [packed]});
            if (!saved.results || !saved.results[0]) throw new Error("Chat synchronization was not acknowledged");
            synced[conv.id] = {version: version, signature: signature};
          }
        }
        // Browser storage may be cleared, migrated or belong to a new profile.
        // Missing IDs never authorize deletion of a saved server copy.
        for (var id in seen) if (Object.prototype.hasOwnProperty.call(seen, id) && !present[id]) {
          delete synced[id];
        }
        seen = present;
        try { localStorage.setItem("qwen-shared-seen-v1", JSON.stringify(seen)); } catch (e) {}
        status = await api("?limit=1");
        failed = false;
      } finally { db.close(); }
    })().catch(function () { failed = true; }).finally(function () { running = null; paint(); });
    return running;
  }
  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    node.setAttribute("data-qw-no-tx", "");
    if (text != null) node.textContent = text;
    return node;
  }
  function button(text, action) {
    var node = element("button", "qw-shared-action", text); node.type = "button";
    node.addEventListener("click", action); return node;
  }
  function paint() {
    var anchor = document.querySelector(".qw-plan");
    if (!anchor || !anchor.parentElement) return;
    if (!pill) {
      pill = element("button", "qw-shared-pill"); pill.type = "button";
      pill.addEventListener("click", showDialog);
    }
    if (!pill.isConnected) anchor.parentElement.appendChild(pill);
    pill.textContent = failed ? label("Shared context: retry", "บริบทร่วม: ลองใหม่") :
      label("Shared context", "บริบทร่วม") + " · " + (status.total || 0);
    pill.title = label("Reference other chats in this project automatically, or search them", "ใช้บริบทจากแชตอื่นในโปรเจกต์นี้อัตโนมัติ และค้นรายละเอียดได้");
    pill.setAttribute("aria-label", pill.title);
  }
  async function showDialog() {
    await syncAll(false);
    if (dialog) dialog.remove();
    dialog = element("dialog", "qw-shared-dialog");
    var heading = element("h2", "", label("Chats in this project", "แชตในโปรเจกต์นี้"));
    heading.id = "qwSharedHeading"; dialog.setAttribute("aria-labelledby", heading.id);
    var close = button(label("Close", "ปิด"), function () { dialog.close(); });
    var top = element("div", "qw-shared-top"); top.append(heading, close); dialog.appendChild(top);
    var toggleLabel = element("label", "qw-shared-toggle"), toggle = element("input");
    toggle.type = "checkbox"; toggle.checked = status.enabled !== false;
    toggle.addEventListener("change", async function () {
      toggle.disabled = true;
      try { var setting = await post("/settings", {enabled: toggle.checked}); status.enabled = setting.enabled; }
      catch (e) { toggle.checked = !toggle.checked; }
      finally { toggle.disabled = false; }
    });
    toggleLabel.append(toggle, document.createTextNode(label("Use shared project context automatically", "รับบริบทจากแชตอื่นในโปรเจกต์อัตโนมัติ")));
    dialog.appendChild(toggleLabel);
    dialog.appendChild(element("p", "qw-shared-help", label(
      "Chat messages stay separate. Qwen uses relevant excerpts and can search for details, with links to the source chats.",
      "แต่ละแชตมีประวัติของตัวเอง Qwen ใช้บริบทที่เกี่ยวข้องและค้นรายละเอียดเพิ่มได้ พร้อมอ้างอิงแชตต้นทาง")));
    var form = element("form", "qw-shared-search"), input = element("input");
    input.type = "search"; input.placeholder = label("Search project chats", "ค้นแชตในโปรเจกต์");
    input.setAttribute("aria-label", input.placeholder);
    var search = element("button", "qw-shared-action", label("Search", "ค้นหา")); search.type = "submit";
    form.append(input, search); dialog.appendChild(form);
    var savedMode = false;
    if (window.qwenHistory) {
      var savedToggle = button(label("Saved chats", "สำเนาแชตที่บันทึกไว้"), function () {
        savedMode = !savedMode;
        savedToggle.textContent = savedMode ? label("Shared context", "บริบทร่วม") : label("Saved chats", "สำเนาแชตที่บันทึกไว้");
        listChats();
      });
      dialog.appendChild(savedToggle);
    }
    var results = element("div", "qw-shared-results"); dialog.appendChild(results);
    async function readChat(id, saved, revision) {
      try {
        var copy = saved ? await window.qwenHistory.read(id, revision) : null;
        var full = saved ? window.qwenHistory.reference(copy) : null;
        var chat = full || await api("/" + encodeURIComponent(id)), offset = full ? 20 : chat.next_offset;
        results.replaceChildren(button(label("Back to chats", "กลับไปรายการแชต"), listChats));
        results.appendChild(element("h3", "", chat.title));
        var source = element("a", "qw-shared-source", label("Open source chat", "เปิดแชตต้นทาง"));
        source.href = location.origin + "/#/chat/" + encodeURIComponent(id); source.target = "_top"; results.appendChild(source);
        if (saved) {
          var versions = await window.qwenHistory.versions(id), select = element("select", "qw-shared-action");
          select.setAttribute("aria-label", label("Saved history version", "รุ่นของประวัติแชต"));
          var latest = element("option", "", label("Latest saved history", "ประวัติที่บันทึกล่าสุด")); latest.value = ""; select.appendChild(latest);
          versions.versions.forEach(function (v) {
            var option = element("option", "", new Date(v.saved_at).toLocaleString() + " · " + v.message_count +
              label(" messages", " ข้อความ") + (v.conflict ? label(" · alternate copy", " · อีกฉบับ") : ""));
            option.value = v.revision; select.appendChild(option);
          });
          select.value = revision || "";
          select.addEventListener("change", function () { readChat(id, true, select.value || null); });
          results.appendChild(select);
          if (copy.text_only) results.appendChild(element("p", "qw-shared-help", label(
            "This saved version contains text. Attachments and reasoning may be available in another saved version.",
            "สำเนารุ่นนี้เก็บเฉพาะข้อความ ไฟล์แนบและข้อความการคิดอาจอยู่ในสำเนารุ่นอื่น")));
        }
        var existing = await localChat(id);
        if (!existing || saved) {
          results.appendChild(element("p", "qw-shared-help", label(
            existing ? "Restore a saved copy as a separate chat. Your current chat is preserved." : "Restore this saved chat to continue in this browser.",
            existing ? "กู้คืนสำเนาที่บันทึกไว้เป็นอีกแชต โดยเก็บแชตปัจจุบันไว้ด้วย" : "กู้คืนแชตที่บันทึกไว้เพื่อคุยต่อในเบราว์เซอร์นี้")));
          var recover = button(existing || revision ? label("Restore as a new chat", "กู้คืนเป็นแชตใหม่") : label("Restore chat to this browser", "กู้คืนแชตในเบราว์เซอร์นี้"), async function () {
            var recoveryDialog = dialog;
            recover.disabled = true; recover.textContent = label("Restoring…", "กำลังกู้คืน…");
            try {
              var copy = window.qwenHistory ? null : await recoveryCopy(id);
              if (!recoveryDialog || !recoveryDialog.open) return;
              var restored = window.qwenHistory ? await window.qwenHistory.restore(id, {copy: !!existing || !!revision, revision: revision}) :
                await saveRecoveredChat(recoveredChatRecords(copy, Date.now()));
              await syncAll(false);
              window.top.location.assign(location.origin + "/#/chat/" + encodeURIComponent(restored.id));
            } catch (e) {
              recover.textContent = label("Could not restore. Retry", "กู้คืนไม่สำเร็จ ลองใหม่");
              recover.disabled = false;
            }
          });
          results.appendChild(recover);
        }
        function appendMessages(page) { page.messages.forEach(function (m) {
          var record = element("section", "qw-shared-record");
          record.append(element("strong", "", m.role), element("pre", "", m.content)); results.appendChild(record);
        }); }
        appendMessages(full ? {messages: full.messages.slice(0, 20)} : chat);
        if (full && offset >= full.messages.length) offset = null;
        var more = button(label("More messages", "อ่านข้อความต่อ"), async function () {
          more.disabled = true;
          try {
            var page = full ? {messages: full.messages.slice(offset, offset + 20), next_offset: offset + 20 < full.messages.length ? offset + 20 : null} :
              await api("/" + encodeURIComponent(id) + "?offset=" + offset);
            more.remove(); appendMessages(page); offset = page.next_offset; if (offset != null) results.appendChild(more);
          }
          finally { more.disabled = false; }
        });
        if (offset != null) results.appendChild(more);
      } catch (e) { results.textContent = label("Could not read this chat. Please retry.", "อ่านแชตนี้ไม่สำเร็จ กรุณาลองใหม่"); }
    }
    async function listChats(event) {
      if (event) event.preventDefault();
      results.textContent = label("Loading…", "กำลังโหลด…");
      try {
        var query = input.value.trim(), data = savedMode ? await window.qwenHistory.list(true) :
          await api(query ? "/search?q=" + encodeURIComponent(query) : "?limit=100");
        results.replaceChildren();
        var chats = savedMode ? data.chats.filter(function (c) { return !query || c.title.toLocaleLowerCase().includes(query.toLocaleLowerCase()); }) :
          query ? data.matches || [] : data.chats || [], shown = {};
        chats.forEach(function (chat) {
          if (shown[chat.chat_id]) return; shown[chat.chat_id] = true;
          var title = chat.title + (chat.archived ? label(" · archived", " · เก็บไว้") : "");
          var card = button(title, function () { readChat(chat.chat_id, savedMode); }); card.classList.add("qw-shared-card");
          var excerpt = chat.snippet || (chat.recent_context || []).map(function (m) { return m.text; }).join("\n");
          card.appendChild(element("span", "", excerpt.slice(0, 450))); results.appendChild(card);
        });
        if (!chats.length) results.textContent = label("No shared chats found. Open each project in your usual browser once to synchronize existing chats.",
          "ยังไม่พบแชตร่วม เปิดโปรเจกต์ในเบราว์เซอร์ที่คุณใช้ตามปกติหนึ่งครั้ง เพื่อดึงประวัติแชตเดิมเข้ามา");
      } catch (e) { results.textContent = label("Synchronization is unavailable. Please retry.", "เชื่อมบริบทร่วมไม่สำเร็จ กรุณาลองใหม่"); }
    }
    form.addEventListener("submit", listChats);
    dialog.addEventListener("close", function () { dialog.remove(); dialog = null; });
    document.body.appendChild(dialog); dialog.showModal(); listChats();
  }
  // Synchronize before a new chat request, with a bounded fail-open wait.
  // The original response object and its SSE stream are passed through untouched.
  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : input && input.url || "";
    var method = String(init && init.method || input && input.method || "GET").toUpperCase();
    var target;
    try { target = new URL(url, location.href); } catch (e) {}
    if (!target || target.origin !== location.origin || target.pathname !== "/v1/chat/completions" || method !== "POST") {
      return originalFetch.apply(window, arguments);
    }
    var args = arguments;
    return Promise.race([syncAll(true), new Promise(function (resolve) { setTimeout(resolve, 2000); })])
      .then(function () { return originalFetch.apply(window, args); });
  };
  window.qwenSharedChats = {sync: syncAll, open: showDialog, makeRecoveryRecords: recoveredChatRecords, saveRecoveryRecords: saveRecoveredChat,
    status: function () { return {total: status.total, enabled: status.enabled, failed: failed}; }};
  function start() { syncAll(false); setInterval(function () { syncAll(false); paint(); }, 5000); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, {once: true}); else start();
})();
