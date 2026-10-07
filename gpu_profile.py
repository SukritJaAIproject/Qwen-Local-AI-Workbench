# -*- coding: utf-8 -*-
"""
gpu_profile.py — จัดว่าโมเดลไหนใช้ GPU ไหน ตาม GPU ที่ต่ออยู่ตอนนี้ แล้วเขียน preset ให้ llama-server router

ทำไมต้องมี
  เครื่องนี้มี GPU ในเครื่อง 6 GB (RTX 1000 Ada) และจะต่อ eGPU ผ่าน Thunderbolt 4 ทีละตัวหรือสองตัว
  (RTX 4060 Ti 8 GB / RTX 4090 24 GB) แล้วถอดออกเมื่อไหร่ก็ได้  -fit on ของ llama.cpp จัดชั้นลง GPU
  ให้เองก็จริง แต่ตัดสินใจทีละโมเดลโดยไม่รู้ว่าโมเดลอื่นจะใช้ GPU ไหน ถ้าปล่อยไว้ 27B จะถูกหั่น
  ข้าม 4090 กับ GPU ในเครื่อง (GPU เล็กช้ากว่ามาก ทุกโทเคนต้องรอมัน) และ 4B ที่โหลดคู่กันจะไปแย่ง
  ที่บน 4090 ไฟล์นี้จึงตัดสินใจระดับ "ทั้งชุด" ว่าโมเดลไหนได้ GPU ไหน แล้วปล่อยรายละเอียด
  (กี่ชั้น แบ่งยังไง) ให้ -fit ทำตอนโหลดเหมือนเดิม

ผลลัพธ์ (ตัวเปิด start-qwen38.ps1 เรียก --write ทุกครั้งที่เปิด)
  C:\\LLM\\models-preset.ini   ส่งให้ router ด้วย --models-preset — สร้างใหม่ทุกครั้ง ห้ามแก้มือ
  C:\\LLM\\gpu-profile.json    สรุปให้ hub / gpu_bench.py / ตัวเปิด
  (เฉพาะ router พอร์ตหลัก 8099 — พอร์ตทดสอบใช้ C:\\LLM\\logs\\gpu-<port>\\ ดู published_dir())
  ค่าที่อยากกำหนดเองใส่ C:\\LLM\\models-preset.user.ini (merge ทับทีหลังสุด; key ว่าง = ลบ key นั้น)
  ตัวอย่าง: ดูรูปได้ทุกครั้งแม้ไม่ได้ต่อ 4090 / ให้ Coder ใช้ 4090 ด้วย
    [Qwen3.8-27B-UD-Q4_K_M]
    mmproj = C:\\LLM\\models\\mmproj-Qwen3.8-27B-F16.gguf
    [Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL]
    device = CUDA1,CUDA0

GPU ที่ผู้ใช้เลือกเองในหน้าแชต (เมนูบัญชี → เลือก GPU…) — C:\\LLM\\gpu-choice.json (hub เขียน ไฟล์นี้แค่อ่าน)
  {"version":1,"updated_at":"...","models":{"<model id>": "auto" | "cpu" | ["<GPU key>", ...]}}
  GPU key = ชื่อเต็มของการ์ด (เช่น "NVIDIA GeForce RTX 4090") ไม่ใช่ CUDAn เพราะเลข CUDA เลื่อนทุกครั้ง
  ที่เสียบ/ถอด eGPU; การ์ดชื่อซ้ำกันใบที่ 2, 3 (ตามลำดับ PCI bus ในบรรดาใบที่ต่ออยู่ตอนนั้น) ต่อท้าย " #2", " #3"
  — ดู assign_gpu_keys() (ถอดใบแรกของรุ่นซ้ำออก ใบที่เหลือได้ชื่อเฉยๆ แทน)
  ลำดับความสำคัญ: แผนอัตโนมัติ < gpu-choice.json < models-preset.user.ini (แก้มือชนะเสมอ)
  ย้ายโมเดลหลักไปจากที่แผนเลือก → โมเดลอื่นที่เป็น "auto" จัดใหม่ให้หลบการ์ดของมัน (ดู apply_choices())

ใช้เป็นโมดูล (import แล้วไม่มีผลข้างเคียง — ไม่เรียกโปรแกรม ไม่เขียนไฟล์จนกว่าจะเรียกฟังก์ชัน)
  current_fingerprint()   hub เรียก (แคช 30 วินาที) เพื่อดูว่ามีการเสียบ/ถอด GPU หรือเปล่า
  discover_live(timeout)  GPU ที่ต่ออยู่ตอนนี้พร้อม key/งบ (QWEN_GPU_SIMULATE=<ไฟล์> = ใช้ GPU จำลอง)
  model_catalog(dir)      ขนาด/หน่วยความจำที่แต่ละโมเดลต้องใช้ ให้หน้าเลือก GPU บอกว่า "พอดีไหม"
  validate_choice(...)    ตรวจสิ่งที่หน้าเว็บส่งมาก่อน hub เขียน gpu-choice.json (save_choice เขียนแบบ atomic)
ใช้ได้เฉพาะ stdlib เพราะรันด้วย C:\\Python313\\python.exe ที่ไม่ได้ลงแพ็กเกจอะไรไว้
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime
import difflib
import hashlib
import json
import mmap
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------- ที่อยู่ไฟล์
LLAMA_SERVER = r"C:\LLM\llama.cpp-b10984\llama-server.exe"
DEFAULT_MODELS_DIR = r"C:\LLM\models"
DEFAULT_OUT_DIR = r"C:\LLM"
LOG_DIR = r"C:\LLM\logs"
DEFAULT_PORT = 8099                # router ตัวจริงที่ hub ต่ออยู่ — มีแค่พอร์ตนี้ที่เขียนไฟล์กลางใน C:\LLM
PRESET_NAME = "models-preset.ini"
PROFILE_NAME = "gpu-profile.json"
USER_INI = r"C:\LLM\models-preset.user.ini"
# GPU ที่ผู้ใช้เลือกในหน้าแชต — hub เป็นคนเขียนคนเดียว ไฟล์นี้แค่อ่าน (--choice none = ไม่อ่าน)
CHOICE_FILE = r"C:\LLM\gpu-choice.json"
# ให้ hub ตรวจ GPU แบบจำลองได้ (ทดสอบหน้าจอ) — ใช้เฉพาะ discover_live() เท่านั้น ห้ามให้ generate() อ่าน
# ไม่งั้นตัวเปิดตัวจริงที่ hub สั่งรันจะสืบทอดตัวแปรนี้ไปแล้วเขียนแผนของ GPU ปลอมให้ router ตัวจริง
SIMULATE_ENV = "QWEN_GPU_SIMULATE"
NVIDIA_SMI = "nvidia-smi"

# ---------------------------------------------------------------- ค่าคงที่ของนโยบาย
# ลำดับ CUDA ปริยายคือ "เร็วสุดก่อน" พอเสียบ 4090 มันจะกลายเป็น CUDA0 แล้ว GPU ในเครื่องเลื่อนไป CUDA1
# preset ที่เขียน device = CUDA0 ไว้จะชี้ผิดตัวทันที  PCI_BUS_ID ทำให้ชื่อคงที่ (eGPU ทาง Thunderbolt
# ได้ bus number สูงกว่าเสมอ) — ต้องตั้งค่าเดียวกันทั้งตอนตรวจและตอนเปิด router
CUDA_DEVICE_ORDER = "PCI_BUS_ID"
NVIDIA_SMI_TIMEOUT_S = 5
LIST_DEVICES_TIMEOUT_S = 20        # ปกติ ~0.7 วินาที แต่ eGPU ที่เพิ่งเสียบอาจ init ช้า
RESERVE_MIB = 1024                 # = --fit-target ปริยายของ llama.cpp (ขอบที่ -fit เว้นไว้ต่อ GPU)
# การ์ดที่งบ (หน่วยความจำทั้งหมด − ขอบ) ต่ำกว่านี้ไม่นับเป็น "GPU ที่เหลือ" ให้โมเดลอื่น: ผูกโมเดลไว้กับการ์ด
# ที่ -fit วางอะไรแทบไม่ได้ เท่ากับส่งไปรัน CPU ทั้งที่การ์ดของโมเดลหลักยังมีที่ว่าง
MIN_USEFUL_GPU_MIB = 2048
COMPUTE_OVERHEAD_GIB = 1.5         # compute buffer + CUDA context + state ของชั้น SSM โดยประมาณ
BASE_CTX = 32768                   # ค่าที่ใช้มาตลอด (ตัวเปิดเดิม -c 32768)
PRIMARY_CTX_CANDIDATES = (65536, 32768)   # ถ้าโมเดลหลักได้ GPU ใหญ่ทั้งตัว ลองขยาย context ก่อน
CACHE_TYPE = "q8_0"                # KV cache ครึ่งหนึ่งของ f16 ต่างกันน้อยมากเมื่อเปิด flash attention
DEFAULT_THREADS = 6                # เฉพาะ P-core ของ Core Ultra 7 165H — วัดแล้วเร็วสุด
PRIMARY_HINT = "qwen3.8"           # โมเดลหลักคือโมเดลที่ชื่อมีคำนี้ (หรือ --primary)
# มีหลายไฟล์ที่ชื่อมี qwen3.8 (เช่นเพิ่ม Q8_0 เข้ามา) ให้ตัวนี้ชนะ — ตรงกับ $Model ของ start-qwen38.ps1
# ไม่งั้นลำดับตัวอักษรจะเลือกตัวใหม่ให้เงียบๆ และแผนทั้งชุดเปลี่ยนตาม
DEFAULT_PRIMARY = "Qwen3.8-27B-UD-Q4_K_M"
INTERNAL_NAME_HINT = "laptop"      # ชื่อ GPU ที่มีคำนี้ = GPU ในตัวเครื่อง ที่เหลือถือว่าเป็น eGPU
# ไบต์ต่อ element ของ KV cache แต่ละชนิด (block 32 ค่า + scale)
CACHE_BYTES_PER_ELEM = {"f32": 4.0, "f16": 2.0, "bf16": 2.0, "q8_0": 34 / 32, "q5_1": 24 / 32,
                        "q5_0": 22 / 32, "q4_1": 20 / 32, "q4_0": 18 / 32, "iq4_nl": 18 / 32}
# สถาปัตยกรรมที่มี sliding window แต่ GGUF ไม่ได้เก็บ pattern ไว้ — llama.cpp ฝังค่าไว้ในโค้ด
# (n = ทุก n ชั้นมีชั้น attention เต็ม 1 ชั้น ที่เหลือเป็น window)
KNOWN_SWA_PATTERN = {"gpt-oss": 2, "gemma2": 2, "gemma3": 6, "cohere2": 4}

# ---------------------------------------------------------------- ค่าประมาณความเร็ว
# การสร้างโทเคนถูกจำกัดด้วยแบนด์วิดท์หน่วยความจำ: ทุกโทเคนต้องอ่าน weight ที่ใช้ครบหนึ่งรอบ
# ตัวเลขนี้แค่ให้ผู้ใช้เห็นภาพ ค่าจริงให้วัดด้วย gpu_bench.py
GPU_BANDWIDTH_GBPS = (            # (คำในชื่อ ตัวพิมพ์เล็ก, GB/s) — ตัวที่เจาะจงกว่าต้องมาก่อน
    ("4090 laptop", 576), ("4090", 1008), ("4080", 717), ("4070 ti", 504), ("4070", 504),
    ("4060 ti", 288), ("4060 laptop", 256), ("4060", 272), ("3090", 936), ("3080", 760),
    ("rtx 6000 ada", 960), ("a6000", 768), ("rtx 1000 ada", 192), ("rtx 2000 ada", 224),
)
DEFAULT_GPU_BANDWIDTH_GBPS = 250
GPU_BW_EFFICIENCY = 0.6            # llama.cpp ได้จริงราว 60% ของแบนด์วิดท์บนสเปก
# CPU (6 P-core, เครื่องถูก throttle) อ่าน weight ได้จริงเท่าไร ขึ้นกับว่ามีงานอื่นกิน CPU อยู่ไหม — วัดบนเครื่องนี้ 2026-09-29:
#   เครื่องว่าง: 27B (RTX 1000 + CPU) 2.07-2.18 tok/s, 4B บน CPU ล้วน 13.4 tok/s → ราว 27 GB/s
#   ตอนมีงาน benchmark อื่นของผู้ใช้กิน CPU อยู่: 27B ได้ 1.2-1.4 tok/s → ราว 17 GB/s
# จึงแสดงเป็นช่วง ตั้งแต่ "CPU มีงานอื่น" ถึง "เครื่องว่าง" ไม่ใช่ตัวเลขเดียว
CPU_EFFECTIVE_GBPS = 27
CPU_BUSY_GBPS = 17
SPEED_RANGE = (0.85, 1.15)         # ขยายช่วงอีก ±15% เพราะเป็นค่าประมาณ

GIB = 1024 ** 3
MIB = 1024 ** 2
GB = 1e9
PROFILE_VERSION = 1
STATE_VERSION = 1
HTTP_TIMEOUT_S = 10
IDLE_POLL_S = 3
# ต้องว่างต่อเนื่องอย่างน้อยเท่านี้ก่อนรีสตาร์ต: ระหว่างที่เครื่องมือ MCP (ค้นเว็บ/รันคำสั่ง) ทำงานกลางคำตอบ
# slot จะว่างชั่วคราวแล้วค่อยรับเทิร์นถัดไป ถ้าดูแค่ครั้งเดียวจะตัดคำตอบนั้นกลางคัน
IDLE_QUIET_S = 9
EXIT_OK, EXIT_ERROR, EXIT_CHANGED, EXIT_BUSY, EXIT_KEEP_LEGACY = 0, 2, 10, 11, 12
# router ปฏิเสธโทเคนปัจจุบัน (401) — ไฟล์โทเคนถูกสร้างใหม่หลัง router เริ่ม ตัวเปิดรีสตาร์ต router ได้ทันที
# เพราะ hub/Gateway ที่ใช้โทเคนชุดใหม่คุยกับ router ตัวนี้ไม่ได้อยู่แล้ว (ไม่มีแชตของเราให้รอ)
EXIT_AUTH = 13

# โทเคนของบริการในเครื่อง (สัญญา C1) — router เปิดด้วย --api-key-file ไฟล์นี้ (ตัวเปิด 2026-09-30)
# ทุกคำขอถึง router ยกเว้น /health ต้องมี "Authorization: Bearer <โทเคน>" ไม่งั้น 401 (วัดบน b10984: /models,
# /v1/models, /slots, /props ก็ต้องใช้) — อ่านเองตรงนี้แทน import secrets_util เพราะ hub โหลดไฟล์นี้จาก path
# (ไม่มี C:\LLM ใน sys.path) และห้ามสร้างไฟล์โทเคนจากตรงนี้: ถ้าไม่มีไฟล์ router ก็ไม่ได้เปิดด้วยคีย์อยู่แล้ว
LOCAL_TOKEN_FILE = r"C:\LLM\secrets\local-services.token"
LOCAL_TOKEN_ENV = "LLM_LOCAL_TOKEN_FILE"
_LOCAL_TOKEN_RE = re.compile(r"[0-9a-fA-F]{64}")
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost")

# gpu-choice.json — ขีดจำกัดเดียวกันทั้งตอน hub ตรวจก่อนเขียน (validate_choice) และตอนอ่าน (read_choice)
CHOICE_VERSION = 1
CHOICE_AUTO, CHOICE_CPU = "auto", "cpu"
CHOICE_KEY_MAX = 120               # ชื่อการ์ดจริงยาวไม่ถึง 60 ตัว — ยาวกว่านี้คือข้อมูลเสีย
CHOICE_LIST_MAX = 8                # Thunderbolt + ในเครื่อง ต่อได้ไม่กี่ใบ
# ไฟล์ที่ hub เขียนจริงราว 0.5 KB ต่อโมเดล (8 key × 120 ตัวอักษรยังไม่ถึง 1.1 KB) — ใหญ่กว่านี้มากคือไฟล์เสีย
CHOICE_FILE_MAX = 256 * 1024
KEY_NAME_MAX = CHOICE_KEY_MAX - 4  # เผื่อที่ให้ " #9" ต่อท้ายแล้วยังไม่เกินขีดของ validate_choice
# ช่อง placement ที่ติดป้าย "มาจากไหน" — ต้องตามไปด้วยทุกครั้งที่คิด placement_entry ใหม่
_CHOICE_FIELDS = ("source", "choice", "choice_missing", "choice_dropped", "choice_overridden", "auto")

# key ที่ router ส่งต่อให้โมเดลลูกและเราใช้เทียบว่า "ค่าเปลี่ยนไหม" (ชื่อยาวตาม preset)
TRACKED_KEYS = ("ctx-size", "cache-type-k", "cache-type-v", "threads", "device", "mmproj")
ARG_ALIASES = {"-c": "ctx-size", "--ctx-size": "ctx-size", "-ctk": "cache-type-k",
               "--cache-type-k": "cache-type-k", "-ctv": "cache-type-v", "--cache-type-v": "cache-type-v",
               "-t": "threads", "--threads": "threads", "-dev": "device", "--device": "device",
               "-mm": "mmproj", "--mmproj": "mmproj"}

# subprocess จาก hub (หน้าต่างซ่อน) ห้ามเด้งหน้าต่าง console ขึ้นมา
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class DiscoveryError(RuntimeError):
    """ตรวจ GPU ไม่สำเร็จ (ไม่มีโปรแกรม / ค้าง / ผลอ่านไม่ออก)"""


def published_dir(port):
    """โฟลเดอร์ของ preset + json ที่ router พอร์ตนั้นใช้จริง

    พอร์ตหลัก (8099) = C:\\LLM ซึ่ง hub และ gpu_bench อ่าน  พอร์ตทดสอบแยกไป C:\\LLM\\logs\\gpu-<port>
    ไม่งั้น router ทดสอบ (หรือรอบที่ซ่อน GPU ด้วย CUDA_VISIBLE_DEVICES) จะเขียนทับแผนของตัวจริง แล้ว hub
    แสดง GPU ผิด  start-qwen38.ps1 ใช้กฎเดียวกันนี้ ($PubDir) ถ้าแก้ที่หนึ่งต้องแก้อีกที่ด้วย
    """
    port = int(port)
    return DEFAULT_OUT_DIR if port == DEFAULT_PORT else os.path.join(LOG_DIR, "gpu-%d" % port)


# ================================================================ ตรวจ GPU
def _run(cmd, timeout, env=None):
    r = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=timeout, env=env, creationflags=_NO_WINDOW)
    return (r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace"))


def _smi_query(fields, timeout=NVIDIA_SMI_TIMEOUT_S, exe=None):
    """แถวจาก nvidia-smi เป็น list ของ list — None ถ้าไม่มีโปรแกรม ล้ม หรือค้าง"""
    try:
        rc, out, _err = _run([exe or NVIDIA_SMI, "--query-gpu=" + fields, "--format=csv,noheader,nounits"],
                             timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    if rc != 0:
        return None
    n = len(fields.split(","))
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != n:
            return None
        rows.append(parts)
    return rows


def fingerprint_from_rows(rows):
    """sha1 ของบรรทัด "name|memory.total|pci.bus_id" ที่เรียงแล้ว — ไม่ขึ้นกับลำดับ CUDA"""
    lines = sorted("%s|%s|%s" % (name, total, bus) for name, total, bus in rows)
    return hashlib.sha1("\n".join(lines).encode("utf-8")).hexdigest()


def current_fingerprint(timeout=NVIDIA_SMI_TIMEOUT_S, exe=None):
    """ลายนิ้วมือของชุด GPU ที่ต่ออยู่ตอนนี้ — None ถ้า nvidia-smi ไม่มีหรือล้ม

    ใช้ nvidia-smi อย่างเดียว (~0.2 วินาที) เพราะ hub เรียกบ่อย และค่า memory.total ของ
    nvidia-smi กับ --list-devices ต่างกันได้ 1 MiB จึงห้ามเอาสองแหล่งมาปนกัน
    """
    rows = _smi_query("name,memory.total,pci.bus_id", timeout, exe)
    if rows is None:
        return None
    return fingerprint_from_rows(rows)


_LIST_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*?\d+):\s+(.+?)\s+\((\d+)\s*MiB,\s*(\d+)\s*MiB free\)\s*$")


def parse_list_devices(text):
    """แปลงผล llama-server --list-devices → [{id,name,total_mib,free_mib}] ([] = "(none)")"""
    lines = text.splitlines()
    try:
        start = next(i for i, l in enumerate(lines) if l.strip().startswith("Available devices"))
    except StopIteration:
        raise DiscoveryError("ไม่พบบรรทัด 'Available devices' ในผลของ --list-devices")
    devices = []
    for l in lines[start + 1:]:
        m = _LIST_RE.match(l)
        if m:
            devices.append({"id": m.group(1), "name": m.group(2), "total_mib": int(m.group(3)),
                            "free_mib": int(m.group(4))})
    return devices


def list_devices_llama(exe=LLAMA_SERVER, timeout=LIST_DEVICES_TIMEOUT_S, cmd=None):
    """ถาม llama-server เองว่าเห็น GPU อะไร (ชื่อ CUDAn ตรงกับที่ router จะใช้จริง)"""
    env = dict(os.environ)
    env["CUDA_DEVICE_ORDER"] = CUDA_DEVICE_ORDER
    try:
        _rc, out, err = _run(cmd or [exe, "--list-devices"], timeout, env)
    except subprocess.TimeoutExpired:
        raise DiscoveryError("llama-server --list-devices ค้างเกิน %d วินาที" % timeout)
    except OSError as e:
        raise DiscoveryError("เรียก llama-server --list-devices ไม่ได้: %s" % e)
    return parse_list_devices(out + "\n" + err)


def short_name(name):
    """"NVIDIA RTX 1000 Ada Generation Laptop GPU" → "RTX 1000 Ada", "NVIDIA GeForce RTX 4090" → "RTX 4090\""""
    drop = {"nvidia", "geforce", "generation", "laptop", "gpu"}
    words = [w for w in str(name or "").split() if w.lower() not in drop]
    return " ".join(words) or str(name or "GPU")


def is_internal(name):
    return INTERNAL_NAME_HINT in str(name or "").lower()


def bandwidth_gbps(name):
    low = str(name or "").lower()
    for key, bw in GPU_BANDWIDTH_GBPS:
        if key in low:
            return bw
    return DEFAULT_GPU_BANDWIDTH_GBPS


def _finish_device(d):
    d = dict(d)
    d["id"] = str(d["id"])
    d["name"] = str(d.get("name") or d["id"])
    d["total_mib"] = int(d.get("total_mib") or 0)
    d["free_mib"] = int(d.get("free_mib") if d.get("free_mib") is not None else d["total_mib"])
    d.setdefault("pci_bus_id", None)
    d["short"] = short_name(d["name"])
    if "external" not in d:
        d["external"] = not is_internal(d["name"])
    d["bandwidth_gbps"] = bandwidth_gbps(d["name"])
    return d


def _attach_bus_ids(devices, smi):
    """เติม pci_bus_id ให้รายการจาก --list-devices ด้วยข้อมูล nvidia-smi

    ภายใต้ CUDA_DEVICE_ORDER=PCI_BUS_ID ลำดับ CUDAn = ลำดับ bus id จึงจับคู่ตามลำดับได้
    แต่ถ้าจำนวน/ชื่อไม่ตรง (เช่นมีคนตั้ง CUDA_VISIBLE_DEVICES) ใช้ชื่อที่ไม่ซ้ำแทน ไม่เดา
    """
    if not smi:
        return
    ordered = sorted(smi, key=lambda r: r["pci_bus_id"])
    if len(ordered) == len(devices) and all(a["name"] == b["name"] for a, b in zip(devices, ordered)):
        for d, r in zip(devices, ordered):
            d["pci_bus_id"] = r["pci_bus_id"]
        return
    for d in devices:
        same = [r for r in ordered if r["name"] == d["name"]]
        if len(same) == 1:
            d["pci_bus_id"] = same[0]["pci_bus_id"]


def _smi_devices():
    """(รายการ GPU จาก nvidia-smi, fingerprint) — (None, None) ถ้า nvidia-smi ใช้ไม่ได้

    fingerprint คิดจากแถวดิบชุดเดียวกัน (ค่าเหมือน current_fingerprint() ทุกตัวอักษร) ไม่เรียก nvidia-smi
    ซ้ำอีกรอบ — รอบที่สองอาจล้มชั่วคราวได้ โปรไฟล์จะได้ fingerprint = null ทั้งที่ตรวจ GPU ได้ปกติ
    """
    rows = _smi_query("name,memory.total,memory.free,pci.bus_id")
    if rows is None:
        return None, None
    out = []
    for name, total, free, bus in rows:
        try:
            out.append({"name": name, "total_mib": int(float(total)), "free_mib": int(float(free)),
                        "pci_bus_id": bus})
        except ValueError:
            return None, None
    return out, fingerprint_from_rows((name, total, bus) for name, total, _free, bus in rows)


def load_simulation(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        doc = json.load(f)
    items = doc.get("devices") if isinstance(doc, dict) else doc
    if not isinstance(items, list):
        raise ValueError("--simulate ต้องเป็น list ของ GPU หรือ {\"devices\": [...]}")
    devices = []
    for i, d in enumerate(items):
        if not isinstance(d, dict) or "name" not in d or "total_mib" not in d:
            raise ValueError("--simulate รายการที่ %d ต้องมีอย่างน้อย name และ total_mib" % i)
        d = dict(d)
        d.setdefault("id", "CUDA%d" % i)
        d.setdefault("pci_bus_id", "00000000:%02X:00.0" % (i + 1))
        devices.append(_finish_device(d))
    return devices


def _bus_sort_key(bus):
    """"00000000:2C:00.0" → (0, (0, 0x2C, 0, 0)) เรียงตามตัวเลขจริง — รูปแบบแปลกเรียงตามตัวอักษรไว้ท้าย"""
    parts = re.split(r"[:.]", str(bus or "").strip())
    try:
        return (0, tuple(int(p, 16) for p in parts))
    except ValueError:
        return (1, str(bus or "").lower())


def assign_gpu_keys(devices):
    """ใส่ d["key"] = ตัวตนของการ์ดที่ไม่เปลี่ยนเมื่อเลข CUDA เลื่อน (เก็บใน gpu-choice.json)

    ใช้ชื่อเต็มจาก --list-devices เพราะเสียบ eGPU แล้ว CUDA0/1/2 สลับกันได้ แต่ชื่อรุ่นไม่เปลี่ยน
    การ์ดชื่อซ้ำ (เช่น 4090 สองใบ) ใบแรกตามลำดับ PCI bus ได้ชื่อเฉยๆ ใบที่ 2, 3 ต่อท้าย " #2", " #3"
    ข้อจำกัดที่ยอมรับไว้ (ตามสัญญาของ gpu-choice.json): เลขต่อท้ายคือ "ลำดับในกลุ่มชื่อเดียวกันที่ต่ออยู่ตอนนี้"
    ไม่ใช่ตัวตนของพอร์ต — ต่อครบทุกใบ key ไม่เปลี่ยนแม้เลข CUDA เลื่อน แต่ถ้าถอดใบที่ bus ต่ำกว่าออก ใบที่เหลือ
    ได้ชื่อเฉยๆ แทน: ที่เลือก "... #2" ไว้กลายเป็น "ไม่ได้ต่ออยู่" (ใช้อัตโนมัติ + choice_missing) และที่เลือกชื่อเฉยๆ
    ไว้ไปใช้ใบที่เหลือ ซึ่งเป็นการ์ดรุ่นเดียวกัน ผลเท่ากัน  ไม่ใช้ bus id ใน key เพราะเลข bus ของ Thunderbolt
    ขึ้นกับลำดับการเสียบ/dock ด้วย ไม่ได้คงที่ต่อพอร์ตเสมอไป และจะทำให้ key ของการ์ดใบเดียวต่างกันไปตามช่องที่เสียบ
    ไม่มี bus id ครบทุกใบในกลุ่ม (nvidia-smi ล้ม) → ใช้ลำดับในรายการ ซึ่งภายใต้ CUDA_DEVICE_ORDER=PCI_BUS_ID
    ก็คือลำดับ bus อยู่แล้ว  แก้ dict ในรายการโดยตรง (เรียกซ้ำได้ ผลเท่าเดิม) และคืนรายการเดิม
    """
    groups = {}
    for i, d in enumerate(devices or []):
        base = (str(d.get("name") or d.get("id") or "GPU").strip() or "GPU")[:KEY_NAME_MAX]
        groups.setdefault(base, []).append((i, d))
    for base, members in groups.items():
        if len(members) > 1 and all(d.get("pci_bus_id") for _i, d in members):
            members = sorted(members, key=lambda m: (_bus_sort_key(m[1]["pci_bus_id"]), m[0]))
        for n, (_i, d) in enumerate(members, 1):
            d["key"] = base if n == 1 else "%s #%d" % (base, n)
    return devices


def discover(exe=LLAMA_SERVER, simulate=None, warnings=None, timeout=LIST_DEVICES_TIMEOUT_S):
    """คืน (devices หรือ None ถ้าตรวจไม่ได้เลย, แหล่งที่มา, fingerprint) — ทุกใบมี key แล้ว"""
    devices, source, fp = _discover(exe, simulate, warnings, timeout)
    if devices is not None:
        assign_gpu_keys(devices)
    return devices, source, fp


def _discover(exe, simulate, warnings, timeout):
    warnings = warnings if warnings is not None else []
    if simulate:
        devices = load_simulation(simulate)
        fp = fingerprint_from_rows((d["name"], d["total_mib"], d["pci_bus_id"]) for d in devices)
        return devices, "simulate", fp
    smi, fp = _smi_devices()
    try:
        devices = [_finish_device(d) for d in list_devices_llama(exe, timeout)]
        source = "list-devices"
        _attach_bus_ids(devices, smi)
        if smi is not None and len(devices) < len(smi):
            # เช่นมีคนตั้ง CUDA_VISIBLE_DEVICES ไว้ — router ที่เปิดจาก process นี้ก็จะเห็นเท่านี้เหมือนกัน
            # แผนจึงยังถูกสำหรับ router ตัวนั้น แต่ต้องบอกให้รู้ ไม่งั้นจะงงว่าทำไม eGPU ไม่ถูกใช้
            warnings.append("llama-server เห็น GPU %d ตัว แต่ nvidia-smi เห็น %d ตัว (ตั้ง CUDA_VISIBLE_DEVICES "
                            "ไว้หรือเปล่า?) — แผนนี้ใช้เฉพาะ GPU ที่ llama-server เห็น" % (len(devices), len(smi)))
    except DiscoveryError as e:
        if smi is None:
            warnings.append("ตรวจ GPU ไม่ได้ทั้งจาก llama-server และ nvidia-smi (%s) — ใช้ค่าแบบเดิม" % e)
            return None, "failed", fp
        # nvidia-smi เรียงตาม bus id เสมอ = ลำดับเดียวกับ CUDA ภายใต้ PCI_BUS_ID
        warnings.append("%s — ใช้รายการจาก nvidia-smi แทน" % e)
        devices = [_finish_device(dict(r, id="CUDA%d" % i))
                   for i, r in enumerate(sorted(smi, key=lambda r: r["pci_bus_id"]))]
        source = "nvidia-smi"
    return devices, source, fp


def public_device(d):
    """ข้อมูลของการ์ดหนึ่งใบที่ส่งให้ hub / เขียนลง gpu-profile.json (budget_mib = งบที่แผนใช้ ดู budget_bytes)"""
    return {"id": d.get("id"), "key": d.get("key"), "name": d.get("name"), "short": d.get("short"),
            "total_mib": d.get("total_mib"), "free_mib": d.get("free_mib"),
            "budget_mib": max(0, int(d.get("total_mib") or 0) - RESERVE_MIB),
            "external": d.get("external"), "pci_bus_id": d.get("pci_bus_id"),
            "bandwidth_gbps": d.get("bandwidth_gbps")}


def discover_live(timeout=LIST_DEVICES_TIMEOUT_S, exe=LLAMA_SERVER, details=False):
    """GPU ที่ต่ออยู่ตอนนี้สำหรับหน้าเลือก GPU ของ hub — วิธีตรวจเดียวกับ generate() ทุกอย่าง

    คืน list ของ public_device() (id, key, name, short, total_mib, free_mib, budget_mib, external, ...)
    details=True คืน {"devices", "fingerprint", "source", "warnings"} แทน (fingerprint เทียบกับ
    gpu-profile.json ได้ตรงตัว เพราะคิดจากแถว nvidia-smi ชุดเดียวกับที่ generate() ใช้)
    ตรวจไม่ได้ทั้งสองทาง → DiscoveryError (ห้ามคืน [] เพราะหน้าเว็บจะเข้าใจว่า "เครื่องนี้ไม่มี GPU")
    env QWEN_GPU_SIMULATE=<ไฟล์ JSON> = ใช้ GPU จำลองแทนการตรวจจริง (ทดสอบหน้าจอเท่านั้น)
    ใช้เวลาได้ถึง nvidia-smi 5 วินาที + timeout — ผู้เรียกต้องเรียกนอกเธรดที่ตอบคำขอ
    """
    warnings = []
    simulate = os.environ.get(SIMULATE_ENV) or None
    devices, source, fp = discover(exe, simulate, warnings, timeout=timeout)
    if devices is None:
        raise DiscoveryError("; ".join(warnings) or "ตรวจ GPU ไม่ได้")
    live = [public_device(d) for d in devices]
    if details:
        return {"devices": live, "fingerprint": fp, "source": source, "warnings": warnings}
    return live


# ================================================================ อ่าน GGUF
_GGUF_SCALAR = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?",
                10: "<Q", 11: "<q", 12: "<d"}
_GGUF_STRING, _GGUF_ARRAY = 8, 9
_KEEP_ARRAY_MAX = 4096        # อาร์เรย์ยาวกว่านี้ (vocab) ข้ามไป ไม่ต้องเก็บ
GGUF_DEFAULT_ALIGNMENT = 32


class _Reader:
    def __init__(self, buf):
        self.buf = buf
        self.pos = 0

    def unpack(self, fmt):
        v = struct.unpack_from(fmt, self.buf, self.pos)[0]
        self.pos += struct.calcsize(fmt)
        return v

    def string(self):
        n = self.unpack("<Q")
        if self.pos + n > len(self.buf):
            raise ValueError("สตริงยาวเกินไฟล์")
        s = bytes(self.buf[self.pos:self.pos + n]).decode("utf-8", "replace")
        self.pos += n
        return s

    def value(self, t):
        if t in _GGUF_SCALAR:
            return self.unpack(_GGUF_SCALAR[t])
        if t == _GGUF_STRING:
            return self.string()
        if t == _GGUF_ARRAY:
            et = self.unpack("<I")
            n = self.unpack("<Q")
            if et in _GGUF_SCALAR:
                fmt = _GGUF_SCALAR[et]
                size = struct.calcsize(fmt)
                if n <= _KEEP_ARRAY_MAX:
                    vals = list(struct.unpack_from("<%d%s" % (n, fmt[1]), self.buf, self.pos))
                    self.pos += size * n
                    return vals
                self.pos += size * n
                return None
            if et == _GGUF_STRING:
                for _ in range(n):
                    # ต้องแยกบรรทัด: "self.pos += self.unpack(...)" อ่าน pos ก่อน unpack ขยับ แล้วทับค่าหาย 8 ไบต์
                    ln = self.unpack("<Q")
                    self.pos += ln
                return None
        raise ValueError("ไม่รู้จัก GGUF value type %d" % t)


def read_gguf(path):
    """คืน (metadata, [(ชื่อ tensor, ขนาดไบต์)]) — อ่านแค่ส่วนหัว ไม่โหลด weight

    ขนาด tensor คิดจากระยะห่างของ offset (ไม่ต้องมีตารางขนาดของแต่ละชนิด quant)
    """
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        if size < 24:
            raise ValueError("ไฟล์เล็กเกินกว่าจะเป็น GGUF")
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            r = _Reader(mm)
            if bytes(mm[0:4]) != b"GGUF":
                raise ValueError("ไม่ใช่ไฟล์ GGUF")
            r.pos = 4
            r.unpack("<I")                    # version
            n_tensors = r.unpack("<Q")
            n_kv = r.unpack("<Q")
            meta = {}
            for _ in range(n_kv):
                key = r.string()
                meta[key] = r.value(r.unpack("<I"))
            infos = []
            for _ in range(n_tensors):
                name = r.string()
                n_dims = r.unpack("<I")
                r.pos += 8 * n_dims
                r.unpack("<I")                # ggml type
                infos.append((name, r.unpack("<Q")))
            align = int(meta.get("general.alignment") or GGUF_DEFAULT_ALIGNMENT)
            data_start = (r.pos + align - 1) // align * align
        except struct.error as e:
            raise ValueError("ส่วนหัว GGUF ไม่ครบ (%s)" % e)
        finally:
            mm.close()
    ordered = sorted(infos, key=lambda t: t[1])
    tensors = []
    for i, (name, off) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else size - data_start
        tensors.append((name, max(0, end - off)))
    return meta, tensors


def kv_layout(meta):
    """(element ต่อโทเคนของชั้น attention เต็ม, element ต่อโทเคนของชั้น sliding window, ขนาด window)

    element = kv_heads × (key_len + value_len) รวมทุกชั้นที่มี KV จริง:
      - ชั้น nextn/MTP ท้ายโมเดลไม่นับ (ไม่ได้ใช้)
      - โมเดล hybrid (SSM + attention) นับเฉพาะชั้น attention เต็ม เช่น qwen35 ทุกชั้นที่ 4
      - ชั้น sliding window กินแค่ขนาด window ไม่โตตาม context
    """
    arch = meta.get("general.architecture", "")

    def g(key, default=None):
        v = meta.get("%s.%s" % (arch, key))
        return default if v is None else v

    n_layer = int(g("block_count", 0))
    n_main = max(0, n_layer - int(g("nextn_predict_layers", 0)))
    n_head = g("attention.head_count", 0)
    n_head_s = max(n_head) if isinstance(n_head, list) and n_head else (n_head if isinstance(n_head, int) else 0)
    n_kv = g("attention.head_count_kv", n_head)
    n_embd = int(g("embedding_length", 0))
    k_len = int(g("attention.key_length", 0)) or (n_embd // n_head_s if n_head_s else 0)
    v_len = int(g("attention.value_length", 0)) or k_len
    if isinstance(n_kv, list):
        kv_per_layer = [int(x) for x in n_kv[:n_main]] + [0] * max(0, n_main - len(n_kv))
    else:
        kv_per_layer = [int(n_kv or 0)] * n_main
    interval = int(g("full_attention_interval", 0))
    has_ssm = any(k.startswith(arch + ".ssm.") for k in meta)
    if interval > 0:
        is_attn = [(il + 1) % interval == 0 for il in range(n_main)]
    elif isinstance(n_kv, list):
        is_attn = [h > 0 for h in kv_per_layer]
    elif has_ssm:
        is_attn = [False] * n_main           # SSM ล้วน ไม่มี KV cache
    else:
        is_attn = [True] * n_main
    window = int(g("attention.sliding_window", 0))
    pattern = g("attention.sliding_window_pattern")
    if window > 0 and isinstance(pattern, list):
        is_swa = [bool(pattern[il]) if il < len(pattern) else False for il in range(n_main)]
    elif window > 0:
        n_pat = pattern if isinstance(pattern, int) and pattern > 0 else KNOWN_SWA_PATTERN.get(arch, 0)
        # สูตรเดียวกับ llama_hparams::set_swa_pattern — ไม่รู้ pattern ก็นับเต็มทุกชั้น (ปลอดภัยไว้ก่อน)
        is_swa = [n_pat > 0 and (il % n_pat) < (n_pat - 1) for il in range(n_main)]
    else:
        is_swa = [False] * n_main
    full = swa = 0
    for il in range(n_main):
        if not is_attn[il]:
            continue
        e = kv_per_layer[il] * (k_len + v_len)
        if is_swa[il]:
            swa += e
        else:
            full += e
    return full, swa, (window if swa else 0)


# ================================================================ สแกนโมเดล
_SHARD_RE = re.compile(r"^(?P<base>.+)-(?P<idx>\d{5})-of-(?P<n>\d{5})$")
_BAD_ID_CHARS = set("[]=\r\n")


def valid_model_id(model_id):
    """ชื่อที่เขียนเป็น [section] ของ INI ได้ปลอดภัย — [ ] = ขึ้นบรรทัดใหม่ ทำให้ INI ผิดรูป
    ส่วน ; กับ # ขึ้นต้นจะกลายเป็นคอมเมนต์"""
    return bool(model_id) and not (_BAD_ID_CHARS & set(model_id)) and model_id[0] not in ";#" \
        and model_id == model_id.strip()


@dataclasses.dataclass
class ModelInfo:
    id: str
    path: str
    size_bytes: int
    arch: str = ""
    basename: str = ""
    kv_elems_full: int = 0
    kv_elems_swa: int = 0
    swa_window: int = 0
    expert_bytes: int = 0
    expert_used: int = 0
    expert_count: int = 0
    token_embd_bytes: int = 0
    n_embd: int = 0                  # <arch>.embedding_length — ไว้เช็กว่า mmproj เป็นของโมเดลนี้จริง
    mmproj_path: str | None = None
    mmproj_bytes: int = 0
    shard_ids: list = dataclasses.field(default_factory=list)   # id ของ shard ที่ 2..N ที่ router ก็แสดงด้วย
    error: str | None = None

    def kv_bytes(self, ctx, cache_type=CACHE_TYPE):
        bpe = CACHE_BYTES_PER_ELEM.get(cache_type, 2.0)
        return int(self.kv_elems_full * bpe * ctx + self.kv_elems_swa * bpe * min(self.swa_window, ctx))

    def kv_bytes_per_token(self, cache_type=CACHE_TYPE):
        return self.kv_elems_full * CACHE_BYTES_PER_ELEM.get(cache_type, 2.0)

    def need_bytes(self, ctx, vision=False, cache_type=CACHE_TYPE, mm_bytes=None):
        """weight + mmproj (ถ้าเปิดดูรูป) + KV(ctx) + compute overhead
        mm_bytes = ขนาด mmproj ที่ใช้จริงเมื่อผู้ใช้ชี้ไฟล์อื่นเองใน models-preset.user.ini"""
        if not vision:
            mm = 0
        elif mm_bytes is not None:
            mm = mm_bytes
        else:
            mm = self.mmproj_bytes if self.mmproj_path else 0
        return int(self.size_bytes + mm + self.kv_bytes(ctx, cache_type) + COMPUTE_OVERHEAD_GIB * GIB)


def mmproj_out_dim(path, cache=None):
    """ขนาดเวกเตอร์ที่ mmproj ส่งให้โมเดลภาษา (clip.*.projection_dim) — 0 ถ้าไม่มี key, None ถ้าอ่านไฟล์ไม่ได้"""
    if cache is not None and path in cache:
        return cache[path]
    try:
        meta, _ = read_gguf(path)
        dim = int(meta.get("clip.vision.projection_dim") or meta.get("clip.audio.projection_dim") or 0)
    except (OSError, ValueError):
        dim = None
    if cache is not None:
        cache[path] = dim
    return dim


def find_mmproj(model, models_dir, names, dim_cache=None):
    """หา mmproj-<ชื่อฐานของโมเดล>*.gguf — ใช้ general.basename ก่อน ไม่มีก็ตัดท้ายชื่อไฟล์ทีละท่อน

    กันหยิบ projector ของโมเดลอื่นมาใส่ (โหลดไม่ขึ้น หรือแย่กว่าคือโหลดได้แต่ดูรูปได้ขยะ):
      - ตัวถัดจากชื่อฐานต้องเป็น "-" หรือจบด้วย ".gguf" พอดี — "Qwen3.8-27B" ไม่จับ mmproj ของ "Qwen3.8-27B2"
        และ basename สั้นๆ อย่าง "Qwen3" (convert_hf_to_gguf ชอบเขียนแบบนี้) ไม่จับ mmproj-Qwen3.8-...
      - projection_dim ของ mmproj ต้องเท่ากับ embedding_length ของโมเดล (llama.cpp ก็เช็กแบบนี้ตอนโหลด)
        ชื่อตรงแต่มิติไม่ตรง = ของรุ่นอื่นในตระกูลเดียวกัน เช่น basename "Qwen3.8" ของรุ่น 9B เจอ mmproj ของ 27B
        อ่าน mmproj ไม่ได้ = ไม่ใช้ (ไม่มีภาพดีกว่าโมเดลโหลดไม่ขึ้น)
    """
    cands = sorted(n for n in names if n.lower().startswith("mmproj") and n.lower().endswith(".gguf"))
    if not cands:
        return None
    bases = []
    if model.basename:
        bases.append(model.basename)
    parts = model.id.split("-")
    for k in range(len(parts), 1, -1):
        bases.append("-".join(parts[:k]))
    for base in bases:
        prefix = ("mmproj-" + base).lower()
        for n in cands:
            low = n.lower()
            rest = low[len(prefix):]
            if not low.startswith(prefix) or not (rest.startswith("-") or rest == ".gguf"):
                continue
            path = os.path.join(models_dir, n)
            dim = mmproj_out_dim(path, dim_cache)
            if dim is None or (dim and model.n_embd and dim != model.n_embd):
                continue
            return path
    return None


def build_model_info(model_id, files, warnings):
    size = 0
    for p in files:
        if not os.path.exists(p):
            warnings.append("%s: ไฟล์ shard หายไป (%s)" % (model_id, os.path.basename(p)))
            continue
        size += os.path.getsize(p)
    info = ModelInfo(id=model_id, path=files[0], size_bytes=size)
    try:
        meta, tensors = read_gguf(files[0])
        for extra in files[1:]:
            if os.path.exists(extra):
                tensors += read_gguf(extra)[1]
    except (OSError, ValueError) as e:
        info.error = str(e)
        warnings.append("%s: อ่าน metadata ไม่ได้ (%s) — คิด KV cache เป็น 0" % (model_id, e))
        return info
    info.arch = str(meta.get("general.architecture", ""))
    info.basename = str(meta.get("general.basename", "") or "")
    info.n_embd = int(meta.get("%s.embedding_length" % info.arch) or 0)
    info.kv_elems_full, info.kv_elems_swa, info.swa_window = kv_layout(meta)
    info.expert_count = int(meta.get("%s.expert_count" % info.arch) or 0)
    info.expert_used = int(meta.get("%s.expert_used_count" % info.arch) or 0)
    if info.expert_count:
        info.expert_bytes = sum(b for n, b in tensors if "_exps." in n)
    info.token_embd_bytes = sum(b for n, b in tensors if n == "token_embd.weight")
    return info


def scan_models(models_dir, warnings):
    """รายการโมเดลแบบเดียวกับที่ router เห็นใน --models-dir (id = ชื่อไฟล์ไม่มี .gguf)

    router ข้ามไฟล์ mmproj* และ mtp-* (ไม่ใช่โมเดลเดี่ยว) แต่ "ไม่" รวมไฟล์ที่แบ่งเป็น shard: ทุกไฟล์
    X-0000k-of-0000N โผล่เป็นโมเดลแยกตามชื่อไฟล์เต็ม (ทดสอบกับ b10984: tests/test_router_listing.py)
    จึงใช้ id ของ shard แรกตามที่ router ใช้ และคิดขนาดรวมทุก shard (โหลด shard แรกแล้ว llama.cpp อ่านที่เหลือเอง)
    ห้ามเขียน section ชื่อ X เฉยๆ — router จะสร้างรายการโมเดลเสียที่ไม่มี --model ขึ้นมาเพิ่ม
    shard ที่ 2..N เลือกแล้วก็โหลดไม่ได้อยู่ดี (llama.cpp ต้องเริ่มจาก shard แรก) จึงไม่เขียน section ให้
    โฟลเดอร์ย่อยไม่สแกน — ตอนนี้ไม่มี และโมเดลที่ไม่มี section จะใช้ [*] ตามปกติอยู่แล้ว
    """
    names = sorted(os.listdir(models_dir), key=str.lower)
    models = []
    dim_cache = {}
    for name in names:
        full = os.path.join(models_dir, name)
        if not name.lower().endswith(".gguf") or not os.path.isfile(full):
            continue
        stem = name[:-5]
        low = stem.lower()
        if low.startswith("mmproj") or low.startswith("mtp-"):
            continue
        m = _SHARD_RE.match(stem)
        shard_ids = []
        if m:
            if int(m.group("idx")) != 1:
                continue
            n = int(m.group("n"))
            base = m.group("base")
            files = [os.path.join(models_dir, "%s-%05d-of-%05d.gguf" % (base, i, n)) for i in range(1, n + 1)]
            shard_ids = ["%s-%05d-of-%05d" % (base, i, n) for i in range(2, n + 1)]
            if n > 1:
                warnings.append("%s แบ่งเป็น %d ไฟล์ — ในรายการโมเดลของหน้าเว็บให้เลือก %s (ไฟล์ส่วนอื่นขึ้นเป็น"
                                "โมเดลแยกด้วย แต่เลือกแล้วโหลดไม่ได้)" % (base, n, stem))
        else:
            files = [full]
        model_id = stem
        if not valid_model_id(model_id):
            warnings.append("ข้ามไฟล์ %s: ชื่อมีอักขระ [ ] = หรือขึ้นบรรทัดใหม่ ซึ่งเขียนลง INI ไม่ได้" % name)
            continue
        info = build_model_info(model_id, files, warnings)
        info.shard_ids = shard_ids
        info.mmproj_path = find_mmproj(info, models_dir, names, dim_cache)
        if info.mmproj_path:
            info.mmproj_bytes = os.path.getsize(info.mmproj_path)
        models.append(info)
    return models


# ================================================================ นโยบายการจัดวาง
@dataclasses.dataclass
class Options:
    ctx: int | None = None          # None = เลือกเอง
    threads: int = DEFAULT_THREADS
    vision: bool | None = None      # None = เลือกเอง, True/False = ผู้ใช้สั่ง
    primary: str | None = None
    # True = บรรยาย router ที่ตัวเปิดถอยไปเปิดด้วยค่าแบบเดิม (preset ใช้ไม่ได้) ให้ hub แสดงตามจริง:
    # ไม่มีการจัดวาง ทุกโมเดลใช้ทุก GPU ตามลำดับ CUDA ปกติ
    legacy: bool = False


def budget_bytes(dev):
    """ใช้หน่วยความจำ "ทั้งหมด" ลบขอบ ไม่ใช่ที่ว่างตอนนี้ — ตอนสร้างโปรไฟล์ใหม่ router ตัวจริง
    อาจถือ VRAM อยู่ ถ้าใช้ที่ว่างจะได้แผนที่ผิดไปตามจังหวะ  -fit ยังจัดละเอียดตอนโหลดอีกชั้น"""
    return max(0, int(dev["total_mib"]) - RESERVE_MIB) * MIB


def pick_primary(models, requested, warnings):
    if requested:
        for m in models:
            if m.id == requested:
                return m
        for m in models:
            if m.id.lower() == requested.lower():
                return m
        warnings.append("ไม่พบโมเดล --primary '%s' — เลือกโมเดลหลักให้เองแทน" % requested)
    cands = [m for m in models if PRIMARY_HINT in m.id.lower()]
    if not cands:
        return None
    chosen = next((m for m in cands if m.id == DEFAULT_PRIMARY), cands[0])
    if len(cands) > 1:
        # ให้เห็นว่าเลือกตัวไหน — ไม่งั้นเพิ่มไฟล์ quant ใหม่ (เช่น Q8_0 ที่ไม่พอดี 4090) แล้วแผนทั้งชุด
        # เปลี่ยนไปแบบไม่รู้ตัว: 27B ตัวที่ใช้อยู่เสียการ์ดใหญ่ทั้งใบ, context 64K และการดูรูป
        others = [m.id for m in cands if m is not chosen]
        warnings.append("มีโมเดลที่ชื่อมี %s หลายตัว — ใช้ %s เป็นโมเดลหลัก (ตัวอื่น: %s) เลือกเองได้ด้วย "
                        "-Primary <ชื่อ> เช่น Qwen38.cmd -Primary %s"
                        % (PRIMARY_HINT, chosen.id, ", ".join(others), others[0]))
    return chosen


def estimate_tps(model, devs, ctx, vision, budgets=None, mm_bytes=None):
    """ประมาณ tok/s ตอนสร้างข้อความ → (tok/s ตอนเครื่องว่าง, tok/s ตอน CPU มีงานอื่น, ไบต์ของ weight บน GPU)

    เวลา/โทเคน = Σ (ไบต์ที่อ่านจาก GPU แต่ละตัว / แบนด์วิดท์) + ไบต์ที่อ่านจาก CPU / แบนด์วิดท์ CPU
    (แบ่งชั้นแบบ layer ทำงานต่อกันเป็นทอด เวลาจึงบวกกัน ข้ามลิงก์ Thunderbolt แค่ activation เล็กๆ)
    MoE อ่าน expert แค่ used/count ส่วน -fit ย้าย expert ลง CPU ก่อนชั้นอื่น
    token_embd ไม่นับ เพราะ llama.cpp เก็บไว้ที่ CPU และอ่านแค่แถวเดียวต่อโทเคน
    budgets = งบของแต่ละ GPU เป็นไบต์ เมื่อไม่ได้ใช้งบเต็มใบ (เช่นใช้การ์ดร่วมกับโมเดลหลัก)
    tok/s เป็น None เมื่อไม่รู้ขนาด weight (อ่านไฟล์ไม่ได้) — ดีกว่าโชว์ตัวเลขหลักพันล้าน
    """
    if model.error or model.size_bytes <= 0:
        return None, None, 0
    weights = max(0, model.size_bytes - model.token_embd_bytes)
    kv = model.kv_bytes(ctx)
    mm = 0
    if vision:
        mm = mm_bytes if mm_bytes is not None else model.mmproj_bytes
    fixed = COMPUTE_OVERHEAD_GIB * GIB + mm
    if budgets is None:
        budgets = [budget_bytes(d) for d in devs]
    room = max(0.0, sum(budgets) - fixed) if devs else 0.0
    if model.expert_count and model.expert_bytes:
        # MoE: -fit ย้าย expert ลง CPU ก่อน ชั้น attention (และ KV ทั้งหมด) จึงอยู่บน GPU ครบ
        active = model.expert_used / model.expert_count
        dense = max(0, weights - model.expert_bytes)
        cap = max(0.0, room - kv)
        dense_gpu = min(dense, cap)
        exp_gpu = min(model.expert_bytes, cap - dense_gpu)
        on_gpu = dense_gpu + exp_gpu
        read_gpu = dense_gpu + exp_gpu * active
        read_cpu = (dense - dense_gpu) + (model.expert_bytes - exp_gpu) * active
    else:
        # dense: ย้ายลง CPU ทีละชั้น และ KV ของชั้นนั้นย้ายตามไปด้วย จึงคิดเป็นสัดส่วนชั้นที่อยู่บน GPU
        # (27B บน RTX 1000: ได้ ~3.5 GB ตรงกับที่วัดจริง ~3.4 GB)
        frac = min(1.0, room / (weights + kv)) if (weights + kv) else 1.0
        on_gpu = weights * frac
        read_gpu = on_gpu
        read_cpu = weights - on_gpu
    t_gpu = 0.0
    total_budget = sum(budgets)
    for d, b in zip(devs, budgets):
        share = (b / total_budget) if total_budget else 0
        t_gpu += read_gpu * share / (d["bandwidth_gbps"] * GPU_BW_EFFICIENCY * GB)
    t_idle = t_gpu + read_cpu / (CPU_EFFECTIVE_GBPS * GB)
    t_busy = t_gpu + read_cpu / (CPU_BUSY_GBPS * GB)
    return (1.0 / t_idle if t_idle > 0 else None), (1.0 / t_busy if t_busy > 0 else None), on_gpu


def _round_tps(v):
    return None if v is None else round(v, 2 if v < 10 else 1)


def placement_entry(m, devs, ctx, vision, is_primary=False, reserved=None, mm_bytes=None, user_override=False):
    """ข้อมูลของโมเดลหนึ่งตัวใน gpu-profile.json (placement)

    reserved = {GPU id: ไบต์} ที่โมเดลหลักจองไว้บนการ์ดที่ใช้ร่วมกัน — router โหลดพร้อมกันได้ 2 ตัว และปกติ
    27B โหลดค้างอยู่ จึงคิดจากที่เหลือหลังหักของโมเดลหลัก ไม่ใช่งบเต็มใบ (ไม่งั้น Coder บน 4090 ใบเดียว
    จะขึ้นว่า "อยู่บนการ์ดทั้งตัว 270 tok/s" ทั้งที่เหลือที่ให้แค่ ~3 GB)
    """
    reserved = reserved or {}
    budgets = [max(0, budget_bytes(d) - int(reserved.get(d["id"], 0))) for d in devs]
    need = m.need_bytes(ctx, vision, mm_bytes=mm_bytes)
    total_budget = sum(budgets)
    tps, tps_busy, _on_gpu = estimate_tps(m, devs, ctx, vision, budgets, mm_bytes)
    p = {
        "devices": [d["id"] for d in devs],
        "ctx": int(ctx),
        "vision": bool(vision),
        "fits_fully": bool(devs) and need <= total_budget,
        "est_vram_gib": round(need / GIB, 1),
        "est_gpu_gib": round(min(need, total_budget) / GIB, 1) if devs else 0.0,
        "est_gen_tps": _round_tps(tps),
        "est_gen_tps_busy": _round_tps(tps_busy),
        "kv_bytes_per_token": int(m.kv_bytes_per_token()),
        "primary": bool(is_primary),
        "shared_with_primary": any(d["id"] in reserved for d in devs),
        "user_override": bool(user_override),
    }
    if m.error:
        p["error"] = m.error
    p["note_th"], p["note_en"] = _notes(p, devs)
    return p


def _devices_key(order, natural):
    """เขียน device ก็ต่อเมื่อเป็นเซตย่อยจริงๆ หรือลำดับต่างจากปกติ — ไม่งั้นปล่อยให้ llama.cpp ใช้ทุกตัวเหมือนเดิม"""
    if not order or order == natural:
        return None
    return ",".join(order)


def single_gpu_ctx_vision(m, budget, opts):
    """(ctx, ดูรูป) ของโมเดลหลักที่ได้การ์ดใบเดียว "คนเดียว" งบ budget ไบต์ — plan() และ apply_choices() ใช้ตัวเดียวกัน
    เลือกการ์ดเดียวกับที่แผนอัตโนมัติเลือกในหน้าแชตจึงได้ค่าเท่าแผนอัตโนมัติทุกตัว (ไม่รีสตาร์ตฟรี ไม่เสียการดูรูป)

    ขั้นบันได: 64K+ดูรูป → 32K+ดูรูป → 64K → 32K — ดูรูปได้สำคัญกว่า context ที่ยาวขึ้น (การ์ด 20 GB จุ 27B
    ที่ 32K+ดูรูปได้แต่ไม่พอ 64K+ดูรูป ต้องได้ 32K+ดูรูป ไม่ใช่เสียการดูรูปไป)
    -Ctx สั่งมา: ใช้ ctx นั้น ปิดดูรูปเมื่อไม่พอ (ตอนเลือกเอง) ดีกว่าให้ชั้นล้นไป CPU
    -Vision/-NoVision สั่งมา: ทำตามนั้นเสมอ
    ไม่มีขั้นไหนพอดีเลย (การ์ดเล็กกว่าโมเดล) → ctx ปกติ ไม่ดูรูป (เว้นสั่ง -Vision) — ของที่ล้นไป CPU ยิ่งมากยิ่งช้า
    """
    has_mm = bool(m.mmproj_path)
    want = has_mm if opts.vision is None else (bool(opts.vision) and has_mm)
    if opts.ctx:
        if opts.vision is None and want and m.need_bytes(opts.ctx, vision=True) > budget:
            want = False
        return opts.ctx, want
    for vis_try in ([want, False] if (want and opts.vision is None) else [want]):
        for c in PRIMARY_CTX_CANDIDATES:
            if m.need_bytes(c, vision=vis_try) <= budget:
                return c, vis_try
    return BASE_CTX, (want if opts.vision is not None else False)


def plan(devices, models, opts, free_reliable=True):
    """หัวใจของนโยบาย — ฟังก์ชันบริสุทธิ์ (ไม่แตะไฟล์/โปรแกรม) เพื่อให้ทดสอบทุกกรณีได้

    devices = None หมายถึงตรวจ GPU ไม่ได้เลย → ใช้ค่าแบบเดิมทุกอย่าง
    free_reliable = free_mib เชื่อได้ไหม (ไม่มี llama-server ตัวไหนถือ VRAM อยู่) — ใช้แค่เตือน ไม่ใช้วางแผน
    """
    warnings, notices = [], []
    gpus = list(devices or [])
    natural = [d["id"] for d in gpus]
    index = {d["id"]: i for i, d in enumerate(gpus)}
    # ใหญ่ก่อน ถ้าเท่ากันเอาตัวที่ลำดับ CUDA ต่ำกว่า — ให้ผลคงที่ไม่ว่า eGPU จะได้เลขอะไร
    by_size = sorted(gpus, key=lambda d: (-d["total_mib"], index[d["id"]]))
    primary = pick_primary(models, opts.primary, warnings)
    base_ctx = opts.ctx or BASE_CTX
    has_mmproj = primary is not None and bool(primary.mmproj_path)
    if primary is not None and opts.vision and not has_mmproj:
        warnings.append("สั่ง --vision แต่ไม่พบไฟล์ mmproj ของ %s" % primary.id)

    fit_gpu = None
    if primary is not None and gpus and not opts.legacy:
        # ทดสอบด้วย context ที่จะใช้จริง: สั่ง -Ctx ใหญ่จนการ์ดเดียวไม่พอ ต้องไปทาง "ทุกโมเดลใช้ทุก GPU"
        # (ถ้ายังผูกไว้การ์ดเดียว ชั้นที่ล้นจะไป CPU ทั้งที่ GPU อีกใบว่างอยู่)  สั่ง -Vision เองก็ต้องจุรวม mmproj
        fit_need = primary.need_bytes(base_ctx, vision=bool(opts.vision) and has_mmproj)
        for g in by_size:
            if fit_need <= budget_bytes(g):
                fit_gpu = g
                break

    primary_vision = False
    others_shared = False
    if fit_gpu is not None:
        primary_devs = [fit_gpu]
        # การ์ดที่เหลือต้องมีงบพอใช้จริง ไม่งั้นโมเดลอื่นถูกผูกไว้กับการ์ดที่ -fit วางอะไรไม่ได้ = รัน CPU ล้วน
        rest = [g for g in by_size if g is not fit_gpu and budget_bytes(g) >= MIN_USEFUL_GPU_MIB * MIB]
        if rest:
            others_devs = rest
        else:
            # ไม่เหลือการ์ดที่ใช้ได้จริง (เช่น 4090 ใบเดียว): ใช้ร่วมกับโมเดลหลัก ไม่เขียน device
            # ให้ -fit จัดตามที่ว่างตอนโหลด (การ์ดเล็กที่ตัดทิ้งไป -fit ก็ยังใช้ได้เท่าที่มันจุ)
            others_devs = gpus
            others_shared = True
        # fit_gpu จุ need(base_ctx) ได้แน่ (เลือกมาแบบนั้น) ขั้นบันไดจึงเจอค่าที่พอดีเสมอ
        primary_ctx, primary_vision = single_gpu_ctx_vision(primary, budget_bytes(fit_gpu), opts)
        profile = "egpu-single-fit" if fit_gpu["external"] else "internal-single-fit"
    else:
        # legacy: command line แบบเดิม llama.cpp ใช้ทุก GPU ตามลำดับ CUDA ปกติ
        # ที่เหลือ: ไม่มีการ์ดใบไหนจุโมเดลหลักได้ทั้งตัว ทุกโมเดลใช้ทุก GPU ใบใหญ่ก่อน ส่วนเกินไป CPU
        primary_devs = others_devs = (gpus if opts.legacy else by_size)
        primary_ctx = base_ctx
        primary_vision = bool(opts.vision) and has_mmproj
        if opts.legacy:
            profile = "legacy"
        elif devices is None:
            profile = "unknown"
        elif not gpus:
            profile = "cpu-only"
        elif all(not g["external"] for g in gpus):
            profile = "internal-only"
        elif len(gpus) > 1:
            profile = "egpu-multi"
        else:
            profile = "egpu-single"

    primary_need = primary.need_bytes(primary_ctx, primary_vision) if primary is not None else 0
    if fit_gpu is not None and free_reliable:
        # วางแผนด้วยหน่วยความจำทั้งหมดตามนโยบาย แต่ถ้าตอนนี้มีอย่างอื่นกินการ์ดใบนั้นอยู่ (จอภาพที่ต่อกับ eGPU,
        # เกม, โปรแกรมอื่น) device key ที่กันการ์ดอื่นไว้จะทำให้ส่วนที่ไม่พอล้นไป CPU — ต้องบอก
        free_room = max(0, int(fit_gpu.get("free_mib", fit_gpu["total_mib"])) - RESERVE_MIB) * MIB
        if free_room < primary_need:
            used = max(0, fit_gpu["total_mib"] - fit_gpu["free_mib"]) / 1024
            args = (fit_gpu["short"], free_room / GIB, used, primary.id, primary_need / GIB)
            notices.append((
                "⚠ %s ว่างจริงแค่ ~%.1f GB (มีอย่างอื่นใช้อยู่ ~%.1f GB เช่นจอภาพหรือโปรแกรมอื่น) แต่ %s ต้องใช้ ~%.1f GB"
                " — ส่วนที่ไม่พอจะไปอยู่บน CPU และช้ากว่าที่ประมาณไว้มาก: ปิดโปรแกรมที่ใช้การ์ดนั้น"
                " (หรือย้ายจอไปต่อที่เครื่อง) แล้วเปิดตัวเปิดใหม่" % args,
                "⚠ %s has only ~%.1f GB free (~%.1f GB used by something else, e.g. a display or another app) but"
                " %s needs ~%.1f GB - the rest spills to the CPU and is much slower than estimated: close that app"
                " (or move the display to the laptop) and start Qwen3.8 again" % args))

    sections = {"*": {"ctx-size": str(base_ctx), "cache-type-k": CACHE_TYPE, "cache-type-v": CACHE_TYPE,
                      "threads": str(int(opts.threads))}}
    placement = {}
    reserved = {fit_gpu["id"]: primary_need} if fit_gpu is not None else None
    for m in models:
        is_primary = primary is not None and m.id == primary.id
        devs = primary_devs if is_primary else others_devs
        ctx = primary_ctx if is_primary else base_ctx
        vision = primary_vision if is_primary else False
        keys = {}
        dkey = _devices_key([d["id"] for d in devs], natural)
        if dkey:
            keys["device"] = dkey
        if ctx != base_ctx:
            keys["ctx-size"] = str(ctx)
        if vision:
            keys["mmproj"] = m.mmproj_path
        sections[m.id] = keys
        placement[m.id] = placement_entry(m, devs, ctx, vision, is_primary=is_primary,
                                          reserved=None if is_primary else reserved)
    return {"profile": profile, "primary": primary.id if primary else None, "sections": sections,
            "placement": placement, "warnings": warnings, "notices": notices,
            "fit_gpu": fit_gpu["id"] if fit_gpu else None,
            # การ์ดที่โมเดลหลักจองไว้ (โมเดลอื่นที่ใช้การ์ดนี้คิดจากที่เหลือ) — เท่ากับ fit_gpu จนกว่า
            # gpu-choice.json จะย้ายโมเดลหลักไปที่อื่น (apply_choices)
            "reserve_gpu": fit_gpu["id"] if fit_gpu else None,
            "others_devices": [d["id"] for d in others_devs], "others_shared": others_shared}


# ================================================================ GPU ที่ผู้ใช้เลือกเอง (gpu-choice.json)
# ชื่อสั้นแบบเดียวกับ gpu_model_label() ของ hub: ตัดชนิด quantize แล้วตัด -Instruct(-2507)
_QUANT_TAIL = re.compile(r"(-UD)?-(I?Q\d\w*|MXFP4\w*|F16|BF16|F32)$", re.I)
_INSTRUCT_TAIL = re.compile(r"-Instruct(-\d{4})?$", re.I)


def model_short(model_id):
    """"Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL" → "Qwen3-Coder-30B-A3B" (ชื่อที่พอดีหนึ่งบรรทัดในเมนู)"""
    s = _INSTRUCT_TAIL.sub("", _QUANT_TAIL.sub("", str(model_id or "")))
    return s or str(model_id or "")


def _gib(n):
    return round(n / GIB, 2)


def model_catalog(models_dir=DEFAULT_MODELS_DIR, primary=None, models=None, warnings=None):
    """ขนาดของแต่ละโมเดลให้หน้าเลือก GPU คิดเองว่า "พอดีการ์ดไหม" โดยไม่ต้องสร้างโปรไฟล์ใหม่

    {"<id>": {"short", "weights_gib", "mmproj_gib", "kv_bytes_per_token", "primary",
              "need_gib": {"32768": x, "65536": y,
                           "32768_vision": v, "65536_vision": z (สองตัวนี้เฉพาะโมเดลหลักที่มี mmproj)}}}
    need = weight + KV (q8_0) + compute overhead (+ mmproj) — สูตรเดียวกับที่ plan() ใช้เทียบกับ budget_mib
    ครบทุกขั้นของ single_gpu_ctx_vision() — การ์ดขนาด 20 GB ได้ 32K+ดูรูป (แผนอัตโนมัติ, -Vision, หรือ mmproj
    ใน models-preset.user.ini) หน้าเว็บต้องหา need ของขั้นนั้นเจอ ไม่งั้นคำแนะนำ "พอดีไหม" ไม่ตรงกับที่รันจริง
    primary = id ของโมเดลหลัก (None = เลือกแบบเดียวกับ plan: DEFAULT_PRIMARY หรือตัวแรกที่มี qwen3.8)
    models = ผลของ scan_models() ที่มีอยู่แล้ว (generate ส่งมา ไม่ต้องอ่านหัวไฟล์ซ้ำ)
    """
    warnings = [] if warnings is None else warnings
    if models is None:
        models = scan_models(models_dir, warnings)
    chosen = pick_primary(models, primary, warnings)
    out = {}
    for m in models:
        is_primary = chosen is not None and m.id == chosen.id
        need = {str(BASE_CTX): _gib(m.need_bytes(BASE_CTX)),
                str(PRIMARY_CTX_CANDIDATES[0]): _gib(m.need_bytes(PRIMARY_CTX_CANDIDATES[0]))}
        if is_primary and m.mmproj_path:
            for c in (BASE_CTX, PRIMARY_CTX_CANDIDATES[0]):
                need["%d_vision" % c] = _gib(m.need_bytes(c, vision=True))
        out[m.id] = {"short": model_short(m.id),
                     "weights_gib": _gib(m.size_bytes),
                     "mmproj_gib": _gib(m.mmproj_bytes) if m.mmproj_path else 0.0,
                     "kv_bytes_per_token": int(m.kv_bytes_per_token()),
                     "need_gib": need,
                     "primary": is_primary}
    return out


class ChoiceError(ValueError):
    """สิ่งที่หน้าเว็บส่งมาใช้ไม่ได้ — str() เป็น "ไทย / English" ให้ hub ส่งกลับใน 400 ได้เลย"""

    def __init__(self, th, en):
        super().__init__("%s / %s" % (th, en))
        self.th, self.en = th, en


def _brief(v, n=60):
    """ค่าที่ผู้ใช้ส่งมาแบบสั้น ไว้ใส่ในข้อความผิดพลาด (ไม่สะท้อนข้อมูลยาวๆ กลับไปทั้งก้อน)
    ห้ามโยนอะไรออกไปเอง: list ซ้อนลึกหลายร้อยชั้น json.dumps โยน RecursionError ซึ่งไม่ใช่ ValueError
    แล้วหลุดจาก read_choice/validate_choice ไปล้มทั้ง generate() — เหลือแค่ชื่อชนิดก็พอบอกว่าผิดตรงไหน"""
    try:
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else repr(v)
    except (ValueError, TypeError, RecursionError):
        s = "<%s>" % type(v).__name__
    return s if len(s) <= n else s[:n - 1] + "…"


def _check_choice_value(v, known_keys=None):
    """ตรวจค่าของโมเดลหนึ่งตัว → ค่าที่ทำความสะอาดแล้ว หรือโยน ChoiceError
    "auto"/"cpu" ไม่สนตัวพิมพ์  list = key ของ GPU 1..8 ตัว ไม่ซ้ำ ไม่ว่าง ยาวไม่เกิน 120
    known_keys = None → ไม่เช็กว่ามีการ์ดนั้นจริงไหม (ตอนอ่านไฟล์: ใบที่ถอดไปแล้วถือเป็น "ไม่ได้ต่ออยู่")"""
    if isinstance(v, str):
        s = v.strip().lower()
        if s in (CHOICE_AUTO, CHOICE_CPU):
            return s
        raise ChoiceError("ค่า %s ใช้ไม่ได้ (ต้องเป็น \"auto\", \"cpu\" หรือรายการ GPU)" % _brief(v),
                          "invalid value %s (must be \"auto\", \"cpu\" or a list of GPUs)" % _brief(v))
    if not isinstance(v, list):
        raise ChoiceError("ค่า %s ใช้ไม่ได้ (ต้องเป็น \"auto\", \"cpu\" หรือรายการ GPU)" % _brief(v),
                          "invalid value %s (must be \"auto\", \"cpu\" or a list of GPUs)" % _brief(v))
    if not 1 <= len(v) <= CHOICE_LIST_MAX:
        raise ChoiceError("รายการ GPU ต้องมี 1-%d ใบ (ได้ %d)" % (CHOICE_LIST_MAX, len(v)),
                          "a GPU list must have 1-%d entries (got %d)" % (CHOICE_LIST_MAX, len(v)))
    out = []
    for k in v:
        if not isinstance(k, str) or not k.strip():
            raise ChoiceError("ชื่อ GPU %s ใช้ไม่ได้" % _brief(k), "invalid GPU key %s" % _brief(k))
        if len(k) > CHOICE_KEY_MAX:
            raise ChoiceError("ชื่อ GPU ยาวเกิน %d ตัวอักษร" % CHOICE_KEY_MAX,
                              "GPU key longer than %d characters" % CHOICE_KEY_MAX)
        if k in out:
            raise ChoiceError("เลือก GPU %s ซ้ำ" % _brief(k), "duplicate GPU %s" % _brief(k))
        if known_keys is not None and k not in known_keys:
            raise ChoiceError("ไม่รู้จัก GPU %s" % _brief(k), "unknown GPU %s" % _brief(k))
        out.append(k)
    return out


def validate_choice(doc, model_ids, known_keys):
    """ตรวจ {"models": {...}} ที่หน้าเว็บส่งมา → เอกสารที่พร้อมเขียนลง gpu-choice.json หรือโยน ChoiceError (ValueError)

    model_ids = โมเดลที่มีอยู่ (model_catalog().keys()) — id อื่นไม่รับ
    known_keys = key ของ GPU ที่รับได้ (hub: การ์ดที่ต่ออยู่ + key ที่มีในไฟล์อยู่แล้ว เพื่อให้บันทึกค่าเดิม
    ของการ์ดที่ถอดไปชั่วคราวได้โดยไม่ต้องล้าง) — None = ไม่เช็ก
    คืน {"version": 1, "updated_at": เวลาตอนนี้, "models": {...}} ("auto" คงไว้ตามที่ส่งมา)
    """
    if not isinstance(doc, dict):
        raise ChoiceError("ข้อมูลต้องเป็น JSON object", "the body must be a JSON object")
    models = doc.get("models")
    if not isinstance(models, dict):
        raise ChoiceError("ต้องมี \"models\" เป็น object", "\"models\" must be an object")
    ids = set(model_ids or ())
    known = None if known_keys is None else set(known_keys)
    clean = {}
    for mid, v in models.items():
        if not isinstance(mid, str) or mid not in ids:
            raise ChoiceError("ไม่รู้จักโมเดล %s" % _brief(mid), "unknown model %s" % _brief(mid))
        try:
            clean[mid] = _check_choice_value(v, known)
        except ChoiceError as e:
            raise ChoiceError("%s: %s" % (mid, e.th), "%s: %s" % (mid, e.en))
    return {"version": CHOICE_VERSION,
            "updated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "models": clean}


def save_choice(doc, path=CHOICE_FILE):
    """เขียน gpu-choice.json แบบ atomic (ไฟล์ชั่วคราวในโฟลเดอร์เดียวกันแล้ว os.replace) UTF-8 ไม่มี BOM
    ชื่อไฟล์ชั่วคราวไม่ซ้ำกันแม้ hub เขียนพร้อมกันสองเธรด (_write_atomic ใช้แค่ PID)"""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".gpu-choice.", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        # Windows: os.replace ล้ม (PermissionError) ถ้ามีคนเปิดไฟล์ปลายทางอ่านอยู่พอดี (ตัวเปิดกำลังอ่าน) — ลองซ้ำสั้นๆ
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.1)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_choice(path, warnings):
    """อ่าน gpu-choice.json แบบไม่มีวันล้ม → {"path", "sha1", "models"} (None = --choice none)

    ไม่มีไฟล์ = ทุกโมเดล "auto" (sha1 = None)  JSON เสีย / รูปแบบแปลก / version อื่น → ไม่ใช้ทั้งไฟล์
    ค่าของโมเดลไหนผิดรูป → ข้ามเฉพาะตัวนั้น (ถือเป็น auto)  ทุกกรณีมีคำเตือนภาษาไทย
    ตัวเปิดต้องเปิด router ได้เสมอ ไฟล์ที่ hub เขียนค้างครึ่งทางหรือคนแก้มือผิดต้องไม่ทำให้เปิดไม่ขึ้น
    """
    if not path or str(path).strip().lower() == "none":
        return None
    info = {"path": str(path), "sha1": None, "models": {}}
    name = os.path.basename(str(path))
    try:
        with open(path, "rb") as f:
            # อ่านไม่เกินขีด +1 ไบต์ — ไฟล์ใหญ่ผิดปกติ (เสีย/ถูกเขียนทับด้วยอย่างอื่น) ต้องไม่กินหน่วยความจำจนตัวเปิดล้ม
            raw = f.read(CHOICE_FILE_MAX + 1)
    except FileNotFoundError:
        return info
    except OSError as e:
        warnings.append("อ่าน %s ไม่ได้ (%s) — ทุกโมเดลจัดวางอัตโนมัติ" % (name, e))
        info["error"] = "unreadable"
        return info
    info["sha1"] = hashlib.sha1(raw).hexdigest()
    if len(raw) > CHOICE_FILE_MAX:
        info["sha1"] = None               # ไม่ได้อ่านทั้งไฟล์ — sha1 ของส่วนต้นไม่ใช่ของไฟล์
        warnings.append("%s ใหญ่เกิน %d KB (hub เขียนแค่ไม่กี่ KB — ไฟล์เสีย?) — ไม่ใช้ ทุกโมเดลจัดวางอัตโนมัติ"
                        % (name, CHOICE_FILE_MAX // 1024))
        info["error"] = "too-large"
        return info
    try:
        doc = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError, RecursionError) as e:
        # RecursionError = [[[[... ซ้อนลึกเกินที่ json ของ Python รับได้ — ไม่ใช่ ValueError ถ้าไม่จับ generate() ล้ม
        # แล้วตัวเปิดถอยไปค่าแบบเดิมทั้งชุด ทั้งที่แค่ควรไม่ใช้ไฟล์นี้
        warnings.append("%s อ่านไม่ออก (%s) — ไม่ใช้ ทุกโมเดลจัดวางอัตโนมัติ" % (name, str(e)[:160]))
        info["error"] = "invalid-json"
        return info
    models = doc.get("models") if isinstance(doc, dict) else None
    version = doc.get("version", CHOICE_VERSION) if isinstance(doc, dict) else None
    if not isinstance(models, dict) or version != CHOICE_VERSION:
        warnings.append("%s ไม่ใช่รูปแบบที่รู้จัก (ต้องเป็น {\"version\": 1, \"models\": {...}}) — ไม่ใช้ "
                        "ทุกโมเดลจัดวางอัตโนมัติ" % name)
        info["error"] = "bad-shape"
        return info
    for mid, v in models.items():
        try:
            info["models"][str(mid)] = _check_choice_value(v)
        except ChoiceError as e:
            warnings.append("%s: ข้ามค่าของ %s (%s) — โมเดลนี้จัดวางอัตโนมัติ" % (name, mid, e.th))
    return info


def _choice_text(v):
    if v == CHOICE_CPU:
        return "CPU"
    if isinstance(v, list):
        return " + ".join(v)
    return str(v)


def apply_choices(result, models, devices, opts, choices, warnings):
    """ใช้ GPU ที่ผู้ใช้เลือก (gpu-choice.json) ทับแผนอัตโนมัติของ plan() — ฟังก์ชันบริสุทธิ์ แก้ result ตรงๆ

    ทุก placement ได้ป้าย source ("auto"|"choice"), choice (ค่าดิบหรือ None), choice_missing,
    และ auto = ที่แผนอัตโนมัติเลือก (ให้หน้าเว็บเขียน "อัตโนมัติ (แนะนำ) — ...") แม้ไม่มีการเลือกเลย
    - "auto" = ตามแผนอัตโนมัติ — ยกเว้นข้อเดียว: ผู้ใช้ย้ายโมเดลหลักไปจากที่แผนเลือก (การ์ดอื่น / หลายใบ / CPU)
               โมเดลอื่นที่เป็น auto จัดใหม่แบบเดียวกับ plan(): ใช้การ์ดที่ใช้ได้จริงทุกใบที่โมเดลหลักไม่ได้ใช้ ใหญ่ก่อน
               ไม่เหลือเลย = ใช้ร่วมกันไม่เขียน device  ไม่งั้นการ์ดที่แผนกันไว้ให้โมเดลหลักถูกทิ้งว่าง (27B ไป CPU
               แต่ Coder ยังอยู่การ์ดเล็ก) หรือโมเดลหลักเสีย 64K/ดูรูปเพราะโมเดล auto ยังนั่งอยู่การ์ดที่มันย้ายไป
               p["auto"] ของตัวที่จัดใหม่ = ผลใหม่นี้ (ป้าย "อัตโนมัติ (แนะนำ) — ..." ตรงกับที่ใช้จริง)
               เลือกโมเดลหลักไว้ตรงกับที่แผนเลือกอยู่แล้ว = ไม่จัดใหม่ (preset/placement เท่าแผนอัตโนมัติทุกอย่าง)
    - "cpu"  = device = none เสมอ (เขียนแม้เครื่องไม่มี GPU — ผู้ใช้สั่งชัดเจน)
    - key    = แปลงเป็น CUDAn ของตอนนี้ ใหญ่ก่อน; ใบที่ไม่ได้ต่ออยู่ตัดทิ้ง; ไม่เหลือเลย = auto + choice_missing
               เขียน device เฉพาะเมื่อไม่เท่ากับ "ทุก GPU ตามลำดับปกติ" (ต่อแค่ GPU ในเครื่อง = preset เดิมทุกไบต์)
    โมเดลหลักที่ถูกเลือก: อยู่การ์ดเดียว "คนเดียว" (ไม่มีโมเดลอื่นถูกวางหรือถูกเลือกไว้ใบนั้น) → ขั้นบันไดเดียวกับ
    plan() (single_gpu_ctx_vision: 64K+ดูรูป → 32K+ดูรูป → 64K → 32K ตามงบของใบ) ไม่งั้น ctx ปกติ ไม่ดูรูป
    (-Ctx/-Vision/-NoVision ที่สั่งมาชนะ) — โมเดลอื่นใช้ ctx ปกติ ไม่ดูรูป
    จองที่ของโมเดลหลัก (โมเดลอื่นบนใบเดียวกันคิดจากที่เหลือ) เฉพาะเมื่ออยู่การ์ดใบเดียวที่จุได้ทั้งตัว — กติกาเดียวกับ
    fit_gpu ของ plan(): ใบที่จุไม่ได้ -fit แบ่งตามที่ว่างตอนโหลด และหลายใบก็ไม่จองเหมือนแผนแบ่งหลายใบของ plan()
    result["choice_devices"] = {id: [CUDAn ที่เลือก]} (ก่อน user.ini ทับ) ให้ข้อความสรุปบอกสิ่งที่ผู้ใช้เลือกจริง
    """
    placement, sections = result["placement"], result["sections"]
    for p in placement.values():
        p["auto"] = {"devices": list(p["devices"]), "ctx": p["ctx"], "vision": p["vision"]}
        p["source"], p["choice"], p["choice_missing"] = "auto", None, False
    result["choices_applied"] = []
    result["choice_devices"] = {}
    result["others_replanned"] = False
    if not choices or opts.legacy:
        # legacy = router ที่เปิดด้วยค่าแบบเดิมไม่มี preset — การเลือกใช้ไม่ได้จริง ห้ามบรรยายว่าใช้
        return result
    gpus = list(devices or [])
    by_key = {d.get("key"): d for d in gpus if d.get("key")}
    index = {d["id"]: i for i, d in enumerate(gpus)}
    natural = [d["id"] for d in gpus]
    info = {m.id: m for m in models}
    primary_id = result["primary"]
    base_ctx = opts.ctx or BASE_CTX

    resolved = {}                       # model id → [device dict] ([] = CPU)
    for mid, raw in choices.items():
        p = placement.get(mid)
        if p is None or mid not in info:
            warnings.append("gpu-choice.json: ไม่มีโมเดล %s ในโฟลเดอร์แล้ว — ข้าม" % mid)
            continue
        p["choice"] = list(raw) if isinstance(raw, list) else raw
        if raw == CHOICE_AUTO:
            continue
        if raw == CHOICE_CPU:
            resolved[mid] = []
            continue
        if devices is None:
            # ตรวจ GPU ไม่ได้รอบนี้ ไม่รู้ว่าการ์ดที่เลือกคือ CUDA อะไร — เดาผิด = โมเดลโหลดไม่ขึ้น (HTTP 500)
            warnings.append("gpu-choice.json: ตรวจ GPU ไม่ได้รอบนี้ — %s ใช้การจัดวางอัตโนมัติแทน GPU ที่เลือกไว้" % mid)
            continue
        found = [by_key[k] for k in raw if k in by_key]
        dropped = [k for k in raw if k not in by_key]
        if dropped:
            p["choice_dropped"] = dropped
        if not found:
            p["choice_missing"] = True
            warnings.append("gpu-choice.json: %s เลือก %s ไว้ แต่ตอนนี้ไม่ได้ต่ออยู่ — ใช้การจัดวางอัตโนมัติแทน"
                            % (mid, _choice_text(raw)))
            continue
        if dropped:
            warnings.append("gpu-choice.json: %s — %s ไม่ได้ต่ออยู่ ใช้เฉพาะ %s"
                            % (mid, " + ".join(dropped), " + ".join(d["short"] for d in found)))
        # ใหญ่ก่อนเหมือนแผนอัตโนมัติ (-fit วางชั้นแรกๆ บนการ์ดใบแรก) เท่ากันเอาเลข CUDA ต่ำกว่า
        resolved[mid] = sorted(found, key=lambda d: (-d["total_mib"], index[d["id"]]))
    if not resolved:
        return result

    # โมเดลหลักถูกย้ายไปจากที่แผนเลือก → โมเดล auto ตัวอื่นจัดใหม่ให้หลบการ์ดของมัน (ดู docstring)
    # ตรวจ GPU ไม่ได้ (devices None) ไม่จัดใหม่ — ไม่รู้ว่ามีการ์ดอะไร แผนเดิมก็ไม่ได้เขียน device อยู่แล้ว
    replanned, replan_devs, replan_shared = [], [], False
    if primary_id in resolved and devices is not None:
        prim_ids = [d["id"] for d in resolved[primary_id]]
        if prim_ids != list(placement[primary_id]["devices"]):
            # คำเตือนของ plan() ("การ์ดใบนั้นว่างจริงไม่พอสำหรับโมเดลหลัก") พูดถึงการ์ดที่โมเดลหลักไม่ได้อยู่แล้ว
            result["notices"] = []
            by_size = sorted(gpus, key=lambda d: (-d["total_mib"], index[d["id"]]))
            # กติกาเดียวกับ rest ของ plan(): การ์ดที่งบต่ำกว่า MIN_USEFUL_GPU_MIB ไม่นับ (-fit วางอะไรแทบไม่ได้)
            rest = [g for g in by_size if g["id"] not in prim_ids and budget_bytes(g) >= MIN_USEFUL_GPU_MIB * MIB]
            if rest:
                replan_devs = rest
            else:
                # โมเดลหลักใช้การ์ดที่ใช้ได้ทุกใบ: ใช้ร่วมกัน ไม่เขียน device ให้ -fit ใช้ที่ว่างตอนโหลด (= others_shared)
                replan_devs, replan_shared = gpus, True
            replanned = [mid for mid in placement if mid != primary_id and mid not in resolved and mid in info]

    # การ์ดที่โมเดลอื่น "ถูกวาง" ไว้ — ใช้ตัดสินว่าโมเดลหลักอยู่คนเดียวไหม
    # โมเดล auto ที่ "ใช้การ์ดร่วมกับโมเดลหลัก" (others_shared: ไม่มี device ให้ -fit ใช้ที่ว่างตอนโหลด)
    # ไม่นับ — แผนอัตโนมัติเองก็ให้ 27B ได้ 64K + ดูรูปในกรณีนั้น เลือกการ์ดเดียวกับที่ auto เลือกต้องได้ผลเท่ากัน
    def placed_on(mid):
        if mid in resolved:
            return {d["id"] for d in resolved[mid]}
        if mid in replanned:
            return set() if replan_shared else {d["id"] for d in replan_devs}
        if result.get("others_shared") and mid != primary_id:
            return set()
        return set(placement[mid]["devices"])

    reserve = result.get("reserve_gpu")
    chosen_prim = None
    if primary_id in resolved:
        pm = info[primary_id]
        devs = resolved[primary_id]
        single = devs[0] if len(devs) == 1 else None
        alone = single is not None and not any(single["id"] in placed_on(mid)
                                               for mid in placement if mid != primary_id)
        if alone:
            ctx, vision = single_gpu_ctx_vision(pm, budget_bytes(single), opts)
        else:
            # ใช้การ์ดร่วมกับโมเดลอื่น / หลายใบ / CPU: 64K และ mmproj แย่งที่ของโมเดลอื่น — ดูรูปเฉพาะเมื่อสั่ง -Vision
            ctx, vision = base_ctx, bool(opts.vision) and bool(pm.mmproj_path)
        # จองเฉพาะการ์ดใบเดียวที่จุได้ทั้งตัว (= fit_gpu ของ plan) — ใบที่จุไม่ได้ถ้าจองเต็ม need โมเดลอื่นบนใบนั้น
        # จะขึ้นว่าได้ GPU ~0 GB และช้าลง 2-3 เท่า ทั้งที่ preset เหมือนแผนอัตโนมัติทุกตัว (แผนอัตโนมัติไม่จอง)
        fits = single is not None and pm.need_bytes(ctx, vision) <= budget_bytes(single)
        reserve = single["id"] if fits else None
        chosen_prim = (devs, ctx, vision)

    # โมเดลหลักก่อน: งบที่โมเดลอื่นเหลือบนการ์ดที่ใช้ร่วมกันขึ้นกับว่าโมเดลหลักจองไปเท่าไร
    order = sorted(placement, key=lambda mid: mid != primary_id)
    by_id = {d["id"]: d for d in gpus}
    reserved = None
    for mid in order:
        m = info.get(mid)
        if m is None:
            continue
        p = placement[mid]
        is_primary = mid == primary_id
        if mid in resolved or mid in replanned:
            if mid in replanned:
                devs, ctx, vision = replan_devs, base_ctx, False
                p["auto"] = {"devices": [d["id"] for d in devs], "ctx": ctx, "vision": vision}
            elif is_primary:
                devs, ctx, vision = chosen_prim
            else:
                devs, ctx, vision = resolved[mid], base_ctx, False
            keys = {}
            if not devs and mid in resolved:
                keys["device"] = "none"
            else:
                dkey = _devices_key([d["id"] for d in devs], natural)
                if dkey:
                    keys["device"] = dkey
            if ctx != base_ctx:
                keys["ctx-size"] = str(ctx)
            if vision:
                keys["mmproj"] = m.mmproj_path
            sections[mid] = keys
        else:
            devs = [by_id[i] for i in p["devices"] if i in by_id]
            ctx, vision = p["ctx"], p["vision"]
        new = placement_entry(m, devs, ctx, vision, is_primary=is_primary,
                              reserved=None if is_primary else reserved)
        for k in _CHOICE_FIELDS:
            if k in p:
                new[k] = p[k]
        if mid in resolved:
            new["source"] = "choice"
            new["note_th"], new["note_en"] = _notes(new, devs)
        placement[mid] = new
        if is_primary and reserve is not None:
            reserved = {reserve: m.need_bytes(ctx, vision)}
    result["reserve_gpu"] = reserve
    result["choices_applied"] = [mid for mid in order if mid in resolved]
    result["choice_devices"] = {mid: [d["id"] for d in resolved[mid]] for mid in result["choices_applied"]}
    if replanned:
        result["others_replanned"] = True
        result["others_devices"] = [d["id"] for d in replan_devs]
        result["others_shared"] = replan_shared
    return result


# ================================================================ ข้อความสรุป
def _where(devs, fits):
    names = [d["short"] for d in devs]
    if not names:
        return "CPU"
    s = " + ".join(names)
    if not fits:
        s += " + CPU"
    return s


def _speed_text(p):
    """ช่วงความเร็ว: ล่าง = CPU มีงานอื่นหนักๆ (−15%), บน = เครื่องว่าง (+15%) — "?" ถ้าประมาณไม่ได้"""
    hi, lo = p.get("est_gen_tps"), p.get("est_gen_tps_busy")
    if hi is None:
        return "?"
    if lo is None:
        lo = hi
    lo, hi = lo * SPEED_RANGE[0], hi * SPEED_RANGE[1]
    if hi < 10:
        return "%.1f-%.1f" % (lo, hi)
    return "%d-%d" % (round(lo), round(hi))


def _notes(p, devs):
    where = _where(devs, p["fits_fully"])
    if not devs:
        th, en = "รันบน CPU ทั้งหมด", "runs entirely on CPU"
    elif p["fits_fully"] and len(devs) == 1:
        th, en = "อยู่บน %s ทั้งตัว" % where, "fully on %s" % where
    elif p["fits_fully"]:
        th, en = "แบ่งชั้นลง %s ได้ทั้งตัว" % where, "layer-split across %s, fits fully" % where
    else:
        th = "วางบน %s ได้ ~%.1f GB ส่วนที่เหลือไป CPU" % (" + ".join(d["short"] for d in devs), p["est_gpu_gib"])
        en = "~%.1f GB on %s, rest on CPU" % (p["est_gpu_gib"], " + ".join(d["short"] for d in devs))
    if p.get("shared_with_primary"):
        th += " (ใช้ GPU ร่วมกับโมเดลหลัก คิดจากที่เหลือตอนโมเดลหลักโหลดอยู่ -fit จัดตามที่ว่างตอนโหลด)"
        en += " (shares the GPU with the primary model; estimated with the primary loaded, -fit uses what is free)"
    if p.get("source") == "choice":
        th += " (เลือกเองในหน้าแชต)"
        en += " (chosen in the chat page)"
    if p.get("user_override"):
        th += " (ตั้งเองใน models-preset.user.ini)"
        en += " (set in models-preset.user.ini)"
    if p.get("error"):
        th += " — อ่าน metadata ไม่ได้ ตัวเลขไม่แน่นอน"
        en += " - metadata unreadable, figures are uncertain"
    return th, en


def build_summary(devices, source, result):
    """คืน (summary_th, summary_en) — ข้อความหลายบรรทัดให้ตัวเปิดพิมพ์และ hub แสดง"""
    gpus = list(devices or [])
    placement = result["placement"]
    primary = result["primary"]
    by_id = {d["id"]: d for d in gpus}
    th, en = [], []
    if devices is None:
        th.append("GPU: ตรวจไม่สำเร็จ — ใช้ค่าแบบเดิม ให้ -fit จัดเองตอนโหลด")
        en.append("GPU: detection failed - using the previous defaults; -fit decides at load time")
    elif not gpus:
        th.append("GPU: ไม่พบ — ทุกโมเดลรันบน CPU (ช้ามาก)")
        en.append("GPU: none found - every model runs on CPU (very slow)")
    else:
        th.append("GPU: " + ", ".join("%s %.0f GB (%s)" % (d["short"], d["total_mib"] / 1024,
                                                           "ต่อภายนอก" if d["external"] else "ในเครื่อง")
                                      for d in gpus))
        en.append("GPU: " + ", ".join("%s %.0f GB (%s)" % (d["short"], d["total_mib"] / 1024,
                                                           "external" if d["external"] else "internal")
                                      for d in gpus))
    prof = result["profile"]
    chosen = result.get("choices_applied") or []
    if chosen:
        # บรรทัด "แผน:" ข้างล่างบรรยายแผนอัตโนมัติ — ต้องบอกก่อนว่ามีโมเดลที่ผู้ใช้เลือกเองทับอยู่
        # ใช้ GPU ที่ "เลือก" (choice_devices) ไม่ใช่ placement ที่ user.ini อาจตั้ง device ทับไปแล้ว — ไม่งั้นบรรทัดนี้
        # บอกว่าผู้ใช้เลือกการ์ดที่ตั้งไว้ใน user.ini (บรรทัดของแต่ละโมเดลข้างล่างบอกสิ่งที่ใช้จริง)
        picked = result.get("choice_devices") or {}
        c_th, c_en = [], []
        for mid in chosen:
            where = _where([by_id[i] for i in picked.get(mid, placement[mid]["devices"]) if i in by_id], True)
            if placement[mid].get("choice_overridden"):
                c_th.append("%s → %s (แทนที่โดย models-preset.user.ini)" % (mid, where))
                c_en.append("%s → %s (overridden by models-preset.user.ini)" % (mid, where))
            else:
                c_th.append("%s → %s" % (mid, where))
                c_en.append("%s → %s" % (mid, where))
        th.append("เลือกเองในหน้าแชต (gpu-choice.json): " + "; ".join(c_th))
        en.append("Chosen in the chat page (gpu-choice.json): " + "; ".join(c_en))
    lab_th, lab_en = ("แผนอัตโนมัติ (โมเดลที่ไม่ได้เลือกเอง)", "Automatic plan (models not chosen)") if chosen \
        else ("แผน", "Plan")
    if result.get("others_replanned"):
        # โมเดลหลักถูกย้ายไปจากที่แผนเลือก — บรรทัดแผนตามโปรไฟล์ข้างล่าง (เช่น "มีแต่ GPU ในเครื่อง" หรือ
        # "27B อยู่บน 4090 ตัวเดียว") ไม่ตรงแล้ว บอกว่าโมเดล auto จัดใหม่ไปใช้การ์ดไหนแทน
        p_where = _where([by_id[i] for i in (result.get("choice_devices") or {}).get(primary, []) if i in by_id], True)
        if result.get("others_shared"):
            o_th = "GPU ที่มีร่วมกับโมเดลหลัก (-fit จัดตามที่ว่างตอนโหลด)"
            o_en = "the GPUs shared with the primary (-fit uses what is free at load time)"
        else:
            o_th = o_en = " + ".join(by_id[i]["short"] for i in result.get("others_devices") or [] if i in by_id)
        th.append("%s: %s อยู่บน %s ตามที่เลือก — โมเดลอื่นที่เป็นอัตโนมัติจัดใหม่ให้หลบ ใช้ %s"
                  % (lab_th, primary, p_where, o_th))
        en.append("%s: %s is on %s as chosen - the other automatic models are re-planned around it and use %s"
                  % (lab_en, primary, p_where, o_en))
    elif prof in ("egpu-single-fit", "internal-single-fit") and primary and primary not in chosen:
        g = by_id[result["fit_gpu"]]
        p = placement[primary]
        vis_th = ", ดูรูปได้" if p["vision"] else ""
        vis_en = ", vision on" if p["vision"] else ""
        # ตัดสินด้วย id ไม่ใช่ชื่อ — การ์ดรุ่นเดียวกันสองใบชื่อเหมือนกันแต่เป็นคนละใบ
        if result.get("others_shared"):
            o_th, o_en = "GPU เดียวกัน (-fit จัดตามที่ว่างตอนโหลด)", "the same GPU (-fit uses what is free at load time)"
        else:
            o_th = o_en = " + ".join(by_id[i]["short"] for i in result["others_devices"] if i in by_id)
        th.append("%s: %s อยู่บน %s ตัวเดียวทั้งโมเดล (ctx %s%s); โมเดลอื่นใช้ %s"
                  % (lab_th, primary, g["short"], format(p["ctx"], ","), vis_th, o_th))
        en.append("%s: %s gets %s to itself (ctx %s%s); other models use %s"
                  % (lab_en, primary, g["short"], format(p["ctx"], ","), vis_en, o_en))
        others = [mid for mid in placement if mid != primary]
        if others and not result.get("others_shared") and not chosen:
            # ค่าปริยายกันการ์ดใหญ่ไว้ให้โมเดลหลัก — บอกวิธีปลดไว้ให้คนที่ใช้โมเดลอื่นเป็นหลักตอนต่อการ์ดนี้
            ex = max(others, key=lambda mid: placement[mid]["est_vram_gib"])
            order = ",".join([g["id"]] + [i for i in result["others_devices"] if i != g["id"]])
            th.append("  อยากให้โมเดลอื่นใช้ %s ด้วย (ตอนไม่ได้ใช้ %s): เลือกในหน้าแชต (เมนูบัญชี → เลือก GPU…) "
                      "หรือเพิ่มใน %s เช่น [%s] แล้วบรรทัดถัดไป device = %s"
                      % (g["short"], primary, USER_INI, ex, order))
            en.append("  To let another model use %s too (when %s is not in use): choose it in the chat page"
                      " (account menu → Choose GPU…) or add to %s e.g. [%s] then the line device = %s"
                      % (g["short"], primary, USER_INI, ex, order))
    elif prof == "internal-only":
        th.append("%s: มีแต่ GPU ในเครื่อง — ค่าเหมือนเดิม (-fit วางชั้นลง GPU ที่เหลือไป CPU)" % lab_th)
        en.append("%s: internal GPU only - same settings as before (-fit offloads what fits, rest on CPU)" % lab_en)
    elif prof in ("egpu-multi", "egpu-single"):
        order = " → ".join(d["short"] for d in sorted(gpus, key=lambda d: -d["total_mib"]))
        th.append("%s: ไม่มี GPU ตัวไหนจุ %s ได้ทั้งตัว — ทุกโมเดลแบ่งชั้นลง %s แล้วที่เหลือไป CPU"
                  % (lab_th, primary or "โมเดลหลัก", order))
        en.append("%s: no single GPU holds %s - every model layer-splits across %s, the rest on CPU"
                  % (lab_en, primary or "the primary model", order))
    elif prof == "legacy":
        th.append("แผน: router เปิดด้วยค่าแบบเดิม (preset ใช้ไม่ได้) — ทุกโมเดลใช้ทุก GPU ตามลำดับปกติ -fit จัดเอง")
        en.append("Plan: the router runs with the old settings (the preset could not be used) - every model uses"
                  " every GPU in the default order; -fit decides")
    for n_th, n_en in result.get("notices") or []:
        th.append(n_th)
        en.append(n_en)
    # โมเดลหลักขึ้นก่อน (เหมือนที่ hub แสดง) ที่เหลือตามลำดับชื่อ
    for mid, p in sorted(placement.items(), key=lambda kv: not kv[1]["primary"]):
        devs = [by_id[i] for i in p["devices"] if i in by_id]
        where = _where(devs, p["fits_fully"])
        mark = "★ " if p["primary"] else "• "
        vis_th = " · ดูรูปได้" if p["vision"] else ""
        vis_en = " · vision" if p["vision"] else ""
        mem_th = "~%.1f GB" % p["est_vram_gib"]
        if devs and not p["fits_fully"]:
            mem_th += " (บน GPU ~%.1f GB)" % p["est_gpu_gib"]
        own_th = " · ตั้งเอง (user.ini)" if p.get("user_override") else ""
        own_en = " · user.ini" if p.get("user_override") else ""
        if p.get("source") == "choice":
            own_th, own_en = own_th + " · เลือกเอง", own_en + " · chosen"
        elif p.get("choice_missing"):
            own_th += " · GPU ที่เลือกไว้ไม่ได้ต่ออยู่ ใช้อัตโนมัติ"
            own_en += " · chosen GPU not connected, automatic"
        shr_th = " · ใช้การ์ดร่วมกับโมเดลหลัก" if p.get("shared_with_primary") else ""
        shr_en = " · shares the primary's GPU" if p.get("shared_with_primary") else ""
        th.append("%s%s: %s · ctx %s%s · %s%s%s · ราว %s tok/s"
                  % (mark, mid, where, format(p["ctx"], ","), vis_th, mem_th, shr_th, own_th, _speed_text(p)))
        en.append("%s%s: %s · ctx %s%s · %s%s%s · about %s tok/s"
                  % (mark, mid, where, format(p["ctx"], ","), vis_en, mem_th.replace("บน GPU", "on GPU"),
                     shr_en, own_en, _speed_text(p)))
    th.append("ความเร็วเป็นค่าประมาณจากแบนด์วิดท์หน่วยความจำ (ค่าต่ำ = ตอน CPU มีงานอื่นหนักๆ) — วัดจริง: "
              "python C:\\LLM\\gpu_bench.py")
    en.append("Speeds are rough memory-bandwidth estimates (low end = CPU busy with other work) - measure with: "
              "python C:\\LLM\\gpu_bench.py")
    return "\n".join(th), "\n".join(en)


# ================================================================ INI
def parse_ini(text):
    """parser แบบเดียวกับที่ llama.cpp อ่าน preset: [section], key = value, คอมเมนต์ ; และ #
    คืน (dict ของ section → dict key → value ตามลำดับ, คำเตือน)"""
    sections, warnings, cur = {}, [], None
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip().lstrip("\ufeff")
        if not line or line[0] in ";#":
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = line[1:-1].strip()
            sections.setdefault(cur, {})
            continue
        if "=" not in line:
            warnings.append("บรรทัด %d อ่านไม่ออก: %s" % (n, line))
            continue
        if cur is None:
            warnings.append("บรรทัด %d อยู่นอก [section]: %s" % (n, line))
            continue
        k, v = line.split("=", 1)
        sections[cur][k.strip()] = v.strip()
    return sections, warnings


_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _bad_device_value(value, device_ids):
    """ชื่อ GPU ใน device = ... ที่ไม่มีอยู่ตอนนี้ ([] = ใช้ได้) — "none" (CPU ล้วน) ใช้ได้เฉพาะตัวเดียวและตัวพิมพ์เล็ก
    ตรงตัวตามที่ llama.cpp เทียบ"""
    parts = [p.strip() for p in str(value).split(",")]
    if parts == ["none"]:
        return []
    return [p for p in parts if p not in device_ids]


def merge_user_overrides(sections, user_text, model_ids, device_ids=None):
    """merge models-preset.user.ini ทับค่าที่สร้าง

    - key ที่ค่าว่าง = ลบ key นั้นออก (เช่น "device =" ให้โมเดลกลับไปใช้ทุก GPU)
    - section ของโมเดลที่ไม่มีจริงและไม่มี model = ... ถูกข้าม เพราะ router จะสร้างรายการโมเดลเสีย
      ขึ้นมาในหน้าเว็บ (ทดสอบแล้ว: Available models กลายเป็น 5 ตัว)
    - device = ที่อ้าง GPU ที่ไม่ได้ต่ออยู่ตอนนี้ (เช่นเขียน CUDA1 ไว้ตอนมี 4090 แล้วถอดออก) ไม่ใช้ และคงค่า
      ที่จัดให้อัตโนมัติไว้ — ถ้าส่งต่อไป โมเดลนั้นจะโหลดไม่ขึ้นเลย (router ตอบ HTTP 500 "failed to load")
      device_ids = None (ตรวจ GPU ไม่ได้) → ไม่เช็ก เชื่อผู้ใช้
    """
    user, warnings = parse_ini(user_text)
    out = {k: dict(v) for k, v in sections.items()}
    known = set(model_ids) | {"*"}
    for name, keys in user.items():
        if name not in known and "model" not in keys:
            warnings.append("models-preset.user.ini: ข้าม [%s] — ไม่มีโมเดลชื่อนี้ (ใส่ model = path ถ้าตั้งใจสร้างใหม่)"
                            % name)
            continue
        if not valid_model_id(name) and name != "*":
            warnings.append("models-preset.user.ini: ข้าม [%s] — ชื่อ section ใช้ไม่ได้" % name)
            continue
        dst = out.setdefault(name, {})
        for k, v in keys.items():
            if not _KEY_RE.match(k):
                warnings.append("models-preset.user.ini: ข้าม key '%s' ใน [%s]" % (k, name))
                continue
            if v == "":
                dst.pop(k, None)
                continue
            if k == "device" and device_ids is not None:
                bad = _bad_device_value(v, device_ids)
                if bad:
                    warnings.append("models-preset.user.ini: [%s] device = %s — ตอนนี้ไม่มี GPU ชื่อ %s (มี: %s) "
                                    "ไม่ใช้ค่านี้ ใช้ที่จัดให้อัตโนมัติแทน (ไม่งั้นโมเดลจะโหลดไม่ขึ้น)"
                                    % (name, v, ", ".join(bad), ", ".join(device_ids) or "none"))
                    continue
            dst[k] = v
    return out, warnings


def apply_user_placement(result, sections, models, devices, warnings):
    """ทำ placement ใน gpu-profile.json ให้ตรงกับ preset หลัง merge models-preset.user.ini

    hub แสดง GPU ของแต่ละโมเดลจาก placement ถ้าคิดจากแผนก่อน merge จะโชว์การ์ดที่ไม่ได้ใช้จริง
    คิดใหม่เฉพาะโมเดลที่ device / ctx-size / mmproj เปลี่ยนจากแผน แล้วติดป้าย user_override + source "user-ini"
    "แผน" ในที่นี้คือหลังใช้ gpu-choice.json แล้ว — user.ini ชนะที่เลือกในหน้าแชต (choice_overridden)
    """
    gpus = list(devices or [])
    by_id = {d["id"]: d for d in gpus}
    planned = result["sections"]
    placement = result["placement"]
    primary_id = result["primary"]
    # การ์ดที่โมเดลหลักจองไว้ — apply_choices อาจย้ายไปแล้ว (โมเดลหลักถูกเลือกไปอยู่การ์ดอื่น)
    fit_id = result.get("reserve_gpu", result["fit_gpu"])

    def carry(old, new):
        # ป้าย "มาจากไหน" ของ apply_choices ต้องตามไปด้วย ไม่งั้นหน้าเว็บไม่รู้ว่าผู้ใช้เลือกอะไรไว้
        for k in _CHOICE_FIELDS:
            if k in old and k not in new:
                new[k] = old[k]
        return new
    info = {m.id: m for m in models}
    # โมเดลหลักก่อน — งบที่โมเดลอื่นเหลือบนการ์ดที่ใช้ร่วมกันขึ้นกับว่าโมเดลหลักจองไปเท่าไร
    order = sorted(placement, key=lambda mid: mid != primary_id)
    reserved_all = None
    primary_moved = False
    for mid in order:
        m = info.get(mid)
        if m is None:
            continue
        new = effective_from_sections(sections, mid)
        old = effective_from_sections(planned, mid)
        changed = any(_norm(k, new[k]) != _norm(k, old[k]) for k in ("device", "ctx-size", "mmproj"))
        p = placement[mid]
        is_primary = mid == primary_id
        if not changed:
            if is_primary and fit_id is not None:
                reserved_all = {fit_id: m.need_bytes(p["ctx"], p["vision"])}
            elif primary_moved and not is_primary:
                # ค่าของโมเดลนี้ไม่ได้เปลี่ยน แต่ที่จองของโมเดลหลักเปลี่ยนไป (เลิกจองใบเดิม หรือไปจองใบที่โมเดลนี้อยู่)
                # — คิดตัวเลขใหม่ทุกตัว ตัวที่ไม่ได้ใช้การ์ดร่วมกันก็ได้ค่าเท่าเดิม
                devs = [by_id[i] for i in p["devices"] if i in by_id]
                new_p = carry(p, placement_entry(m, devs, p["ctx"], p["vision"], reserved=reserved_all))
                if new_p.get("source") == "choice":
                    new_p["note_th"], new_p["note_en"] = _notes(new_p, devs)
                placement[mid] = new_p
            continue
        dev = new["device"]
        if devices is None:
            devs = [by_id[i] for i in p["devices"] if i in by_id]
        elif dev is None:
            devs = gpus                                  # ไม่มี device = llama.cpp ใช้ทุกใบตามลำดับปกติ
        elif dev.strip() == "none":
            devs = []
        else:
            devs = [by_id[i.strip()] for i in dev.split(",") if i.strip() in by_id]
        try:
            ctx = int(new["ctx-size"]) if new["ctx-size"] else p["ctx"]
        except ValueError:
            ctx = p["ctx"]
        mm_path = new["mmproj"]
        mm_bytes = None
        if mm_path:
            if os.path.isfile(mm_path):
                mm_bytes = os.path.getsize(mm_path)
            else:
                mm_bytes = 0
                warnings.append("models-preset.user.ini: [%s] mmproj = %s — ไม่พบไฟล์นี้ (โมเดลจะโหลดไม่ขึ้น)"
                                % (mid, mm_path))
        new_p = carry(p, placement_entry(m, devs, ctx, bool(mm_path), is_primary=is_primary,
                                         reserved=None if is_primary else reserved_all,
                                         mm_bytes=mm_bytes, user_override=True))
        if new_p.get("source") == "choice" and _norm("device", new["device"]) != _norm("device", old["device"]):
            # เลือก GPU ไว้ในหน้าแชตแต่ user.ini ตั้ง device ของโมเดลนี้ทับ — บอกให้รู้ว่าทำไมไม่ตรงกับที่เลือก
            # (user.ini แก้แค่ ctx/mmproj ไม่นับ: GPU ยังเป็นตามที่เลือก)
            new_p["choice_overridden"] = True
            warnings.append("models-preset.user.ini ตั้ง device ของ %s ไว้ — ชนะ GPU ที่เลือกในหน้าแชต (%s)"
                            % (mid, _choice_text(new_p["choice"])))
        new_p["source"] = "user-ini"
        placement[mid] = new_p
        if is_primary:
            primary_moved = True
            # จองเฉพาะเมื่อโมเดลหลักอยู่การ์ดใบเดียวที่จุได้ทั้งตัว — กติกาเดียวกับ plan() และ apply_choices()
            need = m.need_bytes(ctx, bool(mm_path), mm_bytes=mm_bytes)
            reserved_all = None
            if len(devs) == 1 and need <= budget_bytes(devs[0]):
                reserved_all = {devs[0]["id"]: need}
            result["reserve_gpu"] = devs[0]["id"] if reserved_all else None
    return placement


def render_preset(sections, header):
    lines = ["; " + h for h in header] + [""]
    for name, keys in sections.items():
        if name != "*" and not keys:
            continue
        lines.append("[%s]" % name)
        for k, v in keys.items():
            lines.append("%s = %s" % (k, v))
        lines.append("")
    return "\n".join(lines)


def _write_atomic(path, text):
    """เขียนไฟล์ใหม่ทั้งไฟล์แล้วค่อยสลับ — hub อาจอ่านอยู่พอดี และห้ามมี BOM
    (ทดสอบแล้ว: INI ที่ขึ้นต้นด้วย BOM ทำให้ llama-server ปิดตัวทันทีตอนเริ่ม)"""
    tmp = path + ".tmp%d" % os.getpid()
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


# ================================================================ สร้างโปรไฟล์
def llama_running():
    """มี llama-server.exe รันอยู่ไหม (ถือ VRAM อยู่หรือเปล่า) — True ถ้าเช็กไม่ได้ จะได้ไม่เตือนมั่วๆ"""
    try:
        rc, out, _err = _run(["tasklist", "/FI", "IMAGENAME eq llama-server.exe", "/FO", "CSV", "/NH"], 10)
    except (OSError, subprocess.SubprocessError):
        return True
    if rc != 0:
        return True
    return "llama-server.exe" in out.lower()


def sections_sha1(text_or_sections):
    """sha1 ของเนื้อหา preset (เฉพาะ section/key/value ไม่รวมคอมเมนต์) — ใช้เทียบว่า "ค่าเปลี่ยนจริงไหม\""""
    if isinstance(text_or_sections, str):
        text_or_sections = parse_ini(text_or_sections)[0]
    canon = json.dumps(text_or_sections, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()


def generate(models_dir=DEFAULT_MODELS_DIR, out_dir=DEFAULT_OUT_DIR, opts=None, simulate=None,
             user_ini=USER_INI, exe=LLAMA_SERVER, discovery=None, free_reliable=None, choice=CHOICE_FILE):
    """ตรวจ GPU + สแกนโมเดล + วางแผน แล้วเขียน preset/json — คืน dict ของโปรไฟล์

    discovery=(devices, source, fingerprint) ใช้ในเทสต์แทนการตรวจจริง
    free_reliable=None = ตรวจเอง: ค่า free ของ GPU เชื่อได้เมื่อไม่มี llama-server ตัวไหนถือ VRAM อยู่
    choice = gpu-choice.json ที่จะใช้ (None หรือ "none" = ไม่อ่าน) — ลำดับ: แผนอัตโนมัติ < choice < user.ini
    """
    opts = opts or Options()
    warnings = []
    if not os.path.isdir(models_dir):
        raise FileNotFoundError("ไม่พบโฟลเดอร์โมเดล %s" % models_dir)
    if discovery is not None:
        devices, source, fp = discovery
    else:
        devices, source, fp = discover(exe, simulate, warnings)
    if devices is not None:
        assign_gpu_keys(devices)          # discovery จากเทสต์ยังไม่มี key
    if free_reliable is None:
        free_reliable = bool(simulate) or discovery is not None or not llama_running()
    models = scan_models(models_dir, warnings)
    if not models:
        warnings.append("ไม่พบโมเดลใน %s — preset มีแค่ [*]" % models_dir)
    result = plan(devices, models, opts, free_reliable=free_reliable)
    warnings += result["warnings"]
    # router แบบเดิม (legacy) ไม่อ่าน preset — การเลือก GPU ใช้ไม่ได้จริง จึงไม่อ่านเลย (ไม่บรรยายสิ่งที่ไม่ได้ใช้)
    choice_info = None if opts.legacy else read_choice(choice, warnings)
    apply_choices(result, models, devices, opts, (choice_info or {}).get("models"), warnings)
    sections = result["sections"]
    user_applied = False
    if user_ini and os.path.isfile(user_ini):
        with open(user_ini, "r", encoding="utf-8-sig") as f:
            known = [m.id for m in models] + [s for m in models for s in m.shard_ids]
            dev_ids = None if devices is None else [d["id"] for d in devices]
            sections, w = merge_user_overrides(sections, f.read(), known, dev_ids)
        warnings += w
        user_applied = True
        apply_user_placement(result, sections, models, devices, warnings)

    gpus = list(devices or [])
    header = ["สร้างอัตโนมัติโดย C:\\LLM\\gpu_profile.py ทุกครั้งที่เปิดตัวเปิด — อย่าแก้ไฟล์นี้",
              "GENERATED by gpu_profile.py - do not edit; put overrides in models-preset.user.ini",
              "profile: %s" % result["profile"]]
    for d in gpus:
        header.append("%s = %s (%d MiB, %s)" % (d["id"], d["short"], d["total_mib"],
                                                "external" if d["external"] else "internal"))
    # เป็นแค่คอมเมนต์ (compare_running เทียบเฉพาะค่า) — ไม่มีการเลือกก็ไม่มีบรรทัดนี้ preset จึงเหมือนเดิมทุกไบต์
    # โมเดลที่ user.ini ตั้ง device ทับไม่นับ: section ของมันเป็นค่าของ user.ini ไม่ใช่ที่เลือกในหน้าแชต
    chosen_ids = [mid for mid in result["choices_applied"]
                  if not result["placement"].get(mid, {}).get("choice_overridden")]
    if chosen_ids:
        header.append("chosen in the chat page (gpu-choice.json): %s" % ", ".join(chosen_ids))
    if user_applied:
        header.append("merged: %s" % user_ini)
    preset_text = render_preset(sections, header)

    summary_th, summary_en = build_summary(devices, source, result)
    profile = {
        "version": PROFILE_VERSION,
        "generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "fingerprint": fp,
        "cuda_device_order": CUDA_DEVICE_ORDER,
        "profile": result["profile"],
        "discovery": source,
        "devices": [public_device(d) for d in gpus],
        "primary_model": result["primary"],
        # ขนาด/หน่วยความจำที่ต้องใช้ของทุกโมเดล (หน้าเลือก GPU ใช้บอก "พอดี / ล้นไป CPU ~X GB")
        "models": model_catalog(models_dir, primary=result["primary"], models=models),
        "placement": result["placement"],
        # gpu-choice.json ที่อ่านได้รอบนี้ (null = --choice none หรือ legacy) — sha1 null = ไม่มีไฟล์
        "choice": choice_info,
        "options": {"ctx": opts.ctx, "threads": opts.threads, "vision": opts.vision, "primary": opts.primary,
                    "legacy": opts.legacy},
        "user_overrides": user_ini if user_applied else None,
        # ชื่อไฟล์อย่างเดียว (อยู่โฟลเดอร์เดียวกับ json นี้เสมอ) — ตัวเปิดสร้างในโฟลเดอร์ชั่วคราว
        # แล้วค่อยคัดลอกทั้งคู่ไป C:\LLM ถ้าเก็บ path เต็มจะชี้ไปโฟลเดอร์ชั่วคราวที่ไม่มีแล้ว
        "preset_file": PRESET_NAME,
        "preset_sha1": hashlib.sha1(preset_text.encode("utf-8")).hexdigest(),
        "sections_sha1": sections_sha1(preset_text),
        "warnings": warnings,
        "summary_th": summary_th,
        "summary_en": summary_en,
    }
    os.makedirs(out_dir, exist_ok=True)
    _write_atomic(os.path.join(out_dir, PRESET_NAME), preset_text)
    _write_atomic(os.path.join(out_dir, PROFILE_NAME), json.dumps(profile, ensure_ascii=False, indent=2) + "\n")
    return profile


# ================================================================ เทียบกับ router ที่รันอยู่
def router_auth_headers(url):
    """header Authorization สำหรับ router ในเครื่อง — {} ถ้าไม่ใช่ 127.0.0.1/localhost หรืออ่านโทเคนไม่ได้

    ส่งเฉพาะ loopback: โทเคนเดียวกันเปิด MCP ทั้งสองตัวได้ ห้ามหลุดไปเครื่องอื่นแม้ผู้ใช้ส่ง --port/URL แปลกมา
    ไม่แปลงตัวพิมพ์ — llama-server เทียบทั้งสตริงตรงตัวกับบรรทัดในไฟล์
    """
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return {}
    if host not in _LOOPBACK_HOSTS:
        return {}
    path = (os.environ.get(LOCAL_TOKEN_ENV) or "").strip() or LOCAL_TOKEN_FILE
    try:
        with open(path, "rb") as fh:
            tok = fh.read(256).decode("utf-8-sig").strip()
    except (OSError, UnicodeDecodeError):
        return {}
    return {"Authorization": "Bearer " + tok} if _LOCAL_TOKEN_RE.fullmatch(tok) else {}


# ไม่ผ่าน proxy ของระบบ/ตัวแปร HTTP_PROXY: คำขอที่พกโทเคนต้องไม่ถูกส่งออกนอกเครื่อง
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_json(url, timeout=HTTP_TIMEOUT_S, body=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    headers.update(router_auth_headers(url))
    req = urllib.request.Request(url, data=data, headers=headers)
    with _NO_PROXY_OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def router_models(port, fetch=None):
    """[{id, status, args}] จาก GET /models ของ router — args คือ argv จริงที่ router ส่งให้โมเดลลูก"""
    doc = (fetch or http_json)("http://127.0.0.1:%d/models" % port)
    out = []
    for m in doc.get("data") or []:
        st = m.get("status") or {}
        out.append({"id": m.get("id"), "status": st.get("value"), "args": st.get("args") or []})
    return out


def effective_from_args(args):
    eff = {}
    for i, a in enumerate(args):
        k = ARG_ALIASES.get(a)
        if k and i + 1 < len(args):
            eff[k] = str(args[i + 1])
    return {k: eff.get(k) for k in TRACKED_KEYS}


def effective_from_sections(sections, model_id):
    merged = dict(sections.get("*", {}))
    merged.update(sections.get(model_id, {}))
    return {k: merged.get(k) for k in TRACKED_KEYS}


def _norm(key, v):
    if v is None:
        return None
    v = str(v).strip()
    if key == "mmproj":
        return os.path.normcase(os.path.normpath(v))
    if key == "device":
        return ",".join(p.strip() for p in v.split(","))
    return v


def _devices_text(devs):
    if not devs:
        return "ไม่มี GPU"
    return " + ".join("%s %.0f GB" % (d.get("short") or d.get("id"), (d.get("total_mib") or 0) / 1024) for d in devs)


def _dev_sig(devs):
    return [(str(d.get("id")), str(d.get("short") or d.get("name") or ""), int(d.get("total_mib") or 0))
            for d in (devs or [])]


def _canon_lines(sections):
    """preset แบบไม่มีคอมเมนต์และบรรทัดว่าง — ไว้แสดง diff ที่อ่านรู้เรื่อง ไม่มีบรรทัด "+" "-" เปล่าๆ"""
    return [l for l in render_preset(sections, []).splitlines() if l.strip()]


def fail_log_path(port):
    """log ที่ตัวเปิดเก็บไว้ตอน router ปิดตัวทันทีเมื่อใช้ preset (ชื่อเดียวกับ $LlamaLogName ของตัวเปิด)"""
    name = "llama" if int(port) == DEFAULT_PORT else "llama-%d" % int(port)
    return os.path.join(LOG_DIR, name + ".preset-fail.err.log")


def compare_running(port, router_pid, state_path, new_dir, fetch=None):
    """คืน (changed: bool | None, บรรทัดภาษาไทย, keep_legacy: bool)

    changed = None → ตัดสินไม่ได้ ให้ปล่อย router ไว้ตามเดิม
    keep_legacy = True → router ตัวนี้ถอยไปใช้ค่าแบบเดิมเพราะ preset ชุดเดียวกันนี้เคยทำให้มันปิดตัวทันที
      ไม่ต้องรีสตาร์ตวนซ้ำทุกครั้งที่เปิดตัวเปิด (รีสตาร์ต = ทิ้งโมเดลที่โหลดไว้) และห้ามเผยแพร่แผน preset ให้ hub
    เทียบสองทาง:
      1. GPU กับ preset ที่บันทึกไว้ตอน router ตัวนี้เริ่ม (ไฟล์ state ต้องเป็น PID เดียวกัน)
      2. ค่าที่ router ส่งให้โมเดลลูกจริงๆ (/models) กับ preset ใหม่ — ใช้ได้แม้ router ถูกเปิดด้วย
         ตัวเปิดรุ่นเก่า (ไม่มี preset) เพราะ -c/-t เดิมก็โผล่เป็น --ctx-size/--threads เหมือนกัน
    """
    with open(os.path.join(new_dir, PROFILE_NAME), "r", encoding="utf-8") as f:
        new_profile = json.load(f)
    with open(os.path.join(new_dir, PRESET_NAME), "r", encoding="utf-8") as f:
        new_text = f.read()
    new_sections, _ = parse_ini(new_text)
    if new_profile.get("profile") == "unknown":
        # ตรวจ GPU ไม่ได้เลยรอบนี้ แผนใหม่เป็นค่ากลางๆ — ไม่ใช่เหตุผลที่จะรีสตาร์ตทิ้งโมเดลที่โหลดไว้
        return None, ["ตรวจ GPU ไม่สำเร็จรอบนี้ — ไม่เทียบ ปล่อย router เดิมไว้ตามเดิม"], False
    state = None
    if state_path and os.path.isfile(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (OSError, ValueError):
            state = None
    valid = bool(state) and state.get("port") == port and int(state.get("router_pid") or -1) == int(router_pid)
    lines, changed, failed_same = [], False, False
    if valid:
        old_fp, new_fp = state.get("fingerprint"), new_profile.get("fingerprint")
        # fingerprint เป็น null = nvidia-smi ล้มชั่วคราว ไม่ใช่ "GPU เปลี่ยน" (ไม่งั้นรีสตาร์ตทิ้งโมเดลฟรีๆ)
        fp_changed = bool(old_fp and new_fp and old_fp != new_fp)
        # รายการที่ llama-server เห็นจริงก็ต้องเทียบ: รอบที่ซ่อน GPU ด้วย CUDA_VISIBLE_DEVICES ลายนิ้วมือจาก
        # nvidia-smi เท่าเดิม แต่ router เห็นคนละชุด — เทียบเฉพาะเมื่อบันทึกรอบก่อนรู้รายการแน่ชัด
        known = state.get("devices_known")
        if known is None:                      # state รุ่นก่อนไม่มี key นี้
            known = state.get("profile") not in (None, "unknown")
        dev_changed = bool(known) and _dev_sig(state.get("devices")) != _dev_sig(new_profile.get("devices"))
        if fp_changed or dev_changed:
            changed = True
            lines.append("GPU เปลี่ยน: ตอนเริ่ม router มี %s → ตอนนี้มี %s"
                         % (_devices_text(state.get("devices")), _devices_text(new_profile.get("devices"))))
        old_text = state.get("preset_text")
        if state.get("mode") == "preset" and old_text is not None:
            # เทียบเนื้อหา ไม่ใช่ข้อความทั้งไฟล์ — หัวไฟล์เป็นคอมเมนต์ (ชื่อโปรไฟล์ รายการ GPU "merged: ...")
            # เปลี่ยนได้โดยที่ค่าที่ router ใช้ไม่เปลี่ยนเลย
            old_sections, _ = parse_ini(old_text)
            if old_sections != new_sections:
                changed = True
                lines.append("models-preset.ini เปลี่ยน:")
                for l in difflib.unified_diff(_canon_lines(old_sections), _canon_lines(new_sections),
                                              lineterm="", n=0):
                    if l.startswith(("---", "+++", "@@")) or not l[1:].strip():
                        continue
                    lines.append("    " + l)
        failed = state.get("preset_failed_sha1")
        failed_same = state.get("mode") == "legacy" and bool(failed) and failed == sections_sha1(new_sections)
    else:
        lines.append("ไม่มีบันทึกว่า router พอร์ต %d เริ่มด้วย GPU ชุดไหน — เทียบจากค่าที่ router ใช้จริงแทน" % port)
    try:
        running = router_models(port, fetch)
    except (OSError, ValueError, urllib.error.URLError) as e:
        lines.append("อ่าน /models ของ router ไม่ได้ (%s)" % e)
        return (changed if valid else None), lines, False
    new_ids = {k for k in new_sections if k != "*"} | set((new_profile.get("placement") or {}).keys())
    arg_lines = []
    for m in running:
        mid = m["id"]
        if mid not in new_ids:
            continue
        old = effective_from_args(m["args"])
        new = effective_from_sections(new_sections, mid)
        diffs = [(k, old[k], new[k]) for k in TRACKED_KEYS if _norm(k, old[k]) != _norm(k, new[k])]
        if diffs:
            arg_lines.append("%s: %s" % (mid, ", ".join("%s %s → %s" % (k, _short_val(k, a), _short_val(k, b))
                                                       for k, a, b in diffs)))
    keep_legacy = False
    if failed_same and not changed:
        # ค่าต่างจาก preset ก็เพราะ router ใช้ค่าแบบเดิมอยู่ — preset ชุดเดียวกันเปิดไม่ขึ้นมาแล้ว รีสตาร์ตก็ล้มซ้ำ
        keep_legacy = True
        lines.append("router ใช้ค่าแบบเดิมอยู่ เพราะ preset ชุดนี้เคยทำให้ llama-server ปิดตัวทันที (ดู %s) — "
                     "ไม่รีสตาร์ตซ้ำ; ถ้าแก้ models-preset.user.ini แล้ว เปิดตัวเปิดอีกครั้ง หรือปิดด้วย "
                     "stop-qwen38.ps1 แล้วเปิดใหม่เพื่อลอง preset อีกรอบ" % fail_log_path(port))
    elif arg_lines:
        changed = True
        lines += arg_lines
    if not changed and not keep_legacy:
        lines.append("GPU และค่าของทุกโมเดลเหมือนเดิม — ไม่ต้องรีสตาร์ต")
    return changed, lines, keep_legacy


def _short_val(key, v):
    if v is None:
        return "(ไม่กำหนด)"
    return os.path.basename(v) if key == "mmproj" else v


def record_state(port, router_pid, mode, profile_dir, state_path, failed_preset=None):
    """บันทึกว่า router ตัวนี้ (PID) เริ่มด้วย GPU ชุดไหนและ preset อะไร — ไว้เทียบรอบหน้า

    profile_dir = โฟลเดอร์ที่มี preset + json ชุดที่ router ตัวนี้ "อ่านจริง" (ตัวเปิดส่งโฟลเดอร์ที่สร้าง
    ไม่ใช่ไฟล์กลางใน C:\\LLM ที่ตัวเปิดพอร์ตอื่นอาจเขียนทับไปแล้ว)
    failed_preset = preset ที่ทำให้ router ปิดตัวทันที (mode legacy) — จำ sha ไว้ รอบหน้าจะได้ไม่รีสตาร์ตวนซ้ำ
    """
    profile, preset_text = {}, None
    try:
        with open(os.path.join(profile_dir, PROFILE_NAME), "r", encoding="utf-8") as f:
            profile = json.load(f)
    except (OSError, ValueError):
        profile = {}
    if mode == "preset":
        with open(os.path.join(profile_dir, PRESET_NAME), "r", encoding="utf-8") as f:
            preset_text = f.read()
        # json ของรอบนี้ได้ fingerprint = null ถ้า nvidia-smi ล้มตอนสร้าง — ถามใหม่อีกครั้ง
        fp = profile.get("fingerprint") or current_fingerprint()
    else:
        # json ที่ส่งมาอาจเป็นของรอบก่อน (สร้างโปรไฟล์รอบนี้ไม่สำเร็จ) — ถาม nvidia-smi ตรงๆ แล้วทิ้ง json
        # เฉพาะเมื่อรู้ทั้งสองค่าและไม่ตรงกัน (nvidia-smi ล้มชั่วคราวไม่ใช่เหตุผลที่จะลืมรายการ GPU)
        fp = current_fingerprint()
        if fp and profile.get("fingerprint") and profile.get("fingerprint") != fp:
            profile = {}
        fp = fp or profile.get("fingerprint")
    failed_sha = None
    if failed_preset and os.path.isfile(failed_preset):
        with open(failed_preset, "r", encoding="utf-8") as f:
            failed_sha = sections_sha1(f.read())
    state = {
        "version": STATE_VERSION,
        "port": int(port),
        "router_pid": int(router_pid),
        "mode": mode,
        "started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "fingerprint": fp,
        "devices_known": bool(profile) and profile.get("profile") not in (None, "unknown"),
        "devices": [{k: d.get(k) for k in ("id", "short", "total_mib", "external")}
                    for d in (profile.get("devices") or [])],
        "profile": profile.get("profile"),
        "preset_text": preset_text,
        "preset_failed_sha1": failed_sha,
    }
    os.makedirs(os.path.dirname(state_path) or ".", exist_ok=True)
    _write_atomic(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    return state


def router_activity(port, fetch=None):
    """(busy, รายละเอียด, ลายเซ็นกิจกรรม)

    busy = มีโมเดลกำลังโหลด / มี slot กำลังตอบ (is_processing) / อ่าน /slots ของโมเดลที่โหลดอยู่ไม่ได้
    (ไม่รู้ = ถือว่ายุ่ง ปลอดภัยกว่าตัดแชตกลางคัน)
    ลายเซ็น = สถานะโมเดล + id_task ของทุก slot — เปลี่ยนเมื่อมีงานใหม่เข้ามา แม้งานนั้นจะเริ่มและจบ
    ระหว่างสองรอบที่ถาม (เช่นเทิร์นสั้นๆ หลังเครื่องมือ MCP ทำงานเสร็จ)
    router ตอบ /slots เฉพาะเมื่อระบุ ?model= (ไม่ระบุได้ 400) จึงต้องถามทีละโมเดลที่โหลดอยู่
    """
    fetch = fetch or http_json
    busy, notes, sig = False, [], []
    for m in router_models(port, fetch):
        sig.append((m["id"], m["status"]))
        if m["status"] == "loading":
            busy = True
            notes.append("%s กำลังโหลด" % m["id"])
        elif m["status"] == "loaded":
            try:
                slots = fetch("http://127.0.0.1:%d/slots?model=%s" % (port, urllib.parse.quote(m["id"])))
            except (OSError, ValueError, urllib.error.URLError) as e:
                busy = True
                notes.append("%s: อ่าน /slots ไม่ได้ (%s) — ถือว่ายังไม่ว่าง" % (m["id"], e))
                continue
            slots = [s for s in (slots if isinstance(slots, list) else []) if isinstance(s, dict)]
            sig.extend((m["id"], s.get("id"), s.get("id_task")) for s in slots)
            n = sum(1 for s in slots if s.get("is_processing"))
            if n:
                busy = True
                notes.append("%s กำลังตอบอยู่ %d งาน" % (m["id"], n))
    return busy, notes, tuple(sig)


def router_busy(port, fetch=None):
    """(busy, รายละเอียด) — ดู router_activity"""
    busy, notes, _sig = router_activity(port, fetch)
    return busy, notes


def _router_gone(e):
    """ต่อไม่ติดเพราะไม่มีใครฟังพอร์ตแล้ว = router ปิดไปแล้ว ไม่มีแชตให้รอ (ต่างจาก timeout ที่อาจแค่ยุ่ง)"""
    return isinstance(getattr(e, "reason", e), ConnectionRefusedError)


def wait_idle(port, timeout_s, out=print, fetch=None, sleep=time.sleep, clock=time.monotonic):
    """รอจน router ว่างต่อเนื่อง IDLE_QUIET_S วินาที — EXIT_OK = ว่างแล้ว, EXIT_BUSY = ยังไม่ว่างจนหมดเวลา

    ว่าง = ไม่มีโมเดลกำลังโหลด ไม่มี slot กำลังตอบ และไม่มีงานใหม่เข้ามาระหว่างรอ (ลายเซ็นไม่เปลี่ยน)
    ดูครั้งเดียวไม่พอ: ระหว่างที่เครื่องมือ MCP ทำงานกลางคำตอบ slot ว่างอยู่หลายวินาที
    อ่านสถานะไม่ได้ = ถือว่ายังไม่ว่าง ยกเว้นต่อไม่ติดเลย (router ปิดไปแล้ว)
    """
    deadline = clock() + timeout_s
    quiet_since, last_sig, announced = None, None, False
    while True:
        try:
            busy, notes, sig = router_activity(port, fetch)
        except (OSError, ValueError, urllib.error.URLError) as e:
            if isinstance(e, urllib.error.HTTPError) and e.code == 401:
                # router เปิดด้วย --api-key-file แต่โทเคนในไฟล์ตอนนี้ไม่ใช่ตัวที่มันจำไว้ (ไฟล์ถูกสร้างใหม่) —
                # รอไปก็ไม่มีวันอ่านสถานะได้ และ hub/Gateway ที่ถือโทเคนใหม่ก็ส่งแชตถึงมันไม่ได้อยู่แล้ว
                out("router พอร์ต %d ปฏิเสธโทเคนปัจจุบัน (401) — ไฟล์โทเคนถูกสร้างใหม่หลัง router เริ่ม "
                    "ต้องรีสตาร์ต router ให้อ่านโทเคนใหม่" % port)
                return EXIT_AUTH
            if _router_gone(e):
                out("router พอร์ต %d ไม่ตอบแล้ว (ปิดไปแล้ว) — ไม่มีแชตให้รอ" % port)
                return EXIT_OK
            busy, notes, sig = True, ["อ่านสถานะ router ไม่ได้ (%s) — ถือว่ายังไม่ว่าง" % e], None
        now = clock()
        if busy or sig is None or (last_sig is not None and sig != last_sig):
            if quiet_since is not None or not announced:
                out("รอให้แชตที่กำลังตอบอยู่เสร็จก่อน (สูงสุด %d วินาที): %s"
                    % (timeout_s, "; ".join(notes) or "มีงานใหม่เข้ามา"))
                announced = True
            quiet_since = None
        elif quiet_since is None:
            quiet_since = now
        last_sig = sig
        if quiet_since is not None and now - quiet_since >= IDLE_QUIET_S:
            return EXIT_OK
        # กำลังนับช่วงเงียบอยู่ก็ให้นับจนครบ ไม่ตัดจบเพราะหมดเวลาพอดี
        if quiet_since is None and now >= deadline:
            out("ยังมีงานค้างอยู่เมื่อครบ %d วินาที — ไม่รีสตาร์ต" % timeout_s)
            return EXIT_BUSY
        sleep(IDLE_POLL_S)


# ================================================================ CLI
def _same_dir(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _build_parser():
    ap = argparse.ArgumentParser(description="จัดวางโมเดลลง GPU แล้วเขียน models-preset.ini + gpu-profile.json")
    ap.add_argument("--write", action="store_true", help="ตรวจ GPU แล้วเขียน preset + json")
    ap.add_argument("--models-dir", default=DEFAULT_MODELS_DIR)
    ap.add_argument("--ctx", type=int, default=None, help="บังคับ context ของทุกโมเดล")
    ap.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    vis = ap.add_mutually_exclusive_group()
    vis.add_argument("--vision", dest="vision", action="store_true", default=None, help="บังคับเปิดดูรูป")
    vis.add_argument("--no-vision", dest="vision", action="store_false", help="บังคับปิดดูรูป")
    ap.add_argument("--primary", default=None, help="model id ของโมเดลหลัก (ปกติ = %s หรือตัวแรกที่มี qwen3.8)"
                    % DEFAULT_PRIMARY)
    ap.add_argument("--legacy", action="store_true",
                    help="บรรยาย router ที่เปิดด้วยค่าแบบเดิม (ตัวเปิดถอยกลับเพราะ preset ใช้ไม่ได้) ให้ hub แสดงตามจริง")
    ap.add_argument("--simulate", default=None,
                    help="ไฟล์ JSON รายการ GPU ปลอม ใช้แทนการตรวจจริง (ต้องระบุ --out-dir อื่นที่ไม่ใช่ C:\\LLM)")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--user-ini", default=USER_INI)
    ap.add_argument("--choice", default=CHOICE_FILE,
                    help="gpu-choice.json ที่ผู้ใช้เลือก GPU ไว้ในหน้าแชต (none = ไม่ใช้ ทุกโมเดลจัดวางอัตโนมัติ)")
    ap.add_argument("--llama-server", default=LLAMA_SERVER)
    ap.add_argument("--fingerprint", action="store_true", help="พิมพ์ลายนิ้วมือ GPU ตอนนี้")
    ap.add_argument("--compare-running", action="store_true",
                    help="เทียบ router ที่รันอยู่ (--port, --router-pid) กับโปรไฟล์ใน --out-dir; exit 0 = เหมือนเดิม, "
                         "10 = เปลี่ยน, 12 = router ใช้ค่าแบบเดิมเพราะ preset นี้เคยล้ม (ไม่ต้องรีสตาร์ต), 2 = ตัดสินไม่ได้")
    ap.add_argument("--record-state", action="store_true", help="บันทึกว่า router (--port, --router-pid) เริ่มด้วยโปรไฟล์ใน --out-dir")
    ap.add_argument("--mode", choices=("preset", "legacy"), default="preset")
    ap.add_argument("--failed-preset", default=None,
                    help="กับ --record-state --mode legacy: preset ที่ทำให้ router ปิดตัวทันที (จำไว้ ไม่รีสตาร์ตวนซ้ำ)")
    ap.add_argument("--wait-idle", action="store_true",
                    help="รอจน router ไม่มีงานค้าง; exit 11 = ยังไม่ว่าง, 13 = router ปฏิเสธโทเคนปัจจุบัน (ต้องรีสตาร์ต)")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--router-pid", type=int, default=0)
    ap.add_argument("--state", default=None, help="ไฟล์ state ของ router (ปกติ C:\\LLM\\logs\\router-<port>.state.json)")
    ap.add_argument("--report", default=None, help="เขียนข้อความผลลัพธ์ (UTF-8) ลงไฟล์นี้ด้วย ให้ PowerShell 5.1 อ่านได้ไม่เพี้ยน")
    return ap


def main(argv=None):
    args = _build_parser().parse_args(argv)
    report = []

    def out(line=""):
        report.append(line)
        print(line)

    def flush_report():
        if args.report:
            _write_atomic(args.report, "\n".join(report) + "\n")

    state_path = args.state or os.path.join(DEFAULT_OUT_DIR, "logs", "router-%d.state.json" % args.port)
    try:
        if args.fingerprint:
            out(str(current_fingerprint()))
            return EXIT_OK
        if args.compare_running:
            changed, lines, keep_legacy = compare_running(args.port, args.router_pid, state_path, args.out_dir)
            for l in lines:
                out(l)
            if changed is None:
                return EXIT_ERROR
            if changed:
                return EXIT_CHANGED
            return EXIT_KEEP_LEGACY if keep_legacy else EXIT_OK
        if args.record_state:
            st = record_state(args.port, args.router_pid, args.mode, args.out_dir, state_path, args.failed_preset)
            out("บันทึก state ของ router พอร์ต %d (PID %d, %s) แล้ว" % (st["port"], st["router_pid"], st["mode"]))
            return EXIT_OK
        if args.wait_idle:
            return wait_idle(args.port, args.timeout, out)
        if not args.write:
            _build_parser().print_help()
            return EXIT_ERROR
        if args.ctx is not None and args.ctx <= 0:
            raise ValueError("--ctx ต้องมากกว่า 0")
        if args.threads <= 0:
            raise ValueError("--threads ต้องมากกว่า 0")
        if args.simulate and _same_dir(args.out_dir, DEFAULT_OUT_DIR):
            # ผลจำลองลงไฟล์จริงเมื่อไหร่ hub จะแสดง GPU ที่ไม่มีอยู่จริง และ router รอบหน้าจะได้แผนผิด
            raise ValueError("--simulate เขียนลง %s ไม่ได้ (เป็นไฟล์ที่ router ตัวจริงและ hub ใช้) — ระบุ --out-dir อื่น"
                             % DEFAULT_OUT_DIR)
        opts = Options(ctx=args.ctx, threads=args.threads, vision=args.vision, primary=args.primary,
                       legacy=args.legacy)
        prof = generate(args.models_dir, args.out_dir, opts, args.simulate, args.user_ini, args.llama_server,
                        choice=args.choice)
        for line in prof["summary_th"].splitlines():
            out(line)
        for w in prof["warnings"]:
            out("คำเตือน: " + w)
        out("เขียนแล้ว: %s, %s" % (os.path.join(args.out_dir, PRESET_NAME), os.path.join(args.out_dir, PROFILE_NAME)))
        return EXIT_OK
    except Exception as e:     # noqa: BLE001 — ตัวเปิดต้องได้ exit code ไม่ใช่ traceback ค้างจอ
        out("ผิดพลาด: %s: %s" % (type(e).__name__, e))
        return EXIT_ERROR
    finally:
        flush_report()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    sys.exit(main())
