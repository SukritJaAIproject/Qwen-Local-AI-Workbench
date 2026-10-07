# Qwen3.8 UI — architecture and design notes

Goal: a polished, calm, chat-first interface for the local Qwen3.8 stack.

The *design language*: warm paper/ink palette, orange-clay accent, serif
response text, a calm single sidebar (New chat / Search / Projects / Recents), a centered
greeting on the empty state, a large rounded composer card with an orange send button,
generous whitespace, messages in a ~768px column, low-chrome message actions.

**Branding rule (hard):** keep the product name **Qwen3.8** and our own mark. Do NOT use
third-party product names or logos anywhere in the UI (including Qwen/Alibaba's official
logo). Use a simple original mark (e.g. a rounded-square monogram "Q").

**No network resources at runtime.** Everything is served locally (fonts already downloaded).

**All existing features must keep working.** See "Features that must survive" below.

---------------------------------------------------------------------------------------------

## 1. Architecture (already built — do not change unless your task says so)

```
Browser  ──►  http://127.0.0.1:81xx/            one port per project (reverse proxy in hub.py)
              ├─ /                → SHELL page (our HTML, template in hub_i18n_parts.py)
              │    └─ <iframe id="frame" src="/?ui=1&model=...">   ← llama.cpp WebUI (compiled
              │         SvelteKit app, cannot edit its source). Same origin as the shell.
              ├─ /?ui=1           → WebUI index.html with OUR tags injected before </head>:
              │                      inline theme script, fonts.css, tokens.css,
              │                      webui-theme.css, webui-enhance.js (defer)
              ├─ /_qwen/static/*  → files in C:\LLM\projects\static\
              ├─ /_qwen/files     → project attachments API (GET list, POST upload with
              │                      X-Filename: base64(utf8 name), DELETE /_qwen/files/<name>)
              ├─ /_qwen/project   → {project, systemMessage, filesDir, models, primaryModel, uiSrc}
              └─ everything else  → llama-server :8099 (chat completions, /props, models…)
Hub API (cross-origin, CORS enabled): http://127.0.0.1:8100
   GET  /api/projects                → {projects:[...], upstream, model, models, think_modes}
   POST /api/projects {name, system_prompt}
   PATCH /api/projects/<slug> {name?, system_prompt?, model?, think?: off|on|auto, extend?: bool}
   DELETE /api/projects/<slug>
   GET/PATCH /api/settings {lang: th|en}
   GET  /?manage=1                   → PAGE template (project management page)
```

Because shell and iframe share an origin, the shell can: read the WebUI's IndexedDB, read/write
its localStorage, call functions on `frame.contentWindow`, and the iframe can call `parent.*`.

**Hot reload:** hub.py re-imports `hub_i18n_parts.py` when its mtime changes — no hub restart
needed. Static files are served fresh (no-cache). **Never restart the hub or llama-server.**

## 2. Files and ownership (one owner per file — do not edit files you don't own)

| File | Owner | Purpose |
|---|---|---|
| `C:\LLM\projects\static\webui-theme.css` | THEME | all visual styling INSIDE the iframe |
| `C:\LLM\projects\static\webui-enhance.js` | ENHANCE | behavior inside the iframe + `window.qwenEnhance` API |
| `C:\LLM\projects\hub_i18n_parts.py` (SHELL, PAGE, STRINGS_UI) | SHELL | the outer page: sidebar, header, project panel, menus; and the manage page |
| `static\tokens.css`, `static\fonts.css`, `static\boot.js`, `hub.py`, `tools\*` | integrator (read-only for you) | shared design tokens, fonts, boot logic, server |

If you believe a shared file needs a change, say so in your report instead of editing it.

## 3. Design tokens (static/tokens.css — use these, never hard-code colors)

Surfaces `--qw-bg` (main) `--qw-bg-sidebar` `--qw-bg-elev` (composer/cards/popovers)
`--qw-bg-user` (user bubble) `--qw-bg-hover` `--qw-bg-active` `--qw-bg-code` `--qw-bg-inline-code` `--qw-scrim`
Borders `--qw-border` `--qw-border-strong` `--qw-border-focus`
Text `--qw-text` `--qw-text-2` `--qw-text-3` (muted, AA) `--qw-text-4` (faint)
Accent `--qw-accent` `--qw-accent-hover` `--qw-accent-soft` `--qw-accent-fg` `--qw-link`
Status `--qw-ok` `--qw-warn` `--qw-danger` `--qw-focus-ring`
Fonts `--qw-font-ui` (sans, Thai via Leelawadee UI) `--qw-font-serif` (Source Serif 4 + Noto Serif Thai, local) `--qw-font-mono`
Sizes `--qw-fs-xs/sm/base/body/lg/greet` `--qw-lh-body` (1.7 — Thai stacks tone marks)
Radii `--qw-r-xs 6 / sm 8 / md 12 / lg 16 / xl 20 / full`
Shadows `--qw-shadow-sm/md/lg/composer`
Layout `--qw-sidebar-w 288px` `--qw-sidebar-w-min 56px` `--qw-header-h 52px` `--qw-content-w 768px`
Motion `--qw-ease` `--qw-dur` (0 under prefers-reduced-motion)

Theme selection: `<html data-theme="dark|light">` (both documents). In the iframe the WebUI's
mode-watcher also toggles `class="dark"`; ENHANCE mirrors that into `data-theme`.
Default theme is **dark** (the user explicitly asked for dark earlier). Light must look just as good.

## 4. The WebUI DOM map (llama.cpp b10984, observed live — use these hooks)

Theme variables: shadcn-style CSS custom properties on `:root` (light) and `.dark`:
`--background --foreground --card --card-foreground --popover --popover-foreground --primary
--primary-foreground --secondary --secondary-foreground --muted --muted-foreground --accent
--accent-foreground --destructive --border --input --ring --sidebar --sidebar-foreground
--sidebar-primary --sidebar-primary-foreground --sidebar-accent --sidebar-accent-foreground
--sidebar-border --sidebar-ring --code-background --code-foreground --chart-1..5`
(values are oklch). Overriding these re-themes almost everything. Tailwind v4 utility classes.

Structure (desktop):
```
div.flex.flex-col.md:flex-row
├─ aside.svelte-1adgg5m  (48px icon sidebar; buttons aria-label="Expand navigation" | "New chat" | "Search" | "Settings")
└─ div.flex-1 > div[style/class sets --chat-tabs-offset]
   ├─ nav[aria-label="Open conversations"].chat-tabs-fade   (conversation tab strip)
   └─ div[role=main].chat-screen  (px-4, pt-12)
      ├─ .chat-messages > .chat-message (one per message)
      │    [role=group][aria-label="System message with actions"]   ← project system prompt card
      │    [role=group][aria-label="User message with actions"].chat-message-user
      │        [data-slot=card] > .markdown-content.markdown-user-content
      │        .info (token/time stats)   + action row (copy/edit/branch/delete)
      │    [role=group][aria-label="Assistant message with actions"].chat-message-assistant (max-w-3xl)
      │        .agentic-content > .agentic-text > .markdown-content > .markdown-block (p, ul, h2…)
      │        .code-block-wrapper > .code-block-header + .code-block-scroll-container > pre
      │        .info (model pill button, tokens, time, t/s)  + action row
      ├─ (start route only) welcome: div.text-center > h1 "Hello there" + p "Type a message or upload files…"
      └─ div.sticky/fixed bottom > .chat-screen-form-wrapper > form.conversation-chat-form (max-w-3xl)
           [data-slot=input-area] (bg-muted, rounded-3xl) > textarea + toolbar
           toolbar: "+" attach button, model selector button (pill w/ model name + size badge), submit button (↑) / stop
```
Routes (hash): `#/` new chat · `#/chat/<id>` conversation · `#/search` · `#/mcp-servers`.
URL params on load: `?model=<name>` preselects model (WebUI strips it after), `?q=` prefill/send.

Storage (same origin): IndexedDB `LlamaUi` (Dexie, version 10)
- `conversations` keyPath `id`; fields `id, name, lastModified (ms), currNode, reasoningEffort, …`; indexes `lastModified, name, currNode`
- `messages` keyPath `id`; fields `id, convId, type (root|system|text), role, content, parent, children[], timestamp, model?, timings?`; indexes `convId, parent, role, timestamp, type, children`
localStorage: `LlamaUi.config` (JSON: theme, mcpServers(JSON string), systemMessage…),
`LlamaUi.conversationTabs` (JSON array of open conversation ids), `mode-watcher-mode`.
Our keys: `qwen-theme` (dark|light|system), `qwen-font` (serif|sans), `qwen-boot-version`,
`qwen-sidebar` (free for SHELL), anything else prefixed `qwen-`.

## 5. Contracts between the three pieces

### 5a. Shell → iframe globals (defined by SHELL page before the iframe loads)
```js
window.qwenShell = {            // injected server-side via __SHELLDATA__ (already exists)
  lang: "th"|"en", me: 8101, hub: "http://127.0.0.1:8100",
  project: {slug, name, port, think, extend, model, system_prompt},
  projects: [{name, port, slug}], models: [...], primaryModel: "...", filesDir: "C:\\...",
  T: {...all strings for current lang...}          // SHELL adds this from __T_JSON__
}
window.qwenBoot   = {getTheme, setTheme(pref), resolvedTheme, getFont, setFont(f), keys}  // boot.js
window.qwenShellApi = {           // SHELL implements
  newChat(), focusSearch(), toggleSidebar(), openProjectPanel(), refreshRecents(),
  onRoute(route)                  // called by ENHANCE on every route change: {name:"start"|"chat"|"other", id}
}
```
### 5b. iframe API (ENHANCE implements, SHELL consumes)
```js
window.qwenEnhance = {
  version: "1",
  route(),                // → {name:"start"|"chat"|"other", id|null}
  newChat(),              // clicks the hidden aside "New chat" button if present, else location.hash="#/"
  openChat(id),           // location.hash = "#/chat/"+id
  openSearch(),           // clicks hidden aside "Search" button, fallback hash "#/search"
  openSettings(),         // clicks hidden aside "Settings" button
  openMcp(),              // location.hash = "#/mcp-servers"
  prefill(text),          // sets composer textarea value (native setter + input event), focuses, caret at end
  focusComposer(),
  isStreaming(),          // true while a reply is generating (stop button visible)
  applyTheme(), setFont(mode)
}
```
The SHELL must tolerate the API being absent (iframe still loading, or enhance failed) and fall
back to setting `frame.contentWindow.location.hash` directly.

### 5c. Attributes ENHANCE sets on the iframe `<html>` (THEME styles against them)
- `data-theme="dark|light"` — mirrors WebUI's `.dark` class, updates live
- `data-qw-font="serif|sans"` — from `qwen-font` (default serif); live via `storage` event
- `data-qw-route="start|chat|other"`
- `data-qw-embedded="1"` — only when inside our shell (`parent !== window && parent.qwenShell`).
  THEME hides the WebUI's own aside, the tab strip, and the system-message card ONLY under this
  attribute, so opening `/?ui=1` standalone still gives a navigable app.
- `data-qw-hero="1"` — set only after ENHANCE successfully inserted its hero; THEME hides the
  WebUI's original "Hello there" block only under this attribute (graceful fallback).
- `lang` attribute = shell lang.

### 5d. Elements ENHANCE inserts (THEME styles them; class names are fixed)
Start route only, re-inserted if Svelte re-renders them away (MutationObserver, idempotent):
```html
<div class="qw-hero">
  <div class="qw-hero-row"><span class="qw-hero-mark" aria-hidden="true"><svg…/></span>
       <h1 class="qw-greeting">สวัสดีตอนบ่าย</h1></div>
  <div class="qw-project-pill">โปรเจกต์ · วินิจฉัยตู้ชาร์จ</div>        (omit when no project)
</div>                                    ← placed immediately before .chat-screen-form-wrapper
<div class="qw-chips" role="list">       ← placed immediately after the form (inside the wrapper)
  <button type="button" class="qw-chip" role="listitem"><svg class="qw-chip-icon"…/><span>เขียน</span></button> …
</div>
```
Greeting by local hour — th: 05-11 "อรุณสวัสดิ์", 11-17 "สวัสดีตอนบ่าย", 17-21 "สวัสดีตอนเย็น",
21-05 "สวัสดียามค่ำ" · en: "Good morning" / "Good afternoon" / "Good evening" / "Good evening".
Composer placeholder — start: th "วันนี้ให้ช่วยอะไรดี?" en "How can I help you today?";
in a chat: th "ตอบกลับ Qwen…" en "Reply to Qwen…".
Chips (icon + label → prefill text):
th: เขียน→"ช่วยเขียน " · เรียนรู้→"อธิบายให้เข้าใจง่ายๆ ว่า " · โค้ด→"เขียนโค้ด Python ที่ "
    · ไฟล์โปรเจกต์→"อ่านไฟล์ของโปรเจกต์นี้แล้วสรุปประเด็นสำคัญ" · ค้นเว็บ→"ค้นเว็บเรื่อง "
en: Write→"Help me write " · Learn→"Explain simply: " · Code→"Write Python code that "
    · Project files→"Read this project's files and summarize the key points" · Search web→"Search the web for "

## 6. Visual spec (the design language, concretely)

**Sidebar (SHELL)** — width `--qw-sidebar-w`, bg `--qw-bg-sidebar`, no hard border (a 1px
`--qw-border` hairline at most). Top: mark + "Qwen3.8" wordmark (semibold, 15px) + collapse
button. Then a "แชตใหม่ / New chat" row whose icon is a 24px **filled orange circle with a white
+** (the signature accent), then "ค้นหาแชต / Search chats" row (Ctrl+K). Section labels small
(12px, `--qw-text-3`, no uppercase for Thai). Items: 32-36px tall, radius 8-10px, text
`--qw-text-2`, hover `--qw-bg-hover`, active `--qw-bg-active` + `--qw-text`. Recents are
single-line truncated titles; a "⋯" button appears on hover (rename / delete). Footer: a row
like an account row (avatar circle + label) opening a menu (theme, reply font, language,
WebUI settings, MCP servers, manage projects), plus a status dot for model health.
Collapsible to a 56px icon rail (state in `localStorage['qwen-sidebar']`). Under 820px the
sidebar becomes an off-canvas drawer with a scrim; a hamburger appears in the header.

**Header (SHELL)** — `--qw-header-h`, same bg as chat (`--qw-bg`), no border. Left: current
chat title (or project name on the start screen) with a chevron → menu (rename, delete chat).
Right: "Project" button opening the project panel.

**Project panel (SHELL)** — right drawer ~380px, bg `--qw-bg-elev`, `--qw-shadow-lg`, radius on
the inner edge. Sections: *Instructions* (editable textarea for the
project system prompt, Save), *Knowledge* (project files: list, upload, delete, click to copy
path), *Settings* (default model select, thinking mode off/on/auto segmented, auto-continue
switch). Also project rename/delete, and a link to manage all projects.

**Chat (THEME)** — canvas `--qw-bg`. Column max `--qw-content-w`.
- Assistant text: no bubble; `--qw-font-serif` when `data-qw-font="serif"` (else `--qw-font-ui`),
  `--qw-fs-body`, line-height `--qw-lh-body`, color `--qw-text`. Headings serif, weight 600,
  modest sizes (h1 1.5em, h2 1.25em, h3 1.1em). Lists with comfortable spacing.
- User message: rounded bubble (`--qw-r-lg`), bg `--qw-bg-user`, no border/shadow, sans 15px,
  padding ~10px 16px. Keep right alignment the WebUI uses.
- Message stats (`.info`) and action rows: quiet (`--qw-text-4`), revealed/brightened on
  hover or focus-within of the message; the last assistant message's actions stay visible.
- Code blocks: bg `--qw-bg-code`, 0.5-1px `--qw-border`, radius `--qw-r-md`, header row small
  mono label + copy button; inline code bg `--qw-bg-inline-code`, radius 5px, 0.9em mono.
- Tables: hairline borders, header row slightly tinted, rounded outer container, horizontal scroll.
- Blockquote: 3px left rule `--qw-border-strong`, text `--qw-text-2`.
- Links `--qw-link`, underline offset 2px.
- Composer: card bg `--qw-bg-elev`, 0.5px `--qw-border-strong`, radius `--qw-r-xl`,
  `--qw-shadow-composer`; focus-within → border `--qw-border-focus`. Textarea sans 16px,
  placeholder `--qw-text-4`. Send button: 32px, radius 8-10px, bg `--qw-accent`, white arrow;
  hover `--qw-accent-hover`; disabled = accent at ~45% opacity. Model selector: ghost text button.
- Welcome (start route): hero centered above the composer — mark (orange, ~32px) + greeting in
  `--qw-font-serif`, `--qw-fs-greet`, weight 400; project pill small above/below; chips row
  below the composer (ghost pills: 0.5px border, radius 10px, icon + label, hover bg).
- Popovers, dropdowns, dialogs (WebUI settings, model picker, MCP page) must look coherent via
  the variable mapping: bg `--qw-bg-elev`, border `--qw-border`, radius 12px.
- Scrollbars thin and warm; `::selection` `--qw-accent-soft`.
- Both themes, both fonts, desktop and mobile (390px) must look intentional.

## 7. Features that must survive (regression checklist)

1. Switching projects (each project = its own port; links in sidebar navigate the top window).
2. Create / rename / delete project (hub API) — inline, no `prompt()` for create.
3. Thinking mode off/on/auto per project (PATCH think) — proxy applies it per request.
4. Auto-continue (Extend Mode) toggle per project (PATCH extend).
5. Project files: upload (multi, Thai names), list, delete, click-to-copy full path.
6. Project instructions (system prompt): edit → PATCH system_prompt → GET /_qwen/project →
   write `systemMessage` into `LlamaUi.config` → reload iframe (only if not streaming).
7. Default model per project: PATCH model; iframe src carries `?model=`.
8. Language th/en (PATCH /api/settings then reload); every visible string of ours translated.
9. Model health status (poll hub /api/projects every ~10s).
10. Chat navigation: new chat, open chat from Recents, search chats, rename/delete chat.
    Rename/delete = write IndexedDB (`conversations` record; for delete also all `messages`
    with that `convId` via the convId index) + remove id from `LlamaUi.conversationTabs`, then
    reload the iframe if the WebUI may hold stale state (skip/defer while streaming).
11. WebUI settings dialog + MCP servers page reachable from our menu.
12. Dark theme default; light/system selectable; reply font serif/sans selectable.
13. MCP tools still registered (LlamaUi.config.mcpServers written by boot.js — don't touch).

## 8. How to verify (mandatory — look at the screenshots you produce)

Screenshot harness (headless Edge, fresh profile each run, fixtures seeded into IndexedDB):
```
cd C:\LLM\projects\tools
python shot.py "http://127.0.0.1:8101/" shots/<name>.png [--seed fixtures/rich.json]
      [--w 1440 --h 900] [--w 390 --h 844 --mobile] [--theme dark|light] [--font serif|sans]
      [--wait 3500] [--eval "<js in shell page>"] [--frame-eval "<js in iframe>"] [--dom "<selector>"]
```
`{conv0}` in --eval/--frame-eval is replaced by the first fixture conversation id.
Open a chat: `--frame-eval "location.hash='#/chat/{conv0}'"` (or use your sidebar item).
Then **Read the PNG** to look at it. JS errors during load are printed as `JS ERROR:` — fix them.
Use a distinct shots/ filename prefix per agent (theme-*, enhance-*, shell-*, review-*).
Fixtures: `fixtures/rich.json` (9 chats; first one has headings, list, blockquote, table,
python + json code, inline code, link, Thai+English, a system message), `fixtures/single.json`.
The model is slow (CPU is busy with the user's own benchmark) — do NOT send real chat messages
to test rendering; use the fixtures.
Python: `C:\Python313\python.exe`. Do not install packages. Do not restart hub or llama-server.

---------------------------------------------------------------------------------------------

## 9. Round-2 updates (supersede earlier sections where they conflict)

**Routes / API (corrects §4, §5b):** WebUI routes are `#/`, `#/chat/<id>`, `#/search` (mobile only).
`#/mcp-servers` renders the WebUI's 404 — do not use it. Setting `location.hash` directly *reloads*
the WebUI; navigate with `qwenEnhance.openChat(id)` / `newChat()`. `openSettings()` returns a
boolean; `openMcp()` opens the MCP dialog through the composer "+" menu and returns
`Promise<boolean>`. `.qw-chips` is `role="group"` (not list/listitem). On the start screen the
header's left side is intentionally empty (the hero shows the project pill) — that is correct.

**Service worker:** the hub now serves its own `/sw.js` (no caching, clears old Workbox caches).
The WebUI's Workbox worker used to freeze an old copy of the shell. Don't touch this.

**Tokens changed (static/tokens.css):**
- `--qw-focus-ring` is now an opaque colour (light `#b5573a`, dark `#d97757`) — ≥3:1 on all surfaces.
  Use it for outlines. Use `--qw-accent-soft` for any soft halo (but see composer rule below).
- `--qw-text-3` / `--qw-text-4` were darkened (light) / lightened (dark) to pass 4.5:1.
- NEW `--qw-danger-bg` (light `#c0392b`, dark `#b8433a`) — background of filled destructive
  buttons and error toasts, with white text (≥5.3:1). `--qw-danger` is for danger *text* only
  (dark `#f08a80`). Never put white text on `--qw-danger`.
- `--qw-font-ui` now starts with `"Qw Thai UI"` — a local alias (fonts.css) that maps Thai
  glyphs at weight 400 to *Leelawadee UI Semilight*, so Thai and Latin look equally heavy.
  Weights 450-649 map to Leelawadee UI Regular, 650+ to Bold.

**Preferences are server-side now:** theme (dark|light|system) and reply font (serif|sans) live
in the hub (`GET/PATCH http://127.0.0.1:8100/api/settings {theme?, font?, lang?}`) because every
project is a separate origin with its own localStorage. `window.__QWEN_BOOT__.prefs` carries them;
`boot.js` writes them to localStorage on load (server wins) and `qwenBoot.setTheme/setFont` PATCH
the hub. PAGE and SHELL templates can use placeholders `__THEME__` and `__FONT__` (filled by
`fill()` from the hub settings). Anything that changes the theme (e.g. the WebUI's own Settings
dialog) should go through `parent.qwenBoot.setTheme(...)` when embedded so it persists globally.

**Security (hub):** inline JSON is now escaped (`js_json`), and the hub API only accepts Origins
`http://127.0.0.1:8100|81xx` (others get no CORS headers; POST/PATCH/DELETE → 403).

**Harness:** `--seed` now waits for the WebUI to create its IndexedDB (no more NotFoundError).

**Harness cleanup (round 3):** `msedge.exe` relaunches itself, so the PID from `Popen` is not the
real browser; `shot.py` now kills Edge by matching the unique temp-profile path. Windows can keep
an exited Edge in teardown for a while with its LevelDB files locked, so a run's own profile is
sometimes left behind — `python shot.py --sweep-temp` removes old `qwen-shot-*`/`qwen-verify-*`
profiles (>10 min old, Chromium profile signature only). Opt-in on purpose: file deletion needs the
user's go-ahead on this machine.

## 10. Round-3 (2026-09-29): bilingual UI + answer quality (supersedes earlier sections where they conflict)

Built by a workflow (2 builders → 3 independent verifiers → 2 fixers → acceptance check, all PASS).
Backup before this round: `C:\LLM\projects\backup\llm-20260929-111524`.

### 10a. Language switch (SHELL + PAGE, hub_i18n_parts.py)
- Segmented pill `.lsw` "ไทย | EN" in the chat header (`#langSw`, before the Project button) and the
  manage-page header (`#lang`). 28px pill, inset 0.5px `--qw-border-strong`; pressed = `--qw-bg-active`
  + `--qw-shadow-sm` + `--qw-border` hairline; hover = 55% mix of `--qw-bg-hover`; focus = `--qw-focus-ring`.
  Below 640px the pressed button is `display:none` → one compact pill naming the other language.
- A11y: `role=group` + aria-label in the page language (`lang_group`); buttons `aria-pressed`;
  ไทย `lang=th`, EN `lang=en aria-label="English"`. `paintLang()` puts `data-tip` and
  `aria-keyshortcuts="Alt+Shift+L"` only on the non-pressed button. Tooltips are in the **page**
  language (fix round changed this; no Thai text in English mode except the ไทย label). PAGE uses a CSS
  `::after` tooltip (it has no `#tip`).
- Hotkey Alt+Shift+L matched on `e.code === 'KeyL'` (a Thai layout puts a Thai char in `e.key`); caught on
  the shell document, the iframe window (capture listener in `hookFrame`, next to Ctrl+K) and PAGE;
  ignored on repeat and while a shell/WebUI modal is open.
- `setLang(v, seg, how)`: blocked while streaming (`wait_streaming`) or with unsaved project instructions
  (`lang_unsaved`); optimistic UI, PATCH `/api/settings {lang}`, revert + `errlang` toast on failure.
- Carry across the reload: `sessionStorage['qwen-lang-carry'] = {at, hash, draft, focus}`; the hash must
  match `^#/(chat/[A-Za-z0-9_-]+|search)?$` on write AND read; entries older than 2 min are ignored;
  `takeCarry()` deletes the key, a valid hash feeds the iframe src, `applyCarry()` prefills the draft only
  into an empty composer and restores focus (switch button or composer). The preview `?lang=` is stripped.
  PAGE carries the unsaved new-project name and instructions the same way.
- Shell `?model=` is now honoured once, only if it is in the hub's model list (fix round).
- Thai line breaking in shell strings: U+2060 inside loanwords/compounds (never ZWSP inside a compound).

### 10b. Thai translation of the WebUI's own interface (ENHANCE, webui-enhance.js)
- Dictionary built from the served bundle (not guessed): `TH` ~700 exact entries + `TH_RE` ~75 whole-string
  patterns (numbers, names, plurals, durations, "Default: x", "Processing N% (ETA)", byte sizes…). Captured
  values are never altered. Technical identifiers stay English (Temperature, Top K/P, Min P, Max tokens,
  API Key, DRY, XTC, KV cache, Markdown, model names); their help texts are Thai. Terminology follows
  hub STRINGS (แชต, โปรเจกต์, โมเดล, พรอมต์, โทเค็น, เซิร์ฟเวอร์ MCP). `FRAG_TH` handles the one split
  sentence template (MCP delete-server confirm).
- Content is excluded by DOM position (`TX_SKIP`), never by word: markdown, pre/code, `.code-language`,
  textarea/contenteditable, `[data-qw-no-tx]`, `.reasoning-content`, `.chat-message-user-bubble` (sent AND
  pending/queued messages), attachment chips/names, conversation titles (`[data-conversation-row]`, tab strip
  by structure `nav[aria-label="Open conversations"] a[href^="#/chat/"]`), MCP card bodies and server names,
  model names/badges, tool names. `TX_REOPEN` re-allows WebUI controls inside those (code-block header
  buttons, chat-row "…", MCP log `details > summary`). Trap fixtures: `tools/fixtures/tx-trap.json`,
  `acc-trap.json`, `review-trap*.json` — every message/title is exactly a dictionary word and must stay English.
- Mechanism: synchronous inside the body MutationObserver (also watches `characterData`, `title`,
  `aria-label`); only added/changed nodes; records inside message content dropped first; own records
  discarded with `takeRecords()`. Cost ≈ 0.002 ms per streaming batch. Svelte rewrites are re-translated
  before the next frame (no loops).
- `aria-label` is never changed (theme CSS selects on it); Thai names via `aria-labelledby` →
  `qw-tx-<slug>-<djb2(en+NUL+th)>` spans in the hidden `[data-qw-tx-labels]` box.
- Code that reads WebUI labels must use the English originals `enText(node)` / `enAttr(el, a)`
  (isStreaming, asideButton, shownTheme, mcpItem). Theme CSS matches Skip-reasoning on `[title]` or
  `[data-qw-en-title]`.
- Reversible: originals in a WeakMap (text) and `data-qw-en-*` (attributes); `tagEnglish()` marks what it
  tags with `data-qw-lang-en` so `untagEnglish()` removes only its own `lang`.
  `qwenEnhance.setLang("th"|"en")` switches the iframe live (local override only — it does NOT write
  `parent.qwenShell.lang`; the shell owns its language via PATCH + reload). Also `qwenEnhance.lang()`,
  `qwenEnhance.txStats(reset)`.
- Native `confirm/prompt/alert` from the WebUI are wrapped (message translated, values/returns untouched);
  the SvelteKit route announcer reads `<title> - Qwen3.8` in Thai; Fork dialog "Fork of " → "แยกจาก ".
- Known, accepted English in Thai mode: technical identifiers above, MCP connection-log lines,
  server-supplied error text, standalone `/?ui=1` without the shell. U+2060 glue means copied UI labels
  carry invisible joiners (UI chrome only, never content).

### 10c. Hub (hub.py) — answer quality
- `base_system_prompt(model, lang)` is prepended to the first system message of every chat request whose
  `Origin` matches `ALLOWED_ORIGIN` (i.e. from our web UI). Other clients (llm_backend.py, benchmarks,
  scripts) are never touched. Content: model identity, today's date (date only, so the KV-cache prefix is
  reused all day), "reply in the language of the user's latest message; fallback = UI language; project
  instructions may override", style, accuracy, tool-safety rules. English on purpose (shorter, followed
  more reliably, and a Thai system text pulled English questions into Thai answers).
- `project_system_message()` files note is now English and names the real fast-surface tool
  (`local_read` action list/read).
- `apply_sampling(doc, mode)`: fills vendor-recommended sampling only when the request sets none of
  temperature/top_p/top_k/min_p/typical_p/penalties (the WebUI sends none). gpt-oss 1.0/1.0/top_k 0;
  Qwen3-Coder 0.7/0.8/20 + repeat 1.05; Qwen3.8 think-off 0.7/0.8/20, think on/auto 1.0/0.95/20;
  other Qwen3 0.7/0.8/20; min_p 0 for all. No presence_penalty (Thai syllable tokens repeat naturally).
- `?lang=th|en` on shell/manage URLs = render that language without saving (for tests/screenshots).
- MTP speculative decoding (`--models-preset` with `spec-type = draft-mtp`) was measured and NOT enabled:
  no speed-up on this CPU-bound machine (n=1 ≈ baseline, n=2/3 slower).

## 11. Round-4 (2026-09-30): files, code, memory, personalization, panel (supersedes earlier sections where they conflict)

Owners: mcp-docs, mcp-exec (MCP), hub (hub.py), shell (hub_i18n_parts.py), enhance (webui-enhance.js/theme).
Integrator E2E screenshots: `shots/integ-r4-*.png`, re-verified 2026-09-30 18:30–19:00 in `shots/integ2-r4-*.png`
(th, 1440 + 390). Tests: `C:\LLM\tests` (595 OK / 17 skipped at integration; `LLM_SECURITY_LIVE=1` live suites 19 OK).

### 11a. MCP fast surface (`/fast/<slug>`)
- `local_read`: `extract` (PDF/DOCX/XLSX/CSV/PPTX/text → Markdown, page/sheet markers, S07 banner, zip-bomb/XXE-safe),
  `kb` (SQLite FTS5 trigram index at `data\<slug>\kb\index.db`, lazy update from attachments\ + outputs\),
  `checkpoints` (list). `local_do`: `make_file` (docx|xlsx|pptx|pdf|csv|md → `data\<slug>\outputs\`, link
  `[name](/_qwen/out/<pct-encoded>)`, overwrite = confirm), `python` (per-project Jupyter kernel via anaconda,
  cwd `work\`, figures → outputs PNG, **confirm every call**), `undo` (confirm). Write/edit/make_file save a
  checkpoint (`data\<slug>\checkpoints\<id>\`) and return a fenced unified diff. Full surface adds doc_extract,
  make_file, kb_search, python_exec, undo_file, list_checkpoints (44 tools).
- **Schema key order is load-bearing.** llama-server builds a grammar from each tool's JSON schema and lets optional
  keys follow each other only in `properties` order. A model that writes `format` first can never write a key listed
  before it. Integrator fix: `_READ_ORDER`/`_DO_ORDER` in tools_fast.py (short identifiers first, bulk text last —
  `content`/`code`/`spec` at the end), and `_param_map` prints every action's params in schema order. New params
  must be placed in those tuples; `test_integ_round4.FastSchemaKeyOrderTests` enforces it.
- **Project-relative paths:** tools print `attachments/x.pdf` / `outputs/x.docx`. The fast dispatcher maps paths whose
  first segment is `attachments|outputs|work` to `data\<slug>\...` (guard still checks the result; `..` into
  another project is still S04). Other relative paths keep the old behaviour.

### 11b. Hub routes on every project port (same Origin rules as other proxy routes)
- `GET /_qwen/out/` (JSON list) and `GET|HEAD /_qwen/out/<name>[?download=1]` — nosniff, CORP same-origin;
  images/PDF/text inline, office/csv/zip as attachment (`filename*` UTF-8); HTML/SVG get `CSP: sandbox` (no scripts).
- `GET|POST /_qwen/memory`, `GET|PATCH|DELETE /_qwen/memory/<id>` — tools_memory's file format; pin = tag `pinned`
  + `pinned:true`. WebUI chat requests get a "Project memory" block (pinned + newest, ≤ ~1,500 est. tokens).
- `/api/settings` gains `about_me` (≤1500), `style` ∈ normal|concise|explanatory|formal|learning|custom,
  `style_custom` (≤800); returned only to allowed Origins. Prompt order: base → about/style → memory → project.
- `/api/projects` has `keep_awake` (active upstream streams; hub holds ES_SYSTEM_REQUIRED while > 0).
- boot_config default `jsSandboxEnabled: true` (BOOT_VERSION stays 3). Extend-Mode continuations drop X-Conversation-Id.

### 11c. Shell / enhance contracts (extends §5a/§5b)
- `qwenShellApi.notify({kind:'done'|'permission'|'continue', title, body, tag?, chatId?})` → shows a desktop
  Notification only when the tab is hidden and `localStorage['qwen-notify']` is `on|sound`; always adds "(n)" to the
  hidden tab title. `openArtifact({id, kind, title, code, svg?})`, `closeArtifact()`, `openPersonalize()`.
  Keys: `qwen-notify`, `qwen-art-w` (panel width).
- Artifact panel: srcdoc iframe `sandbox="allow-scripts"` + CSP `default-src 'none'` (html); no scripts for
  svg/markdown/mermaid; csv as table; images only from `/_qwen/out/`, `data:image`, same-page `blob:`.
- `qwenEnhance.fastModel()`, `setFast(bool)`, `stopSpeaking()`, `speechState()`; key `qwen-fast-model`.
  Classes `.qw-fast .qw-art-btn .qw-img-art .qw-speak .qw-speak-stop .qw-quote`. New labels are English in the page
  plus TH dictionary entries (live setLang).
- Fast mode is applied once per page load; opening a conversation made with another model lets the WebUI restore
  that model (the chip then honestly shows "off").

### 11d. Operations
- Restart one service with a clean environment: WMI `Win32_Process.Create`, logs appended (`>>`):
  `powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\projects\tools\restart_svc.ps1 -Name
  mcp-local|websearch|scheduler|hub` (mirrors the launcher's `Start-CleanProcess`; check `/api/projects`
  `keep_awake` = 0 first). hub_i18n_parts.py and static files hot-reload; hub.py / MCP modules need a restart.
- Never probe `/props?model=<unloaded model>` or `/models` with a model id: the router autoloads it.
- CDP `Browser.setDownloadBehavior` and `Emulation.*` are per session: a harness that clicks a download link must set
  the download dir in the same session, or the file lands in the user's real Downloads folder.
- The artifact panel's sandboxed srcdoc frame is an out-of-process iframe. `Emulation.setDeviceMetricsOverride`
  does not resize it, so a 390 px screenshot taken by *emulating* a phone in a 1440 px window shows a blank panel
  (the frame still thinks it is ~580 px wide). Start Edge with a real `--window-size=390,844` for mobile shots of
  the panel. Open menus close on the resize that each new CDP session's metrics call triggers: open + capture in
  one session.

## 12. Round-5 / batch 2a (2026-10-01): OCR, semantic kb, deep research, skills (supersedes earlier sections where they conflict)

Owners: docs2 (extract.py, tools_kb.py), research (tools_research.py), skills (C:\LLM\skills, prompts_skills.py,
server.py `[skills]` blocks), stack (launcher step 1d, hub research/services API, shell panel, enhance "+" item).
Integration 2026-10-01 02:20-03:15: full suite 999 OK / 24 skipped; live E2E on project1 (8103, Qwen3-4B).

### 12a. Services and ports
- **8093 embedding** (llama-server `--embeddings --pooling last`, Qwen3-Embedding-0.6B Q8_0, `-ngl 0 --device none -c 8192
  -t 4`, `--api-key-file` = router token file, `--no-webui --no-slots --offline`, CORS = own origin only). Started by the
  launcher step 1d through WMI (`start-qwen38.ps1 -EmbedOnly` = this step only, exit 0 ready). `/health` needs no key;
  `/v1/*` needs Bearer. Logs `C:\LLM\logs\embed.*.log`. `stop-qwen38.ps1` stops it. `restart_svc.ps1` has no embed target.
- Hub: `GET /_qwen/research`, `GET /_qwen/research/<id>`, `POST /_qwen/research/<id>/cancel` (own-origin, JSON only,
  writes `data\<slug>\research\<id>.cancel` + calls MCP research_cancel); `/api/projects` and `GET /api/services` carry
  `services {embed, mcp, web(+provider), research(+running)}` probed every 8 s.

### 12b. Tools (fast surface)
- `local_read extract` OCRs scanned PDF pages and images (Tesseract tha+eng, 300 dpi). Output marker
  `[OCR หน้า N · ความมั่นใจ X% (สูง|ปานกลาง|ต่ำ)]`; cache `data\<slug>\kb\ocr\<sha256>-<page>.json` (never pruned).
- `local_read kb` has `mode=auto|lexical|semantic`; hybrid = RRF(k=60) of trigram + cosine (floor 0.40); hits found only by
  meaning are tagged `ตรงตามความหมาย`; vectors in `index.db` table `vecs`, filled by a per-project background thread that
  yields while hub `keep_awake > 0`. 8093 down = one-line `[หมายเหตุ]` and lexical results.
- `local_do research question [depth] [model]` → background job, returns id + ETA; `local_read research_status [id]`;
  `local_do research_cancel id`. State `data\<slug>\research\<id>.json`; reports `outputs\research-<date>-<id>.md/.docx`.
  No confirm (writes only its own project's research\ and outputs\). `/mcp` surface: research_start/status/cancel.
- **Routing hint (integrator, measured):** the 4B sent "ค้นคว้าเชิงลึกแล้วเขียนรายงานพร้อมอ้างอิงเรื่อง: …" (the "+" menu
  prefill) to `web_search` 3/3 times. Fixed with one sentence at the head of the `local_do` description AND one at the end
  of the `web_search` description (websearch server.py); either alone stayed 0/3, both = 3/3, plain web-search requests
  still use web_search 4/4. Keep both sentences if you edit those descriptions.

### 12c. Skills (MCP prompts)
- `C:\LLM\skills\<name>\SKILL.md` (frontmatter name/title_th/title_en/description/arguments + `{{arg}}` body), write-protected
  for tools. Both surfaces advertise `prompts` + `completions`; WebUI: type `/` in the composer → `/prompt` → picker →
  argument form (file names complete from the project's attachments/outputs) → a prompt chip in the composer.
  Reloaded on file change, no restart. Audit `prompt_get` stores argument lengths only.

### 12d. Shell / enhance
- Project panel section `#ppRes` "งานค้นคว้า / Research" (status, phase, sources, ETA, progress, open report in the artifact
  panel, .docx link, Stop with confirm); account menu block `#mhSvc` "บริการ"; composer "+" item `[data-qw-research]`
  "ค้นคว้าเชิงลึก" prefills th `ค้นคว้าเชิงลึกแล้วเขียนรายงานพร้อมอ้างอิงเรื่อง: ` / en `Do deep research and write a
  cited report on: ` (a typed draft becomes the topic). `qwenShellApi.startResearch()`, `openResearch()`.
- Harness note: the bits-ui "+" menu opens with an animation; a screenshot taken right after the click can show it closed.
  Clicking "+" again then closes it. Check `document.activeElement` or wait ~300 ms before the next click.

### 12e. Final acceptance (2026-10-01 05:30)
- All live services were already running current code (no restart needed); unit suite 1081 OK / 24 skipped; live security
  spot checks passed (8093/8099/8791/8792 auth, Origin/Host, research S04 across projects, write-protected skills/kb/tools).
- E2E on project1 with Qwen3-4B (4 messages): skill picker → long-doc-summary → OCR extract (the 4B again mangled the Thai file
  name; near-name resolution opened the right file); kb hybrid found the OCR'd photo; research job r15f97b finished with real
  Wikipedia citations. Screenshots: `shots/final-b2a-*.jpg`.
- Known limit: the 4B calls kb only when the question mentions files/documents ("จากไฟล์ในโปรเจกต์ …" 3/3 replays); a bare
  question about project data ("ตอนตรวจรอบเดือน วัดได้กี่โวลต์…") got 0/3 and a "no data" answer. The panel's research card
  labels the cited count as "อ่านแล้ว N แหล่ง".

## 13. Batch 2b (2026-10-06): voice, Office bridge, plan mode, project knowledge, 27B vision (supersedes earlier sections where they conflict)

Owners: voice (C:\LLM\stt, tools_stt.py), office (tools_office.py, office_helper.py), stack (launcher, gpu_bench, hub C3 block,
models-preset.user.ini), ui (enhance/theme/shell). Integration 2026-10-06 10:55-11:20 after the 07:53 reboot: full suite 1304 OK / 36
skipped (+5 integrator tests in test_integ_b2b.py); stack started with the launcher via WMI (`-NoBrowser`: `-NonInteractive` skips
MCP/hub/STT by design); live auth spot checks 34/34; E2E on project1 (8103, Qwen3-4B) screenshots `shots/integ-b2b-*.png`.

### 13a. STT service (8795, owner voice)
- `%USERPROFILE%\anaconda3\envs\flexxfast\python.exe -X utf8 C:\LLM\stt\stt_server.py --port 8795` (launcher step 1e, WMI clean env +
  HF_HUB_OFFLINE=1, CUDA_DEVICE_ORDER=PCI_BUS_ID; logs `C:\LLM\logs\stt.*.log`; `-SttOnly` / `-RestartStt` / `-NoStt`; restart_svc.ps1
  has no stt target). Model: faster-whisper large-v3-turbo from the HF cache on E: (E: missing = /health `no_model`, mic dimmed).
- `POST /v1/transcribe` (raw audio or multipart) -> {text, language, segments[{start,end,text}], ...}; Bearer + Host + Origin checks
  (401/403), 411/413/415/503 caps; `GET /health` public, `GET /v1/status` needs the token.
- GPU policy: GPU only when >= 1.5 GB VRAM is free at job time, else CPU int8. ~2 s after each GPU job the weights are parked in RAM
  (VRAM back to ~90 MB) because the router's `-fit on` sizes a chat model's GPU layers once, at load time. Measured live: mic clip
  13 s -> 2.7 s, 32 s file -> 4.4 s on GPU with the 4B loaded; CPU int8 (27B loaded) ~21-24 s per 10-12 s clip.
- MCP `local_read action="transcribe" path=...` (cache `data\<slug>\kb\stt\`, indexed by kb); hub `POST /_qwen/stt` forwards with the
  token (own-origin only, 25 MB cap, 415 for non-audio).

### 13b. Office bridge (owner office)
- `local_read action="office" what=list|excel|word|powerpoint [range] [sheet]` (S07 banner) and `local_do action="office_write"
  target=excel|word [cell] [sheet] [overwrite] data` (confirm token + server review; fingerprint refusal if the target changed; never
  saves/closes/opens). Helper = anaconda python, 30 s timeout, scrubbed env; GetActiveObject only.
- ~~Known gap~~ closed 2026-10-06 (see 13e): Office read routing with the 4B = English capability sentence at the head of the
  `local_read` description (tools_fast.py `[fix-office b2b]`, keep the Thai sentence too: English alone 0/5) + hub `apply_office_note`
  (hub.py `[final b2b]`): for a live-Office READ intent (`auto_kb_skip()=="office"` + `_OFFICE_LIVE_RE`, not `_OFFICE_WRITE_RE`, no
  @mention) the hub appends a fixed note in the user's language to the latest user message ("read it first with local_read
  action=\"office\" what=\"<app>\"", or `office_read` on /mcp; nothing when the request has neither tool). Measured: without the note
  th UI 5/5 but en UI + Thai question 3/5 (misses answered in English); with it 5/5, Word 3/3, PowerPoint 2/2 through the live hub.
  Write intents get no note (with it the 4B reads instead of writing, 4/4) and call office_write with cell=B2 3/3.
- Office write hardening (fix-office): formulas that reference another file/UNC/missing sheet are written as text; macro workbooks
  get a VBA warning in the review and EnableEvents=False around the single Range.Value write; old values in the review keep types.

### 13c. Hub (owner stack)
- Plan mode: header `X-Qwen-Plan: 1` (enhance adds it per chat) -> PLAN_PROMPT at the end of the system message + read-only tools
  only (local_do, local_confirm, write/run/media/task/office_write stripped on the server; header not forwarded).
- Project knowledge: attachments list (<= 20 names) in the system prefix; kb hits (`mode=semantic`, only "ตรงตามความหมาย" hits, k <= 4,
  8 s timeout) or `@attachments/<file>` extracts appended AFTER the latest user message as labelled untrusted data and cached for
  tool steps; project field `auto_kb` (missing = on). Skips: tiny/smalltalk/web/code and (integrator) live-Office intents
  (`_OFFICE_APP_RE` + "ที่เปิดอยู่/ที่เลือก/เคอร์เซอร์/selected/open…" or "ใส่/เขียนลง Excel/Word") — the kb block had made the 4B
  summarise project files instead of the open workbook.

### 13d. 27B vision + context (owner stack, measured 2026-10-06, gpu_bench 128 tokens, think off)
- Run 1 (sequential): base 1.06 tok/s | a ctx64k 1.03 | b mmproj GPU 1.08 | c mmproj CPU 0.96 | d img768 1.14 | e (a+c) 1.12.
  Interleaved ABBA x2 (`--rounds 2`): base 1.25 | e 1.44 | b 1.58. Noise is about +-20% per run, so compare only interleaved runs.
- ~~Chosen: mmproj on CPU~~ superseded by the stack fixer (15:13-15:25): a+b (64K + mmproj on GPU + 768) measured interleaved against
  e, rounds where the live router reloaded a model discarded: a+b 1.19 / 1.10 tok/s vs e 1.03, chart image 27 s vs 31 s, VRAM free
  after load 2,358 vs 2,364 MiB (-fit moves layers for the projector). No vision config was >= 10% slower than the no-vision base.
- **Current** `C:\LLM\models-preset.user.ini` (no BOM, LF) = `ctx-size = 65536`, `mmproj = ...mmproj-Qwen3.8-27B-F16.gguf` (on GPU,
  default device), `image-max-tokens = 768`; merged into models-preset.ini by the launcher. Live check: image question -> "สีแดง" 40 s
  incl. cold load. 768 cap: 4000 px photo 348 s -> 74 s, reading still correct. Re-measure with `gpu_bench.py --variants vision27b
  --rounds 2` after an eGPU is attached. No fit-target (with 27B + 4B both loaded only ~50-120 MiB VRAM is left whatever the margin;
  the hub's `stt_make_room` unloads the least-recently-used idle model when the mic needs the GPU).

### 13e. Fixes after integration + final acceptance (2026-10-06 15:40-16:05)
- Launcher: after a reboot use `powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\start-qwen38.ps1 -Unattended` via WMI
  (full start, never prompts, no browser; exit 0 done / 3 a chat was streaming / 1 failed). `-NonInteractive` is only the hub's
  GPU-apply path (router + embedding). Restart STT alone: `-RestartStt` (restart_svc.ps1 has no stt target).
- STT (voice fixer): auto-detect limited to `--languages th,en`; short clips (<= 30 s) with a low-confidence/out-of-set language
  fall back to `hint=` or `--primary-language th` (12/12 short Thai words now Thai script, English 13/13); `POST /v1/warm` (token);
  `/health` shows `device` + `parked`; decode caps (8-192 kHz, <= 8 channels, sample budget before resampling, 5 in flight, 2 decodes).
  tools_stt: ffmpeg only if it supports `-protocol_whitelist`, demuxer forced from magic bytes, playlist/manifest files refused.
- Hub (stack fixer): kb hits and @mention extracts are now a synthetic `local_read` tool-call exchange right after the latest user
  message (not appended to the user text: the 4B obeyed instructions inside documents 4/4 there, 0/4 in a tool result), relevance
  filter (cosine >= 0.56 and within 0.08 of the best, snippets >= 40 chars, no web-research reports), replies in the user's language;
  `gate_confirm_tool` strips local_confirm until a tool result carries a server-issued token; plan mode = allowlist
  `PLAN_KEEP_TOOLS`; chat body cap 64 MB + WebUI `maxImageMPixels: 4`; services stt has `device: gpu|cpu`.
- Final acceptance (this section's author): added `apply_office_note` (13b) + `tests\test_final_b2b.py` (8 tests); hub restarted with
  restart_svc.ps1 after keep_awake = 0. Unit suite **1393 OK / 38 skipped**. Live spot checks 46/46: 34 auth/health (integ
  live_checks.py: 8791/8792 token+Origin+Host, 8099/8093 key, 8795 token/Host/Origin, hub /_qwen/stt Origin + 415) + 12 more
  (8795 /v1/warm 401, /health device only, plan mode live A/B: same forced local_do request -> call without the header, no call with
  `X-Qwen-Plan: 1`; local_confirm gate; office_write on our own hidden scratch workbook: token + nothing written, server review shows
  file/sheet/F2:G3/every value, target edited -> "ยังไม่ได้เขียนอะไร", approved write lands exactly and the workbook stays unsaved).
- E2E on project1 (8103, Qwen3-4B, headless Edge, 3 model messages + dictation): mic -> text in the composer 2.9 s after stop (GPU);
  plain question "ตอนตรวจรอบเดือน วัดแรงดันขาเข้าได้กี่โวลต์" -> "398 โวลต์" with no tool call; plan chip -> header sent, 5-step plan,
  zero tool calls, plan bar shown; Office chip text with our scratch workbook -> one local_read office card (Allow) -> "ตู้ C-03 …
  92°C … หยุดจ่ายไฟ รอซ่อม", Excel closed unsaved. No JS errors. Screenshots `shots/final-b2b-*.png`.
- Known limits: the WebUI language setting is currently `en` (left as is); dictation runs on CPU (~21-24 s per 10-12 s clip) when
  the 27B holds the GPU and no idle model can be unloaded; the 4B may still add draft content after a plan (tools are stripped, so
  nothing can change); `tools_docs.xl_value` (make_file xlsx) still writes cross-file formulas as formulas (docs owner).

## 14. Batch 3 (2026-10-06): compaction, usage log, doctor (supersedes earlier sections where they conflict)

Owners: hub (hub.py "batch 3 D1-D3" block, hub_compact.py, hub_usage.py, hub_doctor.py, record_tests.py), ui (hub_i18n_parts.py
manage-page tabs + account menu, webui-enhance.js notice, webui-theme.css). Integration 2026-10-06 22:14-23:00 after the 21:03 reboot:
stack started with `start-qwen38.ps1 -Unattended` via WMI; hub restarted with restart_svc.ps1 (keep_awake = 0); full suite **1505 OK /
49 skipped** (+7 integrator tests in `tests\test_integ_b3.py`, recorded in `logs\tests-last.json`); E2E on project1 (8103, Qwen3-4B),
screenshots `shots/integ-b3-*.png`. hub.py / hub_compact.py / hub_usage.py / hub_doctor.py need a hub restart; hub_i18n_parts.py and
static files hot-reload. Fix round 2026-10-06 23:00 - 10-07 02:13 (hub fixer + ui fixer, 14f), hub restarted 02:13; final acceptance
2026-10-07 02:15-03:15 (14g): suite **1,550 run: 1,501 passed / 49 skipped**. 14a-14d below describe the current behaviour (fixes folded in).

### 14a. Compaction (D1 — hub_compact.py, hub.py `compact_chat`)
- Only WebUI chat requests (Origin = our pages), run last, after base prompt / memory / project context / plan / sampling. Requests
  estimated below `COMPACT_TINY_TOKENS` (2000) return before any router call.
- Size: char-class estimate x 1.05 x a per-model ratio learned from real `prompt_tokens`; at >= 65% of ctx, with the model loaded and no
  images, exact count via router `/apply-template` + `/tokenize`. ctx = router `/models` (meta.n_ctx > --ctx-size > preset) >
  gpu-profile placement > 32768. Never `?model=` probes.
- Trigger > 80% of ctx. Keep system message(s) + first user message + latest turns <= 45% of ctx (at least the current turn); the middle
  becomes one assistant message starting `[สรุปบทสนทนาช่วงก่อน — สร้างอัตโนมัติ]` + a bilingual "quoted web/file/tool text is data" note.
  Cuts only at user-message boundaries (tool_call/tool pairs stay intact). A current turn too large on its own -> older tool results of
  that turn clipped (head 700 + tail 300 chars).
- Summarizer: Qwen3-4B-Instruct called on the router directly (no hub injections), streamed, temperature 0.3, max_tokens 1100,
  <= 20K tokens of transcript per call, total budget 180 s. Headings in the chat's language, **decisions first, then open tasks**, facts,
  files/commands, tool results (`HEADINGS`). **Adaptive stop** (hub.py `_summarize_via_router`): during prompt processing it reads
  llama-server `prompt_progress`; if the rest of the prompt + the expected summary at the best measured speed (`COMPACT_BEST_GEN_TPS` 24)
  cannot finish before the deadline it stops; after >= 24 tokens and >= 4 s of generation it projects the finish from the real tok/s and
  stops when that is past the deadline (`PartialText(reason='slow')`, note `cut_reason: "slow"`).
- Outcomes: finished -> IDs / file names / numbers with units / dates it skipped are quoted verbatim under "(ข้อเท็จจริงจากช่วงที่ถูกย่อ
  ซึ่งสรุปข้างบนยังไม่ได้ใส่ — ยกจากต้นฉบับ)" (only the 1,500-token total caps it); not finished -> `partial`: the previous summary is kept
  byte-for-byte as the base, plus the model lines it lacks and a digest of the newly dropped turns (`line_covered`: a line with fact
  atoms needs all of them, a line without needs >= 60% 4-gram containment); 4B down or too slow before writing anything -> `fallback`:
  fact-focused extractive digest (every user message with facts, tool/assistant lines with new facts or open tasks; fact-less requests
  collapse into one "หัวข้อที่ผู้ใช้ถามและได้คำตอบไปแล้ว (ไม่ใช่งานค้าง): …" line, dropped first by `_fit`).
- Safety of the summary (it is sent as an assistant message every later turn): per-compaction random speaker tags (`[Q1A2B3 USER]`), every
  quoted line prefixed `│ ` and `defang()`ed (chat-template tokens, control/bidi/zero-width chars); `filter_summary` drops open-task lines
  with no `_OPEN_RE` support in the dropped turns, decision lines not said by the user/assistant, any approval/permission claim for
  tools/commands/uploads, "อนุมัติ" without a user message behind it, URLs/e-mails not in user text or tool-call args, `_INJECT_RE`
  matches; tool/web lines matching `_INJECT_RE` are reduced to their fact values. Every path runs `scrub()` (secrets_util + key shapes:
  Bearer, api_key=, sk-, BSA, ghp_, AKIA, xox) + `clean_summary()` before saving, and `summary_message()` defangs again on reuse.
  Fact regexes are bounded (no quadratic scans; 200K-char single-line JSON compacts in < 1 s).
- No loop: if head + current turn + expected summary is still > 80% while the request is <= `HARD_FRAC` (95%), the request goes as is
  (`irreducible`, no 4B call); with an existing summary it is reused (`reused_over`) until the request passes 95%.
- `apply_decision_note` (hub.py): when a compacted chat also gets an auto-kb tool result after the latest user message, the summary's
  decision lines are appended to that tool result ("[หมายเหตุจากระบบ: … สิ่งที่ผู้ใช้ตกลงไว้แล้วในแชตนี้ … มาก่อน: …]"), byte-stable.
  A/B with the real 4B: 3/3 kept the agreed decision vs 0/3 for a precedence sentence anywhere else.
- Cache **`C:\LLM\projects\data\_compaction.cache\<slug>\<sha>.json`** (outside the project folder: guard S04 denies tools there as
  `other_project`; slugify never yields `_compaction.cache`; the scheduler skips `_` folders; deleting a project moves its cache to
  `data\_trash`). Key = first user message + first turn (not X-Conversation-Id: WebUI pre-encode requests lack it). Reused byte-for-byte
  until the request passes 80% again, then grows. Retention `RETENTION_DAYS` 30 (older entries never reused, pruned on save) +
  `Store.sweep()` at most every 6 h per project rewrites abandoned files with their unexpired entries (nothing is deleted).
- `X-Qwen-Compacted: <turns>` on chat responses (Extend and generic paths) only when applied. Upstream `X-Qwen-*` headers are dropped
  (integrator, `_upstream_header_skip`). `GET /_qwen/usage[?conversation=<id>]` (own-origin) -> {project, conversation, compaction:
  note|null, **in_progress**: {state "summarizing", turns, new_turns, grow, started_at, elapsed_s, budget_s, message_th/en,
  tooltip_th/en}|null, last, recent <= 20}; the note has turns, reused, fallback, partial, cut_reason, filtered_lines, forced,
  clipped_tool_results, before/after/summary tokens, ctx, model, summarizer, summary_s, message_th/en, tooltip_th/en.
  **`GET /_qwen/compact/summary[?conversation=<id>]`** (own-origin) -> {conversation, turns, created, fallback, partial, summary} = the
  exact text the model reads (404 before the first compaction or after a hub restart). `POST /_qwen/compact {conversation}`
  (application/json, own-origin) -> 202; applies to that chat's next request within 30 min. No UI for in_progress / summary / manual
  compact yet (14g known limits).

### 14b. Usage log (D2 — hub_usage.py)
- One line per proxied generation (WebUI pre-encode `n_predict 0` skipped) in `C:\LLM\projects\data\usage.jsonl`: {ts, project, model,
  prompt_tokens, cached_tokens, completion_tokens, prompt_tps, gen_tps, wall_s, tools_used (names), compacted, error, conv (12-hex hash
  of the WebUI chat id)} — never message content. At ~10 MB renamed to `usage-<stamp>.jsonl` (never deleted).
- `GET /api/usage?days=1..90` on 8100 (our pages or local scripts; other Origins / cross-site fetches 403) -> {days, from, to,
  generated_at, totals, per_day[{date, ..., models{}}], per_project[{project, name, ...}], per_model[{model, short, ...}], models[],
  recent[<= 50], sessions[<= 20]}; tok/s averages are weighted by tokens.
- `gen_tps`: one segment = llama-server's own `timings.predicted_per_second`; Extend Mode segments = sum(predicted_n - 1) /
  sum(predicted_ms) (fix: it was overstated by n/(n-1)). The summarizer's own 4B tokens are not logged (contract: proxied completions only;
  the hub log line "ย่อบทสนทนา … สรุป N วินาที" shows its cost).

### 14c. Doctor (D3 — hub_doctor.py)
- `GET /api/doctor?lang=th|en[&refresh=1][&format=text|&text=1]` (same Origin rule, cached 10 s, ~0.2-0.3 s live) -> {checked_at,
  services[router, mcp_local, mcp_web, embed, stt, scheduler, gateway, hub], models{loaded, available, files}, versions, gpu, memory,
  disks, keys{local_token, brave_key, gateway_key} (booleans only), docker{usable, reason}, errors[<= 20, redacted], tests, fixes[{id,
  severity, th, en}], overall ok|warn|error, took_ms, cached, _meta, lang}. Read-only: no model loads, no hashing.
- Integrator changes (hub_doctor.py `[integ b3]`): fixes carry `severity` error|warn|info (same map as the page's `B3_FIX_LEVEL`);
  `overall` ignores info-only fixes (Brave key, Docker), so a healthy machine reports `ok`; a scheduler heartbeat "error" is superseded
  (`heartbeat_superseded: true`, message hidden) when the live checks of the 4 services it covers (router, both MCP, hub) are all ok —
  the launcher starts the scheduler before router/hub, so the first heartbeat after every start says "2/4 down" for 30 min; llama-server
  `Connection handling canceled` (user pressed stop / hub ended the summarizer at its budget) counts as benign, like ConnectionReset.
- "Last test run" = `logs\tests-last.json`, written by `C:\Python313\python.exe C:\LLM\projects\record_tests.py` (runs the full suite).
- Fix round (hub_doctor.py `[fix-hub b3]`): log errors skip `*.err.log` not written for `ERR_MAX_AGE_S` (3 days) and logs whose name ends
  in a port that is not a live stack port (`live_ports`: gpu-state-8197, llama-8199 …) — counts in `_meta.errors_old_files` /
  `errors_test_logs`; `versions.os` = "Windows 11 (10.0.26200)" from a cached `sys.getwindowsversion()` (build >= 22000); STT device from
  `/v1/status` (token) when `/health` has none; redaction = secrets_util.scrub + `value_scrubber` (gateway/Brave key values read
  in-process, replaced by ***) + label patterns ('client key <v>', X-Api-Key, gateway_key=) + `_TOKENISH_RE` entropy rule + control/bidi/
  zero-width strip, also on heartbeat text and failed test names. Disk/commit thresholds: `DISK_LOW_GB` 10, `COMMIT_LOW_GB` 8 (absolute).

### 14d. UI (D4)
- Manage page (8100) tabs Projects / การใช้งาน Usage / ตรวจระบบ Doctor (ARIA tabs, arrow keys, deep links `#usage` `#doctor`); inline-SVG
  charts (tokens/day stacked by model, tok/s per model, top projects), 7/30-day switch, recent-requests table; doctor table with dots,
  fixes sorted error -> warn -> info, machine/software cards, collapsed log errors, "copy report" text built client-side (b3Report +
  b3Scrub). The chat shell's account menu links open these tabs in a new tab.
- Recent requests (ui fixer): `b3RcFit()` measures the real table width against the card and toggles `#uR.rc-narrow` (table
  display:none, a two-line `ul.rc-list` shown: project · time / model · Prompt N (X cached) · Reply N · tok/s · Took T + badges; values
  are nowrap spans joined by nbsp + "· "); a ResizeObserver re-measures (compares `B3.rcW`, no loop). 1440 keeps the table, 390 and 768
  get the list. No fixed breakpoint.
- Meter colours come only from the hub (`b3MeterLv` / `b3Meter(…, level)`): a per-row `level`/`severity`/`low:true` if the hub ever
  sends one, else a non-info hub fix about that row (`disk` fix whose first drive letter matches — `b3FixDrive` ignores paths like
  C:\LLM\… —, or `commit`) with that fix's level; only when the report has no fixes list at all, the hub's absolute 10 GB / 8 GB as amber.
  The page never decides red by itself; RAM has no hub rule and stays neutral. The copied report marks the same rows "เหลือน้อย/Low".
- Fix severity map `B3_FIX_LEVEL` (page) = hub `severity` (14c): service down = red, brave/docker = tips (not counted as problems).
- enhance wraps `window.fetch` for same-origin POST `.../v1/chat/completions`, reads only the `X-Qwen-Compacted` header and returns the
  WebUI's own Promise; state per chat in localStorage `qwen-compact` (<= 300 chats); `qwenEnhance.compaction()` -> {id, turns, shown};
  a quiet divider above the composer ("สรุปช่วงต้นของบทสนทนาแล้ว (n รอบ)" / "Earlier part of this chat summarized (n turns)") with a
  tooltip on hover, click/tap (pins) or keyboard focus, Esc closes.

### 14e. Integration results and known limits
- Live checks: Origin/Host 36/36 (/api/usage, /api/doctor incl. format=text: our pages + local scripts only, evil/null/8099/8180 Origins,
  cross-site and same-site Sec-Fetch-Site, rebinding Host -> 403; /_qwen/usage and /_qwen/compact own-origin only, text/plain 415, bad id
  400, GET 405, no CORS grant). Secret scan (values via secrets_util, never printed): /api/doctor JSON + text, /api/usage, /_qwen/usage and
  the page's copied report contain neither the local token nor the gateway key. All services ran with a clean environment (45-54 vars, no
  agent variables).
- E2E (project1, 4B): a normal chat was logged (3,814 prompt tokens, 15.9 tok/s, no header, no notice). A seeded 39-turn chat (~31K real
  tokens, more than the 4B's 32,768 ctx with the hub's prompt) -> 24 turns compacted, 34,097 -> 16,192 tokens; the summary hit the 180 s
  budget (partial) but kept 14/14 fixture facts + the open fuse task, and the injected web instruction was not copied; reply 1,056 tokens
  at 2.89 tok/s, wall 585 s; notice shown (th/en, 1440/390, tooltip). Turn 2 reused the summary (no new summarization, 16,624 of 18,017
  prompt tokens from the llama.cpp cache, wall 21 s) and answered "K2 ของตู้ C-03 ภายใน 15 ต.ค. 2569 งบไม่เกิน 48,500 บาท".
- Known limit (stack): the 4B as placed (`--ctx-size 32768`, q8_0 KV, `--fit on`, 6 GB RTX 1000) generates ~3 tok/s at 16K context
  (15.9 tok/s at 4K), so summaries of long chats always end partial at 180 s and the first compacted reply takes ~10 min, with nothing on
  screen during the summary. A GPU-resident 4B for summaries (smaller ctx, measured 24 tok/s at 16K / ngl 99 by the hub owner) would fix it.
  (Hub side mitigated in 14f by the adaptive stop; the placement itself is still open, see 14g.)

### 14f. Fix round after integration (2026-10-06 23:00 - 10-07 02:13)
- Hub fixer (hub.py, hub_compact.py, hub_usage.py, hub_doctor.py; tests in test_b3_hub / test_b3_compaction / test_b3_usage /
  test_b3_doctor): adaptive summarizer stop + `in_progress` (14a); decisions-first headings + `filter_summary` (invented open tasks dropped,
  real ones kept — live 4/4 runs: 2-3 invented "ยังไม่ได้…" lines dropped every run, K2 / 48,500 / 15 ต.ค. 2569 / 7,500 kept 4/4);
  summary growth keeps old facts (`line_covered`, partial keeps the old summary byte-for-byte); fact-less requests collapse into one
  "answered topics" line; prompt-injection hardening (random speaker tags, defang, approval/URL/inject filters — live: raw 4B output put
  forged approvals under Decisions 4/4, stored summary clean 4/4); bounded regexes (pathological 16K-char runs 13.6 s -> 0.00 s; 200K-char
  JSON 9 s GIL stall -> 0.005 s); scrub before save; cache moved to `data\_compaction.cache\<slug>` + 30-day retention + 6-hourly sweep;
  no summary loop (`irreducible` / `reused_over`); `apply_decision_note`; gen_tps fix; doctor log-age/test-log filter, Windows 11 label,
  STT device, value-based redaction. Live replay on a hub copy (8171, temp data, router 8099, 4B): summarizer stopped after 29 s instead
  of 180 s (4B at 3.3 tok/s), whole first compacted reply 82 s instead of 585 s, turn 2 reused the summary (13,364 of 13,417 prompt tokens
  cached, 11.8 s).
- UI fixer (hub_i18n_parts.py only, hot-reloaded): meter colours from the hub verdict (`b3MeterLv`) and the narrow recent-requests list
  (`b3RcFit`, `#uR.rc-narrow`) — 14d. BrowserE2E test_4 now patches `hub.compact_chat` (the integrator's header strip made the fake
  upstream header disappear). `test_b3_ui`: 8 browser tests pass with `QWEN_B3_E2E=1`.

### 14g. Final acceptance (2026-10-07 02:15-03:15)
- Services current: every hub file is older than the hub process (pid 44232, 02:13); scheduler restarted 02:05 after its 02:05 edit;
  MCP/embed/STT/gateway/router started 01:34-01:35 and their sources are unchanged since. All long-lived services have a clean
  environment (45-54 variables, no agent names; psutil, names only). Nothing was restarted by this step.
- Unit suite via `record_tests.py`: **1,550 run: 1,501 passed / 49 skipped / 0 failures** (772 s), recorded in `logs\tests-last.json` (doctor shows
  "ผ่าน 1,501 · ข้าม 49 · ไม่ผ่าน 0").
- Security spot checks 94/94 (`scratchpad\final-b3\sec_checks.py`): /api/usage (7/30 days) and /api/doctor (JSON + format=text) -> 200
  for local scripts and Origins 127.0.0.1:8100/8103 and localhost:8100 (by design, `ALLOWED_ORIGIN`), 403 without ACAO for evil, null,
  :8099, :8180, localhost:8099, localhost.evil.example, cross-site / same-site Sec-Fetch-Site without Origin, and a rebinding Host;
  /_qwen/usage and /_qwen/compact/summary own-origin only (8101/8100/evil/forged same-site/rebinding -> 403, 8103's page cannot read
  8101's), summary bad id 400; /_qwen/compact text/plain 415, other project/evil 403, GET 405, bad id 400, preflight gets no ACAO.
  Leak scan (values loaded in-process via secrets_util, never printed): doctor th/en/text/refresh, usage 30/90 days, /api/projects,
  /api/services, /_qwen/usage, /_qwen/compact/summary, usage.jsonl, hub logs, the new compaction cache file and the text the doctor's
  "คัดลอกรายงาน" button copied — all clean; `keys{}` booleans only. The two new usage.jsonl lines carry numbers only.
- E2E on project1 (8103, Qwen3-4B, one headless Edge, 2 model messages). Machine state: another long-running 27B job
  (1.2 tok/s) was generating the whole time and the 27B held most of the 6 GB VRAM (18-36 MiB free).
  A 39-turn conversation (fixture from test_b3_fixture + 16 filler turns, new first message so the cache key was fresh) was imported
  into the WebUI's IndexedDB and opened. Message 1 ("ตกลงอะไรไว้แล้วบ้าง … งานไหนที่ยังค้าง"): `in_progress` visible from 1 s ("กำลัง
  สรุปช่วงต้นของบทสนทนา… (24 รอบ)"); the 4B read the 17K-token transcript at ~230 tok/s but then wrote at 0.9 tok/s, so the adaptive
  stop fired at 129 s (`cut_reason: slow`) -> extractive digest (`fallback`), 944 tokens, **16/16 fixture facts kept** (C-03 92 °C 398 V,
  inspection_2026-09.pdf, C-07 E-212, K2 15 ต.ค. 2569 48,500 บาท, สมชาย 2417, 85 °C config/alerts.yaml, 1,250 บาท 7,500 บาท, R-04) + the
  open fuse purchase; no injected instruction, no chat-template tokens. 24 turns compacted, 40,413 -> 18,977 est. tokens (the uncompacted
  request would not fit the 32,768 ctx). The reply then took 35 min (16,160 prompt tokens at 9.9 tok/s, 311 tokens at 0.98 tok/s — VRAM
  contention, see limits); usage line compacted true. Notice "สรุปช่วงต้นของบทสนทนาแล้ว (24 รอบ)" shown, tooltip opens on click.
  Message 2 ("K2 ต้องเปลี่ยนภายในวันไหน ฟิวส์สั่งแล้วหรือยัง"): summary reused (reused true, summary_s 0, no new hub summarizing line),
  16,470 of 16,541 prompt tokens from the llama.cpp cache, wall 111 s, answer correct: "ภายในวันที่ 15 ตุลาคม 2569 / ฟิวส์ 125 A ยังไม่ได้
  สั่งซื้อ (1,250 บาท/ตัว 6 ตัว = 7,500 บาท)". Usage tab lists both requests with "สรุปแล้ว"; Doctor tab "ทุกบริการทำงานปกติ · มีคำแนะนำ
  2 ข้อ" (Brave key, Docker = tips), 8/8 services green, 0 log errors, all meters neutral (C: 11.2 GB, E: 11.5 GB free > 10 GB). English
  at 390 light: notice "Earlier part of this chat summarized (24 turns)", recent requests as the two-line list, no horizontal scroll
  (shell, frame and manage page scrollWidth 390). Screenshots `shots/final-b3-1..6-*.png`.
- Known limits / follow-ups:
  - Stack (major for UX, not correctness): the 4B is placed with `--fit on` at load time; when the 27B is loaded first (and busy) the 4B
    gets almost no VRAM and runs at ~1 tok/s generation and ~10 tok/s prompt at 16K, so the first compacted reply can take 30+ min. The
    hub's adaptive stop keeps the summary itself bounded (129 s here, 29 s on a quiet machine). Fix = a GPU-reserved small-ctx 4B for
    summaries or `stt_make_room`-style unloading before a long 4B request — stack owner's call.
  - UI: enhance does not yet poll `/_qwen/usage` `in_progress`, so during the summary the WebUI shows only its own "กำลังประมวลผล…";
    no link to `GET /_qwen/compact/summary` and no manual-compact button (both optional in the contract).
  - Model quality: with a correct summary in context, the 4B's first answer still listed explained filler topics as "งานยังค้าง" and left
    out the fuse purchase and the 15 ต.ค. date; the direct follow-up question answered both correctly. The hub cannot fix reasoning.
  - Disk: C: free went 11.9 -> 11.2 GB during this hour (not caused by this step); below 10 GB the doctor will raise the `disk` fix.
