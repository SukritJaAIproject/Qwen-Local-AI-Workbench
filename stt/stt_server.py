# -*- coding: utf-8 -*-
"""stt_server.py — บริการถอดเสียงพูดเป็นข้อความในเครื่อง (batch 2b สัญญา C1, owner voice)

รันด้วย python ของ conda env "flexxfast" (มี faster-whisper 1.2.x + ctranslate2 + PyAV ครบ ไม่ต้องติดตั้งเพิ่ม):
    %USERPROFILE%\\anaconda3\\envs\\flexxfast\\python.exe -X utf8 C:\\LLM\\stt\\stt_server.py --port 8795

API (127.0.0.1 เท่านั้น)
  GET  /health          ไม่ต้องใช้ token — {"status":"ok","server":"qwen-stt","state":..,"ready":..,"available":..,
                        "device": cuda|cpu|"" (โมเดลที่โหลดอยู่), "parked": bool}
                        state = loading | ready | idle (ปลดโมเดลตอนว่าง โหลดใหม่เองเมื่อมีงาน) | no_model | error
  GET  /v1/status       ต้องใช้ token — โมเดล อุปกรณ์ เวลาเฉลี่ย คิว เพดาน, parked (โมเดล GPU จอดใน RAM อยู่ = ยัง ready)
                        + expect_device (cuda|cpu ที่งานถัดไปจะได้) + window_s (วินาทีต่อหน้าต่างเสียง 30 วิ ต่ออุปกรณ์)
  POST /v1/transcribe   ต้องใช้ token — body เป็นไฟล์เสียงดิบ (Content-Type audio/* หรือ application/octet-stream)
                        หรือ multipart/form-data (ส่วน file/audio + ช่อง language/hint ถ้ามี)
                        query: language=th|en|auto (ค่าเริ่มต้น auto) · hint=th|en (ภาษาของหน้าจอผู้ใช้ — ใช้เฉพาะตอน
                        ตรวจภาษาเองแล้วไม่แน่ใจ) · max_seconds=<ลดเพดานเองได้>
                        -> {"text", "language", "language_probability", "duration", "segments":[{start,end,text}],
                            "model", "device", "elapsed_s", "detected"?}
  POST /v1/warm         ต้องใช้ token — เตรียมโมเดลล่วงหน้า (hub เรียกตอนผู้ใช้เริ่มอัดเสียง) ไม่รอ: {"state","action"}
  ชนิดไฟล์: webm/opus (MediaRecorder ของเบราว์เซอร์), ogg/opus, wav, mp3, m4a/mp4 (AAC), flac, aac (ADTS)

ทำไมออกแบบแบบนี้ (วัดจริงบนเครื่องนี้ 2026-10-01, เสียงสังเคราะห์ Microsoft Pattara/Zira 11-32 วินาที)
  * โมเดล: มีในเครื่องแค่ faster-whisper-small กับ large-v3-turbo (แคช HF บนดิสก์ USB E:) — turbo ภาษาไทยดีกว่ามาก
    (CER 0.20-0.27 เทียบ small 0.31-0.48, อังกฤษเท่ากัน WER ~0.1 ที่ต่างกันแค่ตัวเลขเขียนเป็นคำ/ตัวเลข) จึงใช้ turbo เป็นหลัก
  * อุปกรณ์: GPU (int8_float16, VRAM ~1.2 GB) ถอด 11-12 วินาทีใน ~1.0-1.4 วินาที; CPU int8 ช้ากว่า ~20 เท่า
    (~20-26 วินาทีต่อหน้าต่าง 30 วินาที เพราะ encoder ของ turbo ใหญ่ และเครื่องถูกจำกัดกำลัง) — ใช้ GPU เฉพาะเมื่อ
    VRAM ว่าง >= 1.5 GB ตอนโหลด (สัญญา C1) ไม่งั้น CPU int8 · 4 เธรด (8 เธรดไม่เร็วขึ้น) · CPU ใช้ beam 1 (ความแม่นเท่า beam 5
    ในชุดวัด แต่เร็วกว่า 10-15%) GPU ใช้ beam 5 (ต่างกันไม่ถึง 0.1 วินาที)
  * หน่วยความจำ (private bytes ของโปรเซส วัดจริง): ก่อนโหลดโมเดล ~0.7 GB, turbo บน GPU ~2.7 GB (+VRAM ~1.2 GB),
    บน CPU ~4.0 GB — เดิม import ctranslate2 ลาก torch+transformers มาด้วย (79 วินาที, +0.9 GB) จึงบล็อกสองตัวนั้นไว้
    (ดูข้างล่าง) เครื่องนี้หน่วยความจำใช้ร่วมกับ LLM จึงปลดโมเดลเมื่อว่างเกิน --idle-unload-min นาที (ค่าเริ่มต้น 15)
    — ปลดแล้ว VRAM คืนเหลือ ~90 MB (CUDA context); งานถัดไปโหลดใหม่ (~6 วินาทีจากแคชไฟล์ของ Windows, ~20 วินาทีจาก USB
    เย็นๆ) และเลือกอุปกรณ์ใหม่ตาม VRAM ตอนนั้น (LLM โหลดเต็ม VRAM อยู่ = ได้ CPU)
  * จอดโมเดลไว้ใน RAM หลังงาน GPU (วัดจริง 2026-10-06): router เปิด llama-server ด้วย -fit on = จัดจำนวนชั้นบน GPU ตาม
    VRAM ที่ว่าง "ตอนโหลดโมเดลแชต" ครั้งเดียว ไม่ขยายคืนทีหลัง ถ้า STT ถือ VRAM ~1.1 GB ค้างไว้ตอนนั้น (เช่น ผู้ใช้พูด
    ข้อความแรกด้วยไมค์แล้วกดส่ง) โมเดลแชตจะได้ชั้นบน GPU น้อยลงไปทั้ง session — จึงย้ายน้ำหนักไป RAM หลังงานเสร็จ
    --gpu-hold-s วินาที (unload_model(to_cpu=True) 0.5 วิ, ใช้ RAM เท่าเดิม ~2.6 GB, VRAM คืนเหลือ ~90 MB) แล้วงานถัดไป
    ตรวจ VRAM ใหม่ทุกครั้ง: ว่าง >= 1.5 GB = ย้ายกลับ GPU 0.25 วิ (ไม่ต้องอ่านไฟล์ใหม่ 4.5 วิ), ไม่พอ (โมเดลแชตใช้อยู่ เช่น
    27B) = ใช้ CPU, CPU อยู่แล้วแต่ VRAM กลับมาว่าง = สลับขึ้น GPU (โหลดเต็ม ~4.5 วิ แต่งานเร็วขึ้น ~15 เท่า)
    วัดกับ router ทดสอบที่โหลด Qwen3-4B (-fit, ctx 32K): VRAM เหลือว่าง 1,839 MB -> STT ใช้ GPU ร่วมกับ 4B ได้
    ส่วนการปลดเต็ม/โหลดใหม่ทุกงานรั่ว VRAM ~8 MB ต่อรอบ (ctranslate2) แต่การจอด/ย้ายกลับไม่รั่ว
  * GPU ต้องใช้ cuBLAS ของ CUDA 12 ที่ wheel ของ ctranslate2 ไม่แถมมา และเครื่องนี้ไม่มี CUDA Toolkit — โหลด DLL จาก
    torch\\lib ของ env เดียวกันด้วย path เต็ม (prepare_cuda) โดยไม่ import torch; หาไม่เจอ = CPU
  * เปิด VAD เสมอ (Silero ที่มากับ faster-whisper ไม่ต้องดาวน์โหลด) ตัดช่วงเงียบ = กัน whisper แต่งประโยคเอง ("ขอบคุณที่รับชม")
    และ condition_on_previous_text=False กันวนซ้ำ; โหมดตรวจภาษาเอง: 30 วินาทีแรกเป็นไทย = ล็อกไทย (โหมดไทยถอดประโยค
    อังกฤษได้ถูก) ไม่ใช่ไทยและยาวกว่า 30 วินาที = ถอดแบบ multilingual (ตรวจภาษาใหม่ทุกหน้าต่าง) — ดู Engine._transcribe
  * จำกัดภาษาที่ตรวจได้เป็น --languages (th,en) (วัดจริง 2026-10-06 คำไทยสั้น 1-2 วิ เสียง Pattara 12 คำ): ตัวตรวจภาษาของ
    whisper ให้ไทยแทบเป็นศูนย์ (th <= 0.004 ทุกคำ) แล้วเดาเป็น vi/ja/ko/zh/ms 10 คำ ("โอเค" -> "OK"/"오케이", "ไม่ใช่" ->
    "Mời chạy.") และเป็นอังกฤษไม่มั่นใจ 2 คำ ("ครับ" -> "Crap." en 0.75, "ไม่" -> "Bye." en 0.63) ส่วนคำอังกฤษสั้น 13 คำ
    ได้ en >= 0.965 ทุกคำ — จึงถอดใหม่เป็นภาษาสำรอง (hint จากหน้าจอ หรือ --primary-language) เมื่อผลตรวจอยู่นอกชุด หรือ
    เป็นอีกภาษาในชุดแต่ความน่าจะเป็น < 0.9 (คลิปสั้น) — บังคับไทยกับอังกฤษจริงก็ไม่ได้: โหมดไทยถอดคลิปอังกฤษ 4-11 วิ
    เป็นภาษาไทยมั่วๆ จึงไม่ "ล็อกไทยทุกครั้ง" (ดู choose_language)

ความปลอดภัย
  * ฟังเฉพาะ 127.0.0.1 · Host ต้องเป็น 127.0.0.1/localhost:<port> (กัน DNS rebinding) · Origin ถ้ามีต้องเป็นหน้าของเรา
    (secrets_util.check_request ชุดเดียวกับ MCP) · ทุกอย่างยกเว้น /health ต้องมี Bearer token ของบริการในเครื่อง
    ไม่ส่ง header CORS เลย: เบราว์เซอร์เรียกตรงไม่ได้ ทางของหน้าแชตคือ hub POST /_qwen/stt ที่ส่งต่อพร้อม token
  * ไม่มีเครือข่าย: ตั้ง HF_HUB_OFFLINE ก่อน import, โหลดโมเดลจาก path ในเครื่อง (local_files_only) และปิด
    socket.connect ไปที่อื่นนอกจาก loopback ทั้งโปรเซส (กันไลบรารีไหนแอบดาวน์โหลด/ส่งข้อมูลเสียงออก)
  * body จำกัด --max-bytes (25 MB) ปฏิเสธก่อนอ่าน, เสียงยาวเกิน --max-seconds (600) ปฏิเสธระหว่างถอดรหัส,
    ไม่รับ chunked, socket timeout 60 วินาที, คิวรอสูงสุด 3 งาน (เกิน = 503 + Retry-After)
  * ถอดรหัสไม่ขยายหน่วยความจำ (รอบแก้ 2026-10-06): อัตราสุ่ม 8-192 kHz และไม่เกิน 8 ช่อง ไม่งั้น 415 ก่อนแปลงอัตรา และคำนวณ
    ความยาวที่จะได้ "ก่อน" resample ทุกเฟรม (FLAC 8 KB อัตรา 16 Hz เคยขยายเป็น +1.25 GB ก่อนถึงเพดานเวลา, 1 Hz +2.0 GB)
    คำขอที่ถือ body ในหน่วยความจำพร้อมกันได้ไม่เกินจำนวนช่องคิว (เกิน = อ่านทิ้งแล้ว 503) และถอดรหัสพร้อมกันได้ 2 งาน
  * ถอดรหัสเสียงด้วย PyAV โดย "บอกชนิดไฟล์เอง" จาก magic bytes — ไม่ให้ ffmpeg เดาชนิดจากเนื้อไฟล์ (การเดาอาจเลือก
    demuxer แบบรายการเล่น เช่น HLS ที่ไปเปิดไฟล์/URL อื่นต่อ)
  * log ไม่มีเนื้อความที่ถอดได้และไม่มี token — มีแค่ขนาด ความยาว เวลา ภาษา อุปกรณ์
"""
from __future__ import annotations

import argparse
import gc
import glob
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

# ---- ปิดเน็ตของไลบรารีฝั่ง Hugging Face ก่อน import อะไรทั้งนั้น (faster_whisper import huggingface_hub ตอนโหลด)
for _k in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY",
           "DO_NOT_TRACK", "HF_HUB_DISABLE_IMPLICIT_TOKEN"):
    os.environ[_k] = "1"

# ---- กัน import torch/transformers: ctranslate2.converters.transformers ลอง import สองตัวนี้ตอน "import ctranslate2"
# (ใช้แค่ตอนแปลงโมเดล ไม่ใช่ตอนถอดเสียง) env flexxfast มีทั้งคู่ -> import ctranslate2 ใช้ 79 วินาที และ commit 1.57 GB
# วัดจริง: บล็อกแล้วเหลือ 2.4 วินาที / 0.73 GB  (None ใน sys.modules = "ไม่มีโมดูลนี้" ตามกลไกของ importlib;
# ctranslate2 จับ ImportError อยู่แล้ว, huggingface_hub.find_spec ได้ None = ถือว่าไม่ได้ติดตั้ง)
for _m in ("torch", "transformers", "tensorflow", "torchaudio", "torchvision", "jax", "flax"):
    sys.modules.setdefault(_m, None)

HERE = os.path.dirname(os.path.abspath(__file__))
LLM_ROOT = os.path.dirname(HERE)
# secrets_util อยู่ที่ C:\LLM — ต่อท้าย sys.path (ไม่แทรกหน้า กันชื่อไปทับ stdlib) เหมือนบริการอื่นของสแตก
if LLM_ROOT not in sys.path:
    sys.path.append(LLM_ROOT)
import secrets_util  # noqa: E402

SERVER_NAME = "qwen-stt"
VERSION = "1.0"
HOST = "127.0.0.1"
DEFAULT_PORT = 8795
SAMPLE_RATE = 16000
MAX_BYTES_DEFAULT = 25 * 1024 * 1024       # ไมค์ 10 นาที webm/opus ~2-5 MB, wav 16 kHz 2 นาที ~3.8 MB
MAX_SECONDS_DEFAULT = 600                  # คำขอเดียว; ไฟล์ยาวกว่านี้ MCP (tools_stt) ตัดเป็นท่อนละ 2 นาทีมาเอง
MIN_FREE_MB_DEFAULT = 1536                 # สัญญา C1: GPU เฉพาะเมื่อ VRAM ว่าง >= 1.5 GB ตอนโหลดโมเดล
IDLE_UNLOAD_MIN_DEFAULT = 15
GPU_HOLD_S_DEFAULT = 2.0                   # วินาทีหลังงาน GPU ก่อนจอดน้ำหนักไว้ใน RAM (ท่อนถัดไปของ MCP มาใน ~1 วิ)
IDLE_TICK_S = 1.0                          # รอบตรวจของเธรดว่าง (แค่เทียบเวลา ไม่มีงานหนัก)
THREADS_DEFAULT = 4                       # วัดแล้ว 8 เธรดไม่เร็วขึ้น (CPU ถูกจำกัดกำลัง) และแย่ง P-core กับ llama.cpp
QUEUE_MAX = 3                              # งานที่รอได้นอกเหนือจากงานที่กำลังถอด
QUEUE_WAIT = 300.0                         # วินาทีที่งานหนึ่งยอมรอคิว (CPU: งาน 10 นาทีใช้ ~5-6 นาที)
DECODE_BUDGET = 60.0                       # วินาทีสูงสุดของการถอดรหัสไฟล์เสียงหนึ่งไฟล์ (ก่อนเข้าโมเดล)
SOCKET_TIMEOUT = 60
LANG_RE = re.compile(r"^[a-z]{2,3}$")
PRIMARY_LANGUAGE_DEFAULT = "th"            # ภาษาหลักของผู้ใช้เครื่องนี้ — ดูเหตุผลที่ Engine._transcribe
# ---- [fix 2026-10-06 voice] ภาษาที่ตรวจเองได้ / เพดานการถอดรหัส / เวลาต่อหน้าต่าง (เหตุผลอยู่หัวไฟล์)
LANGUAGES_DEFAULT = ("th", "en")           # สัญญา C1: ไทย + อังกฤษ ตรวจเอง — ผลตรวจนอกชุดนี้ = ถอดใหม่เป็นภาษาสำรอง
LANG_SURE = 0.9                            # คลิปสั้น: อีกภาษาในชุดต้องมั่นใจ >= นี้ (อังกฤษจริง >= 0.965, ไทยที่เพี้ยน <= 0.75)
SHORT_CLIP_S = 30.0                        # หน้าต่างเดียวของ whisper — คลิปยาวกว่านี้ใช้กลยุทธ์ multilingual เดิม
MIN_RATE, MAX_RATE = 8000, 192000          # อัตราสุ่มที่รับ: ต่ำกว่า 8 kHz = แปลงขึ้น 16 kHz แล้วขยายหน่วยความจำได้ไม่จำกัด
MAX_CHANNELS = 8
DECODE_CONCURRENCY = 2                     # ถอดรหัสไฟล์พร้อมกันได้กี่งาน (หน่วยความจำใช้ร่วมกับ LLM)
DECODE_WAIT = 30.0                         # วินาทีที่รอคิวถอดรหัส ก่อนตอบ 503 busy
WARM_MAX_BODY = 4096
# วินาทีต่อ "หน้าต่าง 30 วินาที" ที่วัดจริง (2026-10-06, turbo): GPU 1-3 วิ, CPU int8 21-24 วิ (เครื่องว่าง) ถึง 45-54 วิ
# (มีงานอื่นแย่ง CPU) — ค่าเริ่มต้นก่อนมีงานจริง; หลังจากนั้นใช้ค่าเฉลี่ยเคลื่อนที่ของงานจริงบนเครื่องนี้ (hub/หน้าเว็บใช้บอกผู้ใช้)
WINDOW_S_DEFAULT = {"cuda": 2.0, "cpu": 24.0}
EXPECT_TTL = 5.0                           # วินาทีที่จำผล nvidia-smi ของ expect_device (/v1/status ถูกถามบ่อย)

# ชื่อโมเดล -> ชื่อโฟลเดอร์ในแคช Hugging Face (repo ที่แปลงเป็น CTranslate2 แล้ว) เรียงตามที่ควรลองก่อน
# large-v3-turbo กับ small วัดแล้ว (หัวไฟล์) ตัวอื่นเผื่อผู้ใช้วางไว้ภายหลัง ยังไม่ได้วัด
MODEL_REPOS = {
    "large-v3-turbo": ("models--mobiuslabsgmbh--faster-whisper-large-v3-turbo",
                       "models--deepdml--faster-whisper-large-v3-turbo-ct2",
                       "models--Systran--faster-whisper-large-v3-turbo"),
    "large-v3": ("models--Systran--faster-whisper-large-v3",),
    "medium": ("models--Systran--faster-whisper-medium",),
    "small": ("models--Systran--faster-whisper-small",),
    "base": ("models--Systran--faster-whisper-base",),
}
AUTO_ORDER = ("large-v3-turbo", "large-v3", "medium", "small", "base")
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")


def log(msg: str) -> None:
    """หนึ่งบรรทัดต่อเหตุการณ์ — launcher ส่ง stdout ไปที่ C:\\LLM\\logs\\stt.out.log (ห้ามมีข้อความที่ถอดได้/token)"""
    line = "%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:                          # noqa: BLE001 — log พังต้องไม่ล้มบริการ
        pass


# =============================================================== ไม่มีเครือข่าย
def _loopback(addr) -> bool:
    try:
        host = addr[0] if isinstance(addr, tuple) else addr
        if isinstance(host, bytes):
            host = host.decode("ascii", "ignore")
        if host in ("localhost",):
            return True
        return ipaddress.ip_address(str(host).split("%", 1)[0]).is_loopback
    except (ValueError, IndexError, TypeError):
        return False


def forbid_outbound() -> None:
    """ปิดการเชื่อมต่อออกนอกเครื่องทั้งโปรเซส — บริการนี้ไม่มีเหตุต้องต่อที่ไหนเลย (รับอย่างเดียว)
    ครอบ socket.connect/connect_ex: huggingface_hub, onnxruntime หรือไลบรารีอื่นที่อาจแอบดาวน์โหลด/ส่ง telemetry
    จะได้ OSError แทน ข้อมูลเสียงของผู้ใช้จึงออกนอกเครื่องไม่ได้แม้ไลบรารีมีบั๊ก"""
    orig_connect = socket.socket.connect
    orig_connect_ex = socket.socket.connect_ex
    if getattr(orig_connect, "_qwen_guard", False):
        return

    def connect(self, address):
        if self.family == getattr(socket, "AF_UNIX", -1) or _loopback(address):
            return orig_connect(self, address)
        raise OSError("qwen-stt: network access is disabled in this process")

    def connect_ex(self, address):
        if self.family == getattr(socket, "AF_UNIX", -1) or _loopback(address):
            return orig_connect_ex(self, address)
        return 10013                           # WSAEACCES

    connect._qwen_guard = True
    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex


# =============================================================== หาโมเดลในเครื่อง
def _model_ok(path: str) -> bool:
    """โฟลเดอร์โมเดลใช้ได้จริงไหม — ตรวจไฟล์จริง ไม่ใช่แค่ exists (junction ที่ชี้ไปดิสก์ USB ที่ถอดออกยังผ่าน exists)"""
    try:
        for name in MODEL_FILES:
            st = os.stat(os.path.join(path, name))
            if st.st_size <= 0:
                return False
        return os.stat(os.path.join(path, "model.bin")).st_size > 1024 * 1024
    except OSError:
        return False


def hub_roots() -> list[str]:
    """ที่ที่อาจมีแคช HF: ตัวแปรสภาพแวดล้อม (QWEN_STT_HF_HUB, HUGGINGFACE_HUB_CACHE, HF_HUB_CACHE, HF_HOME)
    แล้วค่อย ~/.cache/huggingface/hub — แคชที่ย้ายไปไว้ดิสก์อื่นให้ชี้ด้วย QWEN_STT_HF_HUB (ไม่เดาอักษรไดรฟ์)"""
    out: list[str] = []
    for env in ("QWEN_STT_HF_HUB", "HUGGINGFACE_HUB_CACHE", "HF_HUB_CACHE"):
        v = (os.environ.get(env) or "").strip()
        if v:
            out.append(v)
    hf_home = (os.environ.get("HF_HOME") or "").strip()
    if hf_home:
        out.append(os.path.join(hf_home, "hub"))
    out.append(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))
    seen, uniq = set(), []
    for r in out:
        k = os.path.normcase(os.path.abspath(r))
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def local_model_dirs() -> list[str]:
    """สำเนาในเครื่อง (ไม่พึ่งดิสก์ USB): <ที่นี่>\\models\\<ชื่อโมเดล>\\model.bin หรือ QWEN_STT_MODELS_DIR"""
    out = []
    v = (os.environ.get("QWEN_STT_MODELS_DIR") or "").strip()
    if v:
        out.append(v)
    out.append(os.path.join(HERE, "models"))
    return out


def find_model(want: str = "auto") -> tuple[str, str] | None:
    """(ชื่อ, path) ของโมเดลตัวแรกที่ใช้ได้จริง — สำเนาในเครื่องมาก่อนแคชบนดิสก์ภายนอก"""
    want = (want or "auto").strip()
    if want not in ("auto",) and want not in MODEL_REPOS:
        # path ของโฟลเดอร์โมเดลโดยตรง (ผู้ดูแลเครื่องสั่งเองผ่าน --model)
        return (os.path.basename(os.path.normpath(want)) or want, want) if _model_ok(want) else None
    names = AUTO_ORDER if want == "auto" else (want,)
    for name in names:
        for d in local_model_dirs():
            cand = os.path.join(d, name)
            if _model_ok(cand):
                return name, cand
        for root in hub_roots():
            for repo in MODEL_REPOS[name]:
                snaps = sorted(glob.glob(os.path.join(root, repo, "snapshots", "*")),
                               key=lambda p: _mtime(p), reverse=True)
                for s in snaps:
                    if _model_ok(s):
                        return name, s
    return None


def _mtime(p: str) -> float:
    try:
        return os.stat(p).st_mtime
    except OSError:
        return 0.0


# =============================================================== เลือกอุปกรณ์
def _nvidia_smi() -> str | None:
    exe = shutil.which("nvidia-smi")
    if exe:
        return exe
    cand = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "nvidia-smi.exe")
    return cand if os.path.isfile(cand) else None


def gpu_free_mb(timeout: float = 8.0) -> int | None:
    """VRAM ว่างของ GPU 0 (MB) จาก nvidia-smi — ไม่ใช้ torch (import torch กินเวลา/หน่วยความจำ และสร้าง CUDA context)"""
    exe = _nvidia_smi()
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--query-gpu=memory.free", "--format=csv,noheader,nounits", "-i", "0"],
                           capture_output=True, text=True, timeout=timeout,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return int(r.stdout.strip().splitlines()[0].strip()) if r.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


CUDA_DLLS = ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll")
_CUDA_READY: list = []


def cuda_dll_dirs() -> list[str]:
    """โฟลเดอร์ที่มี cuBLAS ของ CUDA 12 — wheel ของ ctranslate2 บน Windows ไม่แถม cuBLAS มา (แถมแค่ cudnn64_9)
    เดิมได้มาฟรีเพราะ import ctranslate2 ลาก torch เข้ามา (torch\\lib มีครบ) พอกัน torch (ข้างบน) GPU จึงต้องหาเอง
    เครื่องนี้ไม่มี CUDA Toolkit (ไม่มี CUDA_PATH) — แหล่งจริงคือ torch\\lib ของ env เดียวกัน (โหลดแค่ DLL ไม่ import torch)"""
    import sysconfig
    out = []
    purelib = sysconfig.get_paths().get("purelib") or ""
    cands = [os.path.join(purelib, "torch", "lib")]
    cands += glob.glob(os.path.join(purelib, "nvidia", "*", "bin"))
    for env in ("QWEN_STT_CUDA_BIN", "CUDA_PATH"):
        v = (os.environ.get(env) or "").strip()
        if v:
            cands.append(v if env == "QWEN_STT_CUDA_BIN" else os.path.join(v, "bin"))
    for d in cands:
        if os.path.isfile(os.path.join(d, "cublas64_12.dll")) and d not in out:
            out.append(d)
    return out


def prepare_cuda() -> bool:
    """ให้ ctranslate2 หา cuBLAS/cuDNN เจอ: เพิ่มโฟลเดอร์เข้า DLL search path + PATH (cuDNN โหลดไลบรารีย่อยตามชื่อ)
    แล้วโหลด cudart/cublasLt/cublas ล่วงหน้าด้วย path เต็ม — ทำครั้งเดียวต่อโปรเซส คืน False = ใช้ GPU ไม่ได้
    (วัดจริง: ไม่มีขั้นนี้ คำขอแรกล้มด้วย "cublas64_12.dll is not found" แล้วคำขอถัดไปค้างใน ctranslate2)"""
    if _CUDA_READY:
        return _CUDA_READY[0]
    ok = False
    try:
        import ctypes
        dirs = cuda_dll_dirs()
        for d in dirs:
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
            if d.lower() not in (os.environ.get("PATH") or "").lower():
                os.environ["PATH"] = d + os.pathsep + (os.environ.get("PATH") or "")
        for name in CUDA_DLLS:
            hit = next((os.path.join(d, name) for d in dirs if os.path.isfile(os.path.join(d, name))), None)
            if hit is None:
                raise OSError("%s not found" % name)
            ctypes.WinDLL(hit)
        ok = True
    except Exception as exc:                   # noqa: BLE001
        log("CUDA libraries unavailable (%s) - GPU disabled" % str(exc)[:160])
    _CUDA_READY.append(ok)
    return ok


def choose_device(requested: str, min_free_mb: int) -> tuple[str, str, str]:
    """(device, compute_type, เหตุผล) — auto: GPU เฉพาะเมื่อ ctranslate2 เห็น CUDA, หา cuBLAS เจอ และ VRAM ว่างถึงเกณฑ์
    ไม่งั้น CPU int8 · cuda: บังคับ GPU (ไว้วัดผล) · cpu: บังคับ CPU"""
    requested = (requested or "auto").lower()
    if requested == "cpu":
        return "cpu", "int8", "requested cpu"
    try:
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
    except Exception as exc:                   # noqa: BLE001
        n, why = 0, type(exc).__name__
    else:
        why = "no CUDA device"
    if n and not prepare_cuda():
        n, why = 0, "CUDA libraries (cuBLAS) not found"
    if requested == "cuda":
        return ("cuda", "int8_float16", "requested cuda") if n else ("cpu", "int8", "requested cuda but " + why)
    if not n:
        return "cpu", "int8", why
    free = gpu_free_mb()
    if free is None:
        return "cpu", "int8", "cannot read free VRAM"
    if free >= min_free_mb:
        return "cuda", "int8_float16", "free VRAM %d MB >= %d" % (free, min_free_mb)
    return "cpu", "int8", "free VRAM %d MB < %d" % (free, min_free_mb)


# =============================================================== ถอดรหัสไฟล์เสียง
class AudioError(Exception):
    """ไฟล์เสียงใช้ไม่ได้ — status คือรหัส HTTP ที่ควรตอบ, code คือเหตุผลสั้นๆ ที่เครื่องอ่านได้"""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code = status, code


def sniff_format(data: bytes) -> str | None:
    """ชนิดไฟล์จาก magic bytes -> ชื่อ demuxer ของ ffmpeg (ส่งให้ PyAV ตรงๆ ไม่ให้ ffmpeg เดาเอง)"""
    head = data[:16]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "matroska"                      # webm ของ MediaRecorder
    if head[4:8] == b"ftyp":
        return "mov"                           # mp4 / m4a
    if head[:4] == b"fLaC":
        return "flac"
    if head[:3] == b"ID3":
        return "mp3"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        # frame sync ของ MPEG audio: layer bits = 00 คือ ADTS (AAC), ที่เหลือคือ MP3
        return "aac" if (head[1] & 0x06) == 0 else "mp3"
    return None


def _check_shape(rate, channels) -> None:
    """[fix 2026-10-06 voice] อัตราสุ่ม/จำนวนช่องที่ยอมถอด — อัตราต่ำมาก (เช่น 16 Hz) แปลงขึ้น 16 kHz = ขยาย 1,000 เท่า
    ในเฟรมเดียว (FLAC 8 KB -> +1.25 GB วัดจริง) ก่อนจะถึงเพดานเวลา จึงต้องปฏิเสธ "ก่อน" ให้ resampler แตะ"""
    try:
        rate, channels = int(rate or 0), int(channels or 0)
    except (TypeError, ValueError):
        rate, channels = 0, 0
    if not (MIN_RATE <= rate <= MAX_RATE):
        raise AudioError(415, "unsupported_rate", "audio sample rate must be %d-%d Hz" % (MIN_RATE, MAX_RATE))
    if channels > MAX_CHANNELS:
        raise AudioError(415, "too_many_channels", "audio has more than %d channels" % MAX_CHANNELS)


def _frame_channels(frame) -> int:
    layout = getattr(frame, "layout", None)
    n = getattr(layout, "nb_channels", None)
    if n is None:
        n = len(getattr(layout, "channels", ()) or ())
    return int(n or 0)


def decode_audio(data: bytes, max_seconds: float, budget: float = DECODE_BUDGET):
    """bytes -> (numpy float32 โมโน 16 kHz, วินาที) — หยุดทันทีเมื่อยาวเกินเพดาน ไม่ถอดทั้งไฟล์ก่อนแล้วค่อยปฏิเสธ
    [fix 2026-10-06 voice] ตรวจอัตราสุ่ม/จำนวนช่องของสตรีมและทุกเฟรม + คำนวณความยาวที่จะได้ก่อน resample (ไม่ใช่หลัง)"""
    import av                                  # lazy: เทสต์หน่วยของ HTTP รันด้วย python ที่ไม่มี PyAV ได้
    import numpy as np
    if not data:
        raise AudioError(400, "empty", "empty audio body")
    fmt = sniff_format(data)
    if fmt is None:
        raise AudioError(415, "unsupported_format",
                         "unsupported audio format (use webm/opus, ogg, wav, mp3, m4a, flac or aac)")
    limit = int((max_seconds + 0.5) * SAMPLE_RATE)
    deadline = time.monotonic() + budget
    chunks, total = [], 0
    try:
        with av.open(io.BytesIO(data), mode="r", format=fmt, metadata_errors="ignore") as container:
            streams = [s for s in container.streams if s.type == "audio"]
            if not streams:
                raise AudioError(400, "no_audio", "no audio stream in the file")
            st = streams[0]
            ctx = getattr(st, "codec_context", None)
            rate0 = getattr(st, "sample_rate", 0) or getattr(ctx, "sample_rate", 0)
            ch0 = getattr(st, "channels", 0) or getattr(ctx, "channels", 0)
            if rate0:                           # 0 = หัวไฟล์ไม่บอก (ตรวจที่เฟรมแทน)
                _check_shape(rate0, ch0)
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            projected = 0.0                     # จำนวนตัวอย่าง 16 kHz ที่ "จะได้" — นับก่อนส่งเข้า resampler

            def take(frames):
                nonlocal total
                for fr in frames or ():
                    arr = fr.to_ndarray().reshape(-1)
                    chunks.append(arr)
                    total += arr.size

            for frame in container.decode(st):
                rate = int(getattr(frame, "sample_rate", 0) or getattr(frame, "rate", 0) or 0)
                _check_shape(rate, _frame_channels(frame))    # อัตราเปลี่ยนกลางสตรีมได้ — ตรวจทุกเฟรม
                projected += int(getattr(frame, "samples", 0) or 0) * float(SAMPLE_RATE) / rate
                if projected > limit:
                    raise AudioError(413, "too_long", "audio is longer than %d seconds" % int(max_seconds))
                take(resampler.resample(frame))
                if total > limit:
                    raise AudioError(413, "too_long", "audio is longer than %d seconds" % int(max_seconds))
                if time.monotonic() > deadline:
                    raise AudioError(413, "decode_timeout", "decoding took too long")
            take(resampler.resample(None))
    except AudioError:
        raise
    except Exception as exc:                   # noqa: BLE001 — ไฟล์เสีย/ถอดรหัสไม่ได้ = ข้อผิดพลาดของผู้เรียก
        raise AudioError(400, "decode_failed", "cannot decode audio (%s)" % type(exc).__name__) from None
    if total > limit:
        raise AudioError(413, "too_long", "audio is longer than %d seconds" % int(max_seconds))
    if not chunks or total == 0:
        return np.zeros(0, dtype=np.float32), 0.0
    audio = np.concatenate(chunks).astype(np.float32) / 32768.0
    return audio, audio.size / float(SAMPLE_RATE)


# =============================================================== เลือกภาษา (โหมดตรวจเอง)
def choose_language(detected: str, prob: float, duration: float, allowed, fallback: str, primary: str):
    """[fix 2026-10-06 voice] (ภาษาที่จะล็อก หรือ None = multilingual, เหตุผล) จากผลตรวจหน้าต่างแรกของ whisper

    allowed  = ชุดภาษาที่ตรวจได้ (ว่าง = ไม่จำกัด แบบเดิม)
    fallback = hint จากหน้าจอผู้ใช้ ถ้าอยู่ในชุด ไม่งั้น primary (ไทย)
    คลิปสั้น (<= 30 วิ = หน้าต่างเดียว: ปุ่มไมค์เกือบทั้งหมด)
      * ผลตรวจอยู่ในชุด และเป็นภาษาสำรองเอง หรือมั่นใจ >= LANG_SURE -> ใช้ตามนั้น (อังกฤษจริงได้ >= 0.965)
      * ไม่งั้น -> ภาษาสำรอง: คำไทยสั้นถูกตรวจเป็น vi/ja/ko/zh/ms หรืออังกฤษที่ไม่มั่นใจ ("ครับ" -> "Crap." 0.75)
    คลิปยาว: ภาษาหลักในหน้าต่างแรก = ล็อกภาษาหลัก, อีกภาษาในชุด = multilingual (เหมือนเดิม), นอกชุด = ภาษาสำรอง"""
    detected = (detected or "").lower()
    allowed = tuple(allowed or ())
    if not allowed:
        if duration > SHORT_CLIP_S and detected != primary:
            return None, "multilingual"
        return detected or None, "detected"
    if duration > SHORT_CLIP_S:
        if detected == primary:
            return primary, "primary"
        if detected in allowed:
            return None, "multilingual"
        return fallback, "outside %s" % ",".join(allowed)
    if detected in allowed and (detected == fallback or float(prob or 0.0) >= LANG_SURE):
        return detected, "detected"
    if detected in allowed:
        return fallback, "unsure %s %.2f" % (detected, float(prob or 0.0))
    return fallback, "outside %s" % ",".join(allowed)


# =============================================================== โมเดล
class EngineBusy(Exception):
    pass


class EngineUnavailable(Exception):
    pass


class Engine:
    """โมเดล faster-whisper หนึ่งตัว ถอดทีละงาน (CPU/GPU ตัวเดียว งานคู่ขนานไม่เร็วขึ้น) โหลด/ปลดตามการใช้งาน"""

    def __init__(self, model: str = "auto", device: str = "auto", min_free_mb: int = MIN_FREE_MB_DEFAULT,
                 threads: int = THREADS_DEFAULT, idle_unload_min: float = IDLE_UNLOAD_MIN_DEFAULT,
                 queue_max: int = QUEUE_MAX, queue_wait: float = QUEUE_WAIT,
                 primary_language: str = PRIMARY_LANGUAGE_DEFAULT, gpu_hold_s: float = GPU_HOLD_S_DEFAULT,
                 languages=LANGUAGES_DEFAULT):
        self.want_model, self.want_device = model, device
        self.primary_language = (primary_language or PRIMARY_LANGUAGE_DEFAULT).strip().lower()
        # [fix 2026-10-06 voice] ชุดภาษาที่โหมดตรวจเองเลือกได้ (ว่าง = ไม่จำกัด) — ภาษาหลักต้องอยู่ในชุดเสมอ
        langs = [x.strip().lower() for x in (languages or ()) if LANG_RE.match((x or "").strip().lower())]
        if langs and self.primary_language not in langs:
            langs.insert(0, self.primary_language)
        self.languages = tuple(dict.fromkeys(langs))
        self.window_s = dict(WINDOW_S_DEFAULT)  # วินาทีต่อหน้าต่าง 30 วิ ต่ออุปกรณ์ (ค่าวัดจริง ปรับตามงานจริง)
        self.window_measured = {"cuda": False, "cpu": False}
        self._warming = False
        self._warm_lock = threading.Lock()
        self._expect = (0.0, "", "")            # (เวลา, อุปกรณ์, เหตุผล) ของ expect_device ล่าสุด
        self.min_free_mb, self.threads = int(min_free_mb), max(1, int(threads))
        self.idle_unload_s = max(0.0, float(idle_unload_min) * 60.0)
        # ค่าลบ = ไม่จอดเลย (ถือ VRAM จนปลดตอนว่าง — ไว้วัดผล/เครื่องที่มี GPU แยกให้ STT) ดูหัวไฟล์เรื่อง -fit
        self.gpu_hold_s = float(gpu_hold_s)
        self.parked = False                     # True = โมเดล GPU ที่ย้ายน้ำหนักไป RAM แล้ว (VRAM คืนให้โมเดลแชต)
        self.parks = 0
        self.queue_wait = float(queue_wait)
        self._slots = threading.BoundedSemaphore(1 + max(0, int(queue_max)))
        self._run = threading.Lock()            # งานถอดทีละงาน
        self._load_lock = threading.Lock()
        self.model = None
        self.state = "idle"                     # idle | loading | ready | no_model | error
        self.error = ""
        self.name = self.path = self.device = self.compute = self.reason = ""
        self.loaded_at = 0.0
        self.last_used = time.monotonic()
        self.load_s = 0.0
        self.jobs = 0
        self.audio_s = 0.0
        self.work_s = 0.0
        self.last = {}
        self.force_cpu = False
        found = find_model(model)
        if found is None:
            self.state, self.error = "no_model", "no faster-whisper model found (checked local copies and HF caches)"
        else:
            self.name, self.path = found

    # ---- โหลด / ปลด
    def load(self, choice: tuple | None = None) -> None:
        """โหลดโมเดล — choice = (device, compute, เหตุผล) ที่ _prepare เลือกไว้แล้ว (ไม่เรียก nvidia-smi ซ้ำ)"""
        with self._load_lock:
            if self.model is not None:
                return
            found = find_model(self.want_model)        # ดิสก์ USB อาจถูกถอด/เสียบใหม่ระหว่างทาง — หาใหม่ทุกครั้ง
            if found is None:
                self.state, self.error = "no_model", "no faster-whisper model found (checked local copies and HF caches)"
                raise EngineUnavailable(self.error)
            self.name, self.path = found
            self.state, self.error = "loading", ""
            # เวลาแยกช่วงลง log: การเปิดครั้งแรกหลังบูตเครื่อง import ctranslate2 (DLL ของ CUDA หลายร้อย MB) ช้าได้นับนาที
            # ส่วนการโหลดซ้ำหลังปลดตอนว่างไม่ต้อง import ใหม่ — ตัวเลขนี้ช่วยแยกว่าช้าที่ไลบรารีหรือที่ดิสก์ USB
            t_dev = time.monotonic()
            if self.force_cpu or choice is None:
                choice = choose_device("cpu" if self.force_cpu else self.want_device, self.min_free_mb)
            device, compute, reason = choice
            if self.force_cpu:
                reason = "GPU failed earlier - cpu until the next idle unload"
            t_dev = time.monotonic() - t_dev
            t0 = time.monotonic()
            try:
                from faster_whisper import WhisperModel
                try:
                    model = WhisperModel(self.path, device=device, compute_type=compute, cpu_threads=self.threads,
                                         local_files_only=True)
                except Exception as exc:              # noqa: BLE001 — GPU โหลดไม่ขึ้น (VRAM ถูกแย่งระหว่างนั้น) -> CPU
                    if device != "cuda":
                        raise
                    log("load on cuda failed (%s) - falling back to cpu" % type(exc).__name__)
                    device, compute, reason = "cpu", "int8", "cuda load failed: %s" % type(exc).__name__
                    model = WhisperModel(self.path, device=device, compute_type=compute,
                                         cpu_threads=self.threads, local_files_only=True)
            except Exception as exc:                  # noqa: BLE001
                self.state, self.error = "error", "model load failed: %s: %s" % (type(exc).__name__, str(exc)[:200])
                log(self.error)
                raise EngineUnavailable(self.error) from None
            self.model = model
            self.parked = False
            self.device, self.compute, self.reason = device, compute, reason
            self.load_s = round(time.monotonic() - t0, 2)
            self.loaded_at = time.time()
            self.last_used = time.monotonic()
            self.state = "ready"
            log("model loaded name=%s device=%s compute=%s (%s) in %.1fs (+%.1fs device check/import)" % (
                self.name, device, compute, reason, self.load_s, t_dev))

    def _drop(self, why: str) -> bool:
        """ปลดโมเดลจริง — ผู้เรียกต้องถือ _run อยู่แล้ว (ไม่มีงานถอดค้าง)"""
        with self._load_lock:
            if self.model is None:
                return False
            try:
                inner = getattr(self.model, "model", None)
                if inner is not None and hasattr(inner, "unload_model"):
                    inner.unload_model()
            except Exception:                  # noqa: BLE001
                pass
            self.model = None
            self.parked = False
            gc.collect()
            self.state = "idle"
            log("model unloaded (%s)" % why)
            return True

    def _inner(self):
        """ctranslate2.models.Whisper ข้างใน WhisperModel (ตัวที่ย้ายน้ำหนักระหว่าง GPU/RAM ได้)"""
        inner = getattr(self.model, "model", None)
        if inner is None or not hasattr(inner, "unload_model") or not hasattr(inner, "load_model"):
            return None
        return inner

    def park(self, why: str = "gpu hold") -> bool:
        """ย้ายน้ำหนักของโมเดล GPU ไป RAM คืน VRAM ให้โมเดลแชต — ผู้เรียกต้องถือ _run (ไม่มีงานถอดค้าง)
        ทำไม่ได้ (ไลบรารีไม่มีเมธอด/ล้ม) = ปลดเต็มแทน เพราะเป้าหมายคือ "ไม่ถือ VRAM ตอนว่าง" ไม่ใช่ความเร็วรอบหน้า"""
        with self._load_lock:
            if self.model is None or self.device != "cuda" or self.parked:
                return False
            inner = self._inner()
            t0 = time.monotonic()
            try:
                if inner is None:
                    raise RuntimeError("model cannot be moved to system RAM")
                inner.unload_model(to_cpu=True)
            except Exception as exc:           # noqa: BLE001
                log("park failed (%s) - unloading instead" % str(exc)[:160])
                ok = False
            else:
                ok = True
        if not ok:
            return self._drop("park failed")
        self.parked = True
        self.parks += 1
        log("model parked in RAM (%s) in %.2fs - VRAM returned" % (why, time.monotonic() - t0))
        return True

    def _resume(self) -> bool:
        """โมเดลที่จอดไว้กลับขึ้น GPU (~0.25 วิ) — ล้ม (VRAM ถูกแย่งระหว่างตรวจกับย้าย) = ปลดทิ้ง ให้ผู้เรียกโหลดใหม่"""
        inner = self._inner()
        t0 = time.monotonic()
        try:
            if inner is None:
                raise RuntimeError("no movable model")
            inner.load_model()
        except Exception as exc:               # noqa: BLE001
            log("resume on GPU failed (%s)" % str(exc)[:160])
            self._drop("resume failed")
            return False
        self.parked = False
        log("model resumed on GPU in %.2fs" % (time.monotonic() - t0))
        return True

    def _prepare(self) -> None:
        """ก่อนทุกงาน (ผู้เรียกถือ _run): เลือกอุปกรณ์ของงานนี้ตาม VRAM ที่ว่าง "ตอนนี้" แล้วทำให้โมเดลพร้อมบนอุปกรณ์นั้น
        โมเดลแชตโหลด/ปลดได้ตลอด (router) ค่าที่เลือกตอนโหลดครั้งแรกจึงเก่าได้ — ตรวจใหม่ทุกงาน (nvidia-smi ~0.3 วิ)"""
        if self.model is not None and self.device == "cuda" and not self.parked:
            return                              # ยังถือ VRAM อยู่ (ในช่วง gpu_hold) ตรวจ VRAM ตอนนี้จะไม่นับส่วนของเราเอง
        if self.model is not None and self.device == "cpu" and (self.force_cpu or self.want_device == "cpu"):
            return
        choice = choose_device("cpu" if self.force_cpu else self.want_device, self.min_free_mb)
        if self.model is not None:
            if choice[0] == self.device:
                if not self.parked:
                    return
                if self._resume():
                    self.reason = choice[2]
                    return
                choice = ("cpu", "int8", "GPU resume failed")
            else:
                # ทิ้งตัวเดิมก่อนโหลดตัวใหม่: ถือสองตัวพร้อมกัน = RAM ~6.5 GB บนเครื่องที่ใช้หน่วยความจำร่วมกับ LLM
                self._drop("switch %s -> %s (%s)" % ("parked GPU" if self.parked else self.device, choice[0],
                                                    choice[2]))
        if self.model is None:
            self.load(choice)

    def unload(self, why: str = "idle") -> bool:
        """ปลดโมเดล (คืน VRAM/หน่วยความจำ) — ทำเฉพาะตอนไม่มีงานค้าง
        ปลดตอนว่างแล้วล้าง force_cpu ด้วย: GPU ที่ล้มเพราะ VRAM ถูกแย่งชั่วคราว รอบโหลดหน้าเลือกใหม่ตาม VRAM ตอนนั้น"""
        if not self._run.acquire(blocking=False):
            return False
        try:
            done = self._drop(why)
            self.force_cpu = False
            return done
        finally:
            self._run.release()

    # ---- [fix 2026-10-06 voice] เตรียมล่วงหน้า + บอกอุปกรณ์ที่งานถัดไปจะได้
    def warm(self) -> str:
        """เตรียมโมเดลระหว่างที่ผู้ใช้กำลังอัดเสียง (hub เรียก POST /v1/warm ตอนกดไมค์) — ไม่รอ คืนสิ่งที่ทำ
        วัดจริง: หลังปลดตอนว่าง 15 นาที คำขอแรกรอโหลด 13 วิ (GPU) ถึง 17-23 วิ (CPU) ทั้งที่ /health บอก ready
        ระหว่างพูด 3-10 วินาทีโหลดเสร็จพอดี -> คำตอบเร็วเท่าตอนโมเดลอุ่นอยู่
        GPU: โหลดแล้ว "จอดทันที" (ยังไม่มีงาน) ไม่ถือ VRAM ระหว่างผู้ใช้พูด — router ที่โหลดโมเดลแชตช่วงนั้นเห็น VRAM ว่างครบ"""
        if self.public_state() == "no_model" and find_model(self.want_model) is None:
            return "no_model"
        state = "loading"
        if self.model is not None:
            self.last_used = time.monotonic()   # กำลังจะมีงาน: ไม่ปลดตอนว่างระหว่างผู้ใช้พูด
            state = "parked" if self.parked else "ready"
            # อยู่บน CPU (ตอนนั้น VRAM ไม่พอ) แต่ตอนนี้อาจว่างแล้ว: ให้ _prepare สลับขึ้น GPU ระหว่างผู้ใช้พูด (~4.5 วิ)
            if not (self.device == "cpu" and not self.force_cpu and self.want_device != "cpu"):
                return state
        with self._warm_lock:
            if self._warming:
                return state
            self._warming = True
        threading.Thread(target=self._warm_job, daemon=True, name="stt-warm").start()
        return state

    def _warm_job(self) -> None:
        try:
            if not self._run.acquire(timeout=1.0):     # มีงานถอดอยู่ = งานนั้นเตรียมโมเดลเองแล้ว
                return
            try:
                self.last_used = time.monotonic()
                self._prepare()                 # โหลด (หรือสลับ CPU -> GPU ถ้า VRAM กลับมาว่าง) ตาม VRAM ตอนนี้
                self.last_used = time.monotonic()
                if self.model is not None and self.device == "cuda" and self.gpu_hold_s >= 0 and not self.parked:
                    self.park("warm-up, no job yet")
            finally:
                self._run.release()
        except EngineUnavailable:
            pass
        except Exception:                       # noqa: BLE001 — เตรียมล่วงหน้าพลาด = งานจริงโหลดเองตามปกติ
            log("warm-up failed: %s" % traceback.format_exc()[-400:])
        finally:
            self._warming = False

    def expect_device(self) -> tuple[str, str]:
        """(cuda|cpu, เหตุผล) ที่งานถัดไปจะได้ — ตามกติกาเดียวกับ _prepare แต่ไม่โหลดอะไร (จำผล nvidia-smi 5 วิ)"""
        if self.model is not None and self.device == "cuda" and not self.parked:
            return "cuda", "holding GPU"
        if self.force_cpu:
            return "cpu", "GPU failed earlier"
        if self.model is not None and self.device == "cpu" and self.want_device == "cpu":
            return "cpu", "requested cpu"
        at, dev, why = self._expect
        if time.monotonic() - at > EXPECT_TTL or not dev:
            dev, _c, why = choose_device(self.want_device, self.min_free_mb)
            self._expect = (time.monotonic(), dev, why)
        return dev, why

    def _note_speed(self, device: str, duration: float, took: float) -> None:
        """เวลาต่อหน้าต่าง 30 วิ (whisper เข้ารหัสทีละ 30 วิเสมอ คลิป 3 วิกับ 30 วิจึงใช้เวลาใกล้กัน) — ค่าเฉลี่ยเคลื่อนที่"""
        if device not in self.window_s or duration < 0.1:
            return
        per = took / max(1, int(-(-duration // SHORT_CLIP_S)))
        if not self.window_measured.get(device):
            self.window_s[device], self.window_measured[device] = round(per, 2), True
        else:
            self.window_s[device] = round(0.7 * self.window_s[device] + 0.3 * per, 2)

    def idle_tick(self) -> None:
        idle = time.monotonic() - self.last_used
        if self.idle_unload_s and self.model is not None and idle > self.idle_unload_s:
            self.unload("idle %d min" % int(self.idle_unload_s // 60))
            return
        if self.gpu_hold_s >= 0 and self.model is not None and self.device == "cuda" and not self.parked \
                and idle > self.gpu_hold_s:
            if self._run.acquire(blocking=False):     # มีงานถอดอยู่ = ยังใช้ GPU อยู่ รอรอบหน้า
                try:
                    self.park("idle %.0fs after a GPU job" % idle)
                finally:
                    self._run.release()

    # ---- ถอดเสียง
    def transcribe(self, audio, duration: float, language: str | None, hint: str | None = None) -> dict:
        if not self._slots.acquire(blocking=False):
            raise EngineBusy("queue full")
        try:
            if not self._run.acquire(timeout=self.queue_wait):
                raise EngineBusy("waited too long in queue")
            try:
                self.last_used = time.monotonic()
                self._prepare()
                t0 = time.monotonic()
                try:
                    result = self._transcribe(audio, duration, language, hint)
                except RuntimeError as exc:
                    # GPU พังกลางงาน (DLL ของ CUDA หาไม่เจอ/VRAM หมดเพราะ LLM โหลดเพิ่ม) — วัดจริงแล้วว่าถ้าปล่อยโมเดล GPU
                    # ตัวเดิมไว้ คำขอถัดไปค้างใน ctranslate2 ไม่คืนเลย จึงปลดทิ้งแล้วถอดซ้ำบน CPU ทันทีในคำขอเดียวกัน
                    if self.device != "cuda":
                        raise
                    log("GPU transcription failed (%s) - reloading on CPU" % str(exc)[:160])
                    self._drop("GPU failure")
                    self.force_cpu = True
                    self.load()
                    t0 = time.monotonic()
                    result = self._transcribe(audio, duration, language, hint)
                took = time.monotonic() - t0
                self.jobs += 1
                self.audio_s += duration
                self.work_s += took
                self._note_speed(self.device, duration, took)
                self.last_used = time.monotonic()
                result["elapsed_s"] = round(took, 2)
                self.last = {"audio_s": round(duration, 2), "elapsed_s": round(took, 2),
                             "language": result.get("language")}
                return result
            finally:
                self._run.release()
        finally:
            self._slots.release()

    def _transcribe(self, audio, duration: float, language: str | None, hint: str | None = None) -> dict:
        base = {"model": self.name, "device": self.device, "compute_type": self.compute,
                "duration": round(duration, 2)}
        if duration < 0.1:
            return dict(base, text="", language=language or "", language_probability=0.0, segments=[])
        beam = 5 if self.device == "cuda" else 1
        opts = dict(task="transcribe", beam_size=beam, vad_filter=True, condition_on_previous_text=False)
        segments, info = self.model.transcribe(audio, language=language or None, multilingual=False, **opts)
        lang_out, prob_out = info.language, info.language_probability
        detected = None
        # โหมดตรวจภาษาเอง (วัดจริงกับไฟล์ที่ไทย/อังกฤษสลับกันทีละ ~30 วินาที):
        #   * หน้าต่างแรกเป็นภาษาหลัก (ไทย) -> ล็อกภาษาไทยทั้งคลิป: whisper โหมดไทยถอดประโยคอังกฤษเป็นอังกฤษได้ถูกต้อง
        #     ส่วน multilingual (ตรวจใหม่ทุกหน้าต่าง) ทำช่วงไทยที่อยู่ในหน้าต่างเดียวกับอังกฤษที่ยาวกว่า "หายไปทั้งช่วง"
        #   * หน้าต่างแรกเป็นภาษาอื่น -> ถอดใหม่แบบ multilingual: ล็อกอังกฤษทั้งคลิปทำให้ช่วงภาษาไทยที่ตามมากลายเป็นอังกฤษ
        #     มั่วๆ ("Day 15, I had a full-wide") และวนซ้ำ — ทิ้ง generator แรกโดยไม่ถอด (เสียแค่การตรวจภาษาหนึ่งหน้าต่าง)
        #   คลิปไม่เกิน 30 วินาที (ปุ่มไมค์ส่วนใหญ่) มีหน้าต่างเดียว สองแบบให้ผลเท่ากัน จึงไม่ถอดซ้ำ
        # [fix 2026-10-06 voice] + ผลตรวจต้องอยู่ใน --languages (th,en): คำไทยสั้นถูกตรวจเป็นเกาหลี/ญี่ปุ่น/เวียดนาม/
        #   อังกฤษไม่มั่นใจ ("โอเค" -> "오케이.") -> ถอดเป็นภาษาสำรอง (hint หรือภาษาหลัก) แทน — ดู choose_language
        #   faster-whisper ตรวจภาษาก่อนคืน generator และ generator แรกยังไม่ถูกวน = ยังไม่ได้ถอดจริง การถอดใหม่จึงเสียแค่
        #   feature/VAD ซ้ำ (การเข้ารหัสหน้าต่างแรกเกิดสองครั้งเท่าเดิม: ตรวจภาษา 1 + ถอด 1)
        if language is None:
            det = (info.language or "").lower()
            prob = float(info.language_probability or 0.0)
            fallback = hint if (hint and hint in self.languages) else self.primary_language
            pick, why = choose_language(det, prob, duration, self.languages, fallback, self.primary_language)
            detected = {"language": det, "probability": round(prob, 3), "rule": why}
            if pick is None:
                if duration > SHORT_CLIP_S:
                    segments, info = self.model.transcribe(audio, language=None, multilingual=True, **opts)
                    lang_out, prob_out = info.language, info.language_probability
            elif pick != det:
                probs = dict(getattr(info, "all_language_probs", None) or ())
                segments, _info = self.model.transcribe(audio, language=pick, multilingual=False, **opts)
                # รายงานความน่าจะเป็นของตัวตรวจสำหรับภาษาที่เลือกจริง (ไม่ใช่ 1.0 ที่ faster-whisper ใส่ให้ภาษาที่สั่ง)
                lang_out, prob_out = pick, probs.get(pick, 0.0)
                log("language auto %s(%.2f) -> %s (%s) audio=%.1fs" % (det or "?", prob, pick, why, duration))
        segs, parts = [], []
        for s in segments:                      # generator — การถอดจริงเกิดตอนวนตรงนี้
            text = re.sub(r"\s+", " ", s.text or "").strip()
            if not text:
                continue
            segs.append({"start": round(float(s.start), 2), "end": round(float(s.end), 2), "text": text})
            parts.append(text)
        out = dict(base, text=" ".join(parts).strip(), language=lang_out or (language or ""),
                   language_probability=round(float(prob_out or 0.0), 3), segments=segs)
        if detected is not None:
            out["detected"] = detected
        return out

    def status(self) -> dict:
        rtf = round(self.work_s / self.audio_s, 3) if self.audio_s > 0 else None
        return {"state": self.state, "model": self.name, "model_path": self.path, "device": self.device,
                "compute_type": self.compute, "device_reason": self.reason, "loaded": self.model is not None,
                "parked": bool(self.parked and self.model is not None), "parks": self.parks,
                "gpu_hold_s": self.gpu_hold_s,
                "load_s": self.load_s, "jobs": self.jobs, "audio_s": round(self.audio_s, 1),
                "rtf": rtf, "last": self.last, "error": self.error,
                "idle_s": round(time.monotonic() - self.last_used, 1),
                "idle_unload_min": round(self.idle_unload_s / 60.0, 1),
                # [fix 2026-10-06 voice] ให้ hub/หน้าเว็บบอกผู้ใช้ได้ว่างานถัดไปเร็วแค่ไหน (GPU ~2 วิ, CPU ~24-54 วิ/30 วิเสียง)
                "languages": list(self.languages), "primary_language": self.primary_language,
                "window_s": dict(self.window_s), "window_measured": dict(self.window_measured),
                "warming": bool(self._warming)}

    def status_full(self) -> dict:
        """status + อุปกรณ์ที่งานถัดไปจะได้ (เรียก nvidia-smi ได้ จึงแยกจาก status ที่ /health ใช้)"""
        dev, why = self.expect_device() if self.path or self.model is not None else ("", "no model")
        return dict(self.status(), expect_device=dev, expect_reason=why)

    def public_state(self) -> str:
        if self.state == "idle" and not self.path:
            return "no_model"
        return self.state


# =============================================================== HTTP
_BOUNDARY_RE = re.compile(r'boundary=(?:"([^"]{1,200})"|([^;\s"]{1,200}))', re.I)
_DISP_PARAM_RE = re.compile(r'(?i)\b(name|filename)\s*=\s*(?:"([^"]*)"|([^;\s]*))')


def parse_multipart(content_type: str, body: bytes) -> tuple[bytes | None, dict]:
    """multipart/form-data -> (ไฟล์เสียง, ช่องข้อความ) — ส่วนชื่อ file/audio หรือส่วนแรกที่มี filename

    เขียนเองแทน email.parser: ตัวนั้นอ่านทีละ "บรรทัด" แล้วอาจแปลงไบต์ \\r/\\n กลางข้อมูลไบนารี (ไฟล์เสียงเพี้ยนเงียบๆ)
    ที่นี่ตัดตาม boundary ตรงตัวอย่างเดียว เนื้อไฟล์ไม่ถูกแตะแม้แต่ไบต์เดียว"""
    m = _BOUNDARY_RE.search(content_type or "")
    if not m:
        return None, {}
    delim = b"--" + (m.group(1) or m.group(2)).encode("latin-1", "replace")
    audio, fields, fallback = None, {}, None
    pieces = body.split(delim)
    for raw in pieces[1:]:
        if raw.startswith(b"--"):
            break                               # ตัวปิด --boundary--
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        elif raw.startswith(b"\n"):
            raw = raw[1:]
        end, skip = raw.find(b"\r\n\r\n"), 4
        if end < 0:
            end, skip = raw.find(b"\n\n"), 2
        if end < 0:
            continue
        head = raw[:end].decode("utf-8", "replace")
        data = raw[end + skip:]
        if data.endswith(b"\r\n"):
            data = data[:-2]
        elif data.endswith(b"\n"):
            data = data[:-1]
        disp = ""
        for line in head.splitlines():
            if line.lower().startswith("content-disposition:"):
                disp = line.split(":", 1)[1]
        params = {k.lower(): (a if a is not None and a != "" else b) for k, a, b in _DISP_PARAM_RE.findall(disp)}
        name = params.get("name", "")
        if name in ("file", "audio"):
            audio = data
        elif "filename" in params and fallback is None:
            fallback = data
        elif name and len(data) <= 256:
            fields[name] = data.decode("utf-8", "replace").strip()
    return (audio if audio is not None else fallback), fields


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "%s/%s" % (SERVER_NAME, VERSION)
    timeout = SOCKET_TIMEOUT
    # ค่าที่ main()/เทสต์ตั้งให้
    engine: Engine = None                       # type: ignore[assignment]
    max_bytes = MAX_BYTES_DEFAULT
    max_seconds = MAX_SECONDS_DEFAULT
    decoder = staticmethod(decode_audio)       # เทสต์แทนได้ (python ที่ไม่มี PyAV)
    # [fix 2026-10-06 voice] ThreadingHTTPServer ไม่จำกัดจำนวนเธรด: คำขอที่ถือ body (สูงสุด 25 MB) และงานถอดรหัสต้องมีเพดาน
    # (make_server ตั้งค่าจริงต่อเซิร์ฟเวอร์) — inflight = ช่องคิวของ Engine (1 + QUEUE_MAX), decode_gate = 2
    inflight = threading.BoundedSemaphore(1 + QUEUE_MAX)
    decode_gate = threading.BoundedSemaphore(DECODE_CONCURRENCY)
    decode_wait = DECODE_WAIT

    def log_message(self, fmt, *args):
        pass                                    # log ของเราเองอยู่ใน _done (ไม่มี path/query ดิบ)

    def _port(self) -> int:
        return int(self.server.server_address[1])

    def _json(self, code: int, obj: dict, extra=()) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _gate(self) -> bool:
        verdict = secrets_util.check_request(self.command, self.path, self.headers, self._port(),
                                             public_paths=("/health",))
        if verdict is None:
            return True
        code, reason = verdict
        self.close_connection = True           # ยังไม่ได้อ่าน body — ปิดคอนเนกชันกันไบต์ค้าง (request desync)
        self._json(code, {"error": reason})
        log("%s %s -> %d %s" % (self.command, urlsplit(self.path).path[:60], code, reason))
        return False

    def do_OPTIONS(self):
        # ไม่รองรับ preflight ของเบราว์เซอร์โดยเจตนา (ไม่มี CORS) — ทางของหน้าแชตคือ hub /_qwen/stt
        if self._gate():
            self.close_connection = True
            self._json(405, {"error": "method_not_allowed"}, extra=(("Allow", "GET, POST"),))

    def do_DELETE(self):
        if self._gate():
            self.close_connection = True
            self._json(405, {"error": "method_not_allowed"}, extra=(("Allow", "GET, POST"),))

    do_PUT = do_PATCH = do_DELETE

    def do_GET(self):
        if not self._gate():
            return
        route = urlsplit(self.path).path.rstrip("/") or "/"
        eng = self.engine
        if route == "/health":
            st = eng.public_state()
            body = {"status": "ok", "server": SERVER_NAME, "version": VERSION, "state": st,
                    "ready": st == "ready", "available": st in ("ready", "loading", "idle")}
            # [fix 2026-10-06 voice] อุปกรณ์ของโมเดลที่โหลดอยู่ (ไม่มี path/รายละเอียด — /health ไม่ต้องใช้ token)
            # ให้ hub แสดง "พร้อม · GPU/CPU" ได้; อุปกรณ์ที่งานถัดไปจะได้จริงอยู่ที่ /v1/status (expect_device)
            dev = getattr(eng, "device", "") if getattr(eng, "model", None) is not None else ""
            body["device"] = dev if dev in ("cuda", "cpu") else ""
            body["parked"] = bool(getattr(eng, "parked", False) and body["device"])
            self._json(200, body)
            return
        if route == "/v1/status":
            full = getattr(eng, "status_full", None) or eng.status
            self._json(200, dict(full(), server=SERVER_NAME, version=VERSION,
                                 max_bytes=self.max_bytes, max_seconds=self.max_seconds,
                                 python=sys.executable))
            return
        self._json(404, {"error": "not_found"})

    def _drain(self, n: int) -> bool:
        """อ่าน body ทิ้งทีละ 64 KB (ไม่เก็บ) — ตอบ 503 แล้วคอนเนกชันยังใช้ต่อได้ และผู้เรียก (hub/MCP ที่ส่ง body
        ทั้งก้อนก่อนอ่านคำตอบ) ได้รหัส busy จริง ไม่ใช่ connection reset ที่ถูกแปลว่า "บริการไม่ทำงาน" """
        left = n
        try:
            while left > 0:
                got = self.rfile.read(min(65536, left))
                if not got:
                    return False
                left -= len(got)
        except OSError:
            return False
        return True

    def _warm_request(self) -> None:
        """[fix 2026-10-06 voice] POST /v1/warm — body ว่าง (หรือเล็กมาก) เตรียมโมเดลเบื้องหลังแล้วตอบทันที"""
        if (self.headers.get("Transfer-Encoding") or "").strip():
            self.close_connection = True
            self._json(411, {"error": "length_required", "message": "chunked bodies are not accepted"})
            return
        try:
            n = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            n = -1
        if n < 0 or n > WARM_MAX_BODY:
            self.close_connection = True
            self._json(413 if n > 0 else 411, {"error": "too_large" if n > 0 else "length_required"})
            return
        if n and not self._drain(n):
            self.close_connection = True
            return
        warm = getattr(self.engine, "warm", None)
        action = warm() if warm else "unsupported"
        self._json(200, {"state": self.engine.public_state(), "action": action})
        if action == "loading":
            log("POST /v1/warm -> loading")

    def do_POST(self):
        if not self._gate():
            return
        route = urlsplit(self.path).path.rstrip("/")
        if route == "/v1/warm":
            self._warm_request()
            return
        if route != "/v1/transcribe":
            self.close_connection = True
            self._json(404, {"error": "not_found"})
            return
        if (self.headers.get("Transfer-Encoding") or "").strip():
            self.close_connection = True
            self._json(411, {"error": "length_required", "message": "chunked bodies are not accepted"})
            return
        try:
            n = int(self.headers.get("Content-Length") or "-1")
        except ValueError:
            n = -1
        if n < 0:
            self.close_connection = True
            self._json(411, {"error": "length_required"})
            return
        if n > self.max_bytes:
            self.close_connection = True
            self._json(413, {"error": "too_large", "message": "body is larger than %d bytes" % self.max_bytes})
            log("POST /v1/transcribe -> 413 too_large bytes=%d" % n)
            return
        # [fix 2026-10-06 voice] ถือ body ในหน่วยความจำพร้อมกันได้ไม่เกินจำนวนช่องคิว — เกิน = อ่านทิ้งแล้ว 503 busy
        if not self.inflight.acquire(blocking=False):
            ok = self._drain(n)
            if not ok:
                self.close_connection = True
            self._json(503, {"error": "busy", "message": "too many requests in flight"}, extra=(("Retry-After", "10"),))
            log("POST /v1/transcribe -> 503 busy (in flight) bytes=%d" % n)
            return
        try:
            self._transcribe_request(n)
        finally:
            self.inflight.release()

    def _transcribe_request(self, n: int) -> None:
        t0 = time.monotonic()
        try:
            body = self.rfile.read(n) if n else b""
        except OSError:
            self.close_connection = True
            return
        if len(body) != n:
            self.close_connection = True
            self._json(400, {"error": "short_body"})
            return
        q = parse_qs(urlsplit(self.path).query or "", keep_blank_values=False)
        fields = {}
        ctype = self.headers.get("Content-Type") or ""
        audio_bytes = body
        if ctype.lower().startswith("multipart/"):
            try:
                audio_bytes, fields = parse_multipart(ctype, body)
            except Exception:                  # noqa: BLE001
                audio_bytes = None
            if not audio_bytes:
                self._json(400, {"error": "no_file", "message": "multipart body has no file/audio part"})
                return
        lang = (fields.get("language") or (q.get("language") or [""])[0] or "").strip().lower()
        if lang in ("", "auto"):
            lang = None
        elif not LANG_RE.match(lang):
            self._json(400, {"error": "bad_language", "message": "language must be th, en, auto or an ISO code"})
            return
        # [fix 2026-10-06 voice] hint = ภาษาของหน้าจอผู้ใช้ ใช้เป็นภาษาสำรองเมื่อตรวจเองแล้วไม่แน่ใจ (ค่าแปลก = ไม่สนใจ)
        hint = (fields.get("hint") or (q.get("hint") or [""])[0] or "").strip().lower()[:8]
        hint = hint if LANG_RE.match(hint) else None
        max_s = float(self.max_seconds)
        try:
            ask = float((fields.get("max_seconds") or (q.get("max_seconds") or [""])[0] or "0").strip())
            if 0 < ask < max_s:
                max_s = ask                    # ผู้เรียกลดเพดานของตัวเองได้ เพิ่มเกินของเซิร์ฟเวอร์ไม่ได้
        except ValueError:
            pass
        # [fix 2026-10-06 voice] ถอดรหัสพร้อมกันได้ DECODE_CONCURRENCY งาน (เดิมไม่จำกัด: ทุกเธรดถอดรหัสก่อนเข้าคิว)
        if not self.decode_gate.acquire(timeout=self.decode_wait):
            self._json(503, {"error": "busy", "message": "decoder busy"}, extra=(("Retry-After", "10"),))
            log("POST /v1/transcribe -> 503 busy (decoder) bytes=%d" % n)
            return
        try:
            audio, duration = self.decoder(audio_bytes, max_s)
        except AudioError as exc:
            self._json(exc.status, {"error": exc.code, "message": str(exc)})
            log("POST /v1/transcribe -> %d %s bytes=%d" % (exc.status, exc.code, n))
            return
        finally:
            self.decode_gate.release()
        audio_bytes = body = None               # คืนหน่วยความจำของ body ก่อนรอคิวโมเดล (งานยาวรอได้หลายนาที)
        try:
            result = self.engine.transcribe(audio, duration, lang, hint=hint)
        except EngineBusy as exc:
            self._json(503, {"error": "busy", "message": str(exc)}, extra=(("Retry-After", "10"),))
            log("POST /v1/transcribe -> 503 busy (%s) audio=%.1fs" % (exc, duration))
            return
        except EngineUnavailable as exc:
            self._json(503, {"error": "unavailable", "message": str(exc)[:300]}, extra=(("Retry-After", "30"),))
            log("POST /v1/transcribe -> 503 unavailable")
            return
        except Exception as exc:               # noqa: BLE001 — รายละเอียดอยู่ใน log เท่านั้น
            self._json(500, {"error": "internal", "message": type(exc).__name__})
            log("POST /v1/transcribe -> 500 %s\n%s" % (type(exc).__name__, traceback.format_exc()[-1200:]))
            return
        self._json(200, result)
        log("POST /v1/transcribe -> 200 bytes=%d audio=%.1fs lang=%s(%s) segs=%d dev=%s work=%.2fs total=%.2fs" % (
            n, duration, result.get("language"), "auto" if lang is None else "set", len(result.get("segments") or []),
            result.get("device"), float(result.get("elapsed_s") or 0), time.monotonic() - t0))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # Windows: SO_REUSEADDR ยอมให้สองโปรเซสผูกพอร์ตเดียวกันได้ (ตัวที่สองแย่งคำขอไปเงียบๆ) — ใช้ SO_EXCLUSIVEADDRUSE แทน
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)   # ข้าม getfqdn() ของ HTTPServer (ไม่ต้องถาม DNS)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), int(port)

    def handle_error(self, request, client_address):
        # ค่าเริ่มต้นของ socketserver พิมพ์ traceback ทั้งก้อนลง stderr — ไคลเอนต์ที่ปิดสาย keep-alive ทิ้ง (ตัวเปิดตรวจ
        # /health แล้วจบ, หน้าเว็บยกเลิกการอัด) ทำให้ stt.err.log มี ConnectionReset ทุกครั้ง (owner stack เจอจริง)
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, socket.timeout)):
            return
        log("request handler error: %s" % traceback.format_exc()[-800:])


def make_server(engine: Engine, port: int, max_bytes: int = MAX_BYTES_DEFAULT,
                max_seconds: float = MAX_SECONDS_DEFAULT, decoder=None, inflight: int = 1 + QUEUE_MAX,
                decode_concurrency: int = DECODE_CONCURRENCY) -> Server:
    # [fix 2026-10-06 voice] semaphore ต่อเซิร์ฟเวอร์ (ไม่ใช้ของคลาสร่วมกัน — เทสต์เปิดหลายเซิร์ฟเวอร์ในโปรเซสเดียว)
    handler = type("BoundHandler", (Handler,), {
        "engine": engine, "max_bytes": int(max_bytes), "max_seconds": float(max_seconds),
        "inflight": threading.BoundedSemaphore(max(1, int(inflight))),
        "decode_gate": threading.BoundedSemaphore(max(1, int(decode_concurrency)))})
    if decoder is not None:
        handler.decoder = staticmethod(decoder)
    return Server((HOST, int(port)), handler)


def _idle_loop(engine: Engine, stop: threading.Event) -> None:
    # ทุก 1 วินาที (เดิม 30): การจอดโมเดล GPU หลังงานต้องเกิดภายในไม่กี่วินาที ก่อนผู้ใช้กดส่งข้อความที่พูดไว้
    # แล้ว router โหลดโมเดลแชต — idle_tick แค่เทียบเวลา ไม่มีงานหนักถ้ายังไม่ถึงเวลา
    while not stop.wait(IDLE_TICK_S):
        try:
            engine.idle_tick()
        except Exception:                      # noqa: BLE001
            log("idle tick failed: %s" % traceback.format_exc()[-400:])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Local speech-to-text service (faster-whisper)")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--model", default=os.environ.get("QWEN_STT_MODEL") or "auto",
                    help="auto | large-v3-turbo | small | ... | path to a CTranslate2 model folder")
    ap.add_argument("--device", default=os.environ.get("QWEN_STT_DEVICE") or "auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--min-free-mb", type=int, default=MIN_FREE_MB_DEFAULT)
    ap.add_argument("--threads", type=int, default=THREADS_DEFAULT)
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT)
    ap.add_argument("--max-seconds", type=float, default=MAX_SECONDS_DEFAULT)
    ap.add_argument("--idle-unload-min", type=float, default=IDLE_UNLOAD_MIN_DEFAULT,
                    help="unload the model after this many idle minutes (0 = keep loaded)")
    ap.add_argument("--gpu-hold-s", type=float, default=GPU_HOLD_S_DEFAULT,
                    help="move GPU weights to system RAM this many seconds after a job, so the chat model's "
                         "-fit sees free VRAM (negative = keep them on the GPU until the idle unload)")
    ap.add_argument("--no-preload", action="store_true", help="load the model on the first request")
    ap.add_argument("--primary-language", default=os.environ.get("QWEN_STT_PRIMARY_LANG") or PRIMARY_LANGUAGE_DEFAULT,
                    help="auto mode keeps this language for the whole clip when the first 30 s are in it")
    ap.add_argument("--languages", default=os.environ.get("QWEN_STT_LANGUAGES") or ",".join(LANGUAGES_DEFAULT),
                    help="languages auto mode may pick (comma list; 'any' = no limit). Outside this set, or an "
                         "unsure other language on a short clip, it transcribes in the hint/primary language")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                          # noqa: BLE001
        pass
    if not (1024 <= args.port <= 65535):
        print("bad --port", file=sys.stderr)
        return 2
    forbid_outbound()
    try:
        secrets_util.get_token()               # สร้าง/ตรวจไฟล์ token (ไม่แสดงค่า) — อ่านไม่ได้ = ทุกคำขอได้ 401
        token_state = "ready"
    except Exception as exc:                   # noqa: BLE001
        token_state = "error %s" % type(exc).__name__
    langs = () if args.languages.strip().lower() in ("any", "all", "*", "") else \
        tuple(x for x in args.languages.replace(" ", "").lower().split(",") if x)
    engine = Engine(model=args.model, device=args.device, min_free_mb=args.min_free_mb, threads=args.threads,
                    idle_unload_min=args.idle_unload_min, primary_language=args.primary_language,
                    gpu_hold_s=args.gpu_hold_s, languages=langs)
    try:
        srv = make_server(engine, args.port, args.max_bytes, args.max_seconds)
    except OSError as exc:
        print("cannot listen on %s:%d (%s)" % (HOST, args.port, exc), file=sys.stderr, flush=True)
        return 3
    log("%s %s listening on http://%s:%d python=%s token=%s model=%s path=%s languages=%s" % (
        SERVER_NAME, VERSION, HOST, args.port, sys.executable, token_state, engine.name or "-", engine.path or "-",
        ",".join(engine.languages) or "any"))
    stop = threading.Event()
    threading.Thread(target=_idle_loop, args=(engine, stop), daemon=True, name="stt-idle").start()
    if not args.no_preload and engine.path:
        def _preload():
            try:
                engine.load()
            except EngineUnavailable:
                pass
        threading.Thread(target=_preload, daemon=True, name="stt-preload").start()
    try:
        srv.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
