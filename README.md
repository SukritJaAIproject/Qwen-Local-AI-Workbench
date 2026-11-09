# Qwen Local AI Workbench

[![Tests](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/actions/workflows/tests.yml/badge.svg)](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/SukritJaAIproject/Qwen-Local-AI-Workbench)](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/releases/latest)
[![License](https://img.shields.io/github/license/SukritJaAIproject/Qwen-Local-AI-Workbench)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2011-blue)](#requirements)
[![Python](https://img.shields.io/badge/python-3.13-blue)](#requirements)

A fully local, privacy-first AI workbench for Windows, built around **llama.cpp** and **Qwen** models.
It wraps the llama.cpp server and its built-in WebUI with a clean, chat-first interface in **Thai, English,
Japanese and Simplified Chinese**, per-project workspaces, guarded tools over MCP, a built-in browser, document and knowledge features, voice
input, usage and health dashboards, and automatic GPU placement across the internal GPU and a Thunderbolt eGPU.

Models, chats, files, embeddings, OCR and speech-to-text all run on `127.0.0.1`. Data leaves the machine only
when a web tool runs: web search, page fetch, the isolated browser, the built-in browser panel or a
deep-research job. The web-search tools are enabled in every project by default, and each tool call shows up
in the chat.

> **ภาษาไทย:** Qwen Local AI Workbench คือชุดเครื่องมือ AI ที่ทำงานบนเครื่องของคุณทั้งหมด (Windows 11 + GPU NVIDIA)
> สร้างบน llama.cpp และโมเดล Qwen มีหน้าแชตภาษาไทย อังกฤษ ญี่ปุ่น และจีนตัวย่อ แยกพื้นที่ทำงานเป็นโปรเจกต์
> เครื่องมืออ่านและสร้างเอกสาร ค้นข้อมูลในไฟล์ พิมพ์ด้วยเสียง เบราว์เซอร์ในตัว และการจัดวางโมเดลลง GPU อัตโนมัติ
> ข้อมูลไม่ออกจากเครื่อง ยกเว้นตอนใช้เครื่องมือค้นเว็บ วิธีติดตั้งอยู่ที่ [Quick start](#quick-start) (ภาษาอังกฤษ)
> ส่วนหน้าจอสลับภาษาได้จากปุ่ม ไทย | EN | 日本語 | 中文 หรือกด `Alt+Shift+L`

![Chat in a project: a summary table and action list built from a project file](docs/screenshots/01-chat-en-dark.png)

> **Status.** This is a personal setup that grew feature by feature on one Windows 11 laptop. It works
> day to day and has a large test suite, but it is not a packaged product: paths assume `C:\LLM`, several
> helper environments are expected at fixed places, and most code comments are written in Thai.
> See [Known limitations](#roadmap-and-known-limitations).

> **New in v1.1.0** (November 2026): a built-in browser panel beside the chat, a message queue with Auto Continue
> and reconnectable replies, chat backups on the server, llama.cpp agent mode (on by default), per-project Bypass
> permissions, video generation through a local Creative Studio, web search without an API key (DDGS) and an
> optional Docker sandbox for Python. Details and upgrade notes are in the
> [release notes](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/releases/tag/v1.1.0).

## Contents

- [Highlights](#highlights)
- [Screenshots](#screenshots)
- [Features](#features)
- [Architecture](#architecture)
- [Measured performance](#measured-performance)
- [Requirements](#requirements)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Security notes](#security-notes)
- [Running the tests](#running-the-tests)
- [Roadmap and known limitations](#roadmap-and-known-limitations)
- [Contributing](#contributing)
- [Acknowledgements](#acknowledgements)
- [License](#license)

## Highlights

- **Local by default.** llama.cpp router on `127.0.0.1:8099` and every other service bound to loopback. A shared
  bearer token protects the router, embedding server, MCP servers and STT; Origin/Host checks protect the hub, MCP
  and STT; the remote prompt gateway has its own API key.
- **Projects.** Each project gets its own port, chat history, instructions, files, memory, default model and
  thinking mode, and its own isolated tool scope.
- **Four UI languages.** Thai, English, Japanese and Simplified Chinese for the shell, the manage page, the Doctor
  report, API messages and the notes the hub writes for the model; switch with one click (ไทย | EN | 日本語 | 中文)
  or cycle with `Alt+Shift+L`. The llama.cpp WebUI's own menus are translated too (about 700 strings, Thai and
  English today, Japanese and Chinese in progress), while chat content is never touched. The model is told to
  answer in the language you write in, and the hub detects Thai, Japanese and Chinese text to keep its own notes
  in that language.
- **Tools you can trust.** The local MCP server's tools (files, shell, Python, Office, media and its isolated
  browser) go through a policy guard, and anything that changes the machine needs a two-step confirmation that
  shows you exactly what will run. Two newer paths have lighter gates: llama.cpp's built-in agent tools (on by
  default; `-Agent:$false` turns them off) and the browser panel. Bypass permissions turns the prompts off per
  project; see [Security notes](#security-notes).
- **Documents and knowledge.** Read PDF/DOCX/XLSX/PPTX/CSV, OCR scanned Thai and English pages, create DOCX, XLSX,
  PPTX, PDF, CSV and Markdown files, and search project files by keyword and by meaning.
- **Deep research** in the background with a cited Markdown/DOCX report.
- **Built-in browser.** A per-project browser panel beside the chat: you and the model work in the same visible
  tab, and it can only reach public addresses.
- **Long agent runs.** Queue the next message while the model works; Auto Continue resumes at the agent's turn
  limit and reconnects an interrupted reply without re-running tools that already finished.
- **Voice.** Dictation with faster-whisper on the GPU (CPU fallback) and read-aloud.
- **Long chats keep working.** Automatic compaction summarizes the middle of a conversation when it nears the
  context limit.
- **Dashboards.** Usage (tokens, speed per model, top projects) and Doctor (service health, GPUs, disks, fixes).
- **GPU auto-placement.** Detects the internal GPU and a Thunderbolt eGPU, plans which model goes where, and lets
  you override it per model from the UI. The 27B model went from about 1-2 to **42.8 tok/s** after attaching an
  RTX 4090.

## Screenshots

All but one screenshot come from a demo hub with synthetic projects, chats and numbers
(see [`projects/tools/demo`](projects/tools/demo/README.md)); the confirmation card is from an earlier test run on
the author's machine. Taken with v1.1.0.

| | |
|---|---|
| ![Chat with the built-in browser panel open on a public web page](docs/screenshots/13-browser-panel-en-dark.png) **Built-in browser panel** — an isolated Edge profile per project beside the chat; you and the model work in the same visible tab, and it only reaches public addresses. | ![A reply streaming with two messages waiting in the queue](docs/screenshots/14-message-queue-en-light.png) **Message queue** — Enter queues the next message while a reply is still streaming; each item can be interjected, edited or removed. The Auto Continue and Bypass permissions switches sit in the composer. |
| ![Start screen with greeting, project pill and quick-start chips](docs/screenshots/02-start-en-light.png) **Start screen** — projects and recent chats in the sidebar, quick-start chips, Fast (4B) and Plan-first toggles. | ![HTML dashboard from a code block opened in the side panel](docs/screenshots/03-artifact-panel-en-light.png) **Artifacts panel** — HTML, SVG, Mermaid, Markdown, CSV and images open beside the chat in a sandboxed frame. |
| ![Project panel with instructions and project memory](docs/screenshots/04-project-panel-memory-en-dark.png) **Project panel** — instructions applied to every chat, and project memory (decisions, requirements, facts, to-dos). | ![Project panel with knowledge files, generated files and research jobs](docs/screenshots/05-project-files-research-en-dark.png) **Knowledge, outputs, research** — project files, automatic file search, files the model made, background research jobs. |
| ![Usage dashboard: tokens per day stacked by model](docs/screenshots/06-usage-dashboard-en-light.png) **Usage dashboard** — tokens per day by model, cache reuse, model time; only numbers are logged, never messages. | ![Reply speed per model over 30 days, jumping when the RTX 4090 was attached](docs/screenshots/07-usage-speed-en-light.png) **Reply speed per model** — demo data modeled on the measured speeds before and after attaching the RTX 4090 eGPU. |
| ![Doctor page: overall status, suggested fixes and the services table](docs/screenshots/08-doctor-en-dark.png) **Doctor** — overall status, a suggested fix for each problem, and every service with its status, response time and details. Further down the page (not in the picture): GPUs, memory, disks, model files and the last test run. Keys are reported as present/absent only. | ![Choose GPUs for models dialog with RTX 4090 and RTX 1000 Ada](docs/screenshots/09-gpu-picker-en-dark.png) **GPU picker** — per-model placement with fit/spill hints; saving restarts only the model server. |
| ![Account menu with GPU plan, services, theme, font, language](docs/screenshots/10-account-menu-en-light.png) **Account menu** — GPU per model, service status, theme, reply font, language, notifications, personalization. | ![Thai interface with a Thai answer and table](docs/screenshots/11-chat-th-dark.png) **Thai interface** — the same chat UI in Thai, with Thai-friendly fonts and line height. |
| ![Allow card showing the server-side review of a Python call](docs/screenshots/12-confirm-card-th.png) **Two-step confirmation** (Thai UI, from an earlier test run with a `print(1+1)` call) — the Allow card shows the exact code the server will run, fetched from the server, not from the model. The one-time code in the picture expired long ago. | |

## Features

### Chat UI and projects
- Clean, chat-first shell around the llama.cpp WebUI: single sidebar (new chat, search, projects, recents), centered
  greeting, large composer, serif or sans reply font, dark/light/system themes, works down to phone width.
- One port per project (`8101-8179`), each with its own chat history, instructions (system prompt), default model,
  thinking mode (off / on / auto) and auto-continue for long answers.
- Per-project knowledge files (drag and drop, Thai file names), files the model produced, research jobs and memory
  in a side panel.
- Model picker per chat, **Fast (4B)** chip for quick replies, vision input with the 27B model's projector.
- Artifacts panel for HTML (sandboxed, no network), SVG, Mermaid, Markdown, CSV tables and images.
- Export a chat to Markdown, HTML or PDF; quote part of an answer to ask about it; rename, fork and delete chats.
- Desktop notification when a reply finishes in a background tab; the machine is kept awake while a reply streams.
- **Message queue:** while a chat is working, Enter puts the next message in a queue instead of interrupting the
  running task. Queued messages go out one at a time once the chat is idle; Stop pauses the queue.
- **Auto Continue and recovery** (per project, on by default): continues automatically when the agent reaches its
  turn limit. A dropped connection, a page reload or a tool result that never reached the page reattaches to the
  same server-side operation instead of sending it again, so completed tools are not repeated. Stop cancels the run.
- **Chat backups on the server:** chats are also saved per project under `projects/data`, so history survives a
  cleared browser profile. Within a project, the model can list, search and read the text of other chats as
  reference material through read-only tools (`project_chat_list`, `project_chat_search`, `project_chat_read`);
  old messages never count as approval for anything.
- A base system prompt adds identity, today's date and "answer in the user's language", and the hub applies the
  vendor-recommended sampling settings when the client sets none.

### Tools via guarded MCP
- `mcp-local` (port 8792) serves two surfaces per project: a compact **3-tool surface** (`local_read`, `local_do`,
  `local_confirm`) that small models use reliably, and the **full surface with 53 tools** (files, search, shell,
  checkpoints/undo, media via FFmpeg, background tasks, memory, path aliases, an isolated browser profile, scheduler,
  Python, documents, knowledge search, research, Office, transcription, video generation).
- `mcp-websearch` (port 8791): web search and page fetch. Providers: general web search through
  [DDGS](https://github.com/deedy5/ddgs) (default, no key), Brave, Tavily, Serper, your own SearXNG, or the limited
  built-in mode (Wikipedia + DuckDuckGo instant answers). Searches can be narrowed to domains, recent days or news;
  fetch reads long pages in parts or jumps to a phrase.
- Every call is checked by `guard.py` and written to an audit log; see [Security notes](#security-notes).

### Built-in browser
- A browser panel on the right of each project chat, backed by an isolated Edge profile per project
  (`browser-profile\_panel\<project>`, never your own profile). The page is shown live in the panel and you can
  click and type in it; the model drives the same visible tab with `browser_*` tools (navigate, read, click, type,
  fill, scroll, wait, screenshot, upload, evaluate, tabs). There are no hidden tabs.
- All traffic goes through an egress proxy inside the hub (`127.0.0.1:8797`) that connects only to public
  addresses, so web pages cannot reach the hub, other local services or the LAN. If the system DNS stops working,
  the proxy asks public DNS (1.1.1.1 / 8.8.8.8) under the same rules.
- Text sent with `browser_type` / `browser_fill` is refused in password and payment-card fields, and a page's
  confirm/prompt dialogs wait for you in the panel. These are guard rails rather than a hard boundary:
  `browser_evaluate` runs JavaScript in the page and single key presses are not filtered. Downloads land in the
  project's `outputs`, uploads are limited to project files and the usual user folders, and page text reaches the
  model labelled as data. Sites that need a real window to sign in can be opened from the panel as a normal Edge
  window with the same profile.

### Agent mode (llama.cpp built-in tools)
- The launcher starts the router with llama.cpp's `--agent` by default: the WebUI then offers llama-server's
  built-in tools on Windows (read, write and edit files, search, run commands) under **Tools → Server Tools**, next
  to the MCP tools, and llama.cpp's MCP CORS proxy is enabled. These built-in tools run on the host **outside**
  `guard.py` and the two-step confirmation; the WebUI's own permission prompt is their gate. Start with
  `-Agent:$false` to run without them.
- The hub runs the built-in shell tool through Windows `cmd.exe` with tokens and other credentials removed from its
  environment, refuses it in Plan mode, and stops an identical command after three failures. Long retry loops are
  shortened in the outgoing request only (saved chats are never edited), and a truncated old tool call no longer
  blocks every later reply.
- **Bypass permissions** (per project, off by default) approves tool permission prompts automatically: those of the
  built-in tools, the browser panel and the MCP tools, and also the Allow card of the two-step confirmation once the
  server's review has loaded. File changes and commands then run without asking. It pauses while Plan first is on.

### Video generation (Creative Studio)
- `creative_video` asks the local **AI Creative Studio** (ComfyUI with Wan 2.2 TI2V 5B; a separate local project
  that is not part of this repository) to render a short clip from a description, or from an image attached to
  the project. The tool first returns a REVIEW card (prompt, size, length, seed, output name) with a confirm
  token; after approval it starts ComfyUI if needed, moves idle chat models out of the GPU, renders, converts the
  `.webm` to `.mp4` with FFmpeg and returns links to both files in the project's `outputs`. `creative_status`
  reports Studio health and job progress, `creative_cancel` stops a job. The compact surface has the same three
  as `local_do action=creative_video` / `creative_cancel` and `local_read action=creative_status`.
- When a message asks to create a video, clip or animation, the hub appends a system note to it that points the
  model at this tool, so it does not improvise with FFmpeg test patterns or scripts (same mechanism as the
  Office note).
- Needs `C:\LLM\start-creative-studio.ps1` and ComfyUI on `127.0.0.1:8188` with the Wan 2.2 5B files; without
  them the tool just says what is missing. A 2-second 1280x704 clip takes about 2 minutes on an RTX 4090. The
  free-VRAM figure is cross-checked with `nvidia-smi`, because ComfyUI 0.38 reports the whole card as free
  while llama-server still holds it.

### Documents and knowledge
- **Read** PDF, DOCX, XLSX, CSV, PPTX and text into Markdown with page/sheet markers (zip-bomb and XXE safe).
- **OCR** of scanned PDF pages and images with Tesseract (Thai + English, 300 dpi), with a confidence label per page
  and a cache.
- **Create** DOCX, XLSX, PPTX, PDF, CSV and Markdown files in the project's `outputs` folder, with download links in
  the chat. Every write keeps a checkpoint and shows a diff; undo is one call away.
- **Knowledge search** over attachments and outputs: SQLite FTS5 trigram index plus semantic vectors from a local
  Qwen3-Embedding-0.6B server, fused with reciprocal-rank fusion.
- **Automatic project knowledge:** before the model answers, the hub can look up related passages in the project's
  files and hand them over as clearly labelled, untrusted tool output. `@attachments/<file>` pulls a specific file in.

### Python interpreter and charts
- A persistent Jupyter kernel per project (pandas, matplotlib, plotly from Anaconda), working directory inside the
  project, figures saved as PNG to `outputs` and shown inline. Every run on the host needs approval of the exact
  code.
- **Optional Docker sandbox:** with the image from `mcp-local/python-sandbox` built and enabled, code runs right away
  in a container with no network, a read-only root file system, no Linux capabilities, a non-root user, 1 GB of
  memory and 2 CPUs, which sees only the project's `work` and `outputs` folders (and `attachments` read-only). The
  container is checked before any code runs; if Docker or the image is not available, the tool falls back to the
  host with approval. See [Configuration](#configuration).

### Deep research
- `research` runs in the background: plan, search, pick and read sources, take notes, write a report with
  citations to `outputs` as Markdown and DOCX. Progress, ETA and a Stop button appear in the project panel.

### Skills
- Prompt templates in `skills/<name>/SKILL.md`, served as MCP prompts: type `/` in the composer, pick a skill, fill
  the form. Included: long-document summary, deep research, Python data analysis, code review, formal e-mail, OCPP
  log analysis and EV-charger incident report. File arguments autocomplete from the project's files. The folder is
  write-protected from the model.

### Plan mode
- The **Plan first** chip asks for a numbered plan before doing anything. The hub enforces it server-side by removing
  every tool that could change the machine from that request.

### Office bridge
- Read the workbook, document or presentation you have open in Excel, Word or PowerPoint, and write values into
  Excel or text into Word. Writes need approval, show old and new values, refuse if the target changed since the
  review, and never save or close your file.

### Voice
- **Dictation:** the microphone button records in the browser and the hub forwards the clip to a local
  faster-whisper (large-v3-turbo) service. It uses the GPU when at least 1.5 GB of VRAM is free, otherwise CPU int8,
  and gives the VRAM back two seconds after each clip. Auto language detection is limited to Thai and English.
- **Transcribe files** (audio/video in the project) through the `transcribe` tool; results are cached and indexed.
- **Read aloud** any answer with the browser's speech engine, switching between Thai and English voices.

### Memory and personalization
- Project memory with kinds (decision, requirement, fact, progress, to-do), pinning, and a token budget; the model
  can remember and forget on request, and you can edit entries in the panel.
- "About me" and response style (normal, concise, explanatory, formal, learning, custom) apply to every chat.
- A scheduler tidies each project's `MEMORY.md` nightly and runs a health heartbeat every 30 minutes.

### Automatic compaction
- When a chat passes 80 % of the model's context, the hub keeps the first message and the latest turns and replaces
  the middle with a summary written by the small model: decisions first, then open tasks, facts, files and
  commands. The summary is cached and reused byte-for-byte so the llama.cpp prompt cache still hits. A divider in the
  chat shows how many turns were summarized.
- The summary is treated as untrusted: invented tasks, approval claims, foreign URLs and prompt-injection patterns
  are filtered out, secrets are scrubbed, and if the small model is too slow an extractive digest is used instead.

### Usage and Doctor dashboards
- **Usage** (`http://127.0.0.1:8100/?manage=1#usage`): tokens per day by model, prompt-cache reuse, reply speed per
  model, top projects, recent requests, 7- or 30-day window. The log stores numbers and tool names only.
- **Doctor** (`#doctor`): status and latency of the router, both MCP servers, embedding, STT, scheduler, gateway and
  every project port; GPUs, RAM/commit, disks, model files, recent log errors (redacted) and the last test run, with
  a suggested fix for every problem and a "copy report" button that strips secrets.

### GPU auto-placement and eGPU support
- On every start the launcher runs `gpu_profile.py`, which lists the CUDA devices, reads each GGUF header and writes
  a `models-preset.ini` for the llama.cpp router: if one card can hold the 27B model entirely (RTX 4090), the 27B gets
  that card alone with 64K context and vision, and the other models use the remaining GPU(s) plus CPU; otherwise
  models are split across GPUs and CPU with 32K context.
- When GPUs change (eGPU plugged in or removed), the launcher waits for running chats to finish and restarts only the
  model server. The UI warns when the attached GPUs no longer match the running plan.
- **Choose GPU…** in the account menu: per model Auto / one GPU / several GPUs / CPU only, with "fits fully" or
  "spills to CPU" hints. Priority: automatic plan < UI choice (`gpu-choice.json`) < `models-preset.user.ini`.
- `gpu_bench.py` measures prompt and generation speed per model or per configuration variant.

### Remote prompt gateway
- `mcp-local/gateway.py` (port 8780, loopback only) accepts prompts from local scripts with its own API key, queues
  them (one generation at a time), supports sessions and continuation of cut-off answers, and treats all caller text
  as data.

## Architecture

```mermaid
flowchart LR
  subgraph B["Browser - one tab per project"]
    SH["Shell page<br/>sidebar, project panel, artifacts"]
    UI["llama.cpp WebUI in an iframe<br/>+ injected theme and enhance.js"]
    SH --- UI
  end

  SH -->|"127.0.0.1:81xx"| HUB
  UI -->|"chat completions, same origin"| HUB
  UI -->|"MCP: bearer token, Origin/Host checked"| MCPL
  UI -->|"MCP"| MCPW

  HUB["Project hub - hub.py<br/>8100 manage page, API, dashboards<br/>8101-8179 one proxy per project"]
  HUB -->|"base prompt, memory, project knowledge,<br/>plan mode, compaction, usage log"| R
  HUB -->|"voice clips"| STT["Speech-to-text :8795<br/>faster-whisper"]
  HUB -->|"knowledge lookups"| MCPL
  HUB -->|"browser panel, browser_* tools"| BR["Built-in browser<br/>Edge, isolated profile per project<br/>egress proxy :8797, public addresses only"]

  R["llama-server router :8099 (--agent)<br/>Qwen3.8-27B, Qwen3-4B,<br/>Qwen3-Coder-30B-A3B, gpt-oss-20b"]
  MCPL["MCP local tools :8792<br/>guard.py, two-step confirm, audit log"]
  MCPW["MCP web search :8791<br/>SSRF guard"]
  MCPL --> EMB["Embedding server :8093<br/>Qwen3-Embedding-0.6B"]
  HUB -->|"query embeddings"| EMB
  MCPL --> X["Python kernel, Office COM,<br/>Tesseract OCR, FFmpeg"]
  MCPL -->|"deep research"| R
  MCPL -->|"research search"| MCPW
  GP["gpu_profile.py at launch"] -->|"models-preset.ini"| R
```

**How the UI works.** The llama.cpp WebUI is a compiled SvelteKit app that cannot be edited, so the hub serves it
inside an iframe on the project's own port and injects a stylesheet (`webui-theme.css`) and a script
(`webui-enhance.js`) into its `<head>`. The outer shell page (templates in `hub_i18n_parts.py`) provides the
sidebar, menus and panels; both share one origin, so they talk through small JavaScript APIs
(`qwenShell`, `qwenShellApi`, `qwenEnhance`). `hub_i18n_parts.py` and the static files hot-reload; the full
design and DOM map are in [docs/DESIGN.md](docs/DESIGN.md).

**What the hub adds to each chat request** (only for requests that come from its own pages): the base system
prompt, "about me" and style, project memory, the project's file list and relevant passages, plan-mode tool
filtering, sampling defaults, then compaction as the last step. Other clients can call a project port with the
OpenAI-compatible API (`http://127.0.0.1:81xx/v1/...`); they are proxied without these page-only additions, and the
hub adds the router token for them.

| Port | Service | Started by |
|---|---|---|
| 8099 | llama-server in router mode: chat models, WebUI files | launcher |
| 8100 | hub: manage page, API, Usage and Doctor dashboards | launcher |
| 8101-8179 | one proxy per project: shell page + WebUI + `/_qwen/*` APIs | hub |
| 8791 | MCP web search | launcher |
| 8792 | MCP local tools (`/mcp/<project>`, `/fast/<project>`) | launcher |
| 8093 | embedding server (llama-server `--embeddings`, CPU) | launcher |
| 8795 | speech-to-text (faster-whisper) | launcher |
| 8780 | remote prompt gateway | launcher |
| 8797 | egress proxy of the built-in browser panel (loopback; connects to public addresses only) | hub |

## Measured performance

Measured with `gpu_bench.py` on the author's laptop (Intel Core Ultra 7 165H, NVIDIA RTX 1000 Ada 6 GB) and with
an ASUS ROG Strix RTX 4090 24 GB attached over Thunderbolt (PCIe Gen4 x4). llama.cpp b10984, CUDA 12.4,
128 generated tokens, thinking off. "Prompt" is prompt-processing speed.

| Model (GGUF) | Laptop RTX 1000 Ada 6 GB + CPU | With the RTX 4090 eGPU |
|---|---|---|
| Qwen3.8-27B UD-Q4_K_M | about 1-2 tok/s, prompt 50-80 tok/s (partly offloaded) | **42.8 tok/s**, prompt 711 tok/s (entirely on the 4090, 64K context + vision) |
| Qwen3-4B-Instruct-2507 Q4_K_M | 27-30 tok/s, prompt 0.7-1.3K tok/s | 79.7 tok/s, prompt 4.4K tok/s (4090 + RTX 1000)\* |
| Qwen3-Coder-30B-A3B-Instruct UD-Q4_K_XL | — | 91.0 tok/s, prompt 476 tok/s (4090 + RTX 1000 + CPU)\* |
| gpt-oss-20b MXFP4 | — | 68.5 tok/s, prompt 1,337 tok/s (4090 + RTX 1000 + CPU)\* |

\* Measured with **Choose GPU** set to the RTX 4090 + RTX 1000 for these models. Under the automatic plan the 27B
keeps the RTX 4090 to itself and the other models run on the internal GPU + CPU, so expect speeds closer to the
laptop column for them.

Other measurements from the same machine:

- CPU threads matter on a hybrid CPU: in an earlier A/B test with the 27B offloaded (laptop power-throttled, older
  settings, hence the lower absolute numbers), 6 threads (P-cores only) gave 0.84 tok/s and 14 threads 0.57 tok/s.
  The launcher defaults to 6.
- Dictation: a 13 s clip transcribed in 2.7 s on the GPU; on CPU (int8) about 21-24 s for a 10-12 s clip.
- Image input for the 27B on the laptop: capping the vision projector at 768 image tokens cut a 4000 px photo from
  348 s to 74 s (projector on the CPU at the time), and the model still read the values correctly.
- Deep research job (standard depth, built-in search provider): about 3 minutes end to end with the 4B model.

## Requirements

| | Required | Notes |
|---|---|---|
| OS | Windows 11 | Developed on 10.0.26200; launcher and stop scripts are Windows PowerShell 5.1 |
| Git | any recent Git for Windows | Only needed to clone and update the code |
| GPU | NVIDIA, recent driver | Developed with driver 596.71. 6 GB runs the 4B model well; the 27B needs about 20 GB of VRAM for interactive speed |
| llama.cpp | b10984 Windows CUDA 12.4 build in `C:\LLM\llama.cpp-b10984` | The UI layer is mapped to this build's WebUI; newer builds may need selector updates (see DESIGN.md §4) |
| Python | 3.13 installed to `C:\Python313` + `requirements.txt` | Choose "Customize installation" and set that location: the launcher, `restart_svc.ps1` and the tests call `C:\Python313\python.exe`. Hub is standard library only; document tools need PyMuPDF, python-docx, openpyxl, defusedxml, NumPy, Pillow; the default web-search provider needs DDGS |
| Models | GGUF files in `C:\LLM\models` | **`Qwen3.8-27B-UD-Q4_K_M.gguf` is required** (the launcher exits without it); the others are optional. Not included; see [THIRD_PARTY.md](THIRD_PARTY.md). Embedding model expected at `D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf` |
| Anaconda | optional | Python tool kernel and Office bridge: `%USERPROFILE%\anaconda3\python.exe` by default (jupyter_client, ipykernel, pandas, matplotlib, plotly, pywin32, psutil); point `QWEN_PY_KERNEL_PYTHON` / `QWEN_OFFICE_PYTHON` at another interpreter if yours lives elsewhere |
| faster-whisper | optional | Voice input: conda env named `flexxfast` under `%USERPROFILE%\anaconda3\envs` with faster-whisper 1.2, CTranslate2, PyAV; model large-v3-turbo in the Hugging Face cache (or set `QWEN_STT_HF_HUB`) |
| Tesseract | optional | OCR: Tesseract 5.4 in `C:\LLM\tools\tesseract` with `tessdata_best` tha + eng |
| Microsoft Office | optional | Office bridge (Excel, Word, PowerPoint via COM) |
| FFmpeg | optional | Media tools; on `PATH`, in `C:\LLM\tools\ffmpeg\bin`, or set `MCP_LOCAL_FFMPEG` / `MCP_LOCAL_FFPROBE` |
| Microsoft Edge | included with Windows | Headless screenshot harness, the isolated browser tool and the built-in browser panel |
| Docker Desktop | optional | Python sandbox: the Linux engine and an image built from `mcp-local/python-sandbox` |
| Node.js | optional | Some UI tests run JavaScript functions in Node |

## Quick start

1. Install the prerequisites above, including Python 3.13 at `C:\Python313` and Git.
2. Clone the code into a **new, empty** `C:\LLM` (the scripts use absolute paths). `git clone` refuses a folder that
   already has files in it; if you have an older install there, rename it first instead of turning it into a
   working tree, because an install folder also holds logs, secrets and user data that must never be committed.

   ```powershell
   git clone https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench.git C:\LLM
   C:\Python313\python.exe -m pip install -r C:\LLM\requirements.txt
   ```

3. Add the parts that are not in the repository (both folders are git-ignored): unpack the llama.cpp build into
   `C:\LLM\llama.cpp-b10984` and put your GGUF files in `C:\LLM\models`. File names are the model ids, e.g.
   `Qwen3.8-27B-UD-Q4_K_M.gguf` (required), `mmproj-Qwen3.8-27B-F16.gguf` (vision, optional),
   `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (Fast chip and summaries, optional).
4. Create your local config from the examples. `ui-config.json` is required; the launcher exits without it.

   ```powershell
   Copy-Item C:\LLM\ui-config.example.json C:\LLM\ui-config.json
   Copy-Item C:\LLM\projects\settings.example.json C:\LLM\projects\settings.json   # optional: English UI (default is Thai)
   Copy-Item C:\LLM\models-preset.user.example.ini C:\LLM\models-preset.user.ini   # optional: GPU overrides
   Copy-Item C:\LLM\mcp-local\config.example.json C:\LLM\mcp-local\config.json     # optional: narrow tool write access
   ```

5. Start everything: double-click `C:\LLM\Qwen38.cmd`, or

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\start-qwen38.ps1
   ```

   On first start the launcher creates `C:\LLM\secrets\local-services.token`, plans the GPUs, starts the MCP
   servers, embedding, STT, the model router, the hub, the scheduler and the gateway, then opens
   `http://127.0.0.1:8100`. A fresh install has no projects yet: create one on that page, then open it to chat on
   its own port. The UI starts in Thai unless you copied `settings.example.json`; switch with the
   ไทย | EN | 日本語 | 中文 buttons or cycle with `Alt+Shift+L` (`"lang"` in `settings.json` takes `th`, `en`, `ja` or `zh`). Use `-Unattended` for scripted starts (no prompts, no browser; exit code 0 = ready).
6. Check that everything is up: open **Doctor** (`http://127.0.0.1:8100/?manage=1#doctor`, or the account menu).
   Every service should be green; each problem comes with a suggested fix.
7. Stop everything with `powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\stop-qwen38.ps1`. It stops the
   processes listening on the stack's ports, then **every** remaining `llama-server.exe` and any Python process
   running `scheduler.py`, so stop other llama.cpp servers you run yourself first.

To update later, stop the stack, run `git pull` in `C:\LLM`, run the `pip install` line from step 2 again and start
the launcher; the [release notes](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/releases) list
anything else a version needs.

Optional: web search works without a key (DDGS). To use Brave Search instead, put an API key in
`C:\LLM\secrets\brave-search.key`, set `{"provider": "brave"}` in `mcp-websearch\config.json`, and restrict the
secrets folder's permissions as described in [secrets/README.md](secrets/README.md).

## Configuration

| What | Where |
|---|---|
| Projects (name, port, instructions, model, thinking, auto-continue, auto knowledge) | the UI, stored in `projects/projects.json` |
| Language, theme, reply font, "about me", style | the UI, stored in `projects/settings.json` (example: `projects/settings.example.json`) |
| GPU per model | **Choose GPU…** in the account menu → `gpu-choice.json`; permanent overrides in `models-preset.user.ini` |
| Context size, threads, vision, main model for one run | launcher flags `-Ctx N`, `-Threads N`, `-Vision` / `-NoVision`, `-Primary <id>` |
| llama.cpp built-in agent tools | on by default; launcher flag `-Agent:$false` turns them off for that launch |
| Python sandbox | build the image, then create `mcp-local/python-sandbox.json` (see below); `QWEN_PY_SANDBOX=off` disables it |
| Optional services | launcher flags `-NoEmbed`, `-NoStt`, `-RestartStt`, `-RestartEmbed`, `-EmbedOnly`, `-SttOnly`, `-NoBrowser` |
| Tool permissions (writable folders, extra blocked paths) | `mcp-local/config.json` (start from `mcp-local/config.example.json`); merged with the built-in policy, see [Security notes](#security-notes) |
| Web search provider | `mcp-websearch/config.json` (start from `config.example.json`); without it DDGS general search is used, and a `{"provider": "brave"}` config uses `secrets/brave-search.key` |
| Skills | `skills/<name>/SKILL.md`; optional per-project enable/disable list in `skills/enabled.json` |
| Gateway API key | `GATEWAY_API_KEY` user environment variable |
| Restart one service with a clean environment | `projects\tools\restart_svc.ps1 -Name mcp-local` (or `websearch`, `scheduler`, `hub`) |

To enable the Python sandbox, start Docker Desktop (Linux engine) and build the image once:

```powershell
cd C:\LLM\mcp-local\python-sandbox
docker build -t qwen-python-sandbox .
docker image inspect qwen-python-sandbox --format "{{.Id}}"
```

then write the printed `sha256:...` id into `C:\LLM\mcp-local\python-sandbox.json` as
`{"enabled": true, "image_id": "sha256:..."}` (the tests read the same id from `python-sandbox\image-id.txt`).
Both files are git-ignored because the id is specific to your machine.

Useful environment overrides: `LLM_LOCAL_TOKEN_FILE` (token file for tests), `QWEN_PY_KERNEL_PYTHON` and
`QWEN_OFFICE_PYTHON` (interpreter for the Python tool and Office bridge), `MCP_LOCAL_FFMPEG` / `MCP_LOCAL_FFPROBE`,
`QWEN_BRAVE_KEY_FILE`, `QWEN_STT_MODEL`, `QWEN_STT_DEVICE`, `QWEN_STT_LANGUAGES`, `QWEN_STT_HF_HUB` (Hugging Face
cache folder for the speech model), `QWEN_SKILLS_DIR`. Services are started with your normal user environment, so
set these as user environment variables.

## Project structure

The repository mirrors the install folder `C:\LLM`.

```text
C:\LLM
├── start-qwen38.ps1          launcher: token, MCP, embedding, STT, GPU plan, router, hub, scheduler, gateway
├── stop-qwen38.ps1           stops the services on their ports, then any leftover llama-server.exe and scheduler.py
├── Qwen38.cmd                double-click wrapper for the launcher
├── gpu_profile.py            GPU detection + per-model placement -> models-preset.ini, gpu-profile.json
├── gpu_bench.py              speed benchmark per model or configuration variant
├── secrets_util.py           shared token, Origin/Host checks, secret scrubbing
├── requirements.txt          packages for C:\Python313
├── *.example.*               config templates (copy without ".example")
├── CONTRIBUTING.md           development setup and pull-request notes; also SECURITY.md, CODE_OF_CONDUCT.md,
│                             THIRD_PARTY.md and LICENSE
├── .github\                  tests workflow (GitHub Actions on Windows), issue and pull-request templates
├── projects\
│   ├── hub.py                project hub: API + manage page (8100), per-project proxies (8101-8179)
│   ├── hub_i18n.py           language registry (th/en/ja/zh), fallback rules, API message catalogue
│   ├── hub_i18n_parts.py     shell and manage-page templates, UI strings in four languages (hot-reloaded)
│   ├── hub_compact.py        automatic conversation compaction
│   ├── hub_usage.py          usage log and aggregation
│   ├── hub_doctor.py         health report for the Doctor page
│   ├── hub_browser.py        built-in browser panel: isolated Edge per project, egress proxy, browser_* tools
│   ├── hub_recovery.py       reconnectable replies (Auto Continue / recovery)
│   ├── hub_chats.py          project chat references + read-only project_chat_* tools
│   ├── hub_chat_history.py   server-side chat backups
│   ├── hub_agent.py          Windows command adapter and retry-loop guard for llama.cpp's built-in tools
│   ├── hub_tool_history.py   keeps malformed old tool calls from blocking a chat
│   ├── record_tests.py       runs the test suite, records the result for the Doctor page
│   ├── static\               theme, enhance script, design tokens, boot script, fonts (OFL), browser panel,
│   │                         message queue, recovery and chat-backup scripts
│   └── tools\                shot.py (headless screenshots), restart_svc.ps1, fixtures\, demo\
├── mcp-local\                MCP "this computer": server, guard, netguard, tools_*.py, scheduler, gateway,
│                             Office helper, Jupyter kernel runner, document extractor, skills loader,
│                             Docker sandbox backend (python_sandbox.py, image in python-sandbox\),
│                             Creative Studio video tool (tools_creative.py),
│                             config.example.json (tool permission overrides)
├── mcp-websearch\            MCP web search and fetch (general_search.py: DDGS provider)
├── stt\                      speech-to-text service and benchmark
├── skills\                   prompt templates served as MCP prompts
├── tests\                    unittest suite (+ simulated GPU fixtures)
├── docs\
│   ├── DESIGN.md             engineering notes: UI architecture, contracts, DOM map, every build round
│   └── screenshots\
└── secrets\                  README only; the real files are git-ignored
```

Runtime folders that are created locally and git-ignored: `models\`, `logs\`, `projects\data\` (chats are in the
browser's IndexedDB, with backups here; attachments, outputs, memory, research, usage log and caches are here too),
`browser-profile\`, `tools\` (Tesseract, FFmpeg).

The account menu also links to a GPU monitor on port 8796, and the launcher starts it when `gpumon\` exists. The GPU
monitor and the Creative Studio runtime (ComfyUI, Wan 2.2, Blender and their setup scripts) are separate local
projects and are not part of this repository; `mcp-local\tools_creative.py` is only the MCP side that drives the
Studio over HTTP.

## Security notes

The model can run tools on your computer, so the stack is built around keeping it on a short leash:

- **Loopback only, tokens on the back-end services.** Every service listens on `127.0.0.1`. The router, embedding
  server, both MCP servers and STT require `Authorization: Bearer <token>` (from `secrets/local-services.token`,
  compared in constant time). The hub adds the token server-side when it proxies; the page receives it only for its
  MCP connections. The remote prompt gateway uses its own key (`GATEWAY_API_KEY`). llama-server itself does not
  check the Host header; it relies on the token.
- **Origin and Host checks** on the hub, MCP and STT block other web pages and DNS rebinding. CORS answers only the
  stack's own ports, without credentials.
- **Agent mode is on by default.** The router runs with llama.cpp's `--agent`, which adds llama-server's built-in
  host tools (files and commands) and its MCP CORS proxy. Those tools do **not** go through the policy guard,
  the two-step confirmation or the audit log below; the WebUI's permission prompt is the only gate, and
  **Bypass permissions** (off by default, per project) removes it. The hub runs their shell commands with
  credentials stripped from the environment and refuses them in Plan mode. Start the launcher with `-Agent:$false`
  if you want only the guarded MCP tools.
- **Built-in browser panel.** Its `browser_*` tools are served by the hub, not by `mcp-local`: they are not checked
  by `guard.py`, need no two-step confirmation and are not in its audit log. Their limits are the WebUI's permission
  prompt, the egress proxy (public addresses only) and the fact that everything happens in the visible tab.
  `browser_upload` can send files from the project and your usual user folders to a public website, and
  `browser_evaluate` runs JavaScript in the page.
- **Policy guard (`mcp-local/guard.py`).** Secret folders and credential files (SSH keys, browser profiles and
  history, git and package-manager credentials, CLI tokens, this stack's own secrets) cannot be read.
  **Default writable roots:** your user folder (`%USERPROFILE%`), `C:\LLM`, and the **whole `D:\`, `E:\` and `F:\`
  drives** if they exist; the rest of `C:\` is read-only and other drives are not reachable. To narrow this, create
  `mcp-local/config.json` (see `mcp-local/config.example.json`): it is merged with the built-in policy, so you can
  add roots, block more paths or make a built-in root read-only, but not remove a built-in block. The stack's own
  code, configuration (including that file), skills and Windows start-up locations are write-protected even with
  approval. Destructive commands (`format`, `diskpart`, `reg`, `net user`, `shutdown`, …) are refused permanently.
  Every call is audited.
- **Two-step confirmation with server-side review.** Actions that change the machine — running commands or Python,
  editing or overwriting files, creating scripts and programs, writing into Office documents, starting or stopping
  background tasks, opening the isolated browser, rendering a video with the Creative Studio — return a one-time
  token instead of running. The token is valid
  for 10 minutes (at most 15 if a mismatched review has to be sent again). Only the separate `local_confirm` tool can
  redeem it, and the chat shows an Allow card that loads the exact review text from the server: full code with line
  numbers, the full command, or the diff. Hidden and look-alike characters are made visible, a review sent by the
  model that differs from the server's is flagged in red, and "always allow" is removed for this tool. With
  **Bypass permissions** on for a project, these Allow cards are approved automatically too, so the confirmation
  no longer waits for you.
- **SSRF guard (`netguard.py`).** Web fetches and the browser tool resolve and check every redirect hop, pin the IP
  at connect time, and refuse loopback, private, link-local and cloud-metadata addresses. The built-in browser
  panel applies the same rule in its own egress proxy, which resolves every name itself and connects only to the
  checked public IP, so pages opened there cannot reach the hub, other local services or the LAN.
- **Project isolation.** Each project's tools are bound to its own URL (`/mcp/<project>`); tools cannot read or
  write another project's data. Plan mode removes write tools on the server, not just in the prompt.
- **Untrusted content stays data.** Text from files, web pages and tools is labelled as data; automatic knowledge
  is delivered as a tool result instead of being pasted into the user's message; compaction summaries are filtered
  and defanged; secret values are scrubbed from tool output, logs, the Doctor report and summaries.
- **Clean service environments.** The launcher starts long-running services through WMI so they do not inherit
  the environment (and any tokens) of the shell that launched them.

Residual risks you should know about:

- A command you approve can do anything your account can do.
- With agent mode on, llama-server's built-in tools can read, change and run whatever your account can once their
  permission prompt is accepted; with Bypass permissions on, every approval (the two-step confirmation included)
  happens without you.
- **New files of non-executable types (documents, text, data, HTML and so on) can be created in any writable root
  without confirmation**; overwrites, edits and new scripts or executables need approval.
- The secrets folder inherits broad permissions until you restrict it (see [secrets/README.md](secrets/README.md)).
- The MCP token is stored in the browser's local storage for the project origins.
- The Python tool runs on the host unless the optional Docker sandbox is set up.
- Sign-ins you make in the built-in browser panel stay in that project's browser profile.

## Running the tests

```powershell
C:\Python313\python.exe -m unittest discover -s C:\LLM\tests
C:\Python313\python.exe C:\LLM\projects\record_tests.py        # same, and records the result for the Doctor page
```

The last full run on the author's machine (2026-11-08): 1,860 tests, 1,806 passed, 54 skipped, 0 failures. Tests
that need live services, a browser, Office, Docker or a GPU skip themselves when those are not available (the
Python-sandbox suite needs Docker Desktop running and the sandbox image built). Several live suites are opt-in
through environment flags: `LLM_SECURITY_LIVE`, `LLM_B3_LIVE`, `LLM_STT_LIVE`, `LLM_STACK_LIVE`,
`GPU_PROFILE_ROUTER_TESTS`, `QWEN_BROWSER_LIVE_TEST` (the built-in browser against a real website), and the
browser end-to-end suites `QWEN_B3_E2E` and `QWEN_UI_E2E` (set to `1`).
The suite was written for the author's layout (`C:\LLM`, `C:\Python313`, the Anaconda and `flexxfast`
interpreters, a `D:` drive); on a machine set up differently some tests skip and a few may fail.

The same suite runs on a Windows runner in [GitHub Actions](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/actions/workflows/tests.yml)
for every push and pull request (the badge at the top); the few modules that need the local stack (OCR, the
Anaconda kernel, the embedding service) are skipped there.

## Roadmap and known limitations

- **Fixed paths.** The code assumes `C:\LLM`, `C:\Python313`, `%USERPROFILE%\anaconda3` (or the
  `QWEN_PY_KERNEL_PYTHON` / `QWEN_OFFICE_PYTHON` overrides), a conda env named `flexxfast` and
  `D:\LLM\models-embed`. A configurable install root is the first thing to fix for other machines
  ([#2](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/issues/2)).
- **Windows only.** Launcher, Office bridge, WMI process handling and keep-awake are Windows-specific.
- **Tied to one llama.cpp WebUI build.** The UI layer injects into the WebUI of b10984; newer builds may move
  elements. The DOM map in [docs/DESIGN.md](docs/DESIGN.md) is the place to update.
- **Sandboxing is partial.** Python can run in the optional Docker sandbox; shell commands, the Office bridge and
  llama.cpp's built-in agent tools still run on the host.
- **Web search** without an API key goes through DDGS, which queries several public search engines; they can
  refuse or rate-limit requests, so results vary. An API provider (Brave, Tavily, Serper) or your own SearXNG is
  more predictable.
- **Small models need explicit cues.** The 4B model calls the knowledge search reliably when the question mentions
  files or documents; a bare question about project data may get "no data".
- **Compaction on a shared GPU.** If the small summarizer model has to share VRAM with a busy 27B, the first reply
  after compaction can be slow; the UI does not yet show summarizing progress
  ([#3](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/issues/3)).
- **Language of the code.** Most comments, log messages and parts of the engineering notes are in Thai.
- **Planned:** configurable paths (#2), broader sandboxing, compaction progress and a summary viewer in the UI
  (#3), and evaluation of speculative decoding drafts and newer models on the RTX 4090. Open items live in the
  [issue tracker](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/issues).

## Contributing

Issues and pull requests are welcome, in Thai or English. [CONTRIBUTING.md](CONTRIBUTING.md) has the development
setup and pull-request notes, and issues labelled
[good first issue](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/labels/good%20first%20issue) are a
good place to start; translating the remaining Thai comments into English is an easy way to help. Questions and
ideas go in [Discussions](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/discussions). Please report
security problems privately as described in [SECURITY.md](SECURITY.md). This project follows the
[Contributor Covenant](CODE_OF_CONDUCT.md).

Thanks to [Hamzaisadev](https://github.com/Hamzaisadev) for the first outside contributions: the English
translations in #4, #5 and #6.

## Acknowledgements

- [llama.cpp](https://github.com/ggml-org/llama.cpp) and its WebUI, which do the heavy lifting.
- The Qwen team for the Qwen3 model family and Qwen3-Embedding, and OpenAI for gpt-oss.
- [Unsloth](https://unsloth.ai) and [ggml-org](https://huggingface.co/ggml-org) for GGUF quantizations.
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract), [faster-whisper](https://github.com/SYSTRAN/faster-whisper),
  [PyMuPDF](https://github.com/pymupdf/PyMuPDF), python-docx, openpyxl and the Jupyter project.
- Source Serif 4 (Adobe) and Noto Serif Thai (The Noto Project Authors), under the SIL Open Font License.
- The [Model Context Protocol](https://modelcontextprotocol.io) specification.

Full third-party notes: [THIRD_PARTY.md](THIRD_PARTY.md).

This is an independent personal project. It is not affiliated with or endorsed by Alibaba Cloud or the Qwen team,
OpenAI, the ggml / llama.cpp project or Microsoft. Model and product names are trademarks of their
respective owners and are used here only to describe what the software works with.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Sukrit Jaidee.
Models, llama.cpp, Tesseract and the other components listed in [THIRD_PARTY.md](THIRD_PARTY.md) keep their own
licenses.
