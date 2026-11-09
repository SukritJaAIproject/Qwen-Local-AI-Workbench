# -*- coding: utf-8 -*-
"""Languages of the interface — the one list every module reads.

Thai was the first language and English the second; Japanese and Simplified Chinese were added in
November 2026. Every table of texts in the hub is a dict keyed by these codes. When a table has no entry
for the current language (a new text that was not translated yet, or a third-party message that exists only
in Thai or English), ``pick`` falls back to English, then Thai, so a missing translation never breaks a page.

    from hub_i18n import LANGS, norm_lang, pick, tr

    pick({"th": "...", "en": "...", "ja": "...", "zh": "..."}, lang)
    tr(lang, th="...", en="...", ja="...", zh="...")

The model-facing notes (what the system tells the model about files, documents and the reply language)
follow the same rule: Qwen reads English well, so an English note is a safe fallback, but a note in the user's
language makes the reply language more reliable, which is why those are translated too.
"""

LANGS = ("th", "en", "ja", "zh")
DEFAULT_LANG = "th"
FALLBACK_LANG = "en"

# name = the language's own name (for the switcher), english = its English name (for prompts and logs),
# locale = BCP 47 tag for Intl / toLocaleString, short = the label on the compact switcher
META = {
    "th": {"name": "ไทย", "english": "Thai", "locale": "th-TH", "short": "ไทย"},
    "en": {"name": "English", "english": "English", "locale": "en-GB", "short": "EN"},
    "ja": {"name": "日本語", "english": "Japanese", "locale": "ja-JP", "short": "日本語"},
    "zh": {"name": "中文", "english": "Chinese (Simplified)", "locale": "zh-CN", "short": "中文"},
}

# languages whose text has no spaces between words (line breaking and search behave differently)
NO_SPACE_LANGS = ("th", "ja", "zh")
# languages written in CJK scripts (fonts, the reading voice, OCR and speech models)
CJK_LANGS = ("ja", "zh")


def norm_lang(lang, default=DEFAULT_LANG):
    """A valid code or the default — "zh-CN", "ja-JP" and upper case are accepted and shortened."""
    if not isinstance(lang, str):
        return default
    code = lang.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in LANGS else default


def pick(table, lang, default=""):
    """The entry of ``table`` for ``lang``, else English, else Thai, else ``default``.

    ``table`` is a dict keyed by language code. ``None`` entries count as missing, so a table may list a
    language with ``None`` to say "not translated yet" and still fall back cleanly.
    """
    if not isinstance(table, dict):
        return default
    for code in (lang, FALLBACK_LANG, DEFAULT_LANG):
        v = table.get(code)
        if v is not None:
            return v
    return default


def tr(lang, **texts):
    """``tr(lang, th="...", en="...", ja="...", zh="...")`` — the text for ``lang`` with the same fallback as pick."""
    return pick(texts, lang)


def english_name(lang):
    return META.get(norm_lang(lang), META[FALLBACK_LANG])["english"]


def locale_of(lang):
    return META.get(norm_lang(lang), META[FALLBACK_LANG])["locale"]


def complete(table):
    """A copy of ``table`` where every language has every key: missing keys come from English, then Thai.

    For the big UI tables (``STRINGS_UI`` and the manage page) so the page never shows a bare key.
    """
    base = dict(table.get(DEFAULT_LANG) or {})
    base.update(table.get(FALLBACK_LANG) or {})
    out = {}
    for code in LANGS:
        merged = dict(base)
        merged.update(table.get(code) or {})
        out[code] = merged
    return out


# ---------------------------------------------------------------------------------------------------------------
# API replies. The hub answers with paired fields — error_th / error_en, message_th / message_en, note_th / note_en,
# tooltip_th / tooltip_en — and the page shows the one for its language. The pairs are written inline where the
# error happens (about eighty places in hub.py); rather than turning each into a four-way table, the English text is
# the key of this catalog and ``localize_fields`` adds error_ja / error_zh to a reply on its way out. A text that is
# not here simply has no ja/zh field and the page falls back to English. Templates keep their %d / %s.
# ---------------------------------------------------------------------------------------------------------------
API_TEXTS = {
    # GPU apply job
    "Restarting the model server…": {"ja": "モデルサーバーを再起動しています…", "zh": "正在重启模型服务器…"},
    "The new GPU setup is in use": {"ja": "新しい GPU 設定が使われています", "zh": "新的 GPU 设置已生效"},
    "A chat was still answering, so nothing was restarted. Your choice is saved; try again when it finishes.": {
        "ja": "チャットがまだ回答中だったため再起動していません。選択は保存済みです。回答が終わってからもう一度お試しください。",
        "zh": "有对话仍在回答，因此没有重启。你的选择已保存；等它结束后再试一次。"},
    "Restart failed — see gpu-apply.log": {"ja": "再起動に失敗しました — gpu-apply.log を確認してください",
                                           "zh": "重启失败 — 请查看 gpu-apply.log"},
    "The result of the last restart is unknown — see gpu-apply.log": {
        "ja": "前回の再起動の結果は不明です — gpu-apply.log を確認してください",
        "zh": "上次重启的结果未知 — 请查看 gpu-apply.log"},
    "Waiting for a reply to finish before restarting…": {"ja": "再起動の前に回答の完了を待っています…",
                                                          "zh": "正在等待回答结束后再重启…"},
    "Nothing to change — this setup is already in use": {"ja": "変更はありません — この設定はすでに使われています",
                                                          "zh": "无需更改 — 当前已在使用此设置"},
    "The launcher ran for more than 20 minutes — see gpu-apply.log": {
        "ja": "ランチャーが 20 分以上動作しています — gpu-apply.log を確認してください",
        "zh": "启动器运行已超过 20 分钟 — 请查看 gpu-apply.log"},
    " (code %s)": {"ja": " (コード %s)", "zh": " (代码 %s)"},
    "invalid value": {"ja": "無効な値です", "zh": "无效的值"},
    "invalid GPU list": {"ja": "GPU リストが無効です", "zh": "无效的 GPU 列表"},
    "\"models\" must be an object": {"ja": "\"models\" はオブジェクトである必要があります", "zh": "\"models\" 必须是对象"},
    "unknown model": {"ja": "不明なモデルです", "zh": "未知的模型"},
    "invalid Content-Length": {"ja": "Content-Length が無効です", "zh": "无效的 Content-Length"},
    "request body too large": {"ja": "リクエスト本文が大きすぎます", "zh": "请求体过大"},
    "expected {\"models\": {...}}": {"ja": "{\"models\": {...}} の形式が必要です", "zh": "需要 {\"models\": {...}} 格式"},
    "a restart is running — wait for it to finish, then save again": {
        "ja": "再起動が進行中です — 完了を待ってからもう一度保存してください",
        "zh": "正在重启 — 请等待完成后再保存"},
    "invalid GPU choice: %s": {"ja": "無効な GPU の選択です: %s", "zh": "无效的 GPU 选择：%s"},
    "could not write %s": {"ja": "%s に書き込めませんでした", "zh": "无法写入 %s"},
    "could not start the launcher": {"ja": "ランチャーを起動できませんでした", "zh": "无法启动启动器"},
    "a restart is already running": {"ja": "再起動はすでに進行中です", "zh": "已经在重启中"},
    "could not read the GPU data": {"ja": "GPU の情報を読み取れませんでした", "zh": "无法读取 GPU 数据"},
    # project memory
    "the memory file is locked right now; try again": {"ja": "メモリーファイルは現在ロックされています。もう一度お試しください",
                                                        "zh": "记忆文件当前被锁定，请重试"},
    "memory.json is unreadable (malformed) — not overwriting it; fix the file first": {
        "ja": "memory.json を読み取れません（形式が壊れています） — 上書きはしません。先にファイルを修正してください",
        "zh": "memory.json 无法读取（格式损坏） — 不会覆盖它，请先修复该文件"},
    "the memory file kept changing underneath; try again": {"ja": "メモリーファイルが同時に何度も変更されました。もう一度お試しください",
                                                             "zh": "记忆文件被同时频繁修改，请重试"},
    "text is required": {"ja": "text は必須です", "zh": "需要 text"},
    "text is empty": {"ja": "テキストが空です。記憶するものがありません", "zh": "文本为空，没有可记住的内容"},
    "text is longer than %d characters": {"ja": "テキストが %d 文字を超えています", "zh": "文本超过 %d 个字符"},
    "kind must be one of %s": {"ja": "kind は %s のいずれかである必要があります", "zh": "kind 必须是 %s 之一"},
    "tags must be a list of strings": {"ja": "tags は文字列のリストである必要があります", "zh": "tags 必须是字符串列表"},
    "a tag is longer than %d characters": {"ja": "タグが %d 文字を超えています", "zh": "有标签超过 %d 个字符"},
    "more than %d tags": {"ja": "タグが %d 個を超えています", "zh": "标签超过 %d 个"},
    "pinned must be true or false": {"ja": "pinned は true か false である必要があります", "zh": "pinned 必须是 true 或 false"},
    "Not saved: the text looks like it contains a secret (password, key or token). Project memory is added to every "
    "chat, so keep secrets elsewhere.": {
        "ja": "保存しませんでした: テキストに秘密情報（パスワード、キー、トークン）が含まれているようです。プロジェクトメモリーは"
              "すべてのチャットに追加されるため、秘密情報は別の場所に保管してください。",
        "zh": "未保存：文本看起来包含机密（密码、密钥或令牌）。项目记忆会添加到每个对话中，请把机密放在别处。"},
    "invalid id": {"ja": "id が無効です", "zh": "无效的 id"},
    "no such memory entry (maybe deleted)": {"ja": "そのメモリー項目はありません（削除された可能性があります）",
                                             "zh": "没有这条记忆（可能已被删除）"},
    "memory is full (%d entries); delete old ones first": {"ja": "メモリーがいっぱいです（%d 件）。先に古いものを削除してください",
                                                            "zh": "记忆已满（%d 条），请先删除旧条目"},
    "nothing to change (text, kind, tags, pinned)": {"ja": "変更する項目がありません (text, kind, tags, pinned)",
                                                     "zh": "没有可更改的内容 (text, kind, tags, pinned)"},
    "could not read or write the memory file": {"ja": "メモリーファイルを読み書きできませんでした", "zh": "无法读写记忆文件"},
    # research jobs
    "invalid job id": {"ja": "ジョブ ID が無効です", "zh": "无效的任务 id"},
    "research job not found": {"ja": "リサーチジョブが見つかりません", "zh": "未找到研究任务"},
    "this job is not running": {"ja": "このジョブは実行中ではありません", "zh": "此任务未在运行"},
    "could not cancel — try again": {"ja": "キャンセルできませんでした — もう一度お試しください", "zh": "无法取消 — 请重试"},
    "could not read the research jobs": {"ja": "リサーチジョブを読み取れませんでした", "zh": "无法读取研究任务"},
    # speech to text
    "the local services token is missing — run the Qwen3.8 launcher again": {
        "ja": "ローカルサービスのトークンがありません — Qwen3.8 ランチャーをもう一度実行してください",
        "zh": "缺少本地服务令牌 — 请再次运行 Qwen3.8 启动器"},
    "transcription took too long — try a shorter recording": {"ja": "文字起こしに時間がかかりすぎました — 短い録音でお試しください",
                                                               "zh": "转写耗时过长 — 请试试更短的录音"},
    "the speech-to-text service is not running — run the Qwen3.8 launcher again": {
        "ja": "音声認識サービスが動作していません — Qwen3.8 ランチャーをもう一度実行してください",
        "zh": "语音转文字服务未运行 — 请再次运行 Qwen3.8 启动器"},
    "the speech-to-text service sent a bad reply": {"ja": "音声認識サービスから不正な応答がありました", "zh": "语音转文字服务返回了错误的响应"},
    "the speech-to-text service rejected the token — run the Qwen3.8 launcher again": {
        "ja": "音声認識サービスがトークンを拒否しました — Qwen3.8 ランチャーをもう一度実行してください",
        "zh": "语音转文字服务拒绝了令牌 — 请再次运行 Qwen3.8 启动器"},
    "the recording is too long or too large": {"ja": "録音が長すぎるか大きすぎます", "zh": "录音过长或过大"},
    "the speech-to-text service is busy — try again shortly": {"ja": "音声認識サービスが混み合っています — しばらくしてからお試しください",
                                                                "zh": "语音转文字服务忙 — 请稍后再试"},
    "speech-to-text is not available right now (no model ready) — try again shortly": {
        "ja": "音声認識は現在利用できません（モデルが準備できていません） — しばらくしてからお試しください",
        "zh": "语音转文字当前不可用（没有就绪的模型） — 请稍后再试"},
    "could not transcribe this audio": {"ja": "この音声を文字起こしできませんでした", "zh": "无法转写这段音频"},
    "the speech-to-text service failed": {"ja": "音声認識サービスでエラーが発生しました", "zh": "语音转文字服务出错"},
    "expected audio/* or multipart/form-data": {"ja": "audio/* または multipart/form-data が必要です",
                                                "zh": "需要 audio/* 或 multipart/form-data"},
    "no audio received": {"ja": "音声が受信されていません", "zh": "未收到音频"},
    "audio larger than %d MB": {"ja": "音声が %d MB を超えています", "zh": "音频超过 %d MB"},
    # compaction of long chats
    # the English plural suffix (%s = "" or "s") has no place in ja/zh: the translation keeps only the number
    "Summarizing the earlier part of this chat… (%d turn%s)": {"ja": "このチャットの前半を要約しています… (%d ターン)",
                                                                 "zh": "正在总结这段对话的前半部分… (%d 轮)"},
    "This chat is longer than the model can read at once, so its first %d turns are being condensed into a short "
    "summary before the reply (up to about %d s). Nothing on screen is lost.": {
        "ja": "このチャットはモデルが一度に読める長さを超えているため、最初の %d ターンを短い要約にまとめてから回答します"
              "（最大およそ %d 秒）。画面上の内容は失われません。",
        "zh": "这段对话超过了模型一次能读取的长度，因此会先把前 %d 轮压缩成简短摘要再回答（最多约 %d 秒）。屏幕上的内容不会丢失。"},
    "Summarized the earlier part of this conversation (%d turn%s)": {"ja": "この会話の前半を要約しました (%d ターン)",
                                                                      "zh": "已总结这段对话的前半部分 (%d 轮)"},
    "This chat grew past what the model can read at once, so its first %d turns were condensed into a short summary "
    "for the model (everything on screen is unchanged). Your first message and the latest turns are still sent in "
    "full.": {
        "ja": "このチャットはモデルが一度に読める長さを超えたため、最初の %d ターンをモデル向けの短い要約にまとめました"
              "（画面上の内容は変わりません）。最初のメッセージと直近のターンは引き続きそのまま送られます。",
        "zh": "这段对话超过了模型一次能读取的长度，因此已把前 %d 轮压缩成给模型看的简短摘要（屏幕上的内容不变）。"
              "你的第一条消息和最近几轮仍会完整发送。"},
    "No summary for this chat yet (or the hub restarted — send the next message first)": {
        "ja": "このチャットの要約はまだありません（またはハブが再起動しました — 先に次のメッセージを送ってください）",
        "zh": "这段对话还没有摘要（或者 Hub 已重启 — 请先发送下一条消息）"},
    "The chat will be condensed when you send the next message": {"ja": "次のメッセージを送るとチャットが要約されます",
                                                                   "zh": "发送下一条消息时将压缩这段对话"},
    "bad conversation id": {"ja": "チャット ID が無効です", "zh": "无效的对话 id"},
    "missing conversation id": {"ja": "チャット ID がありません", "zh": "缺少对话 id"},
    "expected JSON {\"conversation\": \"<id>\"}": {"ja": "JSON {\"conversation\": \"<id>\"} が必要です",
                                                   "zh": "需要 JSON {\"conversation\": \"<id>\"}"},
    # generic HTTP
    "method not allowed": {"ja": "このメソッドは使えません", "zh": "不支持该方法"},
    "not found": {"ja": "見つかりません", "zh": "未找到"},
    "file not found": {"ja": "ファイルが見つかりません", "zh": "未找到文件"},
    "cannot open file": {"ja": "ファイルを開けません", "zh": "无法打开文件"},
    "expected Content-Type: application/json": {"ja": "Content-Type: application/json が必要です",
                                                 "zh": "需要 Content-Type: application/json"},
    "expected a JSON object": {"ja": "JSON オブジェクトが必要です", "zh": "需要 JSON 对象"},
    "invalid request body": {"ja": "リクエスト本文が無効です", "zh": "无效的请求体"},
    "could not read the usage log": {"ja": "使用状況の記録を読み取れませんでした", "zh": "无法读取用量记录"},
    "the system check failed": {"ja": "システムチェックに失敗しました", "zh": "系统检查失败"},
    "could not save settings": {"ja": "設定を保存できませんでした", "zh": "无法保存设置"},
    "auto_kb must be true or false": {"ja": "auto_kb は true か false である必要があります", "zh": "auto_kb 必须是 true 或 false"},
    "this request is larger than %d MB (usually several large images in one chat) - resize the images or start a new "
    "chat": {
        "ja": "このリクエストは %d MB を超えています（通常は 1 つのチャットに大きな画像が複数あるため） - 画像を縮小するか新しいチャットを"
              "始めてください",
        "zh": "此请求超过 %d MB（通常是一个对话里有多张大图） - 请缩小图片或开始新对话"},
}

# fields that come in th/en pairs — "<name>_th" / "<name>_en"
PAIRED_FIELDS = ("error", "message", "note", "tooltip", "phase")

_TEMPLATES = None


def _templates():
    """(regex, english template) for every catalog entry with a %d / %s — compiled once."""
    global _TEMPLATES
    if _TEMPLATES is None:
        import re
        out = []
        for en in API_TEXTS:
            if "%" not in en:
                continue
            pat = re.escape(en).replace("%d", r"(-?\d+)").replace("%s", r"(.*?)")
            out.append((re.compile("^" + pat + "$", re.S), en))
        _TEMPLATES = out
    return _TEMPLATES


def translate_api(en_text, lang):
    """The ja/zh version of an English API text, or None when the catalog has no entry for it.

    Exact texts are looked up directly; texts made from a template ("audio larger than 64 MB") are matched against
    the template and the numbers/words are carried into the translation.
    """
    if lang not in CJK_LANGS or not isinstance(en_text, str) or not en_text:
        return None
    hit = API_TEXTS.get(en_text)
    if hit is not None:
        return hit.get(lang)
    for rx, tpl in _templates():
        m = rx.match(en_text)
        if m:
            tr_tpl = API_TEXTS[tpl].get(lang)
            if not tr_tpl:
                return None
            # a translation may use fewer placeholders than the English (no plural "s" in ja/zh): extra groups
            # are dropped from the end; numbers go back to int so %d formats them
            import re
            n = len(re.findall(r"%[sd]", tr_tpl))
            args = []
            for g in m.groups()[:n]:
                if re.fullmatch(r"-?\d+", g or ""):
                    args.append(int(g))
                else:
                    # "invalid GPU choice: <model>: unknown model" — the inner text may be a catalog text itself
                    inner = g.split(": ", 1) if g else [g]
                    tail = translate_api(inner[-1], lang) if len(inner) > 1 else None
                    args.append(inner[0] + ": " + tail if tail else (translate_api(g, lang) or g))
            args = tuple(args)
            try:
                return tr_tpl % args
            except (TypeError, ValueError):
                return None
    return None


def localize_fields(obj, depth=4):
    """Add <field>_ja / <field>_zh next to every <field>_en the reply has, when the catalog knows the text.

    Walks dicts and lists up to ``depth`` levels (the doctor report nests checks in groups). Mutates and returns
    ``obj``. Fields that already exist are kept — a module that writes its own translations wins.
    """
    if depth < 0:
        return obj
    if isinstance(obj, list):
        for item in obj:
            localize_fields(item, depth - 1)
        return obj
    if not isinstance(obj, dict):
        return obj
    for name in PAIRED_FIELDS:
        en = obj.get(name + "_" + FALLBACK_LANG)
        if not isinstance(en, str) or not en:
            continue
        for code in CJK_LANGS:
            key = name + "_" + code
            if obj.get(key):
                continue
            t = translate_api(en, code)
            if t:
                obj[key] = t
    for v in obj.values():
        if isinstance(v, (dict, list)):
            localize_fields(v, depth - 1)
    return obj


def paired(name, lang, th, en, **more):
    """A dict with <name>_th/_en (+ _ja/_zh when known) and ``name`` itself set to the text for ``lang``."""
    out = {name + "_th": th, name + "_en": en}
    for code in CJK_LANGS:
        t = more.get(code) or translate_api(en, code)
        if t:
            out[name + "_" + code] = t
    out[name] = pick({"th": th, "en": en, "ja": out.get(name + "_ja"), "zh": out.get(name + "_zh")}, lang)
    return out
