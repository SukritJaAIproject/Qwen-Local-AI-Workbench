# `C:\LLM\secrets` — local secrets (never committed)

Everything in this folder except this README is ignored by git. The model's tools cannot read or write
this folder: `mcp-local/guard.py` blocks it for every tool, even after the user approves a command.

| File | Created by | What it is |
|---|---|---|
| `local-services.token` | the launcher (`secrets_util.py --ensure`) on first start | 64 hex characters, one line, no BOM. The bearer token shared by the local services: llama-server router (`--api-key-file`), embedding server, both MCP servers, STT. The hub adds it to its own upstream requests and hands it to the chat page for MCP calls. Delete it to rotate; the launcher creates a new one and restarts what needs it. |
| `brave-search.key` | you (optional) | Your Brave Search API key, one line. The web-search MCP reads it on every search, so no restart is needed. Without it, web search falls back to Wikipedia + DuckDuckGo instant answers. |

Related secrets that live elsewhere:

- **Remote prompt gateway key** (`mcp-local/gateway.py`, port 8780): set the `GATEWAY_API_KEY` user
  environment variable. The fallback file `mcp-local/gateway_key.txt` is also git-ignored.
- **Other search providers** (`tavily`, `serper`): `mcp-websearch/config.json` (git-ignored; start from
  `config.example.json`).

Never paste key values into chats, project instructions, issues or logs. The services, the doctor page and the
usage log only ever report whether a key file exists.

## Lock the folder down (do this yourself)

By default the folder inherits the permissions of `C:\`, which lets every account on the machine read it.
The launcher only warns about this; it does not change file-system permissions for you. In an elevated
PowerShell (replace `<you>` with your Windows user name):

```powershell
icacls "C:\LLM\secrets" /inheritance:r /grant:r "<you>:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"
```
