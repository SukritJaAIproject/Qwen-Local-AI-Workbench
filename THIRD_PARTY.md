# Third-party components

The code in this repository is MIT-licensed (see [LICENSE](LICENSE)). It runs on top of, or talks to,
the components below. **None of them are bundled here** except the two font families listed under
"Included". Each one keeps its own license; please read it before you redistribute a full setup.

## Included in this repository

| Component | Where | License |
|---|---|---|
| Source Serif 4 (Adobe), WOFF2 web subsets | `projects/static/fonts/SourceSerif4-*.woff2` | SIL Open Font License 1.1 — notice in [`projects/static/fonts/OFL.txt`](projects/static/fonts/OFL.txt) |
| Noto Serif Thai (The Noto Project Authors), WOFF2 web subsets | `projects/static/fonts/NotoSerifThai-*.woff2` | SIL Open Font License 1.1 — same file |

The UI also asks the browser for *Leelawadee UI* (a Windows system font) by name. That font is not included.

## Runtime dependencies (installed separately)

| Component | Used for | License |
|---|---|---|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) (`llama-server`, built-in WebUI), build b10984, Windows CUDA 12.4 | model router, embedding server, the chat WebUI that this project re-themes | MIT |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) 5.4 + `tessdata_best` (tha, eng) | OCR of scanned PDFs and images | Apache-2.0 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [CTranslate2](https://github.com/OpenNMT/CTranslate2), [PyAV](https://github.com/PyAV-Org/PyAV) | speech-to-text service | MIT, MIT, BSD-3-Clause |
| Whisper large-v3-turbo weights (CTranslate2 conversion) | speech-to-text model | MIT (OpenAI Whisper) — check the converted model's card |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) (`fitz`) | PDF text extraction and page rendering for OCR | **AGPL-3.0** or commercial license from Artifex |
| [python-docx](https://github.com/python-openxml/python-docx), [openpyxl](https://foss.heptapod.net/openpyxl/openpyxl) | reading/writing DOCX and XLSX | MIT |
| [defusedxml](https://github.com/tiran/defusedxml), [NumPy](https://numpy.org), [Pillow](https://python-pillow.org) | safe XML parsing, vectors for semantic search, images | PSF-2.0, BSD-3-Clause, MIT-CMU (HPND) |
| [jupyter_client](https://github.com/jupyter/jupyter_client) / ipykernel, pandas, matplotlib, plotly (Anaconda) | per-project Python interpreter tool | BSD-3-Clause, BSD-3-Clause, PSF-based (matplotlib), MIT |
| [pywin32](https://github.com/mhammond/pywin32), [psutil](https://github.com/giampaolo/psutil) | Office bridge (COM) and process checks | PSF-2.0, BSD-3-Clause |
| Microsoft Edge (Chromium) | headless screenshot harness and the isolated browser tool | proprietary (Microsoft) |
| Microsoft Office (optional) | live Excel / Word / PowerPoint bridge | proprietary (Microsoft) |
| FFmpeg (optional) | media tools (trim, resize, GIF, extract audio) | LGPL-2.1+ or GPL, depending on the build you install |

## Models (not included)

No model weights are part of this repository. The setup was built and measured with GGUF files of:

- Qwen3.8-27B (UD-Q4_K_M) with its vision projector (mmproj F16)
- Qwen3-4B-Instruct-2507 (Q4_K_M)
- Qwen3-Coder-30B-A3B-Instruct (UD-Q4_K_XL)
- gpt-oss-20b (MXFP4)
- Qwen3-Embedding-0.6B (Q8_0) for semantic search

Every model has its own license and acceptable-use terms, published on its model card. Many Qwen3-family
and gpt-oss open-weight releases use Apache-2.0, but do not assume it: check the card of the exact file you
download, including the terms of whoever produced the GGUF quantization.

## Trademarks

This is an independent personal project, not affiliated with or endorsed by any of the projects or companies
named above. Qwen, gpt-oss, llama.cpp, Windows, Office, Edge and the other names are trademarks of their
respective owners and are used only to describe what this software works with.
