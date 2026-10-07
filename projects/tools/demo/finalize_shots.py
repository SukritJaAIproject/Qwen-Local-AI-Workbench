# -*- coding: utf-8 -*-
"""Re-encode the chosen screenshots without metadata into docs/screenshots (PNG; palette fallback if > 400 KB)."""
import os

from PIL import Image

WORK = os.path.dirname(os.path.abspath(__file__))
# repo layout: <root>/projects/tools/demo/finalize_shots.py -> <root>/docs/screenshots
OUT = os.environ.get("QWEN_SHOTS_OUT") or os.path.normpath(os.path.join(WORK, "..", "..", "..", "docs", "screenshots"))
LIMIT = 400 * 1024

PICK = [
    ("raw/01-chat-en-dark.png", "01-chat-en-dark.png"),
    ("raw/02-start-en-light.png", "02-start-en-light.png"),
    ("raw/03-artifact-panel-en-light.png", "03-artifact-panel-en-light.png"),
    ("raw/04-project-panel-en-dark.png", "04-project-panel-memory-en-dark.png"),
    ("raw/04b-project-files-en-dark.png", "05-project-files-research-en-dark.png"),
    ("raw/05a-usage-30d-en-light.png", "06-usage-dashboard-en-light.png"),
    ("raw/05b-usage-speed-en-light.png", "07-usage-speed-en-light.png"),
    ("raw/06-doctor-en-dark.png", "08-doctor-en-dark.png"),
    ("raw/07-gpu-picker-en-dark.png", "09-gpu-picker-en-dark.png"),
    ("raw/08-account-menu-en-light.png", "10-account-menu-en-light.png"),
    ("raw/09-chat-th-dark.png", "11-chat-th-dark.png"),
    # captured during the security acceptance run (synthetic print(1+1) request); skipped when absent
    (r"C:\LLM\projects\tools\shots\e2e-s3-02-a-card2-token-only-server-review.jpg", "12-confirm-card-th.png"),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    for src, name in PICK:
        p = src if os.path.isabs(src) else os.path.join(WORK, src)
        if not os.path.isfile(p):
            print("skip (missing):", src)
            continue
        im = Image.open(p)
        im.load()
        clean = Image.new("RGB", im.size)
        clean.paste(im.convert("RGB"))          # pixels only: no text chunks, EXIF, ICC or timestamps
        dst = os.path.join(OUT, name)
        clean.save(dst, "PNG", optimize=True)
        if os.path.getsize(dst) > LIMIT:
            clean.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(
                dst, "PNG", optimize=True)
        chk = Image.open(dst)
        print("%-42s %4dx%-4d %6.1f KB  info=%s" % (name, chk.size[0], chk.size[1], os.path.getsize(dst) / 1024,
                                                   sorted(chk.info.keys())))


if __name__ == "__main__":
    main()
