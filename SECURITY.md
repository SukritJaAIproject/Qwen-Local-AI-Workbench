# Security policy

## Reporting a vulnerability

Please do not report security problems in a public issue. Report them privately through GitHub instead:
**Security → [Report a vulnerability](https://github.com/SukritJaAIproject/Qwen-Local-AI-Workbench/security/advisories/new)**.
Thai or English is fine.

Say what you found, how to reproduce it, and which release or commit you tested. The maintainer aims to reply within a week.

The areas that matter most are the tool guard and two-step confirmation (`mcp-local/guard.py`), the local token and router authentication, path checks in the file tools, and anything that sends data off `127.0.0.1`.

## Supported versions

Fixes go into `main` and the next release. Only the latest release is supported.
