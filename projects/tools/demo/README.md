# Demo data and README screenshots

The screenshots in `docs/screenshots` (all but `12-confirm-card-th.png`) are taken from a throw-away copy of the
hub that runs on spare ports with **synthetic data only** (made-up projects, chats, files, usage numbers and a
simulated GPU list). Nothing here touches the real hub on 8100, the real `projects/data`, or your settings.
`12-confirm-card-th.png` is copied by `finalize_shots.py` from an earlier test run (a `print(1+1)` call) when that
image is present; the demo hub hides the MCP servers, so it cannot show a confirmation card.

```powershell
cd C:\LLM\projects\tools\demo
C:\Python313\python.exe make_demo_data.py          # fixtures/, data/, projects.json, settings.json, gpu/
C:\Python313\python.exe demo_hub.py --minutes 30   # API on 8171, demo projects on 8172-8174
# in a second terminal
C:\Python313\python.exe shots.py                    # raw/*.png (one headless Edge, temp profile in .\tmp)
C:\Python313\python.exe finalize_shots.py           # re-encode without metadata -> ..\..\..\docs\screenshots
```

How the demo hub stays harmless:

- `hub.py` is imported as a module with `DATA_ROOT`, `projects.json` and `settings.json` pointed at this folder.
- GPUs are simulated (`QWEN_GPU_SIMULATE`: RTX 1000 Ada + RTX 4090); "apply" is a dry run (`QWEN_GPU_DRYRUN=1`).
- The doctor report is built by the real `hub_doctor` code from synthetic probe results (no live probes, no logs).
- The upstream is a fake llama-server: `GET` requests are relayed to the router on 8099 only to serve the WebUI files
  and the model list. Requests that name a model are refused, so no model is ever loaded, and chat requests are refused.
- MCP servers are hidden from the page, so no token is written into it.

Everything this folder generates is git-ignored. Stop the demo hub by creating a file named `STOP` here.
