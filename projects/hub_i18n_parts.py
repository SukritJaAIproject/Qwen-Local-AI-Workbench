# -*- coding: utf-8 -*-
"""ชิ้นส่วน UI สองภาษาของ hub — แยกไฟล์เพื่อให้แก้หน้าตาได้โดยไม่แตะ logic

hub.py โหลดไฟล์นี้ใหม่เองเมื่อเวลาแก้ไฟล์เปลี่ยน (ไม่ต้องรีสตาร์ท hub)  ตัวแปรที่ export:
    SHELL        เทมเพลตหน้า shell: แถบข้าง + ส่วนหัว + แผงโปรเจกต์ + iframe ของ WebUI
    PAGE         เทมเพลตหน้าจัดการโปรเจกต์ (hub พอร์ต 8100 ?manage=1)
    STRINGS_UI   ข้อความของ UI ชุดใหม่ hub.py รวมเข้า STRINGS
                 จึงใช้ได้ทั้ง __T_key__ ใน HTML และ T.key ใน JavaScript

เทมเพลตเป็น raw string เพื่อให้ backslash ใน JavaScript ไปถึงเบราว์เซอร์ตรงตัว
ไม่ต้องคิดเผื่อ escape ของ Python ซ้อนอีกชั้น
"""

# --------------------------------------------------------------------------
# SHELL — หน้านอกสุดของทุกพอร์ตโปรเจกต์
# โครง: CSS grid สองคอลัมน์ (แถบข้าง | ส่วนหลัก) ส่วนหลักแบ่งสองแถว (หัว | iframe)
# iframe ต้องได้ขนาดจาก grid ตรงๆ เพราะเป็น replaced element — ถ้าใช้ position:fixed
# กับ left/right แบบเดิม มันไม่ยืดตาม จะกว้างแค่ 300px ค่าเริ่มต้นของเบราว์เซอร์
# --------------------------------------------------------------------------
SHELL = r"""<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>__TITLE__</title>
<script>window.__QWEN_BOOT__ = __BOOTCFG__; window.qwenShell = __SHELLDATA__; window.qwenShell.T = __T_JSON__;</script>
<script src="/_qwen/static/boot.js"></script>
<link rel="stylesheet" href="/_qwen/static/fonts.css">
<link rel="stylesheet" href="/_qwen/static/tokens.css">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%23d97757'/%3E%3Ctext x='16' y='22.5' text-anchor='middle' font-family='Georgia,serif' font-size='20' font-weight='700' fill='white'%3EQ%3C/text%3E%3C/svg%3E">
<style>
*,*::before,*::after{box-sizing:border-box}
html,body{height:100%;margin:0}
/* ค่าสำรองใน var() เฉพาะส่วนที่กำหนดโครงหน้า — ถ้า tokens.css โหลดไม่ทัน/พลาด หน้ายังเป็นโครงเดิม
   ไม่หล่นเป็น HTML ดิบเรียงลงมา (เคยเกิดตอนเปิดหลายแท็บพร้อมกัน) */
body{overflow:hidden;background:var(--qw-bg,#262624);color:var(--qw-text,#f4f2ec);
  font-family:var(--qw-font-ui,"Segoe UI","Leelawadee UI",system-ui,sans-serif);
  font-size:var(--qw-fs-base,14px);line-height:1.5;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
button,input,select,textarea{font:inherit;color:inherit;letter-spacing:inherit}
button{cursor:pointer;background:none;border:0;padding:0;margin:0}
button:disabled{cursor:default}
a{color:inherit;text-decoration:none}
[hidden]{display:none!important}
:focus{outline:none}
:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:1px}
/* accent-soft (12-16%) แทบมองไม่เห็นบนช่องกรอกสีเข้ม — ใช้ความเข้มเท่าฝั่ง iframe */
::selection{background:color-mix(in srgb,var(--qw-accent) 32%,transparent)}
.ic{width:18px;height:18px;flex:none;fill:none;stroke:currentColor;stroke-width:1.75;
  stroke-linecap:round;stroke-linejoin:round;pointer-events:none}
.ic-sm{width:16px;height:16px}
.ic-xs{width:14px;height:14px}
.vh{position:absolute!important;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
/* ลิงก์ข้ามไปช่องพิมพ์ — มองไม่เห็นจนกว่าจะกด Tab ครั้งแรก (ไม่ต้องไล่ผ่านรายการแชตทั้งหมด) */
.skip{position:fixed;left:12px;top:10px;z-index:120;padding:8px 14px;border-radius:var(--qw-r-sm);
  background:var(--qw-text);color:var(--qw-bg);font-size:var(--qw-fs-sm);font-weight:500;transform:translateY(-200%)}
.skip:focus{transform:none}

/* ---------- โครงหน้า ---------- */
#app{--sb:var(--qw-sidebar-w,288px);display:grid;grid-template-columns:var(--sb,288px) minmax(0,1fr);
  height:100vh;height:100dvh;transition:grid-template-columns var(--qw-dur) var(--qw-ease)}
#main{display:grid;grid-template-rows:var(--qw-header-h,52px) minmax(0,1fr);min-width:0;min-height:0;background:var(--qw-bg,#262624)}
#stage{position:relative;min-width:0;min-height:0}
#frame{display:block;width:100%;height:100%;border:0;background:var(--qw-bg,#262624)}

/* ---------- ปุ่มพื้นฐาน ---------- */
.icon-btn{width:32px;height:32px;display:inline-flex;align-items:center;justify-content:center;flex:none;
  border-radius:var(--qw-r-sm);color:var(--qw-text-3);
  transition:background-color var(--qw-dur) var(--qw-ease),color var(--qw-dur) var(--qw-ease)}
.icon-btn:hover,.icon-btn[aria-expanded="true"]{background:var(--qw-bg-hover);color:var(--qw-text)}
.icon-btn.sm{width:28px;height:28px;border-radius:var(--qw-r-xs)}
.icon-btn.xs{width:24px;height:24px;border-radius:var(--qw-r-xs)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:34px;padding:0 14px;
  border-radius:var(--qw-r-sm);font-size:var(--qw-fs-base);font-weight:500;white-space:nowrap;flex:none;
  transition:background-color var(--qw-dur) var(--qw-ease),color var(--qw-dur) var(--qw-ease),opacity var(--qw-dur)}
.btn.sm{height:30px;padding:0 11px;font-size:var(--qw-fs-sm)}
.btn-ink{background:var(--qw-text);color:var(--qw-bg)}
.btn-ink:hover:not(:disabled){opacity:.86}
/* ปิดใช้งาน = ปุ่มโปร่งแบบ ghost ตัวอักษรจาง — พื้น bg-active ในธีมสว่างเป็นก้อนเบจทึบที่ดูเหมือนกดได้ */
.btn-ink:disabled{background:transparent;color:var(--qw-text-4);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.btn-ghost{color:var(--qw-text-2);box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.btn-ghost:hover{background:var(--qw-bg-hover);color:var(--qw-text)}
/* ปุ่มลบแบบทึบใช้ danger-bg (ตัวอักษรขาว ≥5.3:1 ทั้งสองธีม) — --qw-danger เป็นสีตัวอักษร ธีมมืดสว่างเกินรองขาว */
.btn-danger{background:var(--qw-danger-bg);color:#fff}
/* hover เข้มขึ้นแทนการจางลง — opacity ทำให้ตัวอักษรขาวจมลงไปกับพื้นแผง */
.btn-danger:hover{background:color-mix(in srgb,var(--qw-danger-bg) 88%,#000)}

/* ---------- แถบข้าง ---------- */
#sb{position:relative;z-index:20;display:flex;flex-direction:column;min-width:0;min-height:0;overflow:hidden;
  background:var(--qw-bg-sidebar,#1f1e1d);border-right:.5px solid var(--qw-border)}
.sb-head{display:flex;align-items:center;gap:8px;height:var(--qw-header-h);padding:0 10px 0 14px;flex:none}
.brand{display:flex;align-items:center;gap:10px;min-width:0;flex:1;border-radius:var(--qw-r-sm)}
.mark{width:28px;height:28px;flex:none;border-radius:8px;background:var(--qw-accent);color:var(--qw-accent-fg);
  display:inline-flex;align-items:center;justify-content:center;font-family:var(--qw-font-serif);
  font-weight:600;font-size:17px;line-height:1;padding-bottom:1px;user-select:none}
.wordmark{font-family:var(--qw-font-serif);font-weight:600;font-size:15px;letter-spacing:-.005em;
  white-space:nowrap;color:var(--qw-text)}
.sb-nav{display:flex;flex-direction:column;gap:1px;padding:2px 8px 4px;flex:none}
.item{display:flex;align-items:center;gap:10px;width:100%;height:34px;padding:0 10px;min-width:0;
  border-radius:var(--qw-r-sm);color:var(--qw-text-2);white-space:nowrap;text-align:left;position:relative;
  transition:background-color var(--qw-dur) var(--qw-ease),color var(--qw-dur) var(--qw-ease)}
.item:hover{background:var(--qw-bg-hover);color:var(--qw-text)}
.item.on{background:var(--qw-bg-active);color:var(--qw-text)}
.item .lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
.ib{width:24px;height:24px;flex:none;display:inline-flex;align-items:center;justify-content:center;color:var(--qw-text-3)}
.item:hover .ib,.item.on .ib{color:var(--qw-text-2)}
.new-dot{width:24px;height:24px;border-radius:50%;background:var(--qw-accent);color:var(--qw-accent-fg);
  display:inline-flex;align-items:center;justify-content:center;flex:none;
  transition:background-color var(--qw-dur) var(--qw-ease),transform var(--qw-dur) var(--qw-ease)}
.new-dot .ic{stroke-width:2.4}
.item-new{color:var(--qw-text);font-weight:500}
.item-new:hover .new-dot{background:var(--qw-accent-hover);transform:scale(1.06)}
.kbd{font-size:11px;color:var(--qw-text-4);letter-spacing:.02em;flex:none;opacity:0;transition:opacity var(--qw-dur)}
.item:hover .kbd,.item:focus-visible .kbd{opacity:1}
.rail-only{display:none!important}

.search{display:flex;align-items:center;gap:8px;height:34px;padding:0 4px 0 10px;border-radius:var(--qw-r-sm);
  background:var(--qw-bg-elev);box-shadow:inset 0 0 0 .5px var(--qw-border-strong);color:var(--qw-text-3)}
.search:focus-within{box-shadow:inset 0 0 0 1px var(--qw-border-focus),0 0 0 3px var(--qw-accent-soft)}
.search input{flex:1;min-width:0;height:100%;border:0;background:none;outline:none;color:var(--qw-text);font-size:var(--qw-fs-base)}
.search input::placeholder{color:var(--qw-text-4)}

.sb-scroll{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;padding:0 8px 14px;
  scrollbar-width:thin;scrollbar-color:var(--qw-border-strong) transparent}
.sec{margin-top:14px}
.sec-h{display:flex;align-items:center;justify-content:space-between;height:28px;padding:0 3px 0 10px;
  font-size:var(--qw-fs-xs);font-weight:500;color:var(--qw-text-3);white-space:nowrap}
/* เป็น h2 จริงเพื่อให้โปรแกรมอ่านหน้าจอกระโดดตามหัวข้อได้ แต่หน้าตาเท่าป้ายเล็กเดิม */
.sec-t{margin:0;font:inherit;color:inherit}
.sec-h .icon-btn{color:var(--qw-text-4)}
.sec-h .icon-btn:hover{color:var(--qw-text)}
.list{display:flex;flex-direction:column;gap:1px}
.row{position:relative}
.row .item{height:32px}
.row:hover .item,.row:focus-within .item,.row .item.menu-open{padding-right:34px}
.more{position:absolute;right:3px;top:50%;transform:translateY(-50%);width:28px;height:28px;
  display:inline-flex;align-items:center;justify-content:center;border-radius:var(--qw-r-xs);
  color:var(--qw-text-3);opacity:0;transition:opacity var(--qw-dur),background-color var(--qw-dur)}
.row:hover .more,.row:focus-within .more,.more[aria-expanded="true"]{opacity:1}
.more:hover,.more[aria-expanded="true"]{color:var(--qw-text);background:var(--qw-bg-active)}
.item.menu-open{background:var(--qw-bg-hover);color:var(--qw-text)}
.item.snip{height:auto;min-height:32px;padding-top:6px;padding-bottom:6px;flex-direction:column;align-items:stretch;gap:1px}
.snip-t{font-size:var(--qw-fs-xs);color:var(--qw-text-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
mark{background:color-mix(in srgb,var(--qw-accent) 30%,transparent);color:var(--qw-text);border-radius:3px;padding:0 1px}
.empty{padding:6px 10px;font-size:var(--qw-fs-sm);color:var(--qw-text-4)}
.newproj{padding:2px 0 4px}
.newproj input{width:100%;height:34px;padding:0 10px;border:0;border-radius:var(--qw-r-sm);background:var(--qw-bg-elev);
  color:var(--qw-text);box-shadow:inset 0 0 0 1px var(--qw-border-focus),0 0 0 3px var(--qw-accent-soft);outline:none}
.newproj input::placeholder{color:var(--qw-text-4)}

.sb-foot{flex:none;padding:8px;border-top:.5px solid var(--qw-border)}
.acct{display:flex;align-items:center;gap:10px;width:100%;padding:6px 8px;border-radius:var(--qw-r-md);text-align:left;
  transition:background-color var(--qw-dur) var(--qw-ease)}
.acct:hover,.acct[aria-expanded="true"]{background:var(--qw-bg-hover)}
.avatar{position:relative;width:32px;height:32px;border-radius:50%;flex:none;display:inline-flex;align-items:center;
  justify-content:center;background:var(--qw-bg-active);color:var(--qw-text-2);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.hdot{position:absolute;right:-2px;bottom:-2px;width:11px;height:11px;border-radius:50%;
  background:var(--qw-text-4);border:2px solid var(--qw-bg-sidebar);transition:background-color .3s}
.hdot.ok{background:var(--qw-ok)}
.hdot.bad{background:var(--qw-danger)}
.acct-txt{flex:1;min-width:0;display:flex;flex-direction:column;line-height:1.3}
.acct-1{font-size:var(--qw-fs-base);font-weight:500;color:var(--qw-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.acct-2{font-size:var(--qw-fs-xs);color:var(--qw-text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.acct .updown{color:var(--qw-text-4)}
/* GPU ที่โมเดลหลักใช้ ต่อท้าย "เครื่องนี้" ("เครื่องนี้ · RTX 4090") — บรรทัดสถานะด้านล่างยาวอยู่แล้ว ต่อตรงนั้นจะถูกตัด …
   น้ำหนักปกติ สีรอง ให้ชื่อเครื่องยังเด่นกว่า  เตือน "GPU เปลี่ยน": warn ผสมสีตัวอักษร (warn ล้วนบนพื้นสว่างได้แค่ ~3:1) */
/* 13px: วัดแล้วที่แถบกว้าง 288px ข้อความยาวสุด "This computer · RTX 4060 Ti +1" = 185px จากที่มี 187px (14px ล้นเป็น 192px) */
.acct-gpu{font-weight:400;font-size:var(--qw-fs-sm);color:var(--qw-text-3)}
.acct-gpu.warn{color:color-mix(in srgb,var(--qw-warn) 70%,var(--qw-text))}
/* แถบไอคอนซ่อนข้อความทั้งหมด — เหลือจุดสีเหลืองอำพันมุมบนของไอคอนเครื่องแทน (มุมล่างเป็นจุดสถานะโมเดล) */
.gbadge{position:absolute;right:-2px;top:-2px;width:10px;height:10px;border-radius:50%;background:var(--qw-warn);
  border:2px solid var(--qw-bg-sidebar);display:none}

/* ---------- ส่วนหัวของหน้าแชต ---------- */
#hdr{display:flex;align-items:center;gap:4px;min-width:0;height:var(--qw-header-h);padding:0 12px 0 10px;background:var(--qw-bg)}
.crumb{flex:1;min-width:0;display:flex;align-items:center}
.title-btn{display:inline-flex;align-items:center;gap:6px;height:32px;max-width:100%;min-width:0;padding:0 8px 0 10px;
  border-radius:var(--qw-r-sm);color:var(--qw-text);font-size:var(--qw-fs-base);font-weight:500;
  transition:background-color var(--qw-dur) var(--qw-ease)}
.title-btn:hover,.title-btn[aria-expanded="true"]{background:var(--qw-bg-hover)}
.title-btn .tt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.title-btn .ic{color:var(--qw-text-3)}
.title-static{display:inline-flex;align-items:center;gap:8px;min-width:0;height:32px;padding:0 10px;border-radius:var(--qw-r-sm);
  color:var(--qw-text-3);font-size:var(--qw-fs-base)}
.title-static:hover{background:var(--qw-bg-hover);color:var(--qw-text)}
.title-static .tt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.hdr-btn{display:inline-flex;align-items:center;gap:7px;height:32px;padding:0 12px;border-radius:var(--qw-r-sm);flex:none;
  color:var(--qw-text-2);font-size:var(--qw-fs-sm);box-shadow:inset 0 0 0 .5px var(--qw-border-strong);
  transition:background-color var(--qw-dur) var(--qw-ease),color var(--qw-dur) var(--qw-ease)}
.hdr-btn:hover,.hdr-btn[aria-expanded="true"]{background:var(--qw-bg-hover);color:var(--qw-text)}
.mobile-only{display:none!important}
/* ---------- สวิตช์ภาษา ไทย | EN ----------
   เดิมเปลี่ยนภาษาได้แค่ในเมนูท้ายแถบข้าง (ต้องกดสองชั้นกว่าจะเห็น) — ย้ายมาไว้ที่หัวแบบเงียบๆ
   ปุ่มที่เลือกอยู่ใช้พื้น bg-active แบบเดียวกับ .seg ในเมนู ไม่ใช้สีเน้น เพราะส้มสงวนไว้ให้ปุ่มส่ง/แชตใหม่
   ป้ายไทยใหญ่กว่า 1px: อักษรไทยขนาดเท่ากันดูเล็กกว่า "EN" ตัวพิมพ์ใหญ่ชัดเจน */
.lsw{display:inline-flex;align-items:center;gap:2px;height:28px;padding:2px;margin-right:6px;flex:none;border-radius:var(--qw-r-full,999px);
  box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.lsw button{display:inline-flex;align-items:center;justify-content:center;height:24px;min-width:34px;padding:0 9px;
  border-radius:var(--qw-r-full,999px);color:var(--qw-text-3);font-size:var(--qw-fs-xs);font-weight:500;line-height:1;white-space:nowrap;
  transition:background-color var(--qw-dur) var(--qw-ease),color var(--qw-dur) var(--qw-ease)}
.lsw button[lang="th"]{font-size:var(--qw-fs-sm)}
/* hover จางกว่าตัวที่เลือกอยู่ครึ่งหนึ่ง — bg-hover เต็มๆ เกือบเท่า bg-active (ธีมสว่างต่างกันแค่ 1.1:1)
   ชี้ที่ปุ่มอีกภาษาแล้วดูเหมือนเลือกไว้ทั้งสองปุ่ม */
.lsw button:hover{background:color-mix(in srgb,var(--qw-bg-hover) 55%,transparent);color:var(--qw-text)}
.lsw button[aria-pressed="true"]{background:var(--qw-bg-active);color:var(--qw-text);cursor:default;
  box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px var(--qw-border)}
/* ระหว่างรอ hub บันทึก (ก่อนโหลดหน้าใหม่) — กดซ้ำไม่มีผลอยู่แล้ว (langBusy) แค่บอกด้วยเคอร์เซอร์ว่ากำลังทำงาน */
.lsw[aria-busy="true"] button{cursor:progress}

/* ---------- ม่านตาม dialog ของ WebUI ----------
   dialog ใน iframe มืดได้แค่ในกรอบ iframe แถบข้างกับส่วนหัวจึงต้องมืดตามเอง ไม่งั้นเห็นรอยต่อ */
#hdr{position:relative}
#sb::after,#hdr::after{content:"";position:absolute;inset:0;z-index:40;background:var(--qw-scrim);opacity:0;
  pointer-events:none;transition:opacity var(--qw-dur) var(--qw-ease)}
body.frame-modal #sb::after,body.frame-modal #hdr::after{opacity:1;pointer-events:auto;cursor:default}

/* ---------- ม่าน + แผงโปรเจกต์ ---------- */
#scrim{position:fixed;inset:0;z-index:50;background:var(--qw-scrim);opacity:0;pointer-events:none;
  transition:opacity calc(var(--qw-dur) * 1.4) var(--qw-ease)}
#scrim.on{opacity:1;pointer-events:auto}
#pp{position:fixed;top:0;right:0;bottom:0;z-index:60;width:min(400px,100vw);display:flex;flex-direction:column;
  background:var(--qw-bg-elev);border-left:.5px solid var(--qw-border);border-radius:var(--qw-r-lg) 0 0 var(--qw-r-lg);
  box-shadow:var(--qw-shadow-lg);transform:translateX(104%);visibility:hidden;
  transition:transform calc(var(--qw-dur) * 1.4) var(--qw-ease),visibility 0s linear calc(var(--qw-dur) * 1.4)}
#pp.open{transform:none;visibility:visible;transition:transform calc(var(--qw-dur) * 1.4) var(--qw-ease),visibility 0s}
.pp-head{display:flex;align-items:flex-start;gap:4px;padding:18px 12px 16px 24px;border-bottom:.5px solid var(--qw-border)}
.pp-head-t{flex:1;min-width:0}
.pp-kicker{display:flex;align-items:center;gap:6px;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
#ppTitle{margin:4px 0 0;font-family:var(--qw-font-serif);font-weight:500;font-size:22px;line-height:1.3;color:var(--qw-text);
  overflow-wrap:anywhere}
.pp-body{flex:1;min-height:0;overflow-y:auto;padding:0 24px 28px;scrollbar-width:thin;scrollbar-color:var(--qw-border-strong) transparent}
.pp-sec{padding:20px 0;border-bottom:.5px solid var(--qw-border)}
.pp-sec:last-child{border-bottom:0}
.pp-sec-h{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:30px;margin-bottom:2px}
.pp-sec h3{margin:0;font-size:var(--qw-fs-base);font-weight:600;color:var(--qw-text)}
.pp-hint{margin:0 0 12px;font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-3)}
.input{width:100%;padding:9px 12px;border:0;border-radius:var(--qw-r-md);background:var(--qw-bg);color:var(--qw-text);
  font-size:var(--qw-fs-base);line-height:1.6;box-shadow:inset 0 0 0 .5px var(--qw-border-strong);
  transition:box-shadow var(--qw-dur) var(--qw-ease)}
.input::placeholder{color:var(--qw-text-4)}
.input:focus{box-shadow:inset 0 0 0 1px var(--qw-border-focus),0 0 0 3px var(--qw-accent-soft);outline:none}
textarea.input{display:block;resize:vertical;min-height:132px;max-height:50vh}
.pp-actions{display:flex;align-items:center;justify-content:flex-end;gap:10px;margin-top:10px}
.pp-state{flex:1;font-size:var(--qw-fs-xs);color:var(--qw-text-4)}
.pp-state.dirty{color:var(--qw-warn)}
.files{display:flex;flex-direction:column;gap:1px;margin:0 -8px}
.file{display:flex;align-items:center;gap:8px;height:34px;padding:0 3px 0 8px;border-radius:var(--qw-r-sm)}
.file:hover,.file:focus-within{background:var(--qw-bg-hover)}
.file .ib{width:20px}
.file-name{flex:1;min-width:0;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
  color:var(--qw-text-2);font-size:var(--qw-fs-sm)}
.file-name:hover{color:var(--qw-text);text-decoration:underline;text-underline-offset:2px;text-decoration-color:var(--qw-border-strong)}
.file-sz{flex:none;font-size:var(--qw-fs-xs);color:var(--qw-text-4);font-variant-numeric:tabular-nums}
.file .icon-btn{opacity:0}
.file:hover .icon-btn,.file:focus-within .icon-btn{opacity:1}
.file .icon-btn:hover{color:var(--qw-danger)}
.drop{display:flex;flex-direction:column;align-items:center;gap:6px;width:100%;margin-top:6px;padding:18px 14px;
  border-radius:var(--qw-r-md);border:1px dashed var(--qw-border-strong);color:var(--qw-text-3);font-size:var(--qw-fs-xs);
  text-align:center;transition:background-color var(--qw-dur),border-color var(--qw-dur),color var(--qw-dur)}
.drop:hover{background:var(--qw-bg-hover);color:var(--qw-text-2)}
#ppKnow.drag .drop,#ppKnow.drag .files{background:var(--qw-accent-soft);border-color:var(--qw-accent);color:var(--qw-text)}
#ppKnow.drag .files{border-radius:var(--qw-r-sm)}
.pp-path{display:flex;align-items:center;gap:6px;max-width:100%;margin-top:10px;padding:2px 0;color:var(--qw-text-4);
  font-family:var(--qw-font-mono);font-size:11px;text-align:left}
.pp-path span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;direction:rtl;unicode-bidi:plaintext}
.pp-path:hover{color:var(--qw-text-2)}
.field{margin-top:16px}
.field:first-of-type{margin-top:6px}
.field-l{display:block;margin-bottom:7px;font-size:var(--qw-fs-sm);font-weight:500;color:var(--qw-text-2)}
.field-h{display:block;margin-top:6px;font-size:var(--qw-fs-xs);line-height:1.55;color:var(--qw-text-3)}
.field-row{display:flex;align-items:flex-start;gap:14px}
.field-row>div{flex:1;min-width:0}
.field-row .field-l{margin-bottom:0}
.sel{position:relative}
.sel select{appearance:none;-webkit-appearance:none;width:100%;height:36px;padding:0 34px 0 12px;border:0;
  border-radius:var(--qw-r-md);background:var(--qw-bg);color:var(--qw-text);font-size:var(--qw-fs-sm);cursor:pointer;
  box-shadow:inset 0 0 0 .5px var(--qw-border-strong);text-overflow:ellipsis}
.sel select:focus-visible{outline:none;box-shadow:inset 0 0 0 1px var(--qw-border-focus),0 0 0 3px var(--qw-accent-soft)}
.sel .ic{position:absolute;right:11px;top:50%;transform:translateY(-50%);color:var(--qw-text-3)}
.seg{display:inline-flex;gap:2px;padding:2px;border-radius:var(--qw-r-sm);background:var(--qw-bg-sidebar);
  box-shadow:inset 0 0 0 .5px var(--qw-border)}
.seg button{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:28px;padding:0 11px;
  border-radius:6px;color:var(--qw-text-3);font-size:var(--qw-fs-sm);white-space:nowrap;
  transition:background-color var(--qw-dur),color var(--qw-dur)}
.seg button:hover{color:var(--qw-text)}
.seg button.on{background:var(--qw-bg-active);color:var(--qw-text);box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px var(--qw-border)}
.seg.full{display:flex}
.seg.full button{flex:1}
/* ราง "ปิด" ใช้ text-4 — ต้องต่างจากแผงและจากปุ่มกลมสีขาวอย่างน้อย 3:1 ทั้งสองธีม (เส้นขอบจางได้แค่ 1.4:1) */
.switch{position:relative;width:36px;height:20px;flex:none;margin-top:1px;border-radius:999px;background:var(--qw-text-4);
  transition:background-color var(--qw-dur) var(--qw-ease)}
.switch::after{content:"";position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:#fff;
  box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform var(--qw-dur) var(--qw-ease)}
.switch[aria-checked="true"]{background:var(--qw-accent)}
.switch[aria-checked="true"]::after{transform:translateX(16px)}
.pp-links{display:flex;flex-wrap:wrap;gap:8px}

/* ---------- เมนู ---------- */
.menu{position:fixed;z-index:80;min-width:220px;max-width:min(330px,calc(100vw - 16px));padding:5px;
  background:var(--qw-bg-elev);border-radius:var(--qw-r-md);box-shadow:var(--qw-shadow-lg),inset 0 0 0 .5px var(--qw-border-strong);
  opacity:0;transform:translateY(-3px) scale(.98);transition:opacity var(--qw-dur) var(--qw-ease),transform var(--qw-dur) var(--qw-ease)}
.menu.up{transform:translateY(3px) scale(.98)}
/* เมนูบัญชีที่มีรายการ GPU: ชื่อโมเดล + การ์ดหลายใบ ("RTX 4060 Ti + 1000 Ada + CPU") ต้องการที่มากกว่า 330px */
.menu.wide{max-width:min(360px,calc(100vw - 16px))}
.menu.on{opacity:1;transform:none}
.menu-item{display:flex;align-items:center;gap:10px;width:100%;height:34px;padding:0 10px;border-radius:var(--qw-r-sm);
  color:var(--qw-text-2);font-size:var(--qw-fs-base);text-align:left;white-space:nowrap}
.menu-item:hover,.menu-item:focus-visible{background:var(--qw-bg-hover);color:var(--qw-text);outline:none}
.menu-item:focus-visible{box-shadow:inset 0 0 0 2px var(--qw-focus-ring)}
.menu-item .ic{color:var(--qw-text-3)}
.menu-item:hover .ic{color:var(--qw-text-2)}
.menu-item .mi-l{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis}
.menu-item .mi-x{color:var(--qw-text-4)}
.menu-item.danger,.menu-item.danger .ic{color:var(--qw-danger)}
.menu-item.danger:hover{background:var(--qw-accent-soft)}
.menu-sep{height:.5px;margin:5px 6px;background:var(--qw-border-strong)}
.menu-head{display:flex;align-items:center;gap:8px;padding:8px 10px 6px;font-size:var(--qw-fs-xs);color:var(--qw-text-3);min-width:0}
.menu-head .mh-t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.menu-head .hdot{position:static;border:0;width:8px;height:8px;flex:none}
/* หัวเมนูบัญชี: โมเดลไหนใช้ GPU ไหน — จัดแนวกับข้อความสถานะ (เว้นที่ให้จุดสี 8px + ช่องไฟ 8px)
   ทั้งก้อนเป็นปุ่ม (menuitem) กดแล้วเปิดหน้าต่างเลือก GPU — ข้างในเป็น span ทั้งหมด (ปุ่มใส่ div ไม่ได้) */
.mh-gpu{display:block;width:100%;margin:0 0 2px;padding:5px 10px 7px 26px;border-radius:var(--qw-r-sm);text-align:left;
  font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-3);min-width:0;transition:background-color var(--qw-dur) var(--qw-ease)}
.mh-gpu:hover,.mh-gpu:focus-visible{background:var(--qw-bg-hover);outline:none}
.mh-gpu:focus-visible{box-shadow:inset 0 0 0 2px var(--qw-focus-ring)}
.mh-sub{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:1px;color:var(--qw-text-4)}
.mh-go{display:inline-flex;align-items:center;gap:1px;flex:none;color:var(--qw-text-3)}
.mh-gpu:hover .mh-go,.mh-gpu:focus-visible .mh-go{color:var(--qw-text)}
.mh-pl{display:flex;align-items:baseline;gap:12px;min-width:0}
.mh-pl span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mh-m{flex:0 1 auto;color:var(--qw-text-2)}
.mh-pl.pri .mh-m{color:var(--qw-text);font-weight:500}
.mh-d{flex:0 1 auto;margin-left:auto;font-variant-numeric:tabular-nums}
.mh-devs{display:block;margin-top:3px;color:var(--qw-text-4);overflow-wrap:anywhere}
.mh-dv{white-space:nowrap}
/* เตือน GPU เปลี่ยน: กล่องพื้นเหลืองอำพันจางๆ ตัวอักษรสีปกติ — เห็นชัดแต่ไม่ตะโกนแบบข้อผิดพลาดสีแดง */
.mh-warn{display:flex;align-items:flex-start;gap:8px;margin:1px 6px 7px;padding:7px 10px;border-radius:var(--qw-r-sm);
  font-size:var(--qw-fs-xs);line-height:1.55;color:var(--qw-text-2);background:color-mix(in srgb,var(--qw-warn) 12%,transparent);
  box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 45%,transparent)}
.mh-warn .ic{color:var(--qw-warn);margin-top:2px}
.mh-warn-c{display:flex;flex-direction:column;align-items:flex-start;gap:7px;min-width:0}
/* ปุ่มเล็กแบบหมึก (สีเดียวกับปุ่มหลักของหน้า) — ไม่ใช้ส้ม ส้มสงวนไว้ให้ปุ่มส่ง/แชตใหม่ */
.mh-warn-b{height:26px;padding:0 10px;border-radius:var(--qw-r-xs);font-size:var(--qw-fs-xs);font-weight:500;background:var(--qw-text);color:var(--qw-bg);
  transition:opacity var(--qw-dur)}
.mh-warn-b:hover{opacity:.86}
.mh-warn-b:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:2px}
.menu-row{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:5px 5px 5px 10px}
.menu-row .mr-l{display:flex;align-items:center;gap:10px;font-size:var(--qw-fs-base);color:var(--qw-text-2);white-space:nowrap}
.menu-row .mr-l .ic{color:var(--qw-text-3)}
.menu-row .seg button{height:26px;padding:0 9px;font-size:var(--qw-fs-xs)}
.menu-row .seg button:focus-visible{outline-offset:-1px}

/* ---------- กล่องยืนยัน ---------- */
.dlg-wrap{position:fixed;inset:0;z-index:90;display:flex;align-items:center;justify-content:center;padding:16px;
  background:var(--qw-scrim);opacity:0;transition:opacity var(--qw-dur) var(--qw-ease)}
.dlg-wrap.on{opacity:1}
.dlg{width:min(430px,100%);padding:22px 22px 18px;border-radius:var(--qw-r-lg);background:var(--qw-bg-elev);
  box-shadow:var(--qw-shadow-lg),inset 0 0 0 .5px var(--qw-border-strong);transform:translateY(6px) scale(.98);
  transition:transform var(--qw-dur) var(--qw-ease)}
.dlg-wrap.on .dlg{transform:none}
.dlg h2{margin:0 0 8px;font-family:var(--qw-font-serif);font-weight:500;font-size:20px;line-height:1.35;color:var(--qw-text)}
.dlg p{margin:0 0 18px;font-size:var(--qw-fs-base);line-height:1.65;color:var(--qw-text-2);white-space:pre-line;overflow-wrap:break-word}
.dlg .input{margin:6px 0 18px}
.dlg-actions{display:flex;justify-content:flex-end;gap:8px}

/* ---------- หน้าต่างเลือก GPU ----------
   กล่องกลางจอแบบเดียวกับกล่องยืนยัน แต่กว้างกว่าและเนื้อหาเลื่อนได้ในตัว (หัวกับแถวปุ่มอยู่กับที่ ปุ่มบันทึกไม่หลุดจอ)
   จอแคบ (<640px) เป็นแผ่นเลื่อนขึ้นจากขอบล่าง (sheet) ปุ่มสูงพอกดด้วยนิ้ว — ดู @media ท้ายส่วนนี้
   สีสถานะใช้แค่จุดเล็กๆ กับกล่องจางๆ (warn/danger ผสมพื้น) ตัวอักษรคงสีปกติ อ่านง่ายทั้งสองธีม */
.gd-wrap{position:fixed;inset:0;z-index:90;display:flex;align-items:center;justify-content:center;padding:24px 16px;
  background:var(--qw-scrim);opacity:0;transition:opacity var(--qw-dur) var(--qw-ease)}
.gd-wrap.on{opacity:1}
.gd{display:flex;flex-direction:column;width:min(600px,100%);max-height:min(800px,calc(100vh - 48px));max-height:min(800px,calc(100dvh - 48px));
  border-radius:var(--qw-r-lg);background:var(--qw-bg-elev);box-shadow:var(--qw-shadow-lg),inset 0 0 0 .5px var(--qw-border-strong);
  transform:translateY(6px) scale(.98);transition:transform var(--qw-dur) var(--qw-ease);outline:none}
.gd-wrap.on .gd{transform:none}
.gd-grab{display:none}
.gd-head{display:flex;align-items:flex-start;gap:8px;padding:20px 14px 12px 24px;flex:none}
.gd-head-t{flex:1;min-width:0}
.gd-head h2{margin:0;font-family:var(--qw-font-serif);font-weight:500;font-size:20px;line-height:1.35;color:var(--qw-text)}
.gd-sub{margin:5px 0 0;font-size:var(--qw-fs-sm);line-height:1.6;color:var(--qw-text-3)}
.gd-body{flex:1;min-height:0;overflow-y:auto;padding:0 24px 6px;scrollbar-width:thin;scrollbar-color:var(--qw-border-strong) transparent}
.gd-sec{padding:12px 0 16px}
.gd-sec+.gd-sec{border-top:.5px solid var(--qw-border)}
.gd-sec-h{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:30px;margin-bottom:8px}
.gd-sec-h h3{margin:0;font-size:var(--qw-fs-sm);font-weight:600;color:var(--qw-text-2)}
.gd-sec-h .btn .ic{color:var(--qw-text-3)}
.gd-devs{display:grid;grid-template-columns:repeat(auto-fill,minmax(168px,1fr));gap:8px}
.gd-dev{display:flex;align-items:center;gap:10px;min-width:0;padding:9px 12px 9px 9px;border-radius:var(--qw-r-md);
  background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.gd-dev-ic{width:30px;height:30px;flex:none;display:inline-flex;align-items:center;justify-content:center;border-radius:var(--qw-r-sm);
  background:var(--qw-bg-sidebar);color:var(--qw-text-3)}
.gd-dev-t{display:flex;flex-direction:column;min-width:0;line-height:1.4}
.gd-dev-n{font-size:var(--qw-fs-sm);font-weight:500;color:var(--qw-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gd-dev-m{font-size:var(--qw-fs-xs);color:var(--qw-text-3);white-space:nowrap;font-variant-numeric:tabular-nums}
/* กล่องข้อความในหน้าต่าง: info = พื้นผืนหลัก, warn = เหลืองอำพันจาง (แบบเดียวกับเตือน GPU เปลี่ยนในเมนู), bad = แดงจาง */
.gd-msg{display:flex;align-items:flex-start;gap:9px;padding:9px 12px;border-radius:var(--qw-r-md);font-size:var(--qw-fs-sm);line-height:1.6;
  color:var(--qw-text-2);background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.gd-msg .ic{flex:none;margin-top:3px;color:var(--qw-text-3)}
.gd-msg.warn,.gm-note.warn{background:color-mix(in srgb,var(--qw-warn) 11%,transparent);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 42%,transparent)}
.gd-msg.warn .ic,.gm-note.warn .ic{color:var(--qw-warn)}
.gd-msg.bad{background:color-mix(in srgb,var(--qw-danger-bg) 11%,transparent);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-danger-bg) 45%,transparent)}
.gd-msg.bad .ic{color:var(--qw-danger)}
.gd-msg-c{flex:1;min-width:0}
.gd-stale{margin:2px 0 4px}
.gm{padding:14px 0}
.gm:first-child{padding-top:0}
.gm+.gm{border-top:.5px solid var(--qw-border)}
.gm-h{display:flex;align-items:baseline;gap:8px;min-width:0;margin-bottom:8px}
.gm-name{flex:0 1 auto;min-width:0;font-size:var(--qw-fs-base);font-weight:500;color:var(--qw-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gm-badge{flex:none;align-self:center;height:18px;padding:0 7px;border-radius:var(--qw-r-full);font-size:11px;line-height:18px;font-weight:500;
  color:var(--qw-text-2);background:var(--qw-bg-active)}
.gm-eff{flex:0 1 auto;min-width:0;margin-left:auto;font-size:var(--qw-fs-xs);color:var(--qw-text-3);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;font-variant-numeric:tabular-nums}
.gm .sel select{height:38px;font-size:var(--qw-fs-base)}
.gm .sel select:disabled{cursor:default;opacity:.6}
.gm-fit{display:flex;align-items:baseline;gap:8px;margin-top:8px;font-size:var(--qw-fs-xs);line-height:1.55;color:var(--qw-text-3)}
.gm-fit:empty{display:none}
.gm-fit i{flex:none;width:7px;height:7px;border-radius:50%;background:var(--qw-text-4);transform:translateY(-1px)}
.gm-fit.ok i{background:var(--qw-ok)}
.gm-fit.spill i{background:var(--qw-warn)}
/* CPU = วงกลมกลวง: ไม่ใช่ข้อผิดพลาด แค่ช้าที่สุด — ไม่ใช้แดง */
.gm-fit.cpu i{background:transparent;box-shadow:inset 0 0 0 1.5px var(--qw-text-3)}
.gm-notes:empty{display:none}
.gm-note{display:flex;align-items:flex-start;gap:8px;margin-top:8px;padding:7px 10px;border-radius:var(--qw-r-sm);font-size:var(--qw-fs-xs);
  line-height:1.55;color:var(--qw-text-2)}
.gm-note .ic{flex:none;margin-top:2px}
.gm-note.info{background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.gm-note.info .ic{color:var(--qw-text-3)}
.gd-conf:empty{display:none}
.gd-conf{display:flex;flex-direction:column;gap:6px;margin-top:2px}
.gd-loading{display:flex;align-items:center;gap:10px;padding:26px 0 30px;font-size:var(--qw-fs-sm);color:var(--qw-text-3)}
.gd-foot{flex:none;padding:14px 24px 18px;border-top:.5px solid var(--qw-border)}
.gd-confirm{margin:0 0 12px;font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-3)}
.gd-status:empty{display:none}
.gd-status{margin:0 0 12px;display:flex;flex-direction:column;gap:8px}
.gd-actions{display:flex;align-items:center;gap:8px}
.gd-reset{margin-right:auto;color:var(--qw-text-3)}
.gd-reset:hover:not(:disabled){background:var(--qw-bg-hover);color:var(--qw-text)}
.gd .btn-ghost:disabled,.gd-reset:disabled{opacity:.45;cursor:default}
.gd .btn-ghost:disabled:hover{background:none}
/* ระหว่างโมเดลกำลังตอบ: ปุ่มบันทึกยังโฟกัสได้ (aria-disabled) กดแล้วมี toast บอกเหตุผล แทนการหายไปเงียบๆ */
.gd-apply[aria-disabled="true"]{opacity:.5;cursor:not-allowed}
.gd-spin{width:16px;height:16px;flex:none;margin-top:2px;border-radius:50%;border:2px solid var(--qw-border-strong);border-top-color:var(--qw-accent);
  animation:gdspin .9s linear infinite}
@keyframes gdspin{to{transform:rotate(360deg)}}
.gd-prog-t{display:flex;flex-direction:column;gap:2px;min-width:0;color:var(--qw-text)}
.gd-prog-l{font-family:var(--qw-font-mono);font-size:11.5px;color:var(--qw-text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gd-prog-e{font-size:var(--qw-fs-xs);color:var(--qw-text-3);font-variant-numeric:tabular-nums}
.gd-log{margin-top:8px}
.gd-log summary{width:max-content;max-width:100%;padding:1px 2px;border-radius:var(--qw-r-xs);font-size:var(--qw-fs-xs);color:var(--qw-text-3);cursor:pointer}
.gd-log summary:hover{color:var(--qw-text)}
.gd-log pre{margin:6px 0 0;max-height:min(150px,22vh);overflow:auto;padding:10px 12px;border-radius:var(--qw-r-sm);background:var(--qw-bg-code);
  font-family:var(--qw-font-mono);font-size:11.5px;line-height:1.55;color:var(--qw-text-2);white-space:pre-wrap;overflow-wrap:anywhere}
@media (max-width:639.98px){
  .gd-wrap{align-items:flex-end;padding:0}
  .gd{width:100%;max-height:calc(100vh - 12px);max-height:calc(100dvh - 12px);border-radius:var(--qw-r-xl) var(--qw-r-xl) 0 0;transform:translateY(24px)}
  .gd-grab{display:block;flex:none;width:36px;height:4px;margin:8px auto 0;border-radius:var(--qw-r-full);background:var(--qw-border-strong)}
  .gd-head{padding:10px 8px 10px 18px}
  .gd-body{padding:0 18px 6px}
  .gd-foot{padding:12px 18px calc(14px + env(safe-area-inset-bottom,0px))}
  /* ปุ่มหลักเต็มแถวบนสุด (นิ้วโป้งเอื้อมถึง) ยกเลิก/คืนค่าแบ่งแถวล่าง */
  .gd-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
  .gd-actions .btn{height:42px;white-space:normal;line-height:1.3}
  .gd-apply{grid-column:1/-1;order:-1}
  .gd-reset{margin-right:0;box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
  .gm-h{flex-wrap:wrap;row-gap:2px}
  .gm-eff{flex-basis:100%;margin-left:0;white-space:normal}
  /* การ์ดสองคอลัมน์ (ชื่อ + VRAM สั้นพอ) — คอลัมน์เดียวกินที่ครึ่งจอก่อนถึงรายการโมเดล */
  .gd-devs{grid-template-columns:repeat(auto-fill,minmax(150px,1fr))}
  .gd-dev{padding:8px 10px 8px 8px;gap:8px}
}
@media (prefers-reduced-motion:reduce){.gd-spin{animation-duration:2.4s}}

/* ---------- toast ---------- */
/* ข้อความยาว (path เต็ม, ชื่อไฟล์ + ข้อผิดพลาด) ต้องอ่านได้ครบ — ตัดบรรทัดได้สูงสุด 3 บรรทัด */
#toast{position:fixed;left:50%;bottom:24px;z-index:100;width:max-content;max-width:min(560px,calc(100vw - 32px));padding:8px 16px;
  border-radius:var(--qw-r-md);background:var(--qw-text);color:var(--qw-bg);font-size:var(--qw-fs-sm);font-weight:500;line-height:1.5;
  box-shadow:var(--qw-shadow-md);text-align:center;overflow-wrap:anywhere;pointer-events:none;
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;
  opacity:0;transform:translate(-50%,8px);transition:opacity var(--qw-dur) var(--qw-ease),transform var(--qw-dur) var(--qw-ease)}
#toast.on{opacity:1;transform:translate(-50%,0)}
/* พื้นแดงทึบ + ตัวอักษรขาว = danger-bg เสมอ (ห้ามใช้ --qw-danger ซึ่งเป็นสีตัวอักษร) */
#toast.bad{background:var(--qw-danger-bg);color:#fff}

/* ---------- ป้ายชื่อปุ่มไอคอน (แทน title ของเบราว์เซอร์ ให้หน้าตาเข้าชุดกับใน iframe) ---------- */
#tip{position:fixed;z-index:110;max-width:260px;padding:5px 9px;border-radius:var(--qw-r-xs);pointer-events:none;
  background:var(--qw-text);color:var(--qw-bg);font-size:var(--qw-fs-xs);font-weight:500;line-height:1.4;
  box-shadow:var(--qw-shadow-md);opacity:0;transition:opacity var(--qw-dur) var(--qw-ease)}
#tip.on{opacity:1}

/* ---------- พับเป็นแถบไอคอน 56px (จอกว้างเท่านั้น) ----------
   จุดตัดลิ้นชักอยู่ที่ 830px (ไม่ใช่ 820) เพื่อให้โหมดแถบไอคอนเหลือ iframe กว้าง ≥ 768px เสมอ
   ต่ำกว่านั้น WebUI สลับเป็นหน้าตามือถือ (ช่องพิมพ์ติดขอบล่าง ชิปชิดซ้าย) */
@media (min-width:830px){
  body.sb-min #app,body.sb-peek #app{--sb:var(--qw-sidebar-w-min,56px)}
  /* peek = กางชั่วคราวแบบลอยทับ (Ctrl+K / ปุ่มล่าสุดในแถบไอคอน) — iframe ไม่หดตาม จึงไม่สลับเป็นหน้ามือถือ */
  body.sb-peek #sb{width:var(--qw-sidebar-w,288px);box-shadow:var(--qw-shadow-lg);border-right-color:transparent}
  body.sb-min .sb-head{padding:0;justify-content:center}
  body.sb-min .brand,body.sb-min .search,body.sb-min .kbd{display:none}
  body.sb-min .sb-nav{align-items:center;padding:2px 0 4px}
  body.sb-min .sb-nav .item{width:40px;height:40px;padding:0;justify-content:center}
  body.sb-min .item .lbl{display:none}
  body.sb-min .rail-only{display:flex!important}
  body.sb-min #searchBtn{display:flex!important}
  body.sb-min .sb-scroll{visibility:hidden}
  body.sb-min .sb-foot{padding:8px 0;display:flex;justify-content:center}
  body.sb-min .acct{width:40px;padding:4px;justify-content:center;border-radius:50%}
  body.sb-min .acct-txt,body.sb-min .acct .updown{display:none}
  body.sb-min .gbadge.on{display:block}
}

/* ---------- จอแคบ: แถบข้างเป็นลิ้นชัก ---------- */
@media (max-width:829.98px){
  #app{grid-template-columns:minmax(0,1fr)}
  #sb{position:fixed;top:0;bottom:0;left:0;z-index:60;width:min(var(--qw-sidebar-w),86vw);border-right:0;
    transform:translateX(-100%);visibility:hidden;
    transition:transform calc(var(--qw-dur) * 1.4) var(--qw-ease),visibility 0s linear calc(var(--qw-dur) * 1.4)}
  body.sb-open #sb{transform:none;visibility:visible;box-shadow:var(--qw-shadow-lg);
    transition:transform calc(var(--qw-dur) * 1.4) var(--qw-ease),visibility 0s}
  .mobile-only{display:inline-flex!important}
  .hdr-btn{width:32px;padding:0;justify-content:center;box-shadow:none;color:var(--qw-text-3)}
  .hdr-btn .lbl{display:none}
  #hdr{padding:0 6px}
  /* ส่วนหัวทึบอยู่แล้ว แต่เนื้อหาใน iframe ที่เลื่อนขึ้นไปถูกตัดตรงขอบล่างเป็นเส้นตรง — ไอคอนแถวปุ่มของข้อความ
     โผล่มาครึ่งตัวเหมือนลอดใต้หัว ไล่สีพื้นลงมา 16px ให้จางหายแทน (เฉพาะจอแคบ: จอกว้างจะทับหัว scrollbar ของ iframe) */
  #stage::before{content:"";position:absolute;left:0;right:0;top:0;z-index:1;height:16px;pointer-events:none;
    background:linear-gradient(var(--qw-bg) 25%,transparent);transition:opacity var(--qw-dur) var(--qw-ease)}
  /* dialog ของ WebUI มืดได้แค่ใน iframe — แถบสีพื้นจะกลายเป็นขอบสว่างทับม่าน จึงซ่อนไปพร้อมกัน */
  body.frame-modal #stage::before{opacity:0}
  .kbd{display:none}
  #pp{width:100vw;border-radius:0;border-left:0}
  /* ช่องพิมพ์ของ WebUI อยู่ชิดล่างบนจอแคบ — ย้าย toast ไปใต้ส่วนหัวไม่ให้บังช่องพิมพ์ */
  #toast{top:calc(var(--qw-header-h,52px) + env(safe-area-inset-top,0px) + 6px);bottom:auto;transform:translate(-50%,-8px)}
  #toast.on{transform:translate(-50%,0)}
}
/* จอมือถือ: ชื่อแชตต้องการที่มากกว่า — เหลือปุ่มเดียวที่เขียนชื่อ "อีกภาษา" (EN / ไทย) กดแล้วสลับทันที
   ปุ่มของภาษาปัจจุบันยังอยู่ใน DOM (ซ่อนไว้) กลุ่มจึงยังบอกสถานะ aria-pressed ครบเหมือนจอกว้าง */
@media (max-width:639.98px){
  .lsw{height:32px;padding:0;margin-right:2px;box-shadow:none}
  .lsw button[aria-pressed="true"]{display:none}
  .lsw button{height:28px;min-width:32px;padding:0 9px;color:var(--qw-text-2);box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
}
/* จอสัมผัสไม่มี hover: แสดง ⋯ จางๆ ทุกแถว (เข้มเฉพาะแถวที่เปิดอยู่) แทนการโชว์เต็มทุกแถวจนรก */
@media (hover:none){
  .more{opacity:.5;color:var(--qw-text-4)}
  .item.on + .more,.more[aria-expanded="true"]{opacity:1;color:var(--qw-text-3)}
  .row .item{padding-right:34px}
  .file .icon-btn{opacity:1}
}
/* โหมดความคมชัดสูงของ Windows ลบ box-shadow และพื้นหลังทิ้ง — ขอบกับสถานะที่วาดด้วยสองอย่างนั้นต้องมีตัวแทน */
@media (forced-colors:active){
  .switch{border:1px solid ButtonText;background:Canvas}
  .switch::after{background:ButtonText;top:1px;left:1px}
  .switch[aria-checked="true"]{background:Highlight}
  .switch[aria-checked="true"]::after{background:HighlightText}
  .seg button.on,.menu-row .seg button.on,.lsw button[aria-pressed="true"]{outline:2px solid Highlight;outline-offset:-2px}
  .input,.btn-ghost,.btn-ink,.search,.hdr-btn,.menu,.dlg,.sel select,.newproj input,#toast,#tip,.lsw{border:1px solid CanvasText}
  .item.on,.item.menu-open{outline:1px solid Highlight;outline-offset:-1px}
  .hdot.ok,.hdot.bad,.new-dot,.mark,.gbadge{forced-color-adjust:none}
  .mh-warn{border:1px solid CanvasText}
  .gd,.gd-dev,.gd-msg,.gm-note,.mh-warn-b,.gd-log pre{border:1px solid CanvasText}
  .mh-gpu:focus-visible{outline:2px solid Highlight}
  .gm-fit i,.gd-spin{forced-color-adjust:none}
}

/* =====================================================================================
   รอบ 4 (2026-09-30): ความจำ (K3) · ไฟล์ที่สร้าง (K2) · ปรับให้เป็นของคุณ (K4) · แผงแสดงผล (K7)
   ===================================================================================== */
/* ---------- ความจำของโปรเจกต์ (แผงโปรเจกต์) ----------
   การ์ดแบบเดียวกับไฟล์: พื้นผืนหลักในแผงสีการ์ด ขอบจาง — ปุ่มของแต่ละรายการโผล่ตอนชี้/โฟกัส (จอสัมผัสเห็นตลอด) */
.mem-list{display:flex;flex-direction:column;gap:6px}
.mem{position:relative;padding:8px 8px 10px 12px;border-radius:var(--qw-r-md);background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.mem.pinned{box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.mem-top{display:flex;align-items:center;gap:6px;min-height:24px;min-width:0}
.mem-kind{flex:none;height:19px;padding:0 7px;border-radius:var(--qw-r-full);font-size:11px;font-weight:500;line-height:19px;
  color:var(--qw-text-2);background:var(--qw-bg-active)}
.mem-pin{flex:none;display:inline-flex;color:var(--qw-text-2)}
.mem-date{flex:none;font-size:var(--qw-fs-xs);color:var(--qw-text-4);font-variant-numeric:tabular-nums;white-space:nowrap}
.mem-off{min-width:0;font-size:var(--qw-fs-xs);color:var(--qw-text-4);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mem-off::before{content:"·";margin-right:6px}
.mem-acts{margin-left:auto;display:flex;align-items:center;gap:1px;flex:none;opacity:0;transition:opacity var(--qw-dur) var(--qw-ease)}
.mem:hover .mem-acts,.mem:focus-within .mem-acts{opacity:1}
.mem-acts .icon-btn[aria-pressed="true"]{color:var(--qw-text);background:var(--qw-bg-active)}
.mem-acts .icon-btn.del:hover{color:var(--qw-danger)}
.mem-text{margin-top:4px;padding-right:4px;font-size:var(--qw-fs-sm);line-height:1.6;color:var(--qw-text);white-space:pre-wrap;overflow-wrap:anywhere;
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;overflow:hidden}
.mem-text.open{display:block;-webkit-line-clamp:unset}
.mem.out .mem-text{color:var(--qw-text-3)}
.mem-link{display:inline-flex;align-items:center;height:26px;margin-top:2px;padding:0 6px;margin-left:-6px;border-radius:var(--qw-r-xs);
  font-size:var(--qw-fs-xs);font-weight:500;color:var(--qw-text-3)}
.mem-link:hover{color:var(--qw-text);background:var(--qw-bg-hover)}
.mem-foot{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:6px;min-height:0}
@media (hover:none){.mem-acts{opacity:1}}
.mem-sum{font-size:var(--qw-fs-xs);color:var(--qw-text-4);font-variant-numeric:tabular-nums}
.mem-note,.mem-empty{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;padding:10px 12px;border-radius:var(--qw-r-md);
  font-size:var(--qw-fs-xs);line-height:1.55;color:var(--qw-text-3)}
.mem-empty{justify-content:center;text-align:center;border:1px dashed var(--qw-border-strong)}
.mem-note{background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.mem-note.warn{color:var(--qw-text-2);background:color-mix(in srgb,var(--qw-warn) 11%,transparent);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 42%,transparent)}
.mem-note .mem-link{margin:0}
.mem-form{margin:0 0 10px;padding:10px;border-radius:var(--qw-r-md);background:var(--qw-bg);box-shadow:inset 0 0 0 1px var(--qw-border-focus)}
.mem-form textarea.input,.mem.editing textarea.input{min-height:78px;padding:6px 8px;background:transparent;box-shadow:none;border-radius:var(--qw-r-sm)}
.mem-form textarea.input:focus,.mem.editing textarea.input:focus{box-shadow:none}
.mem.editing{padding:10px;box-shadow:inset 0 0 0 1px var(--qw-border-focus)}
.mem-form-row{display:flex;align-items:center;gap:8px;margin-top:8px}
/* Esc ครั้งแรกตอนมีข้อความที่ยังไม่ได้บันทึก: เตือนก่อน ครั้งที่สองจึงทิ้ง (แบบเดียวกับหน้าต่างปรับให้เป็นของคุณ) */
.mem-esc{margin:8px 0 0;padding:6px 10px}
.mem-grow{flex:1}
.sel-sm{flex:0 1 170px;min-width:0}
.sel-sm select{height:30px;padding:0 30px 0 10px;font-size:var(--qw-fs-xs);background:var(--qw-bg-elev)}
.sel-sm .ic{right:9px}
/* ไฟล์ที่ Qwen สร้าง: แถวเดียวกับไฟล์ความรู้ แต่ชื่อเป็นลิงก์เปิดแท็บใหม่ และปุ่มท้ายคือ "เปิดในแผง" (ไม่ใช่ลบ — ไม่แดง) */
#ppOutList .file .icon-btn:hover{color:var(--qw-text)}
#ppOutList .file-name{display:block;line-height:34px}
#ppOutList .out-sp{width:24px;flex:none}

/* =====================================================================================
   batch 2a (B5, 2026-10-01): งานค้นคว้าเชิงลึก (แผงโปรเจกต์) · สถานะบริการ (เมนูบัญชี)
   ===================================================================================== */
/* การ์ดงานแบบเดียวกับความจำ (.mem) — งานที่ยังทำอยู่ขอบเข้มขึ้นเล็กน้อย ไม่ใช้ส้มทั้งการ์ด (ส้มสงวนให้ปุ่มส่ง/แชตใหม่)
   ส้มมีแค่จุดสถานะ "กำลังค้นคว้า" ที่กะพริบช้าๆ (หยุดเมื่อผู้ใช้ขอลดการเคลื่อนไหว) */
.res-list{display:flex;flex-direction:column;gap:6px}
.res-list:focus{outline:none}
.res{padding:8px 10px 10px 12px;border-radius:var(--qw-r-md);background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.res.active{box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.res-top{display:flex;align-items:center;gap:6px;min-height:24px;min-width:0}
.res-st{display:inline-flex;align-items:center;gap:6px;flex:none;font-size:var(--qw-fs-xs);font-weight:500;color:var(--qw-text-2)}
.res-dot{width:7px;height:7px;flex:none;border-radius:50%;background:var(--qw-text-4)}
.res-st.run .res-dot{background:var(--qw-accent);animation:qwResPulse 1.6s ease-in-out infinite}
.res-st.ok .res-dot{background:var(--qw-ok)}
.res-st.bad .res-dot{background:var(--qw-danger)}
.res-st.warn .res-dot{background:var(--qw-warn)}
@keyframes qwResPulse{50%{opacity:.3}}
.res-time{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:var(--qw-fs-xs);color:var(--qw-text-4);
  font-variant-numeric:tabular-nums}
.res-time::before{content:"·";margin-right:6px}
.res-top .mem-link{flex:none;margin:0 -4px 0 auto}
.res-top .mem-link:hover{color:var(--qw-danger)}
.res-q{margin-top:3px;font-size:var(--qw-fs-sm);line-height:1.6;color:var(--qw-text);overflow-wrap:anywhere;
  display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden}
.res-meta{margin-top:2px;font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-3);overflow-wrap:anywhere}
.res-mp{white-space:nowrap}
.res-note{font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.res-bar{position:relative;height:3px;margin-top:8px;border-radius:999px;background:var(--qw-bg-active);overflow:hidden}
.res-bar>i{position:absolute;top:0;bottom:0;left:0;border-radius:inherit;background:var(--qw-text-3);transition:width .5s var(--qw-ease)}
/* ไม่รู้ว่าไปถึงไหนแล้ว (งานไม่ได้ส่ง progress) — แถบวิ่งแทนตัวเลขที่เดาเอา */
.res-bar.ind>i{width:32%;animation:qwResInd 1.9s ease-in-out infinite}
@keyframes qwResInd{0%{left:-32%}100%{left:100%}}
.res-err{margin-top:6px;font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-danger);overflow-wrap:anywhere}
.res-err.soft{margin-top:2px;color:var(--qw-text-3)}
.res-files{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}
.res-files .btn{height:28px;padding:0 10px;font-size:var(--qw-fs-xs);max-width:100%}
.res-files .btn span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.res-files .btn .ic{color:var(--qw-text-3)}
@media (prefers-reduced-motion:reduce){
  .res-st.run .res-dot{animation:none}
  .res-bar.ind>i{animation:none;left:0;width:100%;opacity:.4}
}
/* เมนูบัญชี: บริการของเครื่องนี้ — ตาราง 2 คอลัมน์ (ชื่อ | จุดสี + สถานะ) จัดแนวกับข้อความสถานะของหัวเมนู (เว้นที่จุด 8px + ช่อง 8px)
   ไม่ใช่รายการที่กดได้ — อยู่ในคำอธิบายของเมนู (aria-describedby) โปรแกรมอ่านหน้าจออ่านตอนเปิดเมนู */
.mh-svc{padding:4px 10px 8px 26px;font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-3);min-width:0}
.mh-svc-h{display:block;margin-bottom:1px;color:var(--qw-text-4)}
.mh-svc-g{display:grid;grid-template-columns:minmax(0,max-content) minmax(0,1fr);column-gap:14px;row-gap:1px;align-items:baseline}
.mh-svc-l{color:var(--qw-text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mh-svc-v{display:flex;align-items:baseline;justify-content:flex-end;gap:6px;min-width:0;text-align:right}
.mh-svc-v span{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mh-svc-v i{width:6px;height:6px;flex:none;border-radius:50%;background:var(--qw-text-4);transform:translateY(-1px)}
.mh-svc-v.ok i{background:var(--qw-ok)}
.mh-svc-v.warn i{background:var(--qw-warn)}
.mh-svc-v.bad i{background:var(--qw-danger)}
.mh-svc-x{grid-column:1 / -1;margin:0 0 2px;color:var(--qw-text-4)}
@media (forced-colors:active){
  .res{border:1px solid CanvasText}
  .res-dot,.mh-svc-v i,.res-bar>i{forced-color-adjust:none}
}

/* ---------- ปรับให้เป็นของคุณ (ใช้โครง .gd-* ของหน้าต่างเลือก GPU) ---------- */
.pd{width:min(640px,100%)}
.pd .gd-sec-h h3 label{cursor:default}
.pd-hint{margin:-2px 0 10px;font-size:var(--qw-fs-xs);line-height:1.6;color:var(--qw-text-3)}
.pd textarea.input{min-height:112px;max-height:40vh;background:var(--qw-bg)}
.pd .pd-custom textarea.input{min-height:76px}
.pd-count{font-size:var(--qw-fs-xs);color:var(--qw-text-4);font-variant-numeric:tabular-nums}
.pd-count.near{color:color-mix(in srgb,var(--qw-warn) 70%,var(--qw-text))}
.pd-msg{margin:4px 0 6px}
.pd-styles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.pd-style{position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-width:0;padding:10px 12px 11px;border-radius:var(--qw-r-md);
  text-align:left;background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border-strong);
  transition:background-color var(--qw-dur) var(--qw-ease),box-shadow var(--qw-dur) var(--qw-ease)}
.pd-style:hover{background:var(--qw-bg-hover)}
/* ตัวที่เลือก: วงหมึก 1.5px + จุดเครื่องหมายถูก — ไม่ใช้ส้มทั้งกรอบ (ส้มสงวนให้ปุ่มส่ง/แชตใหม่ สวิตช์ใช้แค่ตัวราง) */
.pd-style[aria-checked="true"]{box-shadow:inset 0 0 0 1.5px var(--qw-text-2);background:var(--qw-bg-elev)}
.pd-style[aria-checked="true"]::after{content:"";position:absolute;right:9px;top:9px;width:14px;height:14px;border-radius:50%;
  background:var(--qw-accent) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath d='m4.5 8.2 2.3 2.3 4.7-5' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center/12px no-repeat}
.pd-st-n{padding-right:18px;font-size:var(--qw-fs-sm);font-weight:600;color:var(--qw-text)}
.pd-st-d{font-size:var(--qw-fs-xs);line-height:1.45;color:var(--qw-text-3)}
.pd-custom{margin-top:12px}
.pd-lrow{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:6px}
.pd-lrow .field-l{margin:0}
.pd-pv{margin-top:14px;padding:12px 14px 14px;border-radius:var(--qw-r-md);background:var(--qw-bg-sidebar);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.pd-pv-l{display:block;font-size:11px;font-weight:500;color:var(--qw-text-4)}
.pd-pv-q{display:flex;justify-content:flex-end;margin-top:6px}
.pd-pv-q span{max-width:85%;padding:6px 12px;border-radius:var(--qw-r-lg);background:var(--qw-bg-user);font-size:var(--qw-fs-sm);color:var(--qw-text)}
.pd-pv-a{margin-top:10px;font-family:var(--qw-font-serif);font-size:var(--qw-fs-base);line-height:1.7;color:var(--qw-text);white-space:pre-line}
.pd-pv-a.custom{font-family:var(--qw-font-ui);font-size:var(--qw-fs-sm);color:var(--qw-text-3);font-style:italic}
.pd .gd-actions{justify-content:flex-end}
@media (max-width:639.98px){
  .pd-styles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .pd .gd-actions{grid-template-columns:1fr}
}

/* ---------- แผงแสดงผล (artifact) ----------
   จอกว้าง: #app ได้คอลัมน์ที่สาม (กว้าง --art-w) แล้วแผง position:fixed วางทับคอลัมน์นั้นพอดี — iframe ของแชตหดตามจริง
   ไม่ถูกบัง  ต่ำกว่า 830px เป็นแผ่นเต็มจอ (modal) เลื่อนขึ้นจากขอบล่าง */
#art{position:fixed;top:0;right:0;bottom:0;z-index:30;width:var(--art-w,560px);display:flex;flex-direction:column;min-width:0;
  background:var(--qw-bg-elev);border-left:.5px solid var(--qw-border-strong)}
@media (min-width:830px){
  body.art-open #app{grid-template-columns:var(--sb,288px) minmax(0,1fr) var(--art-w,560px)}
}
/* dialog ของ WebUI เปิดอยู่: มืดตามแถบข้าง/ส่วนหัว (คลิกม่านตรงนี้ = ปิด dialog นั้น เหมือนคลิกม่านฝั่งซ้าย) */
#art::after{content:"";position:absolute;inset:0;z-index:40;background:var(--qw-scrim);opacity:0;pointer-events:none;
  transition:opacity var(--qw-dur) var(--qw-ease)}
body.frame-modal #art::after{opacity:1;pointer-events:auto}
.art-grip{position:absolute;left:-5px;top:0;bottom:0;z-index:3;width:10px;cursor:col-resize;touch-action:none}
.art-grip::after{content:"";position:absolute;left:4.5px;top:0;bottom:0;width:1.5px;background:transparent;transition:background-color var(--qw-dur) var(--qw-ease)}
.art-grip:hover::after,body.art-drag .art-grip::after{background:var(--qw-border-focus)}
.art-grip:focus-visible{outline:none}
.art-grip:focus-visible::after{width:2px;background:var(--qw-focus-ring)}
body.art-drag{cursor:col-resize;user-select:none}
body.art-drag iframe{pointer-events:none}
.art-bar{display:flex;align-items:center;gap:6px;height:var(--qw-header-h,52px);padding:0 8px 0 16px;flex:none}
.art-tl{flex:1;min-width:0;display:flex;align-items:center;gap:8px}
.art-kind{flex:none;height:20px;padding:0 8px;border-radius:var(--qw-r-full);font-size:11px;font-weight:500;line-height:20px;
  color:var(--qw-text-2);background:var(--qw-bg-active)}
.art-title{margin:0;min-width:0;font-size:var(--qw-fs-base);font-weight:600;color:var(--qw-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* หัวเรื่องรับโฟกัสจากโค้ดเท่านั้น (tabindex=-1 ให้โปรแกรมอ่านหน้าจออ่านชื่อชิ้นงาน) ไม่ใช่ปุ่ม — ไม่ต้องมีวงโฟกัส
   (เปิดด้วยเมาส์จากใน iframe แล้ว :focus-visible ยังจับ วงส้มขึ้นทุกครั้งที่เปิดแผง) */
.art-title:focus{outline:none}
.art-tools{display:flex;align-items:center;gap:6px;padding:0 10px 10px 16px;flex:none;border-bottom:.5px solid var(--qw-border)}
.art-mode button{height:26px;padding:0 10px;font-size:var(--qw-fs-xs)}
.art-ver{display:inline-flex;align-items:center;gap:2px;color:var(--qw-text-3)}
.art-ver-t{min-width:34px;text-align:center;font-size:var(--qw-fs-xs);font-variant-numeric:tabular-nums}
.art-ver .icon-btn:disabled{opacity:.35}
.art-ver .icon-btn:disabled:hover{background:none;color:var(--qw-text-3)}
.art-sp{flex:1}
.art-note{flex:none;display:flex;align-items:center;gap:8px 12px;flex-wrap:wrap;margin:10px 12px 0;padding:8px 12px;border-radius:var(--qw-r-sm);font-size:var(--qw-fs-xs);line-height:1.55;
  color:var(--qw-text-2);background:var(--qw-bg);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.art-note.warn{background:color-mix(in srgb,var(--qw-warn) 11%,transparent);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 42%,transparent)}
/* แถบบอกสถานะสคริปต์ของหน้า HTML: ข้อความ + ปุ่มสลับ "เรียกใช้สคริปต์ / หยุดสคริปต์" (ปุ่มหมึกเล็ก แบบ .mh-warn-b) */
.art-note-t{flex:1 1 200px;min-width:0}
.art-note-b{flex:none;height:26px;padding:0 10px;border-radius:var(--qw-r-xs);font-size:var(--qw-fs-xs);font-weight:500;white-space:nowrap;
  background:var(--qw-text);color:var(--qw-bg);transition:opacity var(--qw-dur)}
.art-note-b:hover{opacity:.86}
.art-note-b:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:2px}
.art-view{position:relative;flex:1;min-height:0;margin-top:0}
#artFrame{position:absolute;inset:0;width:100%;height:100%;border:0;background:var(--qw-bg)}
#art.k-html #artFrame{background:#fff}
.art-code{position:absolute;inset:0;margin:0;overflow:auto;padding:14px 16px 24px;background:var(--qw-bg-code);color:var(--qw-text-2);
  font:12.5px/1.6 var(--qw-font-mono);white-space:pre;tab-size:2;scrollbar-width:thin;scrollbar-color:var(--qw-border-strong) transparent}
.art-code:focus-visible,.art-table:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:-2px}
.art-img{position:absolute;inset:0;overflow:auto;display:flex;align-items:center;justify-content:center;padding:16px;background:var(--qw-bg)}
.art-img img{max-width:100%;max-height:100%;object-fit:contain;border-radius:var(--qw-r-sm);background:#fff;box-shadow:0 0 0 .5px var(--qw-border)}
.art-table{position:absolute;inset:0;overflow:auto;background:var(--qw-bg);scrollbar-width:thin;scrollbar-color:var(--qw-border-strong) transparent}
.art-table table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:var(--qw-fs-sm);color:var(--qw-text)}
.art-table th,.art-table td{padding:6px 12px;text-align:left;white-space:nowrap;max-width:420px;overflow:hidden;text-overflow:ellipsis;
  border-bottom:.5px solid var(--qw-border)}
.art-table th{position:sticky;top:0;z-index:1;background:var(--qw-bg-elev);font-weight:600;color:var(--qw-text-2);box-shadow:inset 0 -.5px 0 var(--qw-border-strong)}
.art-table td.num,.art-table th.num{text-align:right;font-variant-numeric:tabular-nums}
.art-table tr:hover td{background:var(--qw-bg-hover)}
.art-table .rn{position:sticky;left:0;z-index:1;color:var(--qw-text-4);background:var(--qw-bg);font-variant-numeric:tabular-nums;text-align:right}
.art-table th.rn{z-index:2;background:var(--qw-bg-elev)}
@media (max-width:829.98px){
  #art{left:0;width:auto;z-index:65;border-left:0;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px);
    transform:translateY(24px);opacity:0;transition:transform calc(var(--qw-dur) * 1.4) var(--qw-ease),opacity calc(var(--qw-dur) * 1.4) var(--qw-ease)}
  #art.on{transform:none;opacity:1}
  .art-grip{display:none}
  .art-bar{padding:0 6px 0 14px}
  .art-tools{padding:0 8px 10px 14px}
}
@media (forced-colors:active){
  .mem,.mem-form,.mem-note,.pd-style,.pd-pv,#art,.art-note{border:1px solid CanvasText}
  .pd-style[aria-checked="true"]{outline:2px solid Highlight;outline-offset:-2px}
  .art-grip::after{background:CanvasText}
}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
  <symbol id="i-sidebar" viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M9.5 4.5v15"/></symbol>
  <symbol id="i-plus" viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"/></symbol>
  <symbol id="i-search" viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/></symbol>
  <symbol id="i-folder" viewBox="0 0 24 24"><path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2.2h7.4a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/></symbol>
  <symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></symbol>
  <symbol id="i-more" viewBox="0 0 24 24"><circle cx="5.5" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/><circle cx="18.5" cy="12" r="1.4" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-chevron" viewBox="0 0 24 24"><path d="m7 10 5 5 5-5"/></symbol>
  <symbol id="i-updown" viewBox="0 0 24 24"><path d="m8 9.5 4-4 4 4M8 14.5l4 4 4-4"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24"><path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/></symbol>
  <symbol id="i-pencil" viewBox="0 0 24 24"><path d="M15.2 5.3a2.1 2.1 0 0 1 3 3L8.4 18.1 4.5 19.5l1.4-3.9z"/><path d="m13.5 7 3.5 3.5"/></symbol>
  <symbol id="i-trash" viewBox="0 0 24 24"><path d="M4.5 7h15M9.5 7V5.2c0-.7.5-1.2 1.2-1.2h2.6c.7 0 1.2.5 1.2 1.2V7M6.5 7l.8 11.2A2 2 0 0 0 9.3 20h5.4a2 2 0 0 0 2-1.8L17.5 7"/></symbol>
  <symbol id="i-sliders" viewBox="0 0 24 24"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></symbol>
  <symbol id="i-plug" viewBox="0 0 24 24"><path d="M9 3.5v4M15 3.5v4M6.5 7.5h11V11a5.5 5.5 0 0 1-11 0zM12 16.5v4"/></symbol>
  <symbol id="i-external" viewBox="0 0 24 24"><path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/></symbol>
  <symbol id="i-sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3.8"/><path d="M12 3v1.8M12 19.2V21M5.6 5.6l1.3 1.3M17.1 17.1l1.3 1.3M3 12h1.8M19.2 12H21M5.6 18.4l1.3-1.3M17.1 6.9l1.3-1.3"/></symbol>
  <symbol id="i-moon" viewBox="0 0 24 24"><path d="M19.5 14.2A7.8 7.8 0 0 1 9.8 4.5a7.8 7.8 0 1 0 9.7 9.7z"/></symbol>
  <symbol id="i-monitor" viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="11.5" rx="2"/><path d="M8.5 19.5h7M12 16v3.5"/></symbol>
  <symbol id="i-globe" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.5 3.4 5.3 3.4 8.5s-1 6-3.4 8.5c-2.4-2.5-3.4-5.3-3.4-8.5s1-6 3.4-8.5z"/></symbol>
  <symbol id="i-type" viewBox="0 0 24 24"><path d="M5 7.5V5h14v2.5M12 5v14M9 19h6"/></symbol>
  <symbol id="i-upload" viewBox="0 0 24 24"><path d="M12 15V4.5M7.5 9 12 4.5 16.5 9M4.5 15v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/></symbol>
  <symbol id="i-file" viewBox="0 0 24 24"><path d="M14 3.5H7.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2V8z"/><path d="M14 3.5V8h4.5"/></symbol>
  <symbol id="i-menu" viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h10"/></symbol>
  <symbol id="i-compose" viewBox="0 0 24 24"><path d="M12 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V12"/><path d="M17.4 4.1a1.9 1.9 0 0 1 2.6 2.6l-7.6 7.6-3.4.8.8-3.4z"/></symbol>
  <symbol id="i-grid" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.6"/><rect x="4" y="13" width="7" height="7" rx="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.6"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><path d="M10.3 4.9 3.4 17a2 2 0 0 0 1.7 3h13.8a2 2 0 0 0 1.7-3L13.7 4.9a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4"/><circle cx="12" cy="16.8" r=".9" fill="currentColor" stroke="none"/></symbol>
  <symbol id="i-chip" viewBox="0 0 24 24"><rect x="3" y="6.5" width="18" height="10.5" rx="2"/><circle cx="9" cy="11.75" r="2.6"/><path d="M14.5 10h3.5M14.5 13.5h3.5M6.5 17v2.5M10 17v2.5M13.5 17v2.5"/></symbol>
  <symbol id="i-chev-r" viewBox="0 0 24 24"><path d="m10 7 5 5-5 5"/></symbol>
  <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M19.5 12a7.5 7.5 0 1 1-2.3-5.4"/><path d="M19.5 4.5v4.2h-4.2"/></symbol>
  <symbol id="i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><circle cx="12" cy="8" r=".9" fill="currentColor" stroke="none"/></symbol>
  <!-- รอบ 4: ความจำ / ปรับให้เป็นของคุณ / แจ้งเตือน / แผงแสดงผล / ส่งออก -->
  <symbol id="i-pin" viewBox="0 0 24 24"><path d="M9.3 3.8h5.4l-.9 5.4 3.4 3.3v1.7H6.8v-1.7l3.4-3.3z"/><path d="M12 14.2v6"/></symbol>
  <symbol id="i-user" viewBox="0 0 24 24"><circle cx="12" cy="8.5" r="3.7"/><path d="M4.8 19.8c.9-3.4 3.8-5.5 7.2-5.5s6.3 2.1 7.2 5.5"/></symbol>
  <symbol id="i-bell" viewBox="0 0 24 24"><path d="M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 1.6h-14z"/><path d="M10 20.3a2.2 2.2 0 0 0 4 0"/></symbol>
  <symbol id="i-download" viewBox="0 0 24 24"><path d="M12 4.5V15M7.5 10.5 12 15l4.5-4.5M4.5 15v3a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-3"/></symbol>
  <symbol id="i-copy" viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5v-2a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/></symbol>
  <symbol id="i-code" viewBox="0 0 24 24"><path d="m8.5 8-4 4 4 4M15.5 8l4 4-4 4M13.4 5.5l-2.8 13"/></symbol>
  <symbol id="i-print" viewBox="0 0 24 24"><path d="M7 9V4.5h10V9"/><rect x="4" y="9" width="16" height="7.5" rx="2"/><path d="M7 13.5h10v6.5H7z"/></symbol>
  <symbol id="i-chev-l" viewBox="0 0 24 24"><path d="m14 7-5 5 5 5"/></symbol>
  <symbol id="i-image" viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="10" r="1.7"/><path d="m20.5 16-4.5-4.5-10 8"/></symbol>
  <symbol id="i-panel" viewBox="0 0 24 24"><rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M13.5 4.5v15"/></symbol>
  <!-- batch 3 (D4): เมนูบัญชี → "การใช้งาน" / "ตรวจระบบ" (รูปเดียวกับแท็บในหน้าจัดการ) -->
  <symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 19.5h16"/><path d="M7 16.5v-5"/><path d="M12 16.5V7"/><path d="M17 16.5v-8"/></symbol>
  <symbol id="i-pulse" viewBox="0 0 24 24"><path d="M3.5 12h4l2-5 4 10 2-5h5"/></symbol>
</svg>

<a class="skip" id="skipLink" href="#frame">__T_skip_composer__</a>
<script>
/* ตั้งสถานะแถบข้างก่อนวาดภาพแรก — กันแถบกางเต็มแวบหนึ่งแล้วค่อยพับ (กติกาเดียวกับ wantCollapsed() ข้างล่าง) */
(function () {
  try {
    var w = window.innerWidth, v;
    if (w >= 830 && w < 1056) { v = localStorage.getItem('qwen-sidebar-auto'); v = v ? v === 'collapsed' : true; }
    else v = localStorage.getItem('qwen-sidebar') === 'collapsed';
    if (v) document.body.classList.add('sb-min');
  } catch (e) {}
})();
</script>
<div id="app">
  <aside id="sb" aria-label="__T_sidebar__">
    <div class="sb-head">
      <div class="brand"><span class="mark" aria-hidden="true">Q</span><span class="wordmark">Qwen3.8</span></div>
      <button type="button" class="icon-btn" id="sbToggle" aria-label="__T_collapse__" data-tip="__T_collapse__"><svg class="ic" aria-hidden="true"><use id="sbToggleIc" href="#i-sidebar"/></svg></button>
    </div>
    <nav class="sb-nav" aria-label="__T_main_nav__">
      <button type="button" class="item item-new" id="newChatBtn" aria-label="__T_newchat__" data-tip="__T_newchat__" data-tip-rail><span class="new-dot"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-plus"/></svg></span><span class="lbl">__T_newchat__</span></button>
      <button type="button" class="item" id="searchBtn" aria-label="__T_searchchats__" data-tip="__T_searchchats__ (Ctrl+K)" data-tip-rail aria-keyshortcuts="Control+K"><span class="ib"><svg class="ic" aria-hidden="true"><use href="#i-search"/></svg></span><span class="lbl">__T_searchchats__</span><span class="kbd" aria-hidden="true">Ctrl K</span></button>
      <div class="search" id="searchWrap" hidden>
        <svg class="ic ic-sm" aria-hidden="true"><use href="#i-search"/></svg>
        <input id="q" type="text" role="searchbox" autocomplete="off" spellcheck="false" placeholder="__T_searchph__" aria-label="__T_searchchats__" aria-controls="recList">
        <button type="button" class="icon-btn xs" id="qClear" aria-label="__T_close__" data-tip="__T_close__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-x"/></svg></button>
      </div>
      <button type="button" class="item rail-only" id="railProj" aria-label="__T_project_settings__" data-tip="__T_project_settings__" aria-haspopup="dialog" aria-controls="pp"><span class="ib"><svg class="ic" aria-hidden="true"><use href="#i-folder"/></svg></span><span class="lbl">__T_project_settings__</span></button>
      <button type="button" class="item rail-only" id="railRecents" aria-label="__T_recents__" data-tip="__T_recents__"><span class="ib"><svg class="ic" aria-hidden="true"><use href="#i-clock"/></svg></span><span class="lbl">__T_recents__</span></button>
    </nav>
    <div class="sb-scroll" id="sbScroll">
      <section class="sec" id="secProjects" aria-labelledby="projH">
        <div class="sec-h"><h2 class="sec-t" id="projH">__T_projects__</h2>
          <button type="button" class="icon-btn xs" id="projAdd" aria-label="__T_newproj__" data-tip="__T_newproj__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-plus"/></svg></button></div>
        <div class="newproj" id="newProjWrap" hidden><input id="newProjIn" maxlength="60" autocomplete="off" placeholder="__T_newph__" aria-label="__T_newproj__"></div>
        <div class="list" id="projList" role="list" aria-labelledby="projH"></div>
      </section>
      <section class="sec" id="secRecents" aria-labelledby="recH">
        <div class="sec-h"><h2 class="sec-t" id="recH">__T_recents__</h2></div>
        <div class="list" id="recList" role="list" aria-labelledby="recH"></div>
      </section>
    </div>
    <span class="vh" id="rowKeysHint">__T_row_keys_hint__</span>
    <div class="sb-foot">
      <button type="button" class="acct" id="acctBtn" aria-haspopup="menu" aria-expanded="false" aria-label="__T_account_menu__" data-tip="__T_account_menu__" data-tip-rail>
        <span class="avatar"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-monitor"/></svg><span class="hdot" id="hdot"></span><span class="gbadge" id="gbadge"></span></span>
        <span class="acct-txt"><span class="acct-1">__T_local_account__<span class="acct-gpu" id="gpuTag" hidden></span></span><span class="acct-2" id="stat" data-model="__MODEL__">__T_checking__</span></span>
        <svg class="ic ic-sm updown" aria-hidden="true"><use href="#i-updown"/></svg>
      </button>
    </div>
  </aside>

  <main id="main">
    <header id="hdr">
      <button type="button" class="icon-btn mobile-only" id="burger" aria-label="__T_open_sidebar__" data-tip="__T_open_sidebar__" aria-controls="sb" aria-expanded="false"><svg class="ic" aria-hidden="true"><use href="#i-menu"/></svg></button>
      <div class="crumb">
        <button type="button" class="title-btn" id="titleBtn" aria-haspopup="menu" aria-expanded="false" hidden><span class="tt" id="titleTxt"></span><svg class="ic ic-sm" aria-hidden="true"><use href="#i-chevron"/></svg></button>
        <button type="button" class="title-static" id="titleStatic" data-tip="__T_project_settings__" aria-haspopup="dialog" aria-controls="pp"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-folder"/></svg><span class="tt" id="titleProj"></span></button>
      </div>
      <!-- ตัวปุ่มเขียนชื่อภาษาปลายทาง (ไทย / EN): คนที่อ่านภาษาปัจจุบันไม่ออกก็ยังหาทางกลับได้
           ป้ายชื่อ (data-tip-text) เขียนเป็นภาษาของหน้าเหมือนข้อความอื่น — หน้าอังกฤษต้องไม่มีอักษรไทยนอกจากคำว่า ไทย
           data-tip จริงถูกตั้งเฉพาะปุ่มที่ยังไม่ได้เลือก (paintLang) — ปุ่มที่เลือกอยู่กดแล้วไม่มีอะไรเกิด -->
      <div class="lsw" id="langSw" role="group" aria-label="__T_lang_group__">
        <button type="button" data-lang="th" lang="th" aria-pressed="false" data-tip-text="__T_lang_tip_th__">ไทย</button>
        <button type="button" data-lang="en" lang="en" aria-label="English" aria-pressed="false" data-tip-text="__T_lang_tip_en__">EN</button>
      </div>
      <script>
      /* ทาปุ่มของภาษาปัจจุบันก่อนวาดภาพแรก — สคริปต์หลักอยู่ท้ายหน้า (ไฟล์ใหญ่) ถ้าเบราว์เซอร์วาดก่อนถึง
         จะเห็นสวิตช์ไม่มีปุ่มไหนถูกเลือกแวบหนึ่ง (แบบเดียวกับสคริปต์ตั้งแถบข้างด้านบน) */
      (function () { var l = document.documentElement.lang; [].forEach.call(document.querySelectorAll('#langSw button'), function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-lang') === l)); }); })();
      </script>
      <button type="button" class="icon-btn mobile-only" id="hdrNew" aria-label="__T_newchat__" data-tip="__T_newchat__"><svg class="ic" aria-hidden="true"><use href="#i-compose"/></svg></button>
      <button type="button" class="hdr-btn" id="projBtn" aria-label="__T_project_settings__" aria-haspopup="dialog" aria-controls="pp" aria-expanded="false" data-tip="__T_project_settings__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-sliders"/></svg><span class="lbl">__T_project_btn__</span></button>
    </header>
    <div id="stage"><iframe id="frame" title="__T_chat_frame__" allow="clipboard-read; clipboard-write"></iframe></div>
  </main>
</div>

<div id="scrim" aria-hidden="true"></div>

<aside id="pp" role="dialog" aria-modal="true" aria-labelledby="ppTitle">
  <div class="pp-head">
    <div class="pp-head-t">
      <div class="pp-kicker"><svg class="ic ic-xs"><use href="#i-folder"/></svg>__T_project__</div>
      <h2 id="ppTitle"></h2>
    </div>
    <button type="button" class="icon-btn" id="ppMore" aria-label="__T_proj_options__" data-tip="__T_proj_options__" aria-haspopup="menu" aria-expanded="false"><svg class="ic" aria-hidden="true"><use href="#i-more"/></svg></button>
    <button type="button" class="icon-btn" id="ppClose" aria-label="__T_close__" data-tip="__T_close__"><svg class="ic" aria-hidden="true"><use href="#i-x"/></svg></button>
  </div>
  <div class="pp-body">
    <section class="pp-sec" aria-labelledby="ppInstrH">
      <div class="pp-sec-h"><h3 id="ppInstrH">__T_instructions__</h3></div>
      <p class="pp-hint" id="ppInstrHint">__T_instructions_hint__</p>
      <textarea class="input" id="ppInstr" rows="6" placeholder="__T_instructions_ph__" aria-labelledby="ppInstrH" aria-describedby="ppInstrHint ppInstrState"></textarea>
      <div class="pp-actions"><span class="pp-state" id="ppInstrState">__T_save_hint__</span>
        <button type="button" class="btn btn-ink sm" id="ppInstrSave" disabled>__T_save__</button></div>
    </section>
    <!-- ความจำของโปรเจกต์ (K3) — รายการสร้างด้วย JS จาก GET /_qwen/memory -->
    <section class="pp-sec" id="ppMem" aria-labelledby="ppMemH">
      <div class="pp-sec-h"><h3 id="ppMemH">__T_mem_title__</h3>
        <button type="button" class="btn btn-ghost sm" id="ppMemAdd" aria-expanded="false" aria-controls="ppMemForm"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-plus"/></svg>__T_mem_add__</button></div>
      <p class="pp-hint" id="ppMemHint">__T_mem_hint__</p>
      <div class="mem-form" id="ppMemForm" hidden>
        <textarea class="input" id="ppMemText" rows="3" maxlength="8000" placeholder="__T_mem_ph__" aria-label="__T_mem_new__" aria-describedby="ppMemEsc"></textarea>
        <p class="mem-note warn mem-esc" id="ppMemEsc" hidden>__T_mem_esc_again__</p>
        <div class="mem-form-row">
          <div class="sel sel-sm"><select id="ppMemKind" aria-label="__T_mem_kind__"></select><svg class="ic ic-sm" aria-hidden="true"><use href="#i-chevron"/></svg></div>
          <span class="mem-grow"></span>
          <button type="button" class="btn btn-ghost sm" id="ppMemCancel">__T_cancel__</button>
          <button type="button" class="btn btn-ink sm" id="ppMemSave">__T_save__</button>
        </div>
      </div>
      <div class="mem-list" id="ppMemList" role="list" aria-labelledby="ppMemH" aria-describedby="ppMemSum"></div>
      <div class="mem-foot"><span class="mem-sum" id="ppMemSum"></span><button type="button" class="mem-link" id="ppMemAll" hidden></button></div>
    </section>
    <section class="pp-sec" id="ppKnow" aria-labelledby="ppKnowH">
      <div class="pp-sec-h"><h3 id="ppKnowH">__T_knowledge__</h3>
        <button type="button" class="btn btn-ghost sm" id="ppUpload" aria-describedby="ppFilesHint"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-plus"/></svg>__T_addfile__</button></div>
      <p class="pp-hint" id="ppFilesHint">__T_files_hint__</p>
      <div class="files" id="ppFiles" role="list" aria-labelledby="ppKnowH"></div>
      <button type="button" class="drop" id="ppDrop" hidden><svg class="ic"><use href="#i-upload"/></svg><span>__T_dropfiles__</span></button>
      <input type="file" id="ppFileIn" multiple hidden>
      <button type="button" class="pp-path" id="ppDir" data-tip="__T_copydir__"><svg class="ic ic-xs" aria-hidden="true"><use href="#i-folder"/></svg><span id="ppDirTxt"></span></button>
      <!-- batch 2b (C4): ค้นเอกสารของโปรเจกต์อัตโนมัติ — hub ค้น kb ด้วยข้อความล่าสุดแล้วแนบผลต่อท้ายข้อความนั้น (ฟิลด์ auto_kb ค่าเริ่มต้น เปิด) -->
      <div class="field field-row" id="ppAkbRow">
        <div><span class="field-l" id="ppAkbL">__T_autokb__</span><span class="field-h" id="ppAkbH">__T_autokb_hint__</span></div>
        <button type="button" class="switch" id="ppAkb" role="switch" aria-checked="true" aria-labelledby="ppAkbL" aria-describedby="ppAkbH"></button>
      </div>
    </section>
    <!-- ไฟล์ที่ Qwen สร้าง (K2: GET /_qwen/out/) — ซ่อนไว้จนกว่าจะมีไฟล์ -->
    <section class="pp-sec" id="ppOut" aria-labelledby="ppOutH" hidden>
      <div class="pp-sec-h"><h3 id="ppOutH">__T_out_title__</h3></div>
      <p class="pp-hint" id="ppOutHint">__T_out_hint__</p>
      <div class="files" id="ppOutList" role="list" aria-labelledby="ppOutH"></div>
      <button type="button" class="mem-link" id="ppOutAll" hidden></button>
    </section>
    <!-- batch 2a (B5): งานค้นคว้าเชิงลึก (GET /_qwen/research ทุกครั้งที่เปิดแผง + ถามซ้ำทุก 4 วินาทีระหว่างมีงานที่ยังทำอยู่)
         ปุ่ม "ค้นคว้าใหม่" เติมคำขอลงช่องพิมพ์ (ไม่ส่งเอง) — ผู้ใช้เติมหัวข้อแล้วส่ง โมเดลเรียก local_do action=research -->
    <section class="pp-sec" id="ppRes" aria-labelledby="ppResH">
      <div class="pp-sec-h"><h3 id="ppResH">__T_res_title__</h3>
        <button type="button" class="btn btn-ghost sm" id="ppResNew" aria-describedby="ppResHint"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-search"/></svg>__T_res_new__</button></div>
      <p class="pp-hint" id="ppResHint">__T_res_hint__</p>
      <div class="res-list" id="ppResList" aria-labelledby="ppResH" tabindex="-1"></div>
      <button type="button" class="mem-link" id="ppResAll" hidden></button>
    </section>
    <section class="pp-sec" aria-labelledby="ppSetH">
      <div class="pp-sec-h"><h3 id="ppSetH">__T_settings__</h3></div>
      <div class="field">
        <label class="field-l" for="ppModel">__T_default_model__</label>
        <div class="sel"><select id="ppModel" aria-describedby="ppModelH"></select><svg class="ic ic-sm" aria-hidden="true"><use href="#i-chevron"/></svg></div>
        <span class="field-h" id="ppModelH">__T_default_model_hint__</span>
      </div>
      <div class="field">
        <span class="field-l" id="ppThinkL">__T_think__</span>
        <div class="seg full" id="ppThink" role="radiogroup" aria-labelledby="ppThinkL" aria-describedby="ppThinkH">
          <button type="button" role="radio" data-v="off">__T_think_off__</button>
          <button type="button" role="radio" data-v="on">__T_think_on__</button>
          <button type="button" role="radio" data-v="auto">__T_think_auto__</button>
        </div>
        <span class="field-h" id="ppThinkH"></span>
      </div>
      <div class="field field-row">
        <div><span class="field-l" id="ppExtL">__T_extend__</span><span class="field-h" id="ppExtH">__T_extend_hint__</span></div>
        <button type="button" class="switch" id="ppExt" role="switch" aria-checked="false" aria-labelledby="ppExtL" aria-describedby="ppExtH"></button>
      </div>
    </section>
    <section class="pp-sec">
      <div class="pp-links">
        <button type="button" class="btn btn-ghost sm" id="ppManage"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-grid"/></svg>__T_manage_all__<svg class="ic ic-xs" aria-hidden="true"><use href="#i-external"/></svg></button>
      </div>
    </section>
  </div>
</aside>

<!-- แผงแสดงผล (K7) — จอกว้าง: คอลัมน์ขวาของ #app (แชตแคบลง ไม่ทับ) · จอแคบ: แผ่นเต็มจอแบบ modal
     เนื้อหาจากโมเดลแสดงใน iframe sandbox (ไม่มี allow-same-origin) + CSP default-src 'none' — ดูส่วน "แผงแสดงผล" ในสคริปต์ -->
<section class="art" id="art" aria-labelledby="artTitle" hidden>
  <div class="art-grip" id="artGrip" role="separator" aria-orientation="vertical" tabindex="0" aria-label="__T_art_resize__" aria-controls="art" data-tip="__T_art_resize__"></div>
  <div class="art-bar">
    <div class="art-tl">
      <span class="art-kind" id="artKind"></span>
      <h2 class="art-title" id="artTitle" tabindex="-1"></h2>
      <button type="button" class="icon-btn xs" id="artList" aria-haspopup="menu" aria-expanded="false" aria-label="__T_art_list__" data-tip="__T_art_list__" hidden><svg class="ic ic-sm" aria-hidden="true"><use href="#i-chevron"/></svg></button>
    </div>
    <button type="button" class="icon-btn" id="artClose" aria-label="__T_art_close__" data-tip="__T_art_close__"><svg class="ic" aria-hidden="true"><use href="#i-x"/></svg></button>
  </div>
  <div class="art-tools">
    <div class="seg art-mode" id="artMode" role="radiogroup" aria-label="__T_art_view__">
      <button type="button" role="radio" data-v="preview" aria-checked="true">__T_art_preview__</button>
      <button type="button" role="radio" data-v="code" aria-checked="false">__T_art_code__</button>
    </div>
    <div class="art-ver" id="artVer" role="group" aria-label="__T_art_versions__" hidden>
      <button type="button" class="icon-btn xs" id="artPrev" aria-label="__T_art_prev__" data-tip="__T_art_prev__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-chev-l"/></svg></button>
      <span class="art-ver-t" id="artVerT"></span>
      <button type="button" class="icon-btn xs" id="artNext" aria-label="__T_art_next__" data-tip="__T_art_next__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-chev-r"/></svg></button>
    </div>
    <span class="art-sp"></span>
    <button type="button" class="icon-btn sm" id="artCopy" aria-label="__T_art_copy__" data-tip="__T_art_copy__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-copy"/></svg></button>
    <button type="button" class="icon-btn sm" id="artDl" aria-label="__T_art_download__" data-tip="__T_art_download__"><svg class="ic ic-sm" aria-hidden="true"><use href="#i-download"/></svg></button>
  </div>
  <p class="art-note" id="artNote" hidden></p>
  <div class="art-view" id="artView">
    <iframe id="artFrame" sandbox="" referrerpolicy="no-referrer" allow="camera 'none'; microphone 'none'; geolocation 'none'; display-capture 'none'; clipboard-read 'none'; clipboard-write 'none'; usb 'none'; serial 'none'; hid 'none'; bluetooth 'none'; payment 'none'" aria-describedby="artSandboxD" hidden></iframe>
    <div class="art-table" id="artTable" role="region" tabindex="0" aria-labelledby="artTitle" hidden></div>
    <div class="art-img" id="artImgWrap" hidden><img id="artImg" alt=""></div>
    <pre class="art-code" id="artCode" tabindex="0" aria-labelledby="artTitle" hidden><code id="artCodeC"></code></pre>
  </div>
  <span class="vh" id="artSandboxD">__T_art_sandbox__</span>
</section>

<div class="menu" id="menu" role="menu" hidden></div>
<div id="tip" aria-hidden="true" hidden></div>

<div class="dlg-wrap" id="dlg" hidden>
  <div class="dlg" id="dlgBox" role="alertdialog" aria-modal="true" aria-labelledby="dlgTitle" aria-describedby="dlgBody">
    <h2 id="dlgTitle"></h2>
    <p id="dlgBody"></p>
    <input class="input" id="dlgIn" maxlength="200" autocomplete="off" aria-labelledby="dlgTitle" hidden>
    <div class="dlg-actions">
      <button type="button" class="btn btn-ghost" id="dlgCancel">__T_cancel__</button>
      <button type="button" class="btn btn-ink" id="dlgOk">__T_ok__</button>
    </div>
  </div>
</div>

<!-- หน้าต่างเลือก GPU — เนื้อหา (#gdBody, #gdStatus) สร้างด้วย JS จากข้อมูลของ GET /api/gpu -->
<div class="gd-wrap" id="gdWrap" hidden>
  <div class="gd" id="gd" role="dialog" aria-modal="true" aria-labelledby="gdTitle" aria-describedby="gdSub" tabindex="-1">
    <div class="gd-grab" aria-hidden="true"></div>
    <div class="gd-head">
      <div class="gd-head-t"><h2 id="gdTitle">__T_gpu_title__</h2><p class="gd-sub" id="gdSub">__T_gpu_sub__</p></div>
      <button type="button" class="icon-btn" id="gdClose" aria-label="__T_close__" data-tip="__T_close__"><svg class="ic" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="gd-body" id="gdBody"></div>
    <div class="gd-foot">
      <div class="gd-status" id="gdStatus"></div>
      <p class="gd-confirm" id="gdConfirm">__T_gpu_confirm__</p>
      <div class="gd-actions">
        <button type="button" class="btn gd-reset" id="gdReset">__T_gpu_reset__</button>
        <button type="button" class="btn btn-ghost" id="gdCancel">__T_cancel__</button>
        <button type="button" class="btn btn-ink gd-apply" id="gdApply" aria-describedby="gdConfirm">__T_gpu_apply__</button>
      </div>
    </div>
  </div>
</div>

<!-- ปรับให้เป็นของคุณ (K4) — ใช้โครงเดียวกับหน้าต่างเลือก GPU (.gd-*) : กล่องกลางจอ / แผ่นจากขอบล่างบนจอแคบ
     ค่าเก็บที่ hub (GET/PATCH /api/settings {about_me, style, style_custom}) ใช้ร่วมทุกโปรเจกต์ -->
<div class="gd-wrap" id="pdWrap" hidden>
  <div class="gd pd" id="pd" role="dialog" aria-modal="true" aria-labelledby="pdTitle" aria-describedby="pdSub" tabindex="-1">
    <div class="gd-grab" aria-hidden="true"></div>
    <div class="gd-head">
      <div class="gd-head-t"><h2 id="pdTitle">__T_pers_title__</h2><p class="gd-sub" id="pdSub">__T_pers_sub__</p></div>
      <button type="button" class="icon-btn" id="pdClose" aria-label="__T_close__" data-tip="__T_close__"><svg class="ic" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="gd-body" id="pdBody">
      <div class="gd-msg warn pd-msg" id="pdMsg" hidden><svg class="ic ic-sm" aria-hidden="true"><use href="#i-alert"/></svg><span class="gd-msg-c" id="pdMsgT"></span></div>
      <section class="gd-sec">
        <div class="gd-sec-h"><h3><label for="pdAbout">__T_pers_about__</label></h3><span class="pd-count" id="pdAboutN" aria-hidden="true"></span></div>
        <p class="pd-hint" id="pdAboutH">__T_pers_about_h__</p>
        <textarea class="input" id="pdAbout" rows="5" maxlength="1500" placeholder="__T_pers_about_ph__" aria-describedby="pdAboutH"></textarea>
      </section>
      <section class="gd-sec">
        <div class="gd-sec-h"><h3 id="pdStyleH">__T_pers_style__</h3></div>
        <div class="pd-styles" id="pdStyles" role="radiogroup" aria-labelledby="pdStyleH"></div>
        <div class="pd-custom" id="pdCustomWrap" hidden>
          <div class="pd-lrow"><label class="field-l" for="pdCustom">__T_pers_custom__</label><span class="pd-count" id="pdCustomN" aria-hidden="true"></span></div>
          <textarea class="input" id="pdCustom" rows="3" maxlength="800" placeholder="__T_pers_custom_ph__"></textarea>
        </div>
        <div class="pd-pv" id="pdPv" role="group" aria-labelledby="pdPvL">
          <span class="pd-pv-l" id="pdPvL">__T_pers_preview__</span>
          <div class="pd-pv-q"><span id="pdPvQ">__T_pers_pv_q__</span></div>
          <div class="pd-pv-a" id="pdPvA"></div>
        </div>
      </section>
    </div>
    <div class="gd-foot">
      <div class="gd-status" id="pdStatus"></div>
      <p class="gd-confirm" id="pdNote">__T_pers_privacy__</p>
      <div class="gd-actions">
        <button type="button" class="btn btn-ghost" id="pdCancel">__T_cancel__</button>
        <button type="button" class="btn btn-ink gd-apply" id="pdSave" aria-describedby="pdNote">__T_save__</button>
      </div>
    </div>
  </div>
</div>

<!-- toast ที่เห็นเป็นภาพอย่างเดียว เสียงอ่านมาจากสองช่องที่ซ่อนไว้ แยกระดับสุภาพ/เร่งด่วน (ข้อผิดพลาดต้องขัดจังหวะ) -->
<div id="toast" aria-hidden="true"></div>
<div class="vh" id="srPolite" role="status" aria-live="polite"></div>
<div class="vh" id="srAlert" role="alert" aria-live="assertive"></div>

<script>
(function () {
'use strict';
/* ข้อมูลจากเซิร์ฟเวอร์ — qwenShell ถูกตั้งใน <head> ก่อน boot.js */
var S = window.qwenShell || {};
var ME = __ME__, HUB = "__HUB__", LANG = "__LANG__";
__QW_GLUE__
__QW_GPU__
__QW_LIB__
/* ข้อความของเราผ่าน glue() ครั้งเดียวตอนเริ่ม (สำเนา — qwenShell.T ของ iframe คงตัวอักษรเดิม)
   tRaw() = ตัวอักษรเดิม ใช้กับสิ่งที่เป็น "ชื่อ" บรรทัดเดียว (หัวเรื่อง, แท็บเบราว์เซอร์, title) ไม่มีวันขึ้นบรรทัดใหม่ */
var T = glueAll(S.T || {});
function t(k) { return T[k] != null ? String(T[k]) : k; }
function tRaw(k) { var r = S.T || {}; return r[k] != null ? String(r[k]) : k; }
/* คำอธิบายในแผงโปรเจกต์ที่เซิร์ฟเวอร์เติมลง HTML โดยตรง (ไม่ผ่าน t()) — ข้อความของเราล้วน */
glueText(document.querySelectorAll('#pp .pp-hint, #pp .field-h, #ppDrop span, #gdSub, #gdConfirm, #gd .gd-actions button'));
/* รอบ 4: คำอธิบายในหน้าต่างปรับให้เป็นของคุณ และป้ายของแผงแสดงผล */
glueText(document.querySelectorAll('#pdSub, #pdAboutH, #pdNote, #artSandboxD'));
var UI = "__UI__";
/* ใช้ชื่อโฮสต์เดียวกับที่ผู้ใช้เปิดหน้านี้ (127.0.0.1 หรือ localhost) — คนละชื่อ = คนละ origin
   IndexedDB/localStorage แยกกัน แชต ธีม และสถานะแถบข้างจะดูเหมือนหายไปเมื่อสลับโปรเจกต์ */
function portUrl(port) { return location.protocol + '//' + location.hostname + ':' + port + '/'; }
try { var hubU = new URL(HUB); hubU.hostname = location.hostname; HUB = hubU.origin; } catch (e) {}
/* ใช้รายชื่อจาก qwenShell แทนการฝัง JSON ซ้ำอีกจุด — ถ้าชื่อโปรเจกต์ทำให้สคริปต์ใน <head> พัง
   สคริปต์นี้ยังทำงานต่อได้ แล้วค่อยดึงรายชื่อจริงจาก hub ทาง fetch */
var PROJECTS = (S.projects || []).slice();
var MODELS = (S.models || []).slice();
/* ?model=<ชื่อ> ในลิงก์ของ shell = เปิดแท็บนี้ด้วยโมเดลนั้นแทนโมเดลเริ่มต้นของโปรเจกต์ (เช่นลองกับโมเดลเล็ก)
   ส่งต่อให้ iframe ทาง model= ของ WebUI เอง ซึ่งแค่เลือกให้ ไม่สั่งโหลดโมเดล (ไม่ส่ง load= ต่อ)
   รับเฉพาะชื่อที่อยู่ในรายชื่อโมเดลของ hub — ค่านี้ถูกต่อเข้า URL ของ iframe
   เลิกใช้ทันทีที่ผู้ใช้ตั้งโมเดลเริ่มต้นใหม่ในแผง (dropUrlModel) */
var URL_MODEL = '';
try { var qm = new URLSearchParams(location.search).get('model'); if (qm && MODELS.indexOf(qm) >= 0) URL_MODEL = qm; } catch (e) {}
function uiSrc() {
  if (!URL_MODEL) return UI;
  try { var u = new URL(UI, location.href); u.searchParams.set('model', URL_MODEL); return u.pathname + u.search; } catch (e) { return UI; }
}
function dropUrlModel() {
  URL_MODEL = '';
  try {
    var u = new URL(location.href);
    if (u.searchParams.has('model')) { u.searchParams.delete('model'); history.replaceState(null, '', u.pathname + u.search + u.hash); }
  } catch (e) {}
}
var PROJ = Object.assign({}, S.project || {});
var FILEDIR = S.filesDir || '';
var HEALTH = { state: 'checking', model: '' };
/* GPU ที่แต่ละโมเดลใช้ (d.gpu จาก /api/projects) — null = ไม่มี gpu-profile.json แถบข้างแสดงเหมือนเดิมทุกอย่าง */
var GPU = null;
/* batch 2a (B5): สถานะบริการ (d.services จาก /api/projects: embed / research / web / mcp) — null = hub รุ่นก่อน/ยังไม่เคยตรวจ
   (เมนูบัญชีไม่แสดงก้อนบริการเลย แทนที่จะเดาว่า "ไม่ทำงาน") */
var SVC = null;

var $ = function (s, r) { return (r || document).querySelector(s); };
var body = document.body;
var frame = $('#frame'), sb = $('#sb'), pp = $('#pp'), scrim = $('#scrim'), menu = $('#menu');
var NARROW = window.matchMedia('(max-width: 829.98px)');
/* ช่วงที่ถ้าแถบข้างกางเต็ม (288px) iframe จะแคบกว่า 768px = จุดตัดหน้ามือถือของ WebUI */
var MID = window.matchMedia('(min-width: 830px) and (max-width: 1055.98px)');
function isMobile() { return NARROW.matches; }
HEALTH.model = $('#stat').getAttribute('data-model') || '';
/* เขียน DOM เฉพาะเมื่อค่าเปลี่ยน — ตัวจับเวลา 3/10 วินาทีเรียกซ้ำตลอด ไม่ควรทำให้เกิด mutation เปล่าๆ */
function setText(n, s) { s = s == null ? '' : String(s); if (n.textContent !== s) n.textContent = s; }
function setHidden(n, v) { v = !!v; if (n.hidden !== v) n.hidden = v; }
function setAttr(n, k, v) { if (v == null) { if (n.hasAttribute(k)) n.removeAttribute(k); } else if (n.getAttribute(k) !== String(v)) n.setAttribute(k, v); }
function shown(n) { return !!(n && n.isConnected && n.getClientRects().length); }
/* shown() ยังเห็นตัวที่ visibility:hidden (เช่นรายการในแถบไอคอนที่พับกลับ) เพราะกล่องยังกินที่อยู่
   ตัวแบบนั้นโฟกัสไม่ได้ เบราว์เซอร์จะปล่อยโฟกัสหล่นไป <body> ทีหลัง — ใช้ตัวนี้ตัดสินว่าต้องย้ายโฟกัสหรือไม่ */
function visible(n) {
  if (!shown(n)) return false;
  try { return n.checkVisibility ? n.checkVisibility({ visibilityProperty: true, checkVisibilityCSS: true }) : getComputedStyle(n).visibility !== 'hidden'; }
  catch (e) { return true; }
}
/* โฟกัสไม่อยู่บนอะไรที่ใช้งานได้: <body>, รายการในเมนูที่เพิ่งปิด หรือตัวที่ถูกซ่อน */
function focusLost() {
  var a = document.activeElement;
  return !a || a === document.body || (menu && menu.contains(a)) || !visible(a);
}
function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }
/* แทน %s ด้วยฟังก์ชัน — ถ้าส่งสตริงตรงๆ ชื่อที่มี $' $& $` จะถูกตีความเป็นรูปแบบพิเศษของ replace */
function fmt(s, v) { return String(s).replace('%s', function () { return v; }); }

/* ---------------------------------------------------------------- helpers */
/* สร้าง DOM ด้วย textContent เสมอ — ชื่อแชต/โปรเจกต์/ไฟล์ เป็นข้อความจากผู้ใช้ ห้ามผ่าน innerHTML */
function el(tag, attrs, kids) {
  var n = document.createElement(tag);
  if (attrs) Object.keys(attrs).forEach(function (k) {
    var v = attrs[k];
    if (v == null || v === false) return;
    if (k === 'class') n.className = v;
    else if (k === 'text') n.textContent = v;
    else if (k.slice(0, 2) === 'on' && typeof v === 'function') n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  });
  (kids || []).forEach(function (c) { if (c != null) n.append(c); });
  return n;
}
function icon(name, cls) {
  var NS = 'http://www.w3.org/2000/svg';
  var s = document.createElementNS(NS, 'svg');
  s.setAttribute('class', 'ic' + (cls ? ' ' + cls : ''));
  s.setAttribute('aria-hidden', 'true');
  var u = document.createElementNS(NS, 'use');
  u.setAttribute('href', '#i-' + name);
  s.append(u);
  return s;
}
var toastEl = $('#toast'), toastTimer = 0, srPolite = $('#srPolite'), srAlert = $('#srAlert');
function toast(msg, bad) {
  msg = String(msg == null ? '' : msg);
  /* หน้าต่างเลือก GPU เปิดอยู่: toast ลอยกลางล่างจอทับแถวปุ่มของหน้าต่าง (ปุ่ม "ยกเลิก") อยู่หลายวินาที
     จึงแสดงในกล่องสถานะของหน้าต่างแทน — ข้อความเดียวกัน โปรแกรมอ่านหน้าจออ่านแบบเดียวกัน (gdFlash → announce) */
  if (typeof GD !== 'undefined' && GD && gpuOpen()) { gdFlash(msg, bad); return; }
  toastEl.textContent = msg;
  toastEl.classList.toggle('bad', !!bad);
  toastEl.classList.add('on');
  /* ล้างก่อนแล้วค่อยใส่ในเฟรมถัดไป — ข้อความเดิมซ้ำ โปรแกรมอ่านหน้าจอจะไม่อ่านอีกรอบถ้าไม่ล้าง */
  var live = bad ? srAlert : srPolite;
  live.textContent = '';
  setTimeout(function () { live.textContent = msg; }, 50);
  clearTimeout(toastTimer);
  /* ข้อความยาวอ่านนานกว่า — ให้เวลาตามความยาว (สูงสุด 9 วินาที) */
  toastTimer = setTimeout(function () { toastEl.classList.remove('on'); }, Math.min(9000, (bad ? 6000 : 3200) + msg.length * 25));
}
function api(url, opts) {
  var o = Object.assign({}, opts || {});
  if (o.json !== undefined) {
    o.body = JSON.stringify(o.json);
    o.headers = Object.assign({ 'Content-Type': 'application/json' }, o.headers || {});
    delete o.json;
  }
  return fetch(url, o).then(function (r) {
    return r.json().catch(function () { return null; }).then(function (d) {
      /* er.body = คำตอบทั้งก้อน — API ความจำ/การตั้งค่าของ hub ส่ง error_th/error_en ที่แปลไว้แล้วมาด้วย (ดู srvMsg) */
      if (!r.ok) { var er = new Error((d && d.error) || ('HTTP ' + r.status)); er.status = r.status; er.body = d; throw er; }
      return d;
    });
  }, function (e) {
    /* fetch ล้มเอง = ต่อไม่ติด (hub/proxy ไม่ตอบ) — ติดป้ายไว้ให้ errMsg แยกจากข้อผิดพลาดที่เซิร์ฟเวอร์ตอบกลับมา */
    var er = new Error((e && e.message) || 'network'); er.net = true; throw er;
  });
}
/* ข้อความผิดพลาดที่ hub แปลไว้ให้แล้ว (error_th / error_en) ตามภาษาของหน้า — ไม่มีก็ '' (ใช้ errText แทน)
   เป็นข้อความของเราเอง (ไม่ใช่ข้อความจากโมเดล) และถูกใส่ด้วย textContent เสมอ */
function srvMsg(e) {
  var b = e && e.body, s = b && (LANG === 'th' ? b.error_th : b.error_en);
  return typeof s === 'string' && s.trim() ? s.trim().slice(0, 300) : '';
}
/* ข้อความดิบ ('Failed to fetch', 'HTTP 500', ข้อความอังกฤษจากเซิร์ฟเวอร์, DOMException ของ IndexedDB) ไม่ขึ้นใน toast
   ผู้ใช้อ่านไม่รู้เรื่องและปนภาษา — ต่อไม่ติด = hubdown, สถานะที่รู้ความหมาย (byStatus เช่น 409 ชื่อซ้ำ) = ข้อความที่แปลแล้ว,
   ที่เหลือ = err_retry  ตัวจริงพิมพ์ลง console ไว้ไล่ปัญหา (toast กดไม่ได้ ใส่ title ไปก็ไม่มีใครเห็น) */
function errText(e, byStatus) {
  try { console.warn('[qwen]', e); } catch (x) {}
  return t(e && e.net ? 'hubdown' : (byStatus && e && byStatus[e.status]) || 'err_retry');
}
function failToast(prefix, e, byStatus) { toast(prefix + ': ' + errText(e, byStatus), true); }
function patchProject(slug, data) {
  return api(HUB + '/api/projects/' + encodeURIComponent(slug), { method: 'PATCH', json: data });
}
function fmtSize(n) {
  var u = ['B', 'KB', 'MB', 'GB'], i = 0;
  n = +n || 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(1) : n) + ' ' + u[i];
}
function copyText(s) {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(s);
  return new Promise(function (ok, no) {
    var ta = el('textarea', { style: 'position:fixed;opacity:0' });
    ta.value = s; body.append(ta); ta.select();
    try { document.execCommand('copy') ? ok() : no(new Error('copy')); } catch (e) { no(e); }
    ta.remove();
  });
}

/* ---------------------------------------------------------------- iframe / qwenEnhance */
/* enhance.js ถูกโหลดแบบ defer จึงมี qwenEnhance หลัง load ไม่กี่ร้อยมิลลิวินาที
   ทุกคำสั่งต้องทำงานได้แม้ยังไม่มี (ถอยไปเปลี่ยน hash ของ iframe ตรงๆ) */
function enh() {
  try { var w = frame.contentWindow; return (w && w.qwenEnhance) || null; } catch (e) { return null; }
}
/* คืน {ok, value} — ok = เรียกได้โดยไม่ throw, value = ค่าที่ฟังก์ชันคืน
   (openSettings คืน false เมื่อหาปุ่มไม่เจอ, openMcp คืน Promise<boolean>) ต้องดูทั้งสองอย่าง */
function callEnhR(name) {
  var e = enh(), args = [].slice.call(arguments, 1);
  if (e && typeof e[name] === 'function') {
    try { return { ok: true, value: e[name].apply(e, args) }; } catch (err) { /* ตกไปใช้ทางสำรอง */ }
  }
  return { ok: false, value: undefined };
}
function callEnh() { return callEnhR.apply(null, arguments).ok; }
function frameHash() { try { return frame.contentWindow.location.hash || ''; } catch (e) { return ''; } }
function routeFromHash(h) {
  h = String(h || '').replace(/^#/, '');
  var m = h.match(/^\/chat\/([^/?#]+)/) || h.match(/^chat=([^&]+)/);
  if (m) return { name: 'chat', id: decodeURIComponent(m[1]) };
  if (h === '' || h === '/') return { name: 'start', id: null };
  return { name: 'other', id: null };
}
function streaming() {
  var e = enh();
  try { return !!(e && e.isStreaming && e.isStreaming()); } catch (err) { return false; }
}
/* มีข้อความที่พิมพ์ค้างอยู่ในช่องพิมพ์หรือไม่ — รีโหลดตอนนี้จะทำให้ข้อความนั้นหาย */
function hasDraft() {
  try {
    var ta = frame.contentDocument.querySelector('form textarea');
    return !!(ta && ta.value.trim());
  } catch (e) { return false; }
}
function currentHash() {
  if (ROUTE.name === 'chat' && ROUTE.id) return '#/chat/' + encodeURIComponent(ROUTE.id);
  if (ROUTE.name === 'start') return '#/';
  return frameHash() || '#/';
}
/* โหลด iframe ใหม่ผ่าน URL ที่มี ?model= เสมอ — WebUI ไม่จำโมเดลข้ามการโหลด
   ถ้าใช้ location.reload() เฉยๆ จะได้โมเดลตัวแรกตามตัวอักษรแทนตัวที่โปรเจกต์เลือก
   ใช้ location.replace ครั้งเดียวเสมอ: การตั้ง hash จากภายนอกทำให้ router ของ WebUI รีโหลดเองอีกรอบ
   ถ้า URL ต่างกันแค่ hash เบราว์เซอร์จะไม่โหลดใหม่ จึงเติมพารามิเตอร์ _r ให้เป็น URL ใหม่ */
var framePending = false;   // true ตั้งแต่สั่งโหลดจนกว่า qwenEnhance จะพร้อม (หรือหมดเวลารอ)
var uiStale = false;        // โมเดลเริ่มต้นเปลี่ยนหลัง iframe โหลดแล้ว — แชตใหม่ครั้งหน้าต้องโหลดด้วย URL ใหม่
function reloadFrame(hash) {
  hash = hash || '';
  clearInterval(pendingReload); pendingReload = 0;   // โหลดตรงนี้แล้ว ไม่ต้องให้ตัวที่เลื่อนไว้โหลดซ้ำ
  uiStale = false;
  framePending = true;
  var want = new URL(uiSrc() + hash, location.href);
  try {
    var w = frame.contentWindow;
    if (w.location.pathname + w.location.search === want.pathname + want.search) want.searchParams.set('_r', String(Date.now()));
    w.location.replace(want.href);
  } catch (e) { frame.src = want.href; }
}
/* ระหว่างโมเดลกำลังตอบหรือมีข้อความค้างในช่องพิมพ์ ห้ามรีโหลด — เลื่อนไปจนกว่าจะว่าง */
var pendingReload = 0;
function reloadFrameSoon() {
  if (!streaming() && !hasDraft()) { reloadFrame(currentHash()); return; }
  if (pendingReload) return;
  toast(t('reload_deferred'));
  pendingReload = setInterval(function () {
    if (document.hidden || streaming() || hasDraft()) return;
    clearInterval(pendingReload); pendingReload = 0;
    reloadFrame(currentHash());
  }, 1500);
}
function routeHash(r) {
  return r && r.name === 'chat' && r.id ? '#/chat/' + encodeURIComponent(r.id) : '#/';
}
/* สั่งนำทางใน iframe — ถ้า qwenEnhance ยังไม่พร้อม (กำลังโหลด) จำไว้ก่อน แล้วให้ตัวรอโหลดทำให้
   ถ้าตั้ง hash ใส่เอกสารที่กำลังโหลด router ยังไม่เริ่มก็ไม่รับรู้ ปลายทางหายเงียบ */
var wantRoute = null;
function frameGo(r) {
  var res = r.name === 'chat' ? callEnhR('openChat', r.id) : callEnhR('newChat');
  if (res.ok) { wantRoute = null; return; }
  var loading = framePending;
  try { loading = loading || frame.contentDocument.readyState !== 'complete'; } catch (e) {}
  if (loading) { wantRoute = r; return; }
  /* โหลดเสร็จแล้วแต่ไม่มี qwenEnhance (สคริปต์เสริมพัง) — โหลดใหม่ตรงไปยังปลายทาง */
  reloadFrame(routeHash(r));
}
function hookFrame() {
  var w, d;
  try { w = frame.contentWindow; d = frame.contentDocument; } catch (e) { return; }
  if (!w || !d || w.__qwShellHooked) return;
  w.__qwShellHooked = true;
  /* คลิกในหน้าแชตไม่ bubble มาถึงเอกสารนี้ ต้องฟังในนั้นเพื่อปิดเมนู/แถบข้างที่ลอยค้าง */
  d.addEventListener('pointerdown', function () { closeMenu(); unpeek(); hideTip(); }, true);
  w.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.code === 'KeyK' || e.key === 'k' || e.key === 'K')) {
      e.preventDefault(); e.stopPropagation(); focusSearch();
    } else if (isLangKey(e)) {
      /* Alt+Shift+L จากช่องพิมพ์ในหน้าแชต — ปุ่มกดไม่ bubble ข้าม iframe ต้องดักในเอกสารนั้นเอง */
      e.preventDefault(); e.stopPropagation(); langHotkey(e, true);
    } else if (e.key === 'Escape' && !menu.hidden) {
      closeMenu();
    }
  }, true);
  w.addEventListener('hashchange', function () { if (!enh()) setRoute(routeFromHash(w.location.hash)); });
  /* dialog ของ WebUI ถูก portal ไปเป็นลูกตรงของ <body> ดูแค่ลูกชั้นแรกพอ
     (ไม่ดูทั้ง subtree เพราะระหว่างสตรีมคำตอบ DOM เปลี่ยนถี่มาก) */
  var syncModal = function () {
    body.classList.toggle('frame-modal', !!d.querySelector('body > [data-slot$="overlay"][data-state="open"]'));
  };
  try { new w.MutationObserver(syncModal).observe(d.body, { childList: true }); } catch (e) {}
  syncModal();
}
/* คลิกม่านฝั่ง shell = ปิด dialog ใน iframe (ส่ง Escape ให้ เหมือนผู้ใช้กดเอง) */
function closeFrameModal(e) {
  if (!body.classList.contains('frame-modal') || (e.target !== sb && e.target !== $('#hdr') && e.target !== $('#art'))) return;
  e.preventDefault(); e.stopPropagation();
  try {
    var d = frame.contentDocument, W = frame.contentWindow;
    (d.activeElement || d.body).dispatchEvent(new W.KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }));
  } catch (err) {}
}
var loadPoll = 0;
frame.addEventListener('load', function () {
  body.classList.remove('frame-modal');
  hookFrame();
  if (!enh() && !wantRoute) setRoute(routeFromHash(frameHash()));
  var n = 0;
  framePending = true;
  clearInterval(loadPoll);
  loadPoll = setInterval(function () {
    var e = enh();
    if (!e && ++n <= 60) return;
    clearInterval(loadPoll);
    framePending = false;
    var want = wantRoute; wantRoute = null;
    if (e && want) {
      /* ผู้ใช้กดไปแชตอื่นระหว่างหน้าแชตกำลังโหลด — ทำตามที่ขอไว้ แล้วเชื่อปลายทาง ไม่ใช่เส้นทางเดิมที่ยังไม่ทันเปลี่ยน */
      var cur = null;
      try { cur = e.route(); } catch (err) {}
      var same = cur && cur.name === want.name && (want.name !== 'chat' || cur.id === want.id);
      if (!same) { try { want.name === 'chat' ? e.openChat(want.id) : e.newChat(); } catch (err) {} }
      setRoute(want);
    } else if (e && e.route) {
      try { var r = e.route(); if (r) setRoute(r); } catch (err) {}
    } else if (want) {
      reloadFrame(routeHash(want));   // รอครบ 6 วินาทีแล้วยังไม่มี qwenEnhance
    }
    /* หลังสลับภาษา: เติมข้อความที่พิมพ์ค้างคืน + คืนโฟกัส (ครั้งเดียว ตอน iframe โหลดครั้งแรก) */
    if (e && carryLeft) applyCarry(e);
  }, 100);
});

/* ---------------------------------------------------------------- route + header */
var ROUTE = { name: 'start', id: null };
function setRoute(r) {
  r = { name: (r && r.name) || 'other', id: (r && r.id) || null };
  var changed = r.name !== ROUTE.name || r.id !== ROUTE.id, prev = ROUTE;
  ROUTE = r;
  if (!changed) return;
  /* ย้ายออกจากแชตหนึ่ง (ไปแชตอื่น/แชตใหม่) = ชิ้นงานในแผงแสดงผลเป็นของแชตเดิม — ปิดแผง
     (จากหน้าเริ่มไปแชตใหม่ตอนส่งข้อความแรก ไม่ปิด: แผงที่เปิดจาก "ไฟล์ที่ Qwen สร้าง" ยังใช้อยู่) */
  if (prev.name === 'chat' && typeof ART !== 'undefined' && artOpen()) closeArt(true);
  /* ให้ URL ของ shell ตามแชตที่เปิด — กด F5 หรือคัดลอกลิงก์แล้วกลับมาแชตเดิม */
  try {
    var h = r.name === 'chat' ? '#/chat/' + encodeURIComponent(r.id) : '';
    if (location.hash !== h) history.replaceState(null, '', location.pathname + location.search + h);
  } catch (e) {}
  /* WebUI เขียนรายการแท็บทั้งก้อน (จากหน่วยความจำ) หลังเปิดแชต — ตัดทีหลังการเขียนนั้น ไม่ใช่ก่อน */
  if (r.name === 'chat') setTimeout(function () { if (ROUTE.name === 'chat') pruneTabs(ROUTE.id); }, 1200);
  paintHeader();
  lastRecSig = '';
  renderRecents();
  refreshRecents();
  /* แชตที่เพิ่งสร้างจากข้อความแรก: WebUI เปิดแชต (เราอ่านได้ชื่อชั่วคราว) แล้วตั้งชื่อจริงตามมาในเสี้ยววินาที
     อ่านซ้ำอีกรอบเร็วๆ ไม่ต้องรอรอบ 3 วินาที */
  if (r.name === 'chat') setTimeout(function () { if (ROUTE.id === r.id) refreshRecents(); }, 700);
}
/* แถบแท็บของ WebUI ถูกซ่อนเมื่ออยู่ใน shell ผู้ใช้จึงปิดแท็บเองไม่ได้ — รายการใน localStorage
   โตขึ้นทีละแชตที่เปิดไม่มีวันลด ตัดให้เหลือแชตปัจจุบัน (ข้ามถ้ากำลังตอบ เผื่อแท็บอื่นยังสตรีมอยู่) */
function pruneTabs(id) {
  if (streaming()) return;
  try {
    var k = 'LlamaUi.conversationTabs', arr = JSON.parse(localStorage.getItem(k) || '[]');
    if (!Array.isArray(arr) || arr.length <= 1) return;
    var keep = arr.filter(function (x) { return (x && typeof x === 'object' ? x.id : x) === id; });
    localStorage.setItem(k, JSON.stringify(keep));
  } catch (e) {}
}
function convById(id) {
  for (var i = 0; i < CONVS.length; i++) if (CONVS[i].id === id) return CONVS[i];
  return null;
}
/* แชตที่ WebUI สร้างก่อนมีข้อความ ได้ชื่อชั่วคราว `Chat ${new Date().toLocaleString()}` — อังกฤษ + รูปแบบวันที่ของเบราว์เซอร์
   ("Chat 9/29/2026, 12:52:23 PM", "Chat 29/9/2569 12:52:23", "Chat 2026. 9. 29. 오후 1:05:09") แล้วค่อยเปลี่ยนเป็น
   บรรทัดแรกของข้อความ  บางทางไม่เปลี่ยนเลย: ข้อความแรกมีแต่ไฟล์ หรือเริ่มแชตด้วยข้อความระบบ
   แสดงเป็น "แชตใหม่ · 12:52" แทน — เฉพาะตอนแสดงผล ไม่เขียนกลับ IndexedDB (WebUI เปลี่ยนชื่อเองเมื่อมีข้อความ)
   ตัวบอกเช้า/บ่าย: AM/PM (a.m., p. m.) หรือคำที่ไม่ใช่อักษรละติน (오후, 午後, 下午) ก่อนหรือหลังเวลา */
var DEF_NAME = /^Chat \d{1,4}[\/.\-]\s?\d{1,2}[\/.\-]\s?\d{1,4}\.?,?\s(?:([^\x00-\x7f]{1,4})\s?)?(\d{1,2}):(\d{2}):\d{2}(?:\s?([AaPp]\.?\s?[Mm]\.?|[^\x00-\x7f]{1,4}))?$/;
function convTitle(c) {
  var nm = (c && c.name) || '', m = DEF_NAME.exec(nm);
  if (!m) return nm || tRaw('untitled');
  var h = +m[2], mk = m[1] || m[4] || '';
  if ((/^[Pp]/.test(mk) || /^(오후|午後|下午)$/.test(mk)) && h < 12) h += 12;
  else if ((/^[Aa]/.test(mk) || /^(오전|午前|上午)$/.test(mk)) && h === 12) h = 0;
  var tm;
  try { tm = new Date(2000, 0, 1, h, +m[3]).toLocaleTimeString(LANG, { hour: 'numeric', minute: '2-digit' }); }
  catch (e) { tm = h + ':' + m[3]; }
  return tRaw('newchat') + ' · ' + tm;
}
/* หน้าเริ่มแชตมีป้ายโปรเจกต์ใต้คำทักทายอยู่แล้ว — ไม่ต้องซ้ำที่ส่วนหัว (ถ้า hero ไม่ถูกแทรกก็ยังแสดง) */
function heroShown() {
  try { return frame.contentDocument.documentElement.getAttribute('data-qw-hero') === '1'; } catch (e) { return false; }
}
function paintHeader() {
  var tb = $('#titleBtn'), ts = $('#titleStatic'), title = '';
  var hadFocus = document.activeElement === tb || document.activeElement === ts;
  if (ROUTE.name === 'chat') {
    var c = convById(ROUTE.id);
    title = c ? convTitle(c) : '';
    setText($('#titleTxt'), title);
    setHidden(tb, !title); setHidden(ts, !!title);
    if (!title) setText($('#titleProj'), PROJ.name || '');
  } else {
    var label = /search/.test(frameHash()) ? t('searchchats') : '';
    setHidden(tb, true);
    setHidden(ts, ROUTE.name === 'start' && !label && heroShown());
    setText($('#titleProj'), label || PROJ.name || '');
  }
  /* ปุ่มที่โฟกัสอยู่ถูกซ่อน (เช่นลบแชตที่เปิดจากเมนูหัวเรื่อง) — ย้ายโฟกัสไปปุ่มที่ยังเห็น ไม่ให้หล่นไป <body> */
  if (hadFocus && !shown(document.activeElement)) {
    var fb = [tb, ts, $('#hdrNew'), $('#newChatBtn')].filter(shown)[0];
    if (fb) fb.focus();
  }
  var dt = (title ? title + ' · ' : '') + (PROJ.name ? PROJ.name + ' - ' : '') + 'Qwen3.8';
  /* ชื่อแท็บจริงมี "(n) " นำหน้าเมื่อมีแจ้งเตือนค้างตอนแท็บถูกซ่อน (K5) — paintDocTitle อยู่ในส่วนแจ้งเตือน */
  baseTitle = dt;
  paintDocTitle();
}
var baseTitle = document.title;

/* ---------------------------------------------------------------- IndexedDB (ของ WebUI) */
/* อ่าน/เขียนฐานข้อมูลของ WebUI ตรงๆ ได้เพราะ origin เดียวกัน
   ห้ามสร้างฐานข้อมูลเองถ้ายังไม่มี — Dexie จะสร้าง schema ไม่ได้ ถ้าเจอฐานว่างเปล่ารอไว้ก่อน */
function idbOpen() {
  return new Promise(function (ok, no) {
    var req;
    try { req = indexedDB.open('LlamaUi'); } catch (e) { no(e); return; }
    req.onupgradeneeded = function () { try { req.transaction.abort(); } catch (e) {} };
    req.onsuccess = function () {
      var db = req.result;
      db.onversionchange = function () { db.close(); };   // อย่าขวาง WebUI อัปเกรด schema
      ok(db);
    };
    req.onerror = function () { no(req.error || new Error('idb')); };
    req.onblocked = function () { no(new Error('blocked')); };
  });
}
function withDB(fn) {
  return idbOpen().then(function (db) {
    return Promise.resolve().then(function () { return fn(db); })
      .then(function (v) { db.close(); return v; }, function (e) { db.close(); throw e; });
  });
}
function reqP(r) { return new Promise(function (ok, no) { r.onsuccess = function () { ok(r.result); }; r.onerror = function () { no(r.error); }; }); }
function txDone(tx) {
  return new Promise(function (ok, no) {
    tx.oncomplete = function () { ok(); };
    tx.onerror = function () { no(tx.error); };
    tx.onabort = function () { no(tx.error || new Error('abort')); };
  });
}
function listConvs() {
  return withDB(function (db) {
    if (!db.objectStoreNames.contains('conversations')) return [];
    return reqP(db.transaction('conversations').objectStore('conversations').getAll());
  }).then(function (all) {
    return (all || []).filter(function (c) { return c && c.id; })
      .sort(function (a, b) { return (b.lastModified || 0) - (a.lastModified || 0); });
  }).catch(function () { return null; });   // null = อ่านไม่ได้ครั้งนี้ (ถูกบล็อก/กำลังอัปเกรด) ≠ ไม่มีแชต
}
function renameConv(id, name) {
  return withDB(function (db) {
    var tx = db.transaction('conversations', 'readwrite'), st = tx.objectStore('conversations');
    var done = txDone(tx);
    return reqP(st.get(id)).then(function (c) {
      if (!c) throw new Error('not found');
      c.name = name;
      st.put(c);
      return done;
    });
  });
}
function deleteConv(id) {
  return withDB(function (db) {
    var names = ['conversations', 'messages'].filter(function (s) { return db.objectStoreNames.contains(s); });
    var tx = db.transaction(names, 'readwrite'), done = txDone(tx);
    tx.objectStore('conversations').delete(id);
    if (names.indexOf('messages') < 0) return done;
    var ms = tx.objectStore('messages');
    if (ms.indexNames.contains('convId')) {
      return reqP(ms.index('convId').getAllKeys(IDBKeyRange.only(id))).then(function (keys) {
        keys.forEach(function (k) { ms.delete(k); });
        return done;
      });
    }
    return new Promise(function (ok, no) {
      var cur = ms.openCursor();
      cur.onsuccess = function () {
        var c = cur.result;
        if (!c) { ok(); return; }
        if (c.value && c.value.convId === id) c.delete();
        c.continue();
      };
      cur.onerror = function () { no(cur.error); };
    }).then(function () { return done; });
  }).then(function () {
    /* แถบแท็บของ WebUI จำ id ไว้ใน localStorage ต้องลบออกด้วย ไม่งั้นมันพยายามเปิดแชตที่ไม่มีแล้ว */
    try {
      var k = 'LlamaUi.conversationTabs', arr = JSON.parse(localStorage.getItem(k) || '[]');
      if (Array.isArray(arr)) {
        localStorage.setItem(k, JSON.stringify(arr.filter(function (x) { return (x && typeof x === 'object' ? x.id : x) !== id; })));
      }
    } catch (e) {}
  });
}
function snippet(text, i, len) {
  var a = Math.max(0, i - 28), b = Math.min(text.length, i + len + 70);
  return { pre: (a ? '…' : '') + text.slice(a, i), hit: text.slice(i, i + len), post: text.slice(i + len, b) + (b < text.length ? '…' : '') };
}
/* ค้นในเนื้อความ — ข้ามข้อความระบบ เพราะคำสั่งของโปรเจกต์อยู่ในทุกแชต จะทำให้ทุกแชตติดผลค้นหา */
function searchContent(q) {
  return withDB(function (db) {
    var out = new Map();
    if (!db.objectStoreNames.contains('messages')) return out;
    var st = db.transaction('messages').objectStore('messages');
    return new Promise(function (ok, no) {
      var cur = st.openCursor();
      cur.onsuccess = function () {
        var c = cur.result;
        if (!c) { ok(out); return; }
        var m = c.value;
        if (m && typeof m.content === 'string' && m.role !== 'system' && m.type !== 'root' && m.type !== 'system' && !out.has(m.convId)) {
          var flat = m.content.replace(/\s+/g, ' ');
          var i = flat.toLocaleLowerCase().indexOf(q);
          if (i >= 0) out.set(m.convId, snippet(flat, i, q.length));
        }
        c.continue();
      };
      cur.onerror = function () { no(cur.error); };
    });
  }).catch(function () { return new Map(); });
}

/* ---------------------------------------------------------------- Recents + ค้นหา */
var CONVS = [], QUERY = '', CONTENT_HITS = null, lastRecSig = '', recBusy = false;
var recList = $('#recList');
function refreshRecents() {
  if (recBusy) return Promise.resolve();
  recBusy = true;
  return listConvs().then(function (list) {
    if (list) CONVS = list;   // อ่านพลาดชั่วคราว: คงรายการเดิมไว้ ไม่ขึ้น "ยังไม่มีแชต" หลอก
  }).finally(function () {
    recBusy = false;
    renderRecents();
    paintHeader();
  });
}
function hlText(parent, text, q) {
  var i = q ? text.toLocaleLowerCase().indexOf(q) : -1;
  if (i < 0) { parent.append(text); return; }
  parent.append(text.slice(0, i), el('mark', { text: text.slice(i, i + q.length) }), text.slice(i + q.length));
}
function recentRow(c, snip) {
  var name = convTitle(c);
  var active = ROUTE.name === 'chat' && ROUTE.id === c.id;
  var a = el('a', {
    class: 'item rec' + (active ? ' on' : '') + (snip ? ' snip' : ''),
    href: '#/chat/' + encodeURIComponent(c.id), title: name, 'data-id': c.id, tabindex: '-1',
    'aria-current': active ? 'page' : null, 'aria-describedby': 'rowKeysHint'
  });
  var lbl = el('span', { class: 'lbl' });
  hlText(lbl, name, QUERY);
  a.append(lbl);
  if (snip) {
    a.append(el('span', { class: 'snip-t' }, [snip.pre, el('mark', { text: snip.hit }), snip.post]));
  }
  var more = el('button', {
    type: 'button', class: 'more', 'aria-label': t('chat_options') + ': ' + name, 'data-tip': t('chat_options'),
    'aria-haspopup': 'menu', 'aria-expanded': 'false', 'data-id': c.id, tabindex: '-1'
  }, [icon('more')]);
  return el('div', { class: 'row', role: 'listitem', 'data-key': c.id }, [a, more]);
}
/* ---- รายการในแถบข้าง: จุดหยุด Tab เดียวต่อรายการ (roving tabindex) ----
   แชตมีได้หลายร้อยแถว ถ้าทุกลิงก์และทุก ⋯ อยู่ในลำดับ Tab ต้องกดหลายร้อยครั้งกว่าจะถึงช่องพิมพ์
   ลูกศรขึ้นลงเลื่อนแถว · → / Shift+F10 / ปุ่ม Menu เปิดตัวเลือกของแถว */
function rowsOf(list) { return [].slice.call(list.querySelectorAll('.row')); }
function setRoving(list, link) {
  var links = [].slice.call(list.querySelectorAll('a.item'));
  if (!links.length) return;
  if (!link || links.indexOf(link) < 0) link = list.querySelector('a.item.on') || links[0];
  links.forEach(function (x) { setAttr(x, 'tabindex', x === link ? '0' : '-1'); });
}
/* จำว่าโฟกัสอยู่แถวไหนก่อนวาดรายการใหม่ แล้วคืนให้แถวเดิม (หรือแถวที่มาแทนที่ถ้าแถวนั้นถูกลบ)
   ไม่งั้นเปลี่ยนชื่อ/ลบแชตแล้วโฟกัสหล่นไป <body> ผู้ใช้คีย์บอร์ดต้องเริ่มจากต้นหน้า */
function focusMemo(list) {
  var a = document.activeElement;
  if (!a || !list.contains(a)) return null;
  var row = a.closest('.row');
  return { key: row && row.getAttribute('data-key'), more: a.classList.contains('more'), idx: rowsOf(list).indexOf(row) };
}
function focusRestore(list, m) {
  if (!m) return;
  var rows = rowsOf(list), row = null;
  rows.forEach(function (r) { if (!row && r.getAttribute('data-key') === m.key) row = r; });
  var same = !!row;
  if (!row && rows.length) row = rows[Math.min(Math.max(m.idx, 0), rows.length - 1)];
  if (!row) { var fb = [searchBtn, $('#newChatBtn'), $('#hdrNew')].filter(shown)[0]; if (fb) fb.focus(); return; }
  var link = row.querySelector('a.item');
  setRoving(list, link);
  ((same && m.more && row.querySelector('.more')) || link).focus({ preventScroll: true });
}
function rowKeys(list, e, openRowMenu) {
  var link = e.target.closest && e.target.closest('a.item');
  if (!link || !list.contains(link)) return;
  var links = [].slice.call(list.querySelectorAll('a.item')), i = links.indexOf(link), nx = null;
  if (e.key === 'ArrowDown') nx = links[Math.min(links.length - 1, i + 1)];
  else if (e.key === 'ArrowUp') {
    if (i === 0 && list === recList && !searchWrap.hidden) { e.preventDefault(); qIn.focus(); return; }
    nx = links[Math.max(0, i - 1)];
  }
  else if (e.key === 'Home') nx = links[0];
  else if (e.key === 'End') nx = links[links.length - 1];
  else if (e.key === 'ArrowRight' || e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey)) {
    var more = link.parentNode.querySelector('.more');
    if (more) { e.preventDefault(); openRowMenu(more, link); }
    return;
  } else return;
  e.preventDefault();
  if (nx) { setRoving(list, nx); nx.focus(); }
}
function renderRecents() {
  var searching = body.classList.contains('searching') && QUERY;
  var rows = [];
  if (searching) {
    CONVS.forEach(function (c) {
      /* ค้นทั้งชื่อที่เก็บไว้และชื่อที่แสดง ("แชตใหม่ · 12:52" ของแชตที่ยังไม่มีชื่อ) — พิมพ์ตามที่เห็นแล้วต้องเจอ */
      var hay = (c.name || '') + '\n' + convTitle(c);
      if (hay.toLocaleLowerCase().indexOf(QUERY) >= 0) rows.push({ c: c });
    });
    if (CONTENT_HITS) {
      CONVS.forEach(function (c) {
        if (CONTENT_HITS.has(c.id) && !rows.some(function (r) { return r.c === c; })) rows.push({ c: c, snip: CONTENT_HITS.get(c.id) });
      });
    }
    rows = rows.slice(0, 50);
  } else {
    rows = CONVS.slice(0, 300).map(function (c) { return { c: c }; });
  }
  var sig = JSON.stringify([searching ? QUERY : '', !!CONTENT_HITS, ROUTE.id, rows.map(function (r) { return [r.c.id, r.c.name, !!r.snip]; })]);
  if (sig === lastRecSig) return;
  lastRecSig = sig;
  setText($('#recH'), searching ? t('results') : t('recents'));
  var memo = focusMemo(recList);
  if (!rows.length) {
    recList.replaceChildren(el('div', { class: 'empty', text: searching ? (CONTENT_HITS ? t('noresults') : t('searching')) : t('norecents') }));
    focusRestore(recList, memo);
    return;
  }
  recList.replaceChildren.apply(recList, rows.map(function (r) { return recentRow(r.c, r.snip); }));
  setRoving(recList, null);
  focusRestore(recList, memo);
}
recList.addEventListener('click', function (e) {
  var more = e.target.closest('.more');
  if (more) { e.preventDefault(); chatMenu(more, more.getAttribute('data-id')); return; }
  var a = e.target.closest('a.rec');
  if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;   // เปิดแท็บใหม่ได้ตามปกติ
  e.preventDefault();
  openChat(a.getAttribute('data-id'));
});

var searchBtn = $('#searchBtn'), searchWrap = $('#searchWrap'), qIn = $('#q'), qTimer = 0, qSeq = 0;
function focusSearch() {
  /* กล่องยืนยัน/หน้าต่างเลือก GPU/ปรับให้เป็นของคุณ เปิดอยู่ = ต้องจบก่อน ห้ามย้ายโฟกัสไปหลังม่าน (คำสั่งของกล่องจะค้างไม่มีวันจบ) */
  if (!dlg.wrap.hidden || gpuOpen() || pdOpen()) return;
  if (artModal()) closeArt(true);   // แผงแสดงผลเต็มจอบนจอแคบบังลิ้นชักอยู่
  closeMenu();
  if (panelOpen()) closePanel(true);   // แผงเป็น modal ทับแถบข้างอยู่ — ปิดก่อนค่อยไปช่องค้นหา
  if (isMobile()) openDrawer();
  else peek();
  body.classList.add('searching');
  searchBtn.hidden = true; searchWrap.hidden = false;
  $('#secProjects').hidden = true;
  qIn.focus(); qIn.select();
}
function endSearch() {
  if (!body.classList.contains('searching')) return;
  body.classList.remove('searching');
  qIn.value = ''; QUERY = ''; CONTENT_HITS = null; clearTimeout(qTimer); qSeq++;
  searchWrap.hidden = true; searchBtn.hidden = false;
  $('#secProjects').hidden = false;
  lastRecSig = ''; renderRecents();
  unpeek();
}
qIn.addEventListener('input', function () {
  QUERY = qIn.value.trim().toLocaleLowerCase();
  CONTENT_HITS = null;
  renderRecents();
  clearTimeout(qTimer);
  if (!QUERY) return;
  var mine = ++qSeq, q = QUERY;
  /* ชื่อแชตกรองทันที ส่วนเนื้อความต้องไล่ทุกข้อความ จึงรอให้หยุดพิมพ์ก่อน */
  qTimer = setTimeout(function () {
    searchContent(q).then(function (hits) {
      if (mine !== qSeq) return;
      CONTENT_HITS = hits;
      renderRecents();
    });
  }, 250);
});
qIn.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') {
    e.preventDefault(); e.stopPropagation();
    if (qIn.value) { qIn.value = ''; qIn.dispatchEvent(new Event('input')); }
    else { endSearch(); searchBtn.focus(); }
  } else if (e.key === 'ArrowDown') {
    var first = recList.querySelector('a.rec');
    if (first) { e.preventDefault(); setRoving(recList, first); first.focus(); }
  } else if (e.key === 'Enter' && !e.isComposing) {
    var hit = recList.querySelector('a.rec');
    if (hit) { e.preventDefault(); openChat(hit.getAttribute('data-id')); }
  }
});
qIn.addEventListener('blur', function () {
  setTimeout(function () {
    if (!qIn.value && document.activeElement !== qIn && !sb.contains(document.activeElement)) endSearch();
  }, 150);
});
$('#qClear').addEventListener('click', function () { endSearch(); searchBtn.focus(); });
searchBtn.addEventListener('click', focusSearch);
/* เลื่อนลูกศรขึ้นลงในรายการแชต (ต่อจากช่องค้นหา) และเปิดเมนูของแถวด้วยคีย์บอร์ด */
recList.addEventListener('keydown', function (e) {
  rowKeys(recList, e, function (more, link) { chatMenu(more, more.getAttribute('data-id'), null, link); });
});
recList.addEventListener('focusin', function (e) {
  var a = e.target.closest && e.target.closest('a.item');
  if (a) setRoving(recList, a);   // คลิก/โฟกัสแถวไหน Tab กลับมาก็เจอแถวนั้น
});

/* ---------------------------------------------------------------- คำสั่งนำทาง */
function newChat() {
  closeMenu();
  if (isMobile()) closeDrawer();
  endSearch();
  unpeek();
  var r = { name: 'start', id: null };
  /* โมเดลเริ่มต้นเปลี่ยนไปแล้ว: แชตใหม่ต้องโหลดด้วย ?model= ใหม่ ไม่งั้นช่องพิมพ์ยังเลือกโมเดลเดิม */
  if (uiStale && !streaming() && !hasDraft()) reloadFrame('#/');
  else frameGo(r);
  setRoute(r);
  setTimeout(function () { callEnh('focusComposer'); }, 150);
}
function openChat(id) {
  if (!id) return;
  closeMenu();
  if (isMobile()) closeDrawer();
  unpeek();
  var r = { name: 'chat', id: id };
  frameGo(r);
  setRoute(r);
}
$('#newChatBtn').addEventListener('click', newChat);
sb.addEventListener('click', closeFrameModal, true);
$('#art').addEventListener('click', closeFrameModal, true);
$('#hdr').addEventListener('click', closeFrameModal, true);
$('#hdrNew').addEventListener('click', newChat);

/* ---------------------------------------------------------------- เมนู */
/* menuBack = ที่คืนโฟกัสเมื่อปิดเมนู (ปกติคือปุ่มที่เปิด แต่เปิดจากลิงก์แถวด้วยคีย์บอร์ดให้กลับไปที่ลิงก์)
   lastBack = ค่าเดียวกันที่จำไว้หลังเมนูปิด — กล่องยืนยันที่เปิดจากรายการเมนูใช้เป็นที่คืนโฟกัส
   (ตอนกล่องเปิด ปุ่มในเมนูที่เพิ่งกดถูกซ่อนไปแล้ว activeElement จึงเป็น <body>) */
var menuAnchor = null, menuBack = null, lastBack = null;
function openMenu(anchor, items, place, opts) {
  if (menuAnchor === anchor && !menu.hidden) { closeMenu(); return; }
  closeMenu();
  hideTip();
  opts = opts || {};
  menu.replaceChildren();
  /* ตั้งคลาสก่อนวัดขนาด (placeMenu) — เมนูอื่นที่เปิดทีหลังต้องได้คลาสเดิมกลับมา ไม่ติด wide ค้างไป */
  menu.className = 'menu' + (opts.cls ? ' ' + opts.cls : '');
  menu.setAttribute('aria-label', opts.label || anchor.getAttribute('aria-label') || '');
  setAttr(menu, 'aria-describedby', opts.describedby || null);
  menuBack = opts.back || anchor;
  items.forEach(function (it) {
    if (!it) return;
    if (it === 'sep') { menu.append(el('div', { class: 'menu-sep', role: 'separator' })); return; }
    if (it.node) { menu.append(it.node); return; }
    var b = el('button', { type: 'button', role: 'menuitem', class: 'menu-item' + (it.danger ? ' danger' : '') },
      [it.icon ? icon(it.icon) : null, el('span', { class: 'mi-l', text: it.label }), it.external ? icon('external', 'ic-xs mi-x') : null]);
    b.addEventListener('click', function (e) { e.stopPropagation(); closeMenu(); if (it.run) it.run(); });
    menu.append(b);
  });
  menu.hidden = false;
  menu.classList.toggle('up', place === 'up');
  menuAnchor = anchor;
  if (anchor) {
    anchor.setAttribute('aria-expanded', 'true');
    var rowItem = anchor.closest('.row') && anchor.closest('.row').querySelector('.item');
    if (rowItem) rowItem.classList.add('menu-open');
  }
  placeMenu(anchor, place);
  requestAnimationFrame(function () { menu.classList.add('on'); });
  /* โฟกัสตัวแรกของเมนู — ถ้าเป็นกลุ่มตัวเลือก ให้ไปที่ตัวที่เลือกอยู่ของกลุ่มนั้น */
  var first = menuItems()[0];
  if (first && first.closest('.seg')) first = first.closest('.seg').querySelector('[aria-checked="true"]') || first;
  if (first) first.focus({ preventScroll: true });
}
/* ทุกอย่างที่กดได้ในเมนูตามลำดับบนลงล่าง — รวมปุ่มในหัวเมนูบัญชี (ก้อน GPU, "ใช้ GPU ใหม่") ที่ไม่ใช่ .menu-item */
function menuItems() { return [].slice.call(menu.querySelectorAll('[role="menuitem"], [role="menuitemradio"]')); }
function placeMenu(anchor, place) {
  var r = anchor.getBoundingClientRect(), mw = menu.offsetWidth, mh = menu.offsetHeight, pad = 8, x, y;
  if (place === 'up') { x = r.left; y = r.top - mh - 6; }
  else if (place === 'right') { x = r.right + 8; y = r.bottom - mh; }
  else if (place === 'end') { x = r.right - mw; y = r.bottom + 6; }
  else { x = r.left; y = r.bottom + 6; }
  if (place !== 'up' && y + mh > innerHeight - pad) y = r.top - mh - 6;
  x = Math.min(Math.max(pad, x), innerWidth - mw - pad);
  y = Math.min(Math.max(pad, y), innerHeight - mh - pad);
  menu.style.left = Math.round(x) + 'px';
  menu.style.top = Math.round(y) + 'px';
}
function closeMenu() {
  if (menu.hidden) return;
  menu.hidden = true;
  menu.classList.remove('on');
  document.querySelectorAll('.item.menu-open').forEach(function (n) { n.classList.remove('menu-open'); });
  if (menuAnchor) menuAnchor.setAttribute('aria-expanded', 'false');
  lastBack = menuBack;
  menuAnchor = null; menuBack = null;
}
/* ปิดเมนูแล้วคืนโฟกัส — ตัวที่ใช้จริงคือ lastBack ที่ closeMenu เพิ่งตั้ง */
function closeMenuFocus() {
  closeMenu();
  if (lastBack && shown(lastBack)) lastBack.focus();
}
menu.addEventListener('keydown', function (e) {
  var items = menuItems();
  var i = items.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    var n = items.length; if (!n) return;
    items[(i + (e.key === 'ArrowDown' ? 1 : -1) + n) % n].focus();
  } else if (e.key === 'Home' || e.key === 'End') {
    e.preventDefault();
    if (items.length) items[e.key === 'Home' ? 0 : items.length - 1].focus();
  } else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && document.activeElement.closest('.seg')) {
    /* แถวตัวเลือก (ธีม/ฟอนต์/ภาษา) วางแนวนอน — ซ้ายขวาเลื่อนภายในกลุ่ม Enter/Space เลือก */
    e.preventDefault();
    var sib = [].slice.call(document.activeElement.closest('.seg').querySelectorAll('button'));
    var j = sib.indexOf(document.activeElement);
    sib[(j + (e.key === 'ArrowRight' ? 1 : -1) + sib.length) % sib.length].focus();
  } else if (e.key === 'Escape') {
    e.preventDefault(); e.stopPropagation();
    closeMenuFocus();
  } else if (e.key === 'Tab') {
    /* ไม่ preventDefault: คืนโฟกัสให้ปุ่มที่เปิดเมนูก่อน แล้วให้ Tab ของเบราว์เซอร์เดินต่อจากตรงนั้น
       (ถ้าแค่ปิดเมนู โฟกัสอยู่บนปุ่มที่ถูกซ่อน Tab ถัดไปหลุดออกนอกหน้า) */
    closeMenuFocus();
  }
});
document.addEventListener('pointerdown', function (e) {
  if (menu.hidden) return;
  if (menu.contains(e.target) || (menuAnchor && menuAnchor.contains(e.target))) return;
  closeMenu();
}, true);
/* คลิกเข้าไปใน iframe = หน้านี้เสียโฟกัส */
window.addEventListener('blur', function () {
  hideTip();
  setTimeout(function () { if (document.activeElement === frame) { closeMenu(); unpeek(); } }, 0);
});
window.addEventListener('resize', function () { closeMenu(); hideTip(); });
$('#sbScroll').addEventListener('scroll', function () { closeMenu(); hideTip(); }, { passive: true });

/* แถวตัวเลือกในเมนู: role=menu ใส่ได้แค่ menuitem (และแบบ radio/checkbox), group, separator
   จึงเป็น group ที่มีชื่อ + ปุ่ม menuitemradio (ไม่ใช่ radiogroup/radio ซ้อนใน menu) */
var segN = 0;
function segSet(seg, v) {
  [].forEach.call(seg.children, function (x) {
    var on = x.getAttribute('data-v') === v;
    x.classList.toggle('on', on); x.setAttribute('aria-checked', String(on));
  });
}
/* onPick(ค่า, seg) — ส่ง seg ไปด้วยให้ตัวที่ทำงานแบบรอผล (เช่นสลับภาษา) ย้อนตัวเลือกกลับได้เมื่อไม่สำเร็จ
   ไม่งั้นปุ่มค้างว่าเลือก English ทั้งที่ภาษายังเป็นไทย
   options = [ค่า, ป้าย, ไอคอน?, style?, lang?] — lang ให้เสียงอ่านใช้กฎของภาษานั้น ("English" ในหน้าไทย) */
function segRow(label, ic, options, current, onPick) {
  var lid = 'mrl' + (++segN);
  var seg = el('div', { class: 'seg', role: 'none' });
  options.forEach(function (o) {
    var on = o[0] === current;
    var b = el('button', { type: 'button', role: 'menuitemradio', 'aria-checked': String(on), class: on ? 'on' : null, 'data-v': o[0], lang: o[4] || null },
      [o[2] ? icon(o[2], 'ic-xs') : null, el('span', { text: o[1], style: o[3] || null })]);
    b.addEventListener('click', function (e) {
      e.stopPropagation();
      segSet(seg, o[0]);
      onPick(o[0], seg);
    });
    seg.append(b);
  });
  return el('div', { class: 'menu-row', role: 'group', 'aria-labelledby': lid },
    [el('span', { class: 'mr-l' }, [icon(ic), el('span', { id: lid, text: label })]), seg]);
}

/* ---------------------------------------------------------------- กล่องยืนยัน / ตั้งชื่อ */
var dlg = { wrap: $('#dlg'), title: $('#dlgTitle'), body: $('#dlgBody'), input: $('#dlgIn'), ok: $('#dlgOk'), cancel: $('#dlgCancel') };
var dlgResolve = null, dlgBack = null, dlgBackKey = null;
function openDialog(o) {
  closeMenu();
  hideTip();
  if (dlgResolve) closeDialog(null);
  return new Promise(function (resolve) {
    dlgResolve = resolve;
    dlgBack = document.activeElement;
    /* เปิดจากรายการเมนู: ปุ่มนั้นถูกซ่อนไปแล้ว — คืนโฟกัสให้ปุ่ม ⋯/หัวเรื่องที่เปิดเมนูแทน */
    if (!dlgBack || dlgBack === body || menu.contains(dlgBack) || !shown(dlgBack)) dlgBack = lastBack;
    var backRow = dlgBack && dlgBack.closest ? dlgBack.closest('.row') : null;
    dlgBackKey = backRow ? backRow.getAttribute('data-key') : null;
    /* ช่องตั้งชื่อ = dialog ธรรมดา, คำถามยืนยัน = alertdialog */
    $('#dlgBox').setAttribute('role', o.input != null ? 'dialog' : 'alertdialog');
    dlg.title.textContent = o.title || '';
    dlg.body.textContent = o.body || '';
    dlg.body.hidden = !o.body;
    var asking = o.input != null;
    dlg.input.hidden = !asking;
    dlg.input.value = asking ? o.input : '';
    dlg.ok.textContent = o.okLabel || t('ok');
    /* batch 2a: ปุ่มปฏิเสธตั้งชื่อเองได้ — "ยกเลิกงานค้นคว้า?" ที่มีปุ่ม "ยกเลิก" สองความหมายในกล่องเดียวอ่านแล้วงง */
    dlg.cancel.textContent = o.cancelLabel || t('cancel');
    dlg.ok.className = 'btn ' + (o.danger ? 'btn-danger' : 'btn-ink');
    dlg.wrap.hidden = false;
    requestAnimationFrame(function () {
      dlg.wrap.classList.add('on');
      if (asking) { dlg.input.focus(); dlg.input.select(); }
      else (o.danger ? dlg.cancel : dlg.ok).focus();
    });
  });
}
function closeDialog(val) {
  if (!dlgResolve) return;
  var r = dlgResolve; dlgResolve = null;
  dlg.wrap.classList.remove('on');
  dlg.wrap.hidden = true;
  /* ปุ่มเดิมอาจถูกวาดใหม่ไปแล้ว (รายการรีเฟรชระหว่างกล่องเปิด) — หาแถวเดิมจาก data-key
     ไม่เจอก็ไปปุ่มหัวเรื่อง/แชตใหม่ อย่าปล่อยโฟกัสหล่นไป <body> */
  var back = dlgBack;
  if (!shown(back) && dlgBackKey) {
    [recList, projList].forEach(function (l) {
      var row = !shown(back) && l.querySelector('.row[data-key="' + CSS.escape(dlgBackKey) + '"]');
      if (row) back = row.querySelector('.more') || row.querySelector('a.item');
    });
  }
  if (!shown(back)) back = [$('#titleBtn'), $('#titleStatic'), searchBtn, $('#hdrNew')].filter(shown)[0];
  try { if (back) back.focus(); } catch (e) {}
  dlgBack = null;
  r(val);
}
function dlgNo() { return dlg.input.hidden ? false : null; }
dlg.ok.addEventListener('click', function () { closeDialog(dlg.input.hidden ? true : dlg.input.value); });
dlg.cancel.addEventListener('click', function () { closeDialog(dlgNo()); });
dlg.wrap.addEventListener('mousedown', function (e) { if (e.target === dlg.wrap) closeDialog(dlgNo()); });
dlg.input.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); dlg.ok.click(); }
});
dlg.wrap.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeDialog(dlgNo()); return; }
  if (e.key !== 'Tab') return;
  var f = [dlg.input, dlg.cancel, dlg.ok].filter(function (x) { return !x.hidden; });
  var i = f.indexOf(document.activeElement);
  e.preventDefault();
  f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
});
function confirmBox(title, text, okLabel) { return openDialog({ title: title, body: text, okLabel: okLabel || t('delete_btn'), danger: true }); }
function promptBox(title, value) { return openDialog({ title: title, input: value || '', okLabel: t('save') }); }

/* ---------------------------------------------------------------- เปลี่ยนชื่อ / ลบแชต */
function chatMenu(anchor, id, place, back) {
  var c = convById(id);
  openMenu(anchor, [
    { label: t('rename_chat'), icon: 'pencil', run: function () { renameChat(id); } },
    /* ส่งออก (K10) — อ่านจาก IndexedDB ของ WebUI ตรงๆ ดู exportChat ในส่วน "ส่งออกแชต" */
    'sep',
    { label: t('exp_md'), icon: 'download', run: function () { exportChat(id, 'md'); } },
    { label: t('exp_html'), icon: 'code', run: function () { exportChat(id, 'html'); } },
    { label: t('exp_pdf'), icon: 'print', run: function () { exportChat(id, 'pdf'); } },
    'sep',
    { label: t('delete_chat'), icon: 'trash', danger: true, run: function () { deleteChat(id); } }
  ], place, { back: back, label: t('chat_options') + (c ? ': ' + convTitle(c) : '') });
}
function renameChat(id) {
  var c = convById(id) || {};
  /* เติมชื่อตามที่ผู้ใช้เห็น (ชื่อชั่วคราวของ WebUI แสดงเป็น "แชตใหม่ · 12:52") — กดบันทึกโดยไม่แก้ = ไม่เปลี่ยนอะไร */
  var shownName = c.name ? convTitle(c) : '';
  promptBox(t('rename_chat'), shownName).then(function (v) {
    if (v == null) return;
    var nm = v.trim();
    if (!nm || nm === c.name || nm === shownName) return;
    renameConv(id, nm).then(function () {
      c.name = nm;
      lastRecSig = '';
      return refreshRecents();
    }).then(function () {
      toast(t('chat_renamed'));
      reloadFrameSoon();   // ให้ WebUI ไม่ถือชื่อเก่าค้างไว้ในหน่วยความจำ
    }).catch(function (e) { failToast(t('errrename'), e); });
  });
}
/* batch 2a (fix, owner stack): แชตที่เริ่มจากชิปสกิล (MCP prompt) ได้ชื่อตามสกิล
   WebUI ตั้งชื่อแชตจากเนื้อความของข้อความแรกเท่านั้น — เลือกสกิลจาก "/prompt" แล้วส่งชิปอย่างเดียว เนื้อความว่าง ชื่อจึงค้าง
   เป็นชื่อชั่วคราว (แสดงเป็น "แชตใหม่ · 3:08") ทุกแชตที่เริ่มจากสกิลหน้าตาเหมือนกันหมดใน Recents
   enhance เรียก qwenShellApi.nameSkillChat(id) ตอนเริ่ม/จบการตอบ — การเขียนชื่อแชตอยู่ที่ shell ที่เดียว (เหมือนเปลี่ยนชื่อ/ลบแชต)
   enhance ไม่เขียนฐานข้อมูลของ WebUI ตามสัญญารอบ 4
   ข้อความผู้ใช้แรก (ไม่นับข้อความสังเคราะห์ เช่น cwd) เนื้อความว่าง + มีชิป extra.type="MCP_PROMPT" → ชื่อ = ชื่อสกิลที่ picker
   แสดง (extra.name = title ของ prompts/list ตามภาษาของ hub) · ค่าอาร์กิวเมนต์แรก (เช่นชื่อไฟล์)
   เขียนเฉพาะตอนชื่อยังเป็นชื่อชั่วคราว (DEF_NAME) — ตรวจในทรานแซกชันเดียวกับที่เขียน จึงไม่ทับชื่อที่ผู้ใช้/WebUI ตั้งแล้ว
   WebUI แก้ระเบียนแชตแบบบางฟิลด์ (Dexie update) ชื่อเก่าในหน่วยความจำของมันจึงไม่ถูกเขียนทับกลับ — ไม่ต้องรีโหลด iframe
   ระหว่างที่ผู้ใช้อ่านคำตอบ  ค่าในชิปเป็นข้อความที่ผู้ใช้พิมพ์ → ตัดอักขระควบคุม/สลับทิศทาง/ความกว้างศูนย์ และวาดด้วย textContent */
var SKILL_NAMED = {};   /* convId → 1 = ตัดสินแล้ว (ตั้งชื่อแล้ว หรือไม่ใช่แชตจากสกิล) ไม่ต้องเปิดฐานข้อมูลซ้ำ */
var SKILL_HIDDEN = /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u2069\ufeff]/g;
function skillClean(s, max) {
  s = String(s == null ? '' : s).replace(SKILL_HIDDEN, ' ').replace(/\s+/g, ' ').trim();
  return s.length > max ? s.slice(0, max - 1).trim() + '…' : s;
}
/* {done, name}: done = ตัดสินได้แล้ว (เจอข้อความผู้ใช้แรก), name = ชื่อใหม่ ('' = ไม่ใช่แชตที่เริ่มจากชิปสกิล) */
function skillChatTitle(msgs) {
  var users = (Array.isArray(msgs) ? msgs : []).filter(function (m) {
    return m && m.role === 'user' && m.type !== 'root' && m.type !== 'system' && !m.isSynthetic;
  }).sort(function (a, b) { return (a.timestamp || 0) - (b.timestamp || 0); });
  var first = users[0];
  if (!first) return { done: false, name: '' };
  if (String(first.content || '').trim()) return { done: true, name: '' };   /* มีเนื้อความ = WebUI ตั้งชื่อเอง */
  var ex = Array.isArray(first.extra) ? first.extra : [];
  for (var i = 0; i < ex.length; i++) {
    var x = ex[i];
    if (!x || x.type !== 'MCP_PROMPT') continue;
    var title = skillClean(x.name || x.promptName, 60);
    if (!title) continue;
    var arg = '', a = x.arguments;
    if (a && typeof a === 'object' && !Array.isArray(a)) {
      for (var k in a) {
        if (Object.prototype.hasOwnProperty.call(a, k) && typeof a[k] === 'string' && a[k].trim()) {
          arg = skillClean(a[k], 40);
          break;
        }
      }
    }
    return { done: true, name: arg ? title + ' · ' + arg : title };
  }
  return { done: true, name: '' };
}
/* → Promise<ชื่อใหม่ที่เขียนลงไป | ''> (ไม่เคย reject) */
function nameSkillChat(id) {
  if (!id || typeof id !== 'string' || SKILL_NAMED[id]) return Promise.resolve('');
  return withDB(function (db) {
    if (!db.objectStoreNames.contains('conversations') || !db.objectStoreNames.contains('messages')) return '';
    var tx = db.transaction(['conversations', 'messages'], 'readwrite'), done = txDone(tx);
    var cs = tx.objectStore('conversations'), ms = tx.objectStore('messages');
    function finish(v) { return done.then(function () { return v; }); }
    return reqP(cs.get(id)).then(function (c) {
      if (!c || !DEF_NAME.test(String(c.name || ''))) { SKILL_NAMED[id] = 1; return finish(''); }
      if (!ms.indexNames.contains('convId')) return finish('');
      return reqP(ms.index('convId').getAll(IDBKeyRange.only(id))).then(function (list) {
        var r = skillChatTitle(list);
        if (r.done) SKILL_NAMED[id] = 1;
        if (!r.name) return finish('');
        c.name = r.name;
        cs.put(c);
        return finish(r.name);
      });
    });
  }).then(function (nm) {
    if (nm) {
      var c = convById(id);
      if (c) c.name = nm;
      /* refreshRecents ข้ามรอบที่ชนกับการอ่านที่ค้างอยู่ (recBusy — เช่นรอบ "ตอบจบ" ที่ enhance เพิ่งสั่ง) จึงสั่งซ้ำอีกครั้ง */
      lastRecSig = '';
      refreshRecents();
      setTimeout(function () { lastRecSig = ''; refreshRecents(); }, 1200);
    }
    return nm;
  }).catch(function () { return ''; });
}
function deleteChat(id) {
  var c = convById(id) || {};
  var isOpen = ROUTE.name === 'chat' && ROUTE.id === id;
  confirmBox(t('delchat_title'), fmt(t('delchat_body'), convTitle(c))).then(function (yes) {
    if (!yes) return;
    /* ลบแชตที่กำลังตอบอยู่ = WebUI จะเขียนข้อความลงแชตที่ไม่มีแล้ว ให้รอจบก่อน */
    if (isOpen && streaming()) { toast(t('wait_streaming'), true); return; }
    deleteConv(id).then(function () {
      CONVS = CONVS.filter(function (x) { return x.id !== id; });
      lastRecSig = '';
      renderRecents();
      toast(t('chat_deleted'));
      if (isOpen) {
        setRoute({ name: 'start', id: null });
        reloadFrame('#/');
      } else {
        reloadFrameSoon();
      }
    }).catch(function (e) { failToast(t('errdelete'), e); });
  });
}
$('#titleBtn').addEventListener('click', function () { if (ROUTE.id) chatMenu(this, ROUTE.id); });
$('#titleStatic').addEventListener('click', function () { openPanel(); });
$('#skipLink').addEventListener('click', function (e) {
  e.preventDefault();
  frame.focus();
  if (!callEnh('focusComposer')) frame.focus();
});

/* ---------------------------------------------------------------- โปรเจกต์ในแถบข้าง */
var projList = $('#projList'), lastProjSig = '';
function renderProjects() {
  var sig = JSON.stringify(PROJECTS.map(function (p) { return [p.slug, p.name, p.port]; }));
  if (sig === lastProjSig) return;
  lastProjSig = sig;
  var memo = focusMemo(projList);
  projList.replaceChildren.apply(projList, PROJECTS.map(function (p) {
    var cur = p.port === ME;
    var a = el('a', {
      class: 'item proj' + (cur ? ' on' : ''), href: portUrl(p.port), target: '_top', tabindex: '-1',
      title: p.name, 'aria-current': cur ? 'page' : null, 'data-port': String(p.port), 'aria-describedby': 'rowKeysHint',
      'aria-haspopup': cur ? 'dialog' : null
    }, [el('span', { class: 'ib' }, [icon('folder')]), el('span', { class: 'lbl', text: p.name })]);
    var more = el('button', {
      type: 'button', class: 'more', 'aria-label': t('proj_options') + ': ' + p.name, 'data-tip': t('proj_options'),
      'aria-haspopup': 'menu', 'aria-expanded': 'false', 'data-slug': p.slug, tabindex: '-1'
    }, [icon('more')]);
    return el('div', { class: 'row', role: 'listitem', 'data-key': p.slug }, [a, more]);
  }));
  setRoving(projList, null);
  focusRestore(projList, memo);
}
projList.addEventListener('click', function (e) {
  var more = e.target.closest('.more');
  if (more) { e.preventDefault(); projectMenu(more, more.getAttribute('data-slug')); return; }
  var a = e.target.closest('a.proj');
  /* โปรเจกต์ปัจจุบัน: เปิดแผงโปรเจกต์แทนการโหลดหน้าเดิมซ้ำ */
  if (a && a.classList.contains('on') && !e.ctrlKey && !e.metaKey && !e.shiftKey) { e.preventDefault(); openPanel(); }
});
projList.addEventListener('keydown', function (e) {
  rowKeys(projList, e, function (more, link) { projectMenu(more, more.getAttribute('data-slug'), null, link); });
});
projList.addEventListener('focusin', function (e) {
  var a = e.target.closest && e.target.closest('a.item');
  if (a) setRoving(projList, a);
});
function projectMenu(anchor, slug, place, back) {
  var p = PROJECTS.find(function (x) { return x.slug === slug; });
  openMenu(anchor, [
    { label: t('rename_project'), icon: 'pencil', run: function () { renameProject(slug); } },
    PROJECTS.length > 1 ? { label: t('delete_project'), icon: 'trash', danger: true, run: function () { deleteProject(slug); } } : null
  ], place, { back: back, label: t('proj_options') + (p ? ': ' + p.name : '') });
}
function renameProject(slug) {
  var p = PROJECTS.find(function (x) { return x.slug === slug; }) || {};
  promptBox(t('rename_project'), p.name || '').then(function (v) {
    if (v == null) return;
    var nm = v.trim();
    if (!nm || nm === p.name) return;
    patchProject(slug, { name: nm }).then(function () { return refreshHub(); })
      .then(function () { toast(t('renamed')); })
      .catch(function (e) { failToast(t('errrename'), e, { 409: 'err_exists' }); });
  });
}
function deleteProject(slug) {
  if (PROJECTS.length <= 1) { toast(t('cant_delete_last'), true); return; }
  var p = PROJECTS.find(function (x) { return x.slug === slug; }) || {};
  confirmBox(t('delproj_title'), fmt(t('delproj_body'), p.name || '')).then(function (yes) {
    if (!yes) return;
    api(HUB + '/api/projects/' + encodeURIComponent(slug), { method: 'DELETE' }).then(function () {
      if (slug === PROJ.slug) {
        var other = PROJECTS.find(function (x) { return x.slug !== slug; });
        if (other) { location.href = portUrl(other.port); return; }
      }
      return refreshHub().then(function () { toast(t('deleted')); });
    }).catch(function (e) { failToast(t('errdelete'), e, { 409: 'cant_delete_last' }); });
  });
}
/* สร้างโปรเจกต์แบบพิมพ์ในที่ ไม่ใช้ prompt() */
var npWrap = $('#newProjWrap'), npIn = $('#newProjIn');
$('#projAdd').addEventListener('click', function () {
  npWrap.hidden = false; npIn.value = ''; npIn.disabled = false; npIn.focus();
});
npIn.addEventListener('blur', function () { if (!npIn.disabled) npWrap.hidden = true; });
npIn.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); npIn.blur(); $('#projAdd').focus(); return; }
  if (e.key !== 'Enter' || e.isComposing) return;
  var name = npIn.value.trim();
  if (!name) return;
  npIn.disabled = true;
  api(HUB + '/api/projects', { method: 'POST', json: { name: name } }).then(function (d) {
    location.href = portUrl(d.port);
  }).catch(function (err) {
    failToast(t('errcreate'), err, { 409: 'err_exists', 507: 'err_noport' });
    npIn.disabled = false; npIn.focus();
  });
});

/* ---------------------------------------------------------------- แถบข้าง: พับ / ลิ้นชัก */
/* สองคีย์: qwen-sidebar = ที่ผู้ใช้เลือกบนจอกว้าง, qwen-sidebar-auto = ที่เลือกเองในช่วงจอกลาง
   ช่วงจอกลางพับเป็นแถบไอคอนเป็นค่าเริ่มต้น (ไม่งั้น iframe < 768px กลายเป็นหน้ามือถือ)
   แยกคีย์เพื่อไม่ให้การพับอัตโนมัติไปเขียนทับค่าที่ผู้ใช้ตั้งไว้สำหรับจอกว้าง
   (กติกาเดียวกันเขียนซ้ำในสคริปต์ต้น <body> เพื่อให้ถูกตั้งแต่ภาพแรก) */
var SB_KEY = 'qwen-sidebar', SB_AUTO_KEY = 'qwen-sidebar-auto';
function wantCollapsed() {
  if (MID.matches) { var a = lsGet(SB_AUTO_KEY); return a ? a === 'collapsed' : true; }
  return lsGet(SB_KEY) === 'collapsed';
}
function applySidebarPref() {
  unpeek();
  body.classList.toggle('sb-min', wantCollapsed());
  syncToggle();
}
/* ผู้ใช้กดพับ/กางเอง — จำไว้ในคีย์ของช่วงความกว้างปัจจุบัน */
function setCollapsed(v) {
  unpeek();
  if (typeof ART !== 'undefined') ART.autoMin = false;   // ผู้ใช้เลือกเองแล้ว — ปิดแผงแสดงผลทีหลังไม่ต้องกางคืนให้
  body.classList.toggle('sb-min', v);
  lsSet(MID.matches ? SB_AUTO_KEY : SB_KEY, v ? 'collapsed' : 'expanded');
  syncToggle();
  if (v) endSearch();
}
/* ---- peek: กางชั่วคราวแบบลอยทับหน้าแชต (จากแถบไอคอน: Ctrl+K, ปุ่มล่าสุด) ----
   ไม่บันทึกเป็นค่าที่ผู้ใช้เลือก และไม่ทำให้ iframe แคบลง — ปิดเองเมื่อเปิดแชต คลิกข้างนอก หรือโฟกัสออก */
var sbPeek = false, peekBack = null;
function peek() {
  if (isMobile() || sbPeek || !body.classList.contains('sb-min')) return;
  peekBack = document.activeElement;
  sbPeek = true;
  body.classList.remove('sb-min');
  body.classList.add('sb-peek');
  syncToggle();
}
function unpeek() {
  if (!sbPeek) return;
  sbPeek = false;
  var had = sb.contains(document.activeElement);
  body.classList.remove('sb-peek');
  body.classList.add('sb-min');
  if (body.classList.contains('searching')) endSearch();
  syncToggle();
  /* โฟกัสอยู่บนแถวที่เพิ่งถูกซ่อน — คืนให้ตัวที่เปิด peek (ปุ่มล่าสุดในแถบไอคอน, ช่องพิมพ์ในแชต) หรือปุ่มในแถบไอคอน
     รายการใน .sb-scroll ถูกซ่อนด้วย visibility:hidden ซึ่ง shown() ยังนับว่าเห็น — ต้องเช็กด้วย focusLost() */
  if (had && focusLost()) {
    var back = visible(peekBack) && peekBack !== body ? peekBack : [$('#railRecents'), searchBtn].filter(visible)[0];
    if (back) back.focus();
  }
  peekBack = null;
}
function syncToggle() {
  var btn = $('#sbToggle'), lbl;
  if (isMobile()) lbl = t('close');
  else lbl = body.classList.contains('sb-min') ? t('expand') : t('collapse');
  setAttr(btn, 'aria-label', lbl); setAttr(btn, 'data-tip', lbl);
  /* ในลิ้นชักบนจอแคบ ปุ่มนี้คือปุ่มปิด ใช้ไอคอน X ให้ตรงความหมาย */
  setAttr($('#sbToggleIc'), 'href', isMobile() ? '#i-x' : '#i-sidebar');
}
function scrimSync() {
  var modal = body.classList.contains('sb-open') || pp.classList.contains('open');
  scrim.classList.toggle('on', modal);
  /* ลิงก์ข้ามอยู่นอกส่วนที่ถูก inert — ซ่อนระหว่างลิ้นชัก/แผงเปิด ไม่ให้ Tab หลุดไปหลังม่าน */
  setHidden($('#skipLink'), modal);
}
/* ลิ้นชักบนจอแคบเป็น modal จริง: ส่วนหลักถูก inert (Tab/คลิกเข้าไม่ได้) และอ่านเป็น dialog */
function openDrawer() {
  if (body.classList.contains('sb-open')) return;
  body.classList.add('sb-open');
  $('#main').inert = true;
  sb.setAttribute('role', 'dialog');
  sb.setAttribute('aria-modal', 'true');
  $('#burger').setAttribute('aria-expanded', 'true');
  scrimSync();
}
function closeDrawer() {
  if (!body.classList.contains('sb-open')) return;
  /* ส่วนหลักถูก inert ระหว่างลิ้นชักเปิด โฟกัสจึงอยู่ได้แค่ในลิ้นชักหรือหล่นไป <body> (กดที่ว่างที่โฟกัสไม่ได้) —
     ทั้งสองกรณีต้องคืนให้ปุ่มแฮมเบอร์เกอร์ */
  var had = sb.contains(document.activeElement) || focusLost();
  body.classList.remove('sb-open');
  $('#main').inert = false;
  sb.removeAttribute('role');
  sb.removeAttribute('aria-modal');
  $('#burger').setAttribute('aria-expanded', 'false');
  scrimSync();
  /* ทุกทางที่ปิดลิ้นชัก (X, ม่าน, เลือกแชต) คืนโฟกัสให้ปุ่มแฮมเบอร์เกอร์ — ไม่ค้างบนปุ่มที่ถูกซ่อน */
  if (had && shown($('#burger'))) $('#burger').focus();
}
function toggleSidebar() {
  if (isMobile()) { body.classList.contains('sb-open') ? closeDrawer() : openDrawer(); return; }
  setCollapsed(!body.classList.contains('sb-min'));
}
applySidebarPref();
$('#sbToggle').addEventListener('click', toggleSidebar);
$('#burger').addEventListener('click', function () { openDrawer(); setTimeout(function () { $('#newChatBtn').focus(); }, 60); });
$('#railRecents').addEventListener('click', function () {
  peek();
  /* ปุ่มนี้หายไปเมื่อแถบกาง — ย้ายโฟกัสไปแถวแรกของรายการ ไม่ปล่อยให้หล่นไป <body> */
  var first = recList.querySelector('a.rec[tabindex="0"]') || recList.querySelector('a.rec');
  (first || searchBtn).focus();
});
$('#railProj').addEventListener('click', function () { openPanel(); });
/* ม่านโฟกัสไม่ได้ — กดลงไปเบราว์เซอร์จะปล่อยโฟกัสหล่นไป <body> ก่อน click มาถึง
   กันไว้ที่ mousedown (แตะบนจอสัมผัสก็ส่ง mousedown ตามมา) โฟกัสจึงยังอยู่ในลิ้นชัก/แผงตอนปิด แล้วถูกคืนให้ปุ่มที่เปิด */
scrim.addEventListener('mousedown', function (e) { e.preventDefault(); });
scrim.addEventListener('click', function () { closeDrawer(); closePanel(); });
NARROW.addEventListener('change', function () { closeDrawer(); closeMenu(); applySidebarPref(); });
MID.addEventListener('change', function () { closeMenu(); applySidebarPref(); });
/* peek ปิดเมื่อคลิกนอกแถบข้าง (ยกเว้นเมนู/กล่องที่เปิดจากแถบเอง) หรือโฟกัสย้ายไปส่วนหลัก */
document.addEventListener('pointerdown', function (e) {
  if (sbPeek && !sb.contains(e.target) && !menu.contains(e.target) && dlg.wrap.hidden) unpeek();
}, true);
sb.addEventListener('focusout', function (e) {
  if (sbPeek && e.relatedTarget && $('#main').contains(e.relatedTarget)) unpeek();
});

/* ---------------------------------------------------------------- เมนูท้ายแถบ (บัญชี) */
function modelText(m) {
  var n = /^(\d+) models$/.exec(m || '');
  return n ? t('nmodels').replace('%d', n[1]) : (m || '');
}
function paintHealth() {
  var dot = $('#hdot'), stat = $('#stat');
  var cls = 'hdot' + (HEALTH.state === 'ok' ? ' ok' : HEALTH.state === 'checking' ? '' : ' bad');
  if (dot.className !== cls) dot.className = cls;
  var txt = HEALTH.state === 'ok' ? t('ready') + (HEALTH.model ? ' · ' + modelText(HEALTH.model) : '')
    : HEALTH.state === 'down' ? t('notready') : HEALTH.state === 'hub' ? t('hubdown') : t('checking');
  setText(stat, txt);
  /* GPU ของโมเดลหลักต่อท้ายชื่อเครื่อง — แสดงเฉพาะตอนโมเดลพร้อม (เซิร์ฟเวอร์ไม่ทำงาน = ยังไม่ได้ใช้ GPU ไหนเลย) */
  var g = HEALTH.state === 'ok' ? GPU : null, gtxt = gpuShort(g, true), tag = $('#gpuTag');
  setText(tag, gtxt ? ' · ' + gtxt : '');
  setHidden(tag, !gtxt);
  tag.classList.toggle('warn', !!(g && g.stale));
  $('#gbadge').classList.toggle('on', !!(g && g.stale));
  /* แถบไอคอนซ่อนข้อความสถานะ เหลือแค่จุดสี — ชื่อปุ่มและป้ายชื่อจึงต้องมีสถานะเป็นตัวหนังสือด้วย
     GPU เปลี่ยน: ใส่ประโยคเต็ม (ต้องทำอะไรต่อ) ไม่ใช่แค่ป้ายสั้น */
  var lbl = t('account_menu') + ' — ' + txt + (gtxt ? ' · ' + (g.stale ? t('gpu_changed_btn') : gpuShort(g)) : '');
  setAttr($('#acctBtn'), 'aria-label', lbl);
  setAttr($('#acctBtn'), 'data-tip', lbl);
}
/* หัวเมนูบัญชี: แต่ละโมเดลใช้ GPU ไหน + GPU ที่พบ (+ คำเตือนถ้า GPU เปลี่ยนหลังเปิดครั้งล่าสุด)
   เตือน GPU เปลี่ยนมีปุ่ม "ใช้ GPU ใหม่" ในตัว — เดิมต้องปิดแล้วเปิด Qwen3.8 จากไอคอน ตอนนี้รีสตาร์ตจากหน้าต่างเลือก GPU ได้ */
function gpuWarnNode(g) {
  if (!(g && g.stale)) return null;
  var b = el('button', { type: 'button', role: 'menuitem', class: 'mh-warn-b', text: t('gpu_use_new') });
  b.addEventListener('click', function (e) { e.stopPropagation(); closeMenu(); openGpu({ apply: true }); });
  return el('div', { class: 'mh-warn' }, [icon('alert', 'ic-xs'), el('div', { class: 'mh-warn-c' }, [el('span', { text: t('gpu_changed_menu') }), b])]);
}
function gpuBlock(g) {
  if (!g) return null;
  var rows = (g.placement || []).map(function (p) {
    /* ป้ายชื่อเต็ม (การ์ดทุกใบ ขนาดบริบท รองรับภาพ) — แถวในเมนูตัด … ได้เมื่อชื่อยาว */
    return el('span', { class: 'mh-pl' + (p.primary ? ' pri' : ''), 'data-tip': gpuLine(p) }, [
      el('span', { class: 'mh-m', text: p.label }), el('span', { class: 'mh-d', text: gpuDev(p) })]);
  });
  /* การ์ดแต่ละใบห้ามถูกตัดขึ้นบรรทัดใหม่กลางชื่อ ("(ต่อ|ภายนอก)") — ขึ้นบรรทัดได้เฉพาะระหว่างการ์ด */
  var devs = g.devices || [], dk = [];
  if (devs.length) {
    dk.push(t('gpu_found') + ': ');
    devs.forEach(function (x, i) { if (i) dk.push(', '); dk.push(el('span', { class: 'mh-dv', text: gpuDevName(x) })); });
  } else dk.push(gpuNoDev(g));
  /* ทั้งก้อนเป็นปุ่มเดียว (กดที่แถวไหนก็เปิดหน้าต่างเลือก GPU) — "เปลี่ยน ›" มุมขวาบอกว่ากดได้
     ชื่อของรายการ = หัวข้อ + "เปลี่ยน" สั้นๆ (เดิมเป็นข้อความทั้งก้อนต่อกันไม่มีเว้น "…เปลี่ยนQwen3.8-27BRTX…")
     รายละเอียดทีละโมเดลเป็นคำอธิบาย (กล่องซ่อน ประโยคคั่นด้วยจุด) */
  var head = t('gpu_where') + (g.stale ? ' ' + t('gpu_as_started') : '');
  var desc = (g.placement || []).map(gpuLine).concat([gpuDevs(g)]).map(function (s) { return String(s).replace(/[\s.]+$/, ''); }).join('. ') + '.';
  var b = el('button', { type: 'button', role: 'menuitem', class: 'mh-gpu', 'aria-label': head + ' — ' + t('gpu_edit'),
    'aria-describedby': 'mhGpuD' }, [
    el('span', { class: 'mh-sub' }, [el('span', { text: head }),
      el('span', { class: 'mh-go' }, [el('span', { text: t('gpu_edit') }), icon('chev-r', 'ic-xs')])])
  ].concat(rows, [el('span', { class: 'mh-devs' }, dk), el('span', { id: 'mhGpuD', hidden: true, text: desc })]));
  b.addEventListener('click', function (e) { e.stopPropagation(); closeMenu(); openGpu(); });
  return b;
}
/* tab = 'usage' | 'doctor' (batch 3, D4): เปิดหน้าจัดการที่แท็บนั้นตรงๆ ผ่าน #hash — ค่าอื่น/ไม่ส่ง = แท็บโปรเจกต์ */
function manageUrl(tab) {
  var th = 'dark';
  try { th = window.qwenBoot.resolvedTheme(); } catch (e) {}
  return HUB + '/?manage=1&theme=' + th + (tab === 'usage' || tab === 'doctor' ? '#' + tab : '');
}
function openManage(tab) { window.open(manageUrl(typeof tab === 'string' ? tab : ''), '_blank', 'noopener'); }
/* เปิดหน้าต่างของ WebUI — ดูค่าที่คืนจริง ไม่ใช่แค่ "เรียกได้" (openSettings คืน false ถ้าหาปุ่มไม่เจอ,
   openMcp คืน Promise<boolean>) ไม่งั้นกดแล้วเงียบ ไม่มีอะไรเกิดขึ้น */
function openFrameDialog(name) {
  if (isMobile()) closeDrawer();
  unpeek();
  var r = callEnhR(name);
  if (!r.ok) { toast(t('not_ready_yet'), true); return; }
  Promise.resolve(r.value).then(function (ok) { if (!ok) toast(t('not_ready_yet'), true); },
    function () { toast(t('not_ready_yet'), true); });
}
$('#acctBtn').addEventListener('click', function () {
  var B = window.qwenBoot || {};
  var theme = B.getTheme ? B.getTheme() : 'dark', font = B.getFont ? B.getFont() : 'serif';
  var g = HEALTH.state === 'ok' ? GPU : null;
  /* หัวเมนู (สถานะ + เตือน GPU เปลี่ยน) เป็นคำอธิบายของเมนู (aria-describedby) — ก้อน GPU แยกออกมาเป็นรายการที่กดได้ */
  var head = el('div', { role: 'none', id: 'menuHead' }, [
    el('div', { class: 'menu-head' }, [
      el('span', { class: $('#hdot').className, 'aria-hidden': 'true' }),
      el('span', { class: 'mh-t', text: $('#stat').textContent })
    ]),
    gpuWarnNode(g)
  ]);
  var place = (!isMobile() && body.classList.contains('sb-min')) ? 'right' : 'up';
  /* แถวแจ้งเตือนแสดงค่าที่ใช้ได้จริง (ntfEff) + คำเตือนใต้แถวเมื่อเลือกเปิดไว้แต่เบราว์เซอร์ไม่อนุญาต */
  var ntfWarn = el('div', { class: 'mh-warn', id: 'ntfWarn', hidden: true }, [icon('alert', 'ic-xs'), el('span', { class: 'ntf-warn-t' })]);
  var ntfRow = segRow(t('notify'), 'bell', [['off', t('ntf_off')], ['on', t('ntf_on')], ['sound', t('ntf_sound')]], ntfEff(), function (v, seg) { setNotifyPref(v, seg, ntfWarn); });
  ntfPaintWarn(ntfWarn, ntfRow.querySelector('.seg'));
  /* batch 2a (B5): บริการของเครื่องนี้ (embedding / ค้นคว้าเชิงลึก / ค้นเว็บ) ต่อจากก้อน GPU — เป็นคำอธิบายของเมนูเหมือนหัวเมนู */
  var svc = svcNode();
  openMenu(this, [
    { node: head },
    g ? { node: gpuBlock(g) } : null,
    svc ? { node: svc } : null,
    /* มีรายการ GPU = หัวเมนูสูงขึ้นมาก — คั่นเส้นให้แยกเป็นกลุ่ม "สถานะ" กับ "การตั้งค่า" ชัดเจน */
    g || svc ? 'sep' : null,
    { node: segRow(t('theme'), 'moon', [['dark', t('theme_dark'), 'moon'], ['light', t('theme_light'), 'sun'], ['system', t('theme_system'), 'monitor']], theme, function (v) {
      if (B.setTheme) B.setTheme(v);
      callEnh('applyTheme');
    }) },
    { node: segRow(t('font'), 'type', [['serif', t('font_serif'), null, 'font-family:var(--qw-font-serif)'], ['sans', t('font_sans'), null, 'font-family:var(--qw-font-ui)']], font, function (v) {
      if (B.setFont) B.setFont(v);
      callEnh('setFont', v);
    }) },
    { node: segRow(t('language'), 'globe', [['th', 'ไทย', null, null, 'th'], ['en', 'English', null, null, 'en']], LANG, function (v, seg) { setLang(v, seg, ''); }) },
    /* แจ้งเตือนเมื่อแท็บถูกซ่อน (K5) — สิทธิ์ของเบราว์เซอร์เป็นต่อ origin (ต่อพอร์ตโปรเจกต์) ค่านี้จึงเก็บต่อโปรเจกต์ด้วย */
    { node: ntfRow },
    { node: ntfWarn },
    'sep',
    { label: t('pers_menu'), icon: 'user', run: function () { openPers(); } },
    { label: t('gpu_choose'), icon: 'chip', run: function () { openGpu(); } },
    { label: t('webui_settings'), icon: 'sliders', run: function () { openFrameDialog('openSettings'); } },
    { label: t('mcp_servers'), icon: 'plug', run: function () { openFrameDialog('openMcp'); } },
    { label: t('manage_projects'), icon: 'grid', external: true, run: openManage },
    /* batch 3 (D4): สถิติการใช้งาน + ตรวจระบบ อยู่ในหน้าจัดการ (พอร์ต hub) — เปิดแท็บใหม่ที่แท็บนั้นเลย */
    { label: t('b3_menu_usage'), icon: 'chart', external: true, run: function () { openManage('usage'); } },
    { label: t('b3_menu_doctor'), icon: 'pulse', external: true, run: function () { openManage('doctor'); } }
  ], place, { label: t('account_menu'), describedby: svc ? 'menuHead mhSvc' : 'menuHead', cls: g || svc ? 'wide' : '' });
});
/* batch 2a (B5): ก้อน "บริการ" ในเมนูบัญชี — ค่าจาก SVC (hub ตรวจทุก ~8 วินาที) ไม่ถามเพิ่มตอนเปิดเมนู
   hub ไม่ตอบ = ไม่แสดง (บรรทัดสถานะบนสุดบอกอยู่แล้วว่าติดต่อ hub ไม่ได้) */
function svcNode() {
  var s = SVC;
  if (!s || HEALTH.state === 'hub') return null;
  var g = [];
  function row(label, cls, text, extra) {
    g.push(el('span', { class: 'mh-svc-l', text: label }));
    g.push(el('span', { class: 'mh-svc-v' + (cls ? ' ' + cls : '') }, [el('i', { 'aria-hidden': 'true' }), el('span', { text: text })]));
    if (extra) g.push(el('span', { class: 'mh-svc-x', text: extra }));
  }
  var e = s.embed || {}, r = s.research || {}, w = s.web || {};
  var es = e.state;
  row(t('svc_embed'), es === 'ok' ? 'ok' : es === 'loading' ? 'warn' : 'bad',
    es === 'ok' ? t('svc_ok') : es === 'loading' ? t('svc_loading') : es === 'absent' ? t('svc_embed_absent') : t('svc_embed_down'));
  var rs = r.state, n = Math.max(0, Math.floor(+r.running || 0));
  row(t('svc_research'), rs === 'ok' ? 'ok' : rs === 'missing' ? '' : 'bad',
    rs === 'ok' ? (n ? fmt(t('svc_res_running'), n.toLocaleString(LANG)) : t('svc_ok'))
      : rs === 'missing' ? t('svc_res_missing') : rs === 'broken' ? t('svc_res_broken')
      : (s.mcp && s.mcp.state === 'auth') ? t('svc_auth') : t('svc_res_down'));
  var ws = w.state, prov = String(w.provider || '');
  row(t('svc_web'), ws === 'ok' ? (prov === 'builtin' ? 'warn' : 'ok') : 'bad',
    ws === 'ok' ? (prov === 'builtin' ? t('svc_web_builtin') : prov === 'brave' ? 'Brave Search' : (prov || t('svc_ok')))
      : ws === 'auth' ? t('svc_auth') : t('svc_down'),
    ws === 'ok' && prov === 'builtin' ? t('svc_web_hint') : '');
  /* batch 2b (C4): พูดแทนพิมพ์ (บริการถอดเสียง 8795) — แสดงเฉพาะเมื่อ hub รายงานมา (hub รุ่นก่อนไม่มีแถวนี้)
     อุปกรณ์ (gpu/cpu) มาจากการตรวจสุขภาพของบริการ — ตัดสั้นและใส่ด้วย textContent เหมือนค่าอื่น */
  var v = s.stt;
  if (v && typeof v === 'object') {
    var vs = v.state, dev = String(v.device || '').replace(/[^\w .+-]/g, '').slice(0, 12).toUpperCase();
    row(t('svc_stt'), vs === 'ok' ? 'ok' : vs === 'loading' ? 'warn' : vs === 'absent' || vs === 'missing' ? '' : 'bad',
      vs === 'ok' ? (dev ? fmt(t('svc_stt_dev'), dev) : t('svc_ok')) : vs === 'loading' ? t('svc_loading')
        : vs === 'absent' || vs === 'missing' ? t('svc_res_missing') : vs === 'auth' ? t('svc_auth') : t('svc_down'),
      vs === 'ok' || vs === 'loading' ? '' : t('svc_stt_hint'));
  }
  return el('div', { class: 'mh-svc', id: 'mhSvc', role: 'none' }, [el('span', { class: 'mh-svc-h', text: t('svc_head') }), el('div', { class: 'mh-svc-g' }, g)]);
}

/* ---------------------------------------------------------------- หน้าต่างเลือก GPU */
/* แต่ละโมเดลใช้การ์ดใบไหน: บันทึก = PUT /api/gpu/choice (hub เขียน gpu-choice.json) แล้ว POST /api/gpu/apply
   (hub สั่งตัวเปิดทำงานซ้ำ ซึ่งรอแชตที่ยังตอบอยู่ แล้วรีสตาร์ตเฉพาะ llama-server) — การจัดวางจริงยังเป็นของ gpu_profile.py
   เหมือนตอนเปิดจากไอคอน คำแนะนำ "ใส่ได้ทั้งตัว / ล้นไป CPU" ในหน้าต่างนี้คิดจาก need_gib (ขนาดที่โมเดลต้องใช้)
   เทียบ budget_mib ของการ์ดที่เลือก = สูตรเดียวกับแผน แต่เป็นค่าประมาณ ตัดสินจริงตอนรีสตาร์ต
   ชื่อการ์ด/โมเดลมาจากไดรเวอร์และไฟล์ — ถือว่าไว้ใจไม่ได้ สร้าง DOM ด้วย el() (textContent) เท่านั้น */
var GD = {
  wrap: $('#gdWrap'), box: $('#gd'), body: $('#gdBody'), status: $('#gdStatus'), confirm: $('#gdConfirm'),
  reset: $('#gdReset'), cancel: $('#gdCancel'), apply: $('#gdApply'),
  data: null, form: {}, back: null, seq: 0, loadErr: false, tries: 0, focusApply: false,
  job: null,          // งานที่หน้านี้เห็น: null | 'running' | 'busy' | 'failed' | 'unknown'
  busy: false,        // กำลังบันทึก/สั่งเริ่ม (ก่อน hub ตอบว่างานเริ่มแล้ว)
  phase: '',          // ช่วงของงานที่กำลังทำ: 'waiting' = ตัวเปิดรอแชตที่ตอบอยู่ (ยังไม่ได้รีสตาร์ตอะไร)
  still: false,       // งานเกิน 20 นาทีแล้วแต่ตัวเปิดยังไม่จบ (สั่งใหม่ยังไม่ได้)
  flash: null, flashT: 0,   // ข้อความชั่วคราวในหน้าต่าง (แทน toast) — {text, bad}
  watch: false, jobAt: 0, tail: [], line: '', logName: '', t0: 0, pollT: 0, pollErr: 0, tick: 0
};
function gpuOpen() { return !GD.wrap.hidden; }
function own(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
/* %1 %2 … ในข้อความ (fmt() รับแค่ %s ตัวเดียว) — แทนด้วยฟังก์ชัน ชื่อที่มี $& ไม่ถูกตีความ */
function fmtN(s) { var a = arguments; return String(s).replace(/%(\d)/g, function (m, i) { return a[+i] != null ? String(a[+i]) : m; }); }
function gdGb(x) { return (Math.round((+x || 0) * 10) / 10).toFixed(1); }
function gdVram(mib) { return Math.round((mib || 0) / 1024) + ' GB'; }
/* ข้อความสำหรับโปรแกรมอ่านหน้าจอเท่านั้น (ช่องเดียวกับ toast) — สถานะของหน้าต่างเปลี่ยนโดยไม่มี toast */
function announce(msg, bad) {
  var live = bad ? srAlert : srPolite;
  live.textContent = '';
  setTimeout(function () { live.textContent = msg; }, 50);
}
function gdLive() { return (GD.data && GD.data.live) || {}; }
/* การ์ดเรียง VRAM มากไปน้อย (แบบที่ gpu_profile เลือกใช้) — ลำดับ CUDA เปลี่ยนได้เมื่อเสียบ eGPU จึงไม่ใช้ */
function gdDevs() {
  return (gdLive().devices || []).slice().sort(function (a, b) { return (b.total_mib || 0) - (a.total_mib || 0); });
}
function gdDev(k) {
  var l = gdLive().devices || [];
  for (var i = 0; i < l.length; i++) if (l[i].key === k) return l[i];
  return null;
}
/* การ์ดรุ่นเดียวกันสองใบ: key ใบที่สองลงท้าย " #2" — ชื่อสั้นต้องมีด้วย ไม่งั้นตัวเลือกสองอันอ่านเหมือนกัน */
function gdShort(d) {
  var s = String(d.short || d.key || 'GPU'), m = /\s#(\d+)$/.exec(d.key || '');
  return m && !/#\d+$/.test(s) ? s + ' #' + m[1] : s;
}
/* ชื่อสั้นของการ์ดที่ไม่ได้ต่ออยู่ (มีแค่ key ในไฟล์ตัวเลือก) — ตัดคำแบบเดียวกับ gpu_short() ของ hub */
function gdKeyShort(k) {
  var d = gdDev(k);
  if (d) return gdShort(d);
  var m = /^(.*?)(\s#\d+)?$/.exec(String(k || ''));
  var s = m[1].replace(/^NVIDIA\s+/i, '').replace(/^GeForce\s+/i, '').replace(/\s+Laptop GPU$/i, '').replace(/\s+Generation$/i, '').trim();
  return (s || String(k)) + (m[2] || '');
}
function gdKeys(v) {
  if (!v || v === 'auto' || v === 'cpu') return null;
  try { var a = JSON.parse(v); return Array.isArray(a) && a.length ? a : null; } catch (e) { return null; }
}
/* ค่าในไฟล์ → value ของ <option>: การ์ดเรียงตาม VRAM (ใบที่ไม่ได้ต่ออยู่ไว้ท้าย) ค่าเดียวกันจึงได้สตริงเดียวกันเสมอ */
function gdVal(v) {
  if (v === 'cpu') return 'cpu';
  if (!Array.isArray(v) || !v.length) return 'auto';
  var rank = Object.create(null);
  gdDevs().forEach(function (d, i) { rank[d.key] = i; });
  var r = function (k) { return k in rank ? rank[k] : 99; };
  return JSON.stringify(v.slice().sort(function (a, b) { return r(a) - r(b); }));
}
function gdBudget(keys) {
  var s = 0;
  keys.forEach(function (k) { var d = gdDev(k); if (d) s += d.budget_mib || 0; });
  return s / 1024;
}
function gdCombos(devs) {
  var out = [], n = devs.length;
  function rec(size, start, acc) {
    if (acc.length === size) { out.push(acc.slice()); return; }
    for (var i = start; i < n; i++) { acc.push(devs[i]); rec(size, i + 1, acc); acc.pop(); }
  }
  for (var size = 2; size <= n; size++) rec(size, 0, []);
  return out;
}
function gdList(names) {
  return names.length < 2 ? names.join('') : names.slice(0, -1).join(', ') + t('gpu_and') + names[names.length - 1];
}
/* สิ่งที่แผนอัตโนมัติเลือกให้โมเดลนี้ (effective.auto จาก gpu_profile — มีแม้ผู้ใช้เลือกเองอยู่)
   GPU เปลี่ยนไปแล้ว (stale) = แผนนั้นเป็นของการ์ดชุดเก่า ยังไม่มีใครคิดแผนของชุดใหม่ → null (บอกว่า "เลือกตอนรีสตาร์ต") */
function gdAuto(r) {
  var e = r.effective;
  if (!e || gdLive().stale) return null;
  if (e.auto && e.auto.devices_short) return e.auto;
  return e.source === 'auto' && e.devices_short ? { devices_short: e.devices_short, device_keys: e.device_keys, ctx: e.ctx, vision: e.vision } : null;
}
/* ขนาดที่ต้องใช้ ณ บริบท ctx (+ รองรับภาพ) หน่วย GiB — need_gib มีแค่ 32K / 64K / 64K+ภาพ (สูตรเดียวกับ gpu_profile)
   ค่าอื่น (เช่น models-preset.user.ini ตั้ง ctx-size = 16384) คิดเป็นเส้นตรงจากสองจุดนั้น: KV โตตามจำนวนโทเคนตรงๆ
   ส่วน sliding window ของ gpt-oss คงที่เมื่อบริบทยาวกว่าหน้าต่าง  ภาพ = ส่วนต่างของ 64K+ภาพ กับ 64K (ไม่มีก็ขนาด mmproj) */
function gdNeedAt(r, ctx, vision) {
  var ng = r.need_gib || {}, a = ng['32768'], b = ng['65536'], g;
  ctx = +ctx || 32768;
  if (vision && ng[ctx + '_vision'] != null) return ng[ctx + '_vision'];
  if (ng[String(ctx)] != null) g = ng[String(ctx)];
  else if (a != null && b != null) g = a + (b - a) * (ctx - 32768) / 32768;
  else return null;
  if (vision) g += ng['65536_vision'] != null && b != null ? ng['65536_vision'] - b : (+r.mmproj_gib || 0);
  return g;
}
/* models-preset.user.ini (แก้มือ) ชนะทั้งแผนอัตโนมัติและที่เลือกในหน้านี้ — ctx-size / mmproj ที่ตั้งไว้เปลี่ยนขนาดที่ต้องใช้
   r.user_ini = {keys, ctx, vision} จาก hub (อ่านไฟล์นั้นด้วย parser ตัวเดียวกับตัวเปิด) */
function gdUiHas(r, k) { var u = r.user_ini; return !!(u && u.keys && u.keys.indexOf(k) >= 0); }
function gdWithUi(r, ctx, vision) {
  var u = r.user_ini || {};
  return { ctx: u.ctx || ctx, vision: u.vision != null ? !!u.vision : vision };
}
function gdPrimary() { return ((GD.data && GD.data.models) || []).filter(function (r) { return r.primary; })[0] || null; }
/* การ์ดใบเดียวที่แผนอัตโนมัติให้โมเดลหลักแล้วจุทั้งตัว (fit_gpu ของ gpu_profile) — null ถ้าไม่มี
   (ไม่มีใบไหนจุ = แผน "ทุกโมเดลใช้ทุก GPU" ไม่มีการจองการ์ด) */
function gdAutoCard() {
  var p = gdPrimary(), a = p && gdAuto(p);
  if (!a || !a.device_keys || a.device_keys.length !== 1 || !gdDev(a.device_keys[0])) return null;
  var plan = gdNeedAt(p, a.ctx, a.vision);
  if (plan == null || plan > gdBudget(a.device_keys)) return null;
  var o = gdWithUi(p, a.ctx, a.vision);
  return { key: a.device_keys[0], gib: gdNeedAt(p, o.ctx, o.vision) || plan };
}
/* การ์ดที่โมเดลหลักจะจองไว้หลังรีสตาร์ต ตามค่าในฟอร์ม → {key, gib, row} หรือ null — กติกาเดียวกับ gpu_profile:
   จองเฉพาะเมื่อโมเดลหลักอยู่การ์ดใบเดียว (เลือกเองใบเดียว หรืออัตโนมัติที่ได้การ์ดใบเดียวที่จุทั้งตัว)
   โมเดลอื่นบนการ์ดใบนั้นได้งบที่เหลือหลังหักส่วนนี้ — router โหลดค้างพร้อมกันได้สองตัว และปกติโมเดลหลักโหลดอยู่
   (เดิมคิดจากงบเต็มใบ: Coder ที่เลือก 4090 ขณะ 27B อัตโนมัติอยู่บน 4090 ขึ้นว่า "ใส่ได้ทั้งตัว" ทั้งที่แผนจริงล้นไป CPU) */
function gdReserve() {
  var p = gdPrimary();
  if (!p || gdUiHas(p, 'device')) return null;       // user.ini ย้ายโมเดลหลักเอง — ไม่รู้ว่าจองใบไหน
  var v = GD.form[p.id] || 'auto', ks = gdKeys(v), live = ks ? ks.filter(gdDev) : [];
  if (v === 'cpu' || live.length > 1) return null;
  if (live.length === 1) {
    var n = gdNeed(p, live);
    return n ? { key: live[0], gib: n.gib, row: p } : null;
  }
  if (ks && gdLive().state !== 'ok') return null;
  var c = gdAutoCard();          // อัตโนมัติ (หรือการ์ดที่เลือกไม่ได้ต่ออยู่เลย = ตัวเปิดใช้แผนอัตโนมัติแทน)
  return c ? { key: c.key, gib: c.gib, row: p } : null;
}
/* งบรวมของการ์ดที่ใช้ (GiB) หลังหักส่วนที่โมเดลหลักจองบนการ์ดใบนั้น (เฉพาะโมเดลอื่น) */
function gdBudgetFor(r, keys, res) {
  var s = 0;
  keys.forEach(function (k) {
    var d = gdDev(k);
    if (!d) return;
    var b = (d.budget_mib || 0) / 1024;
    if (res && res.row !== r && k === res.key) b = Math.max(0, b - res.gib);
    s += b;
  });
  return s;
}
/* การ์ดใบนี้มีโมเดลอื่นใช้ด้วยไหม — ตามที่เลือกในหน้าต่างนี้ หรือตามแผนอัตโนมัติของโมเดลที่ยังเป็นอัตโนมัติ
   แผนอัตโนมัติแบบ "ใช้การ์ดร่วมกับโมเดลหลัก" (การ์ดใหญ่ใบเดียว: โมเดลอื่นไม่ระบุ device ให้ -fit ใช้ที่ว่างตอนโหลด)
   gpu_profile ไม่นับว่าโมเดลพวกนั้นครอบครองการ์ด — เลือกการ์ดเดียวกับที่อัตโนมัติเลือกจึงต้องได้ 64K + ภาพเท่ากัน */
function gdShared(key, mid) {
  var pc = gdAutoCard();
  return (GD.data.models || []).some(function (r) {
    if (r.id === mid) return false;
    var v = GD.form[r.id] || 'auto', ks = gdKeys(v), a;
    if (ks) return ks.indexOf(key) >= 0;
    if (v !== 'auto' || !(a = gdAuto(r)) || !a.device_keys || a.device_keys.indexOf(key) < 0) return false;
    return !(pc && a.device_keys.indexOf(pc.key) >= 0);
  });
}
/* ขนาดที่ต้องใช้บนการ์ดที่เลือก — กติกาเดียวกับ gpu_profile: โมเดลหลักได้บริบท 64K + ดูรูป ก็ต่อเมื่ออยู่การ์ดใบเดียว
   คนเดียว และงบของใบนั้นพอ ไม่งั้นบริบท 32K ไม่ดูรูป (โมเดลอื่นบริบท 32K เสมอ) — แล้วทับด้วยค่าใน user.ini ถ้ามี */
function gdNeed(r, keys) {
  var ng = r.need_gib || {}, ctx = 32768, vision = false;
  if (r.primary && keys.length === 1 && !gdShared(keys[0], r.id)) {
    var k = ng['65536_vision'] != null ? '65536_vision' : '65536';
    if (ng[k] != null && gdBudget(keys) >= ng[k]) { ctx = 65536; vision = k === '65536_vision'; }
  }
  var o = gdWithUi(r, ctx, vision), gib = gdNeedAt(r, o.ctx, o.vision);
  return gib == null ? null : { gib: gib, ctx: o.ctx, vision: o.vision };
}
/* แผนอัตโนมัติของโมเดลนี้ใส่ได้ไหม → {fits, need, bud, spill, prof, shared} หรือ null (บอกล่วงหน้าไม่ได้)
   ใช้ตัวเลขของแผนเอง (prof) เมื่อผลตอนเปิดครั้งล่าสุดคือแผนเดียวกับที่จะได้: โมเดลนี้เป็นอัตโนมัติทั้งในไฟล์และในฟอร์ม
   และโมเดลหลักยังเลือกเหมือนเดิม (ส่วนที่จองบนการ์ดร่วมไม่เปลี่ยน) — ไม่งั้นคิดจาก need_gib เทียบงบที่หักส่วนจองแล้ว */
function gdAutoEst(r, a) {
  var e = r.effective, p = gdPrimary();
  var same = e && (e.source === 'auto' || e.source === 'user-ini') && gdVal(r.choice) === 'auto' &&
    (!p || p === r || (GD.form[p.id] || 'auto') === gdVal(p.choice));
  if (same && e.est_vram_gib != null && typeof e.fits_fully === 'boolean') {
    var pr = !r.primary && e.shared_with_primary ? gdReserve() : null;
    return { fits: e.fits_fully, need: e.est_vram_gib, bud: null, prof: true, shared: !!pr, res: pr,
      spill: e.est_gpu_gib != null ? Math.max(0, e.est_vram_gib - e.est_gpu_gib) : null };
  }
  if (!a.device_keys || !a.device_keys.length || !a.device_keys.every(gdDev)) return null;
  var o = gdWithUi(r, a.ctx, a.vision), need = gdNeedAt(r, o.ctx, o.vision);
  if (need == null) return null;
  var res = r.primary ? null : gdReserve(), bud = gdBudgetFor(r, a.device_keys, res);
  return { fits: need <= bud, need: need, bud: bud, spill: Math.max(0, need - bud), prof: false,
    shared: !!(res && a.device_keys.indexOf(res.key) >= 0), res: res };
}
function gdAutoFits(r, a) { var x = gdAutoEst(r, a); return x ? x.fits : null; }
/* ท้ายคำแนะนำ: บริบท/การรองรับภาพที่จะได้ (ไม่บอกเมื่อเป็นค่าปกติ 32K ไม่ดูรูป) */
function gdCtxNote(n) {
  if (n.ctx === 32768 && !n.vision) return '';
  if (n.ctx === 65536) return ' · ' + t(n.vision ? 'gpu_fit_64kv' : 'gpu_fit_64k');
  return ' · ' + fmt(t('gpu_ctx'), gpuCtx(n.ctx)) + (n.vision ? ' + ' + t('gpu_vision') : '');
}
function gdSharedNote(res) { return res ? ' · ' + fmt(t('gpu_fit_shared'), gdKeyShort(res.key)) : ''; }
/* คำแนะนำใต้ตัวเลือก: ok = ใส่ได้ทั้งตัว, spill = ล้นไป CPU (ช้าลง), cpu = CPU ล้วน (ช้าสุด), '' = บอกล่วงหน้าไม่ได้ */
function gdFit(r) {
  var v = GD.form[r.id] || 'auto', e = r.effective;
  /* user.ini ตั้ง device ของโมเดลนี้เอง = ตัวเลือกในหน้านี้ไม่เปลี่ยนการ์ดที่ใช้ (หมายเหตุบอกไว้แล้ว) — บอกตามที่ใช้จริง
     (ตัวเลขของแผนหลัง merge user.ini) ไม่ใช่ของการ์ดที่เลือก/ที่อัตโนมัติจะเลือก */
  if (gdUiHas(r, 'device') && e && e.source === 'user-ini' && e.est_vram_gib != null && typeof e.fits_fully === 'boolean') {
    if (e.devices_short && !e.devices_short.length) return { cls: 'cpu', text: t('gpu_fit_cpu') };
    return e.fits_fully ? { cls: 'ok', text: fmtN(t('gpu_fit_ok_auto'), gdGb(e.est_vram_gib)) }
      : { cls: 'spill', text: fmtN(t('gpu_fit_spill'), gdGb(Math.max(0, e.est_vram_gib - (e.est_gpu_gib || 0)))) };
  }
  if (v === 'cpu') return { cls: 'cpu', text: t('gpu_fit_cpu') };
  var keys = gdKeys(v);
  if (!keys) {
    /* อัตโนมัติ: ตัวเลขของแผนเองถ้ายังเป็นแผนเดียวกัน ไม่งั้นคิดจาก need_gib เทียบงบ (gdAutoEst) */
    var a = gdAuto(r);
    if (!a) return { cls: '', text: t('gpu_fit_auto') };
    if (!a.devices_short.length) return { cls: 'cpu', text: t('gpu_fit_cpu') };
    var x = gdAutoEst(r, a);
    if (!x) return { cls: '', text: t('gpu_fit_auto') };
    var sh = x.shared ? gdSharedNote(x.res) : '';
    if (x.fits) {
      return { cls: 'ok', text: (x.bud == null ? fmtN(t('gpu_fit_ok_auto'), gdGb(x.need)) : fmtN(t('gpu_fit_ok'), gdGb(x.need), gdGb(x.bud))) + sh };
    }
    return x.spill == null ? { cls: '', text: t('gpu_fit_auto') } : { cls: 'spill', text: fmtN(t('gpu_fit_spill'), gdGb(x.spill)) + sh };
  }
  var live = keys.filter(gdDev);
  /* การ์ดที่เลือกไม่ได้ต่ออยู่เลย — หมายเหตุสีเหลืองใต้ตัวเลือกบอกแล้วว่าจะใช้อัตโนมัติแทน ไม่ต้องซ้ำ */
  if (!live.length) return gdLive().state === 'ok' ? null : { cls: '', text: t('gpu_fit_nodetect') };
  var need = gdNeed(r, live);
  if (!need) return { cls: '', text: t('gpu_fit_unknown') };
  var res = r.primary ? null : gdReserve(), bud = gdBudgetFor(r, live, res);
  var tail = res && live.indexOf(res.key) >= 0 ? gdSharedNote(res) : '';
  if (need.gib <= bud) return { cls: 'ok', text: fmtN(t('gpu_fit_ok'), gdGb(need.gib), gdGb(bud)) + gdCtxNote(need) + tail };
  return { cls: 'spill', text: fmtN(t('gpu_fit_spill'), gdGb(need.gib - bud)) + tail };
}
function gdNotes(r) {
  var out = [], e = r.effective, v = GD.form[r.id] || 'auto', keys = gdKeys(v), miss = [];
  if (keys && gdLive().state === 'ok') {
    miss = keys.filter(function (k) { return !gdDev(k); });
    if (miss.length) out.push(['warn', fmt(t(miss.length === keys.length ? 'gpu_note_missing_now' : 'gpu_note_missing_part'),
      gdList(miss.map(gdKeyShort)))]);
  }
  /* ผลตอนเปิดครั้งล่าสุด (จากโปรไฟล์) — เฉพาะเมื่อตัวเลือกในฟอร์มยังเป็นค่าที่บันทึกไว้ (เปลี่ยนแล้ว/คืนเป็นอัตโนมัติ = ไม่เกี่ยวแล้ว)
     และยังไม่มีหมายเหตุ "ตอนนี้ไม่พบ" ที่บอกเรื่องเดียวกัน */
  var saved = keys && GD.form[r.id] === gdVal(r.choice) && !miss.length;
  if (e && saved && e.choice_missing) out.push(['warn', t('gpu_note_missing_then')]);
  else if (e && saved && e.choice_dropped && e.choice_dropped.length) {
    out.push(['warn', fmt(t('gpu_note_dropped_then'), gdList(e.choice_dropped.map(gdKeyShort)))]);
  }
  /* models-preset.user.ini — บอกตามสิ่งที่ไฟล์ตั้งไว้จริง: device = GPU ที่เลือกในหน้านี้ไม่มีผล (เตือน)
     ctx-size / mmproj = เปลี่ยนแค่บริบทกับการรองรับภาพ GPU ยังเป็นตามที่เลือก (ข้อมูล) — เดิมขึ้น "มีผลเหนือตัวเลือกนี้"
     ทุกครั้งที่ source เป็น user-ini แม้ไฟล์ตั้งแค่ ctx-size และแม้โมเดลนั้นเป็นอัตโนมัติ (ไม่มีตัวเลือกให้ทับ) */
  if ('user_ini' in r) {
    if (gdUiHas(r, 'device')) out.push(v !== 'auto' ? ['warn', t('gpu_note_userini_dev')] : ['info', t('gpu_note_userini_devauto')]);
    if (gdUiHas(r, 'ctx-size') || gdUiHas(r, 'mmproj')) out.push(['info', t('gpu_note_userini_opts')]);
  } else if (e && e.choice_overridden) out.push(['warn', t('gpu_note_userini_dev')]);
  else if (e && e.source === 'user-ini') out.push(['info', t('gpu_note_userini_opts')]);
  return out;
}
/* เตือน (ไม่ห้าม) เมื่อสองโมเดลขึ้นไปใช้การ์ดใบเดียวกันแล้วรวมกันเกินงบของใบ — router โหลดพร้อมกันได้สองตัว
   นับโมเดลที่ตรึงไว้ในหน้านี้ + โมเดลหลักที่เป็นอัตโนมัติแต่จะจองการ์ดใบนั้น (ตรึงโมเดลเดียวไว้การ์ดของโมเดลหลักก็ต้องเตือน)
   ส่วนของแต่ละโมเดลบนใบนั้นคิดตามสัดส่วนงบของการ์ดที่มันใช้ และไม่เกินงบของใบ (ที่เกินล้นไป CPU อยู่แล้ว) */
function gdConflicts() {
  var per = Object.create(null), out = [], counted = Object.create(null);
  (GD.data.models || []).forEach(function (r) {
    var ks = gdKeys(GD.form[r.id] || 'auto');
    if (!ks) return;
    var live = ks.filter(gdDev), need = live.length ? gdNeed(r, live) : null;
    if (!need) return;
    counted[r.id] = true;
    var tot = gdBudget(live);
    live.forEach(function (k) {
      var b = (gdDev(k).budget_mib || 0) / 1024;
      (per[k] = per[k] || []).push({ r: r, gib: tot > 0 ? Math.min(b, need.gib * b / tot) : 0 });
    });
  });
  var res = gdReserve();
  if (res && !counted[res.row.id] && per[res.key]) {
    per[res.key].unshift({ r: res.row, gib: Math.min((gdDev(res.key).budget_mib || 0) / 1024, res.gib) });
  }
  Object.keys(per).forEach(function (k) {
    var l = per[k], b = (gdDev(k).budget_mib || 0) / 1024;
    var sum = l.reduce(function (a, x) { return a + x.gib; }, 0);
    if (l.length > 1 && sum > b + 0.05) {
      out.push(fmtN(t('gpu_conflict'), gdList(l.map(function (x) { return x.r.short; })), gdKeyShort(k), gdGb(sum), gdGb(b)));
    }
  });
  return out;
}
/* "ตอนนี้: RTX 1000 Ada + CPU · บริบท 32K" — ที่ router ใช้จริงตอนเปิดครั้งล่าสุด (GPU เปลี่ยนแล้ว = "ตอนเปิดครั้งล่าสุด:")
   คำเดียวกับเมนูบัญชี (gpu_ctx, gpu_vision) — สิ่งเดียวกันต้องไม่เรียกสองแบบในหน้าต่างเดียว */
function gdEff(r) {
  var e = r.effective;
  if (!e) return '';
  var s = (e.devices_short ? gpuDev({ devices_short: e.devices_short, fits_fully: e.fits_fully }, true) : t('gpu_auto')) +
    (e.ctx ? ' · ' + fmt(t('gpu_ctx'), gpuCtx(e.ctx)) : '') + (e.vision ? ' · ' + t('gpu_vision') : '') +
    (e.source === 'choice' ? ' · ' + t('gpu_now_chosen') : '');
  return fmt(t(gdLive().stale ? 'gpu_then' : 'gpu_now'), s);
}
function gdOptions(r, devs) {
  var a = gdAuto(r), auto = t('gpu_opt_auto');
  if (a) auto += ' — ' + gpuDev({ devices_short: a.devices_short, fits_fully: gdAutoFits(r, a) }, true);
  var o = [['auto', auto]];
  devs.forEach(function (d) { o.push([JSON.stringify([d.key]), gdShort(d) + ' · ' + gdVram(d.total_mib)]); });
  if (devs.length > 1) gdCombos(devs).forEach(function (c) {
    o.push([JSON.stringify(c.map(function (d) { return d.key; })),
      c.map(gdShort).join(' + ') + ' · ' + gdVram(c.reduce(function (a, d) { return a + (d.total_mib || 0); }, 0))]);
  });
  /* ค่าที่บันทึกไว้ของการ์ดที่ถอดอยู่ (หรือค่าที่เลือกค้างไว้ก่อนกดตรวจใหม่) ยังเลือกคงไว้ได้ — ไม่ถูกเปลี่ยนเป็นอัตโนมัติเงียบๆ */
  [gdVal(r.choice), GD.form[r.id]].forEach(function (v) {
    var ks = gdKeys(v);
    if (!ks || o.some(function (x) { return x[0] === v; })) return;
    o.push([v, ks.map(function (k) { return gdKeyShort(k) + (gdDev(k) ? '' : ' (' + t('gpu_not_connected') + ')'); }).join(' + ')]);
  });
  o.push(['cpu', t('gpu_opt_cpu')]);
  return o;
}
function gdRow(r, i, devs) {
  var id = 'gm' + i, v = GD.form[r.id] || 'auto', eff = gdEff(r);
  /* คำอธิบายของตัวเลือกเป็นกล่องซ่อนกล่องเดียว (gdPaintHints เติม) ประโยคคั่นด้วยจุด — เดิมชี้ไปสามกล่องที่เห็นบนจอ
     โปรแกรมอ่านหน้าจออ่านต่อกันเป็นประโยคเดียว ("…ตามที่เลือก ใส่ลง GPU ได้…") และไม่บอกว่าตัวไหนเป็นโมเดลหลัก */
  var sel = el('select', { id: id + 's', 'aria-describedby': id + 'd' });
  gdOptions(r, devs).forEach(function (o) { sel.append(el('option', { value: o[0], text: o[1] })); });
  sel.value = v;
  if (sel.value !== v) { sel.value = 'auto'; GD.form[r.id] = 'auto'; }
  sel.addEventListener('change', function () { GD.form[r.id] = sel.value; if (GD.flash) gdFlash(''); gdPaintHints(); });
  return el('div', { class: 'gm' }, [
    el('div', { class: 'gm-h' }, [
      el('label', { class: 'gm-name', for: id + 's', text: r.short, title: r.id, lang: 'en' }),
      r.primary ? el('span', { class: 'gm-badge', id: id + 'b', text: t('gpu_primary') }) : null,
      el('span', { class: 'gm-eff', id: id + 'e', text: eff, title: eff || null })
    ]),
    el('div', { class: 'sel' }, [sel, icon('chevron', 'ic-sm')]),
    el('div', { class: 'gm-fit', id: id + 'f' }),
    el('div', { class: 'gm-notes', id: id + 'n' }),
    el('span', { id: id + 'd', hidden: true })
  ]);
}
/* ประโยคของคำอธิบาย — ตัดจุดท้ายเดิมก่อนต่อ ไม่ให้เป็น ".." */
function gdSentences(parts) {
  return parts.filter(Boolean).map(function (s) { return String(s).replace(/[\s.]+$/, ''); }).join('. ') + '.';
}
function gdPaintHints() {
  if (!GD.data) return;
  (GD.data.models || []).forEach(function (r, i) {
    var f = document.getElementById('gm' + i + 'f'), n = document.getElementById('gm' + i + 'n'), d = document.getElementById('gm' + i + 'd');
    if (!f || !n) return;
    var fit = gdFit(r), notes = gdNotes(r);
    f.className = 'gm-fit' + (fit && fit.cls ? ' ' + fit.cls : '');
    f.replaceChildren.apply(f, fit ? [el('i', { 'aria-hidden': 'true' }), el('span', { text: fit.text })] : []);
    n.replaceChildren.apply(n, notes.map(function (x) {
      return el('div', { class: 'gm-note ' + x[0] }, [icon(x[0] === 'warn' ? 'alert' : 'info', 'ic-xs'), el('span', { text: x[1] })]);
    }));
    if (d) setText(d, gdSentences([r.primary ? t('gpu_primary_desc') : '', gdEff(r), fit && fit.text].concat(notes.map(function (x) { return x[1]; }))));
  });
  var c = document.getElementById('gdConf');
  if (c) c.replaceChildren.apply(c, gdConflicts().map(function (s) {
    return el('div', { class: 'gd-msg warn' }, [icon('alert', 'ic-sm'), el('span', { text: s })]);
  }));
}
function gdRender() {
  /* วาดใหม่ทั้งก้อน (เปิด, ตรวจใหม่, งานจบ) — คืนโฟกัสให้ตัวเดิมตาม id ไม่ให้หล่นไป <body> */
  var a = document.activeElement, keep = a && GD.body.contains(a) && a.id ? a.id : '';
  var d = GD.data, kids = [];
  if (!d) {
    kids.push(GD.loadErr
      ? el('div', { class: 'gd-sec' }, [el('div', { class: 'gd-msg bad' }, [icon('alert', 'ic-sm'), el('div', { class: 'gd-msg-c' }, [
          el('div', { text: t('gpu_err_load') }),
          el('button', { type: 'button', class: 'btn btn-ghost sm', id: 'gdRetry', style: 'margin-top:8px', text: t('gpu_retry'),
            onclick: function () { gdLoad(false, true); } })])])])
      : el('div', { class: 'gd-loading' }, [el('span', { class: 'gd-spin', 'aria-hidden': 'true' }), el('span', { text: t('gpu_loading') })]));
    GD.body.replaceChildren.apply(GD.body, kids);
    setAttr(GD.body, 'aria-busy', GD.loadErr ? null : 'true');
    gdPaintFoot();
    return;
  }
  var lv = gdLive(), devs = gdDevs(), models = d.models || [];
  if (lv.stale) kids.push(el('div', { class: 'gd-msg warn gd-stale' }, [icon('alert', 'ic-sm'), el('span', { text: t('gpu_stale_banner') })]));
  var devBody = devs.length
    ? el('div', { class: 'gd-devs', role: 'list', 'aria-labelledby': 'gdDevH' }, devs.map(function (x) {
        return el('div', { class: 'gd-dev', role: 'listitem' }, [
          el('span', { class: 'gd-dev-ic', 'aria-hidden': 'true' }, [icon('chip', 'ic-sm')]),
          el('span', { class: 'gd-dev-t' }, [
            el('span', { class: 'gd-dev-n', text: gdShort(x), title: x.name || x.key, lang: 'en' }),
            el('span', { class: 'gd-dev-m', text: gdVram(x.total_mib) + ' · ' + t(x.external ? 'gpu_external' : 'gpu_internal') })])
        ]);
      }))
    : el('div', { class: 'gd-msg' }, [icon('info', 'ic-sm'),
        el('span', { text: t(lv.state === 'ok' ? 'gpu_no_gpu' : lv.detecting ? 'gpu_detecting_long' : 'gpu_detect_fail') })]);
  kids.push(el('section', { class: 'gd-sec', 'aria-labelledby': 'gdDevH' }, [
    el('div', { class: 'gd-sec-h' }, [el('h3', { id: 'gdDevH', text: t('gpu_devs_h') }),
      el('button', { type: 'button', class: 'btn btn-ghost sm', id: 'gdRedetect', 'aria-busy': lv.detecting ? 'true' : null,
        onclick: function () { gdLoad(true); } }, [icon('refresh', 'ic-sm'), el('span', { text: t(lv.detecting ? 'gpu_detecting' : 'gpu_redetect') })])]),
    devBody
  ]));
  kids.push(el('section', { class: 'gd-sec', 'aria-labelledby': 'gdModH' }, [
    el('div', { class: 'gd-sec-h' }, [el('h3', { id: 'gdModH', text: t('gpu_models_h') })]),
    models.length ? el('div', { class: 'gd-models' }, models.map(function (r, i) { return gdRow(r, i, devs); }))
      : el('div', { class: 'gd-msg' }, [icon('info', 'ic-sm'), el('span', { text: t('gpu_no_models') })]),
    el('div', { class: 'gd-conf', id: 'gdConf' })
  ]));
  GD.body.replaceChildren.apply(GD.body, kids);
  setAttr(GD.body, 'aria-busy', null);
  gdPaintHints();
  gdPaintFoot();
  if (keep && gpuOpen()) {
    var n = document.getElementById(keep);
    if (n && !n.disabled) n.focus({ preventScroll: true });
    else if (focusLost()) GD.box.focus();
  }
}
function gdElapsed() {
  var s = Math.max(0, Math.round((Date.now() - GD.t0) / 1000));
  return fmt(t('gpu_elapsed'), Math.floor(s / 60) + ':' + ('0' + s % 60).slice(-2)) + ' · ' + t('gpu_applying_hint');
}
/* หัวข้อของกล่องความคืบหน้า — ตัวเปิดกำลังรอแชตที่ตอบอยู่ (ยังไม่ได้รีสตาร์ตอะไร อาจนานถึง 3 นาที) ต้องไม่บอกว่า "กำลังรีสตาร์ต" */
function gdHeadText() { return t(GD.phase === 'waiting' ? 'gpu_waiting' : 'gpu_applying'); }
/* ข้อความชั่วคราวในหน้าต่าง (แทน toast ที่จะไปทับแถวปุ่ม) — หายเองตามความยาว, เมื่อเปลี่ยนตัวเลือก หรือเมื่อปิดหน้าต่าง
   msg ว่าง = ล้าง  อ่านให้โปรแกรมอ่านหน้าจอทางช่องเดียวกับ toast (announce) */
function gdFlash(msg, bad) {
  clearTimeout(GD.flashT);
  msg = String(msg || '');
  GD.flash = msg ? { text: msg, bad: !!bad } : null;
  if (gpuOpen()) gdPaintStatus();
  if (!msg) return;
  announce(msg, bad);
  GD.flashT = setTimeout(function () { GD.flash = null; if (gpuOpen()) gdPaintStatus(); },
    Math.min(12000, (bad ? 7000 : 4500) + msg.length * 30));
}
function gdPaintStatus() {
  var kids = [];
  if (GD.busy || GD.job === 'running') {
    kids.push(el('div', { class: 'gd-msg' }, [el('span', { class: 'gd-spin', 'aria-hidden': 'true' }),
      el('div', { class: 'gd-prog-t gd-msg-c' }, [
        el('span', { id: 'gdHead', text: gdHeadText() }),
        el('span', { class: 'gd-prog-l', id: 'gdLine', text: GD.line, hidden: !GD.line }),
        el('span', { class: 'gd-prog-e', id: 'gdElapsed', text: gdElapsed() })])]));
  } else if (GD.job === 'busy') {
    kids.push(el('div', { class: 'gd-msg warn' }, [icon('alert', 'ic-sm'), el('span', { class: 'gd-msg-c', text: t('gpu_busy') })]));
  } else if (GD.job === 'failed' || GD.job === 'unknown') {
    /* unknown = hub ถูกเปิดใหม่ระหว่างงานและบันทึกไม่มีบรรทัดผลลัพธ์ — ไม่รู้จริงๆ ห้ามบอกว่าล้ม (สีเหลือง ไม่ใช่แดง) */
    var pre = GD.tail.join('\n'), unk = GD.job === 'unknown';
    kids.push(el('div', { class: 'gd-msg ' + (unk ? 'warn' : 'bad') }, [icon('alert', 'ic-sm'), el('div', { class: 'gd-msg-c' }, [
      el('div', { text: t(unk ? 'gpu_unknown' : 'gpu_apply_failed') }),
      GD.still ? el('div', { text: t('gpu_still_running') }) : null,
      pre ? el('details', { class: 'gd-log' }, [el('summary', { text: fmt(t('gpu_log'), GD.logName || 'gpu-apply.log') }),
        el('pre', { text: pre, tabindex: '0', lang: /[฀-๿]/.test(pre) ? 'th' : 'en' })]) : null])]));
  }
  if (GD.flash) {
    kids.push(el('div', { class: 'gd-msg gd-flash' + (GD.flash.bad ? ' bad' : '') }, [icon(GD.flash.bad ? 'alert' : 'info', 'ic-sm'),
      el('span', { class: 'gd-msg-c', text: GD.flash.text })]));
  }
  GD.status.replaceChildren.apply(GD.status, kids);
}
function gdPaintFoot() {
  var run = GD.busy || GD.job === 'running', ready = !!GD.data;
  GD.reset.disabled = run || !ready;
  GD.apply.disabled = run || !ready;
  /* โมเดลกำลังตอบในแท็บนี้: ปุ่มยังโฟกัส/กดได้ แต่กดแล้วบอกให้รอ (aria-disabled) — รีสตาร์ตตอนนี้คำตอบจะขาดกลางคัน */
  setAttr(GD.apply, 'aria-disabled', !run && ready && streaming() ? 'true' : null);
  setText(GD.cancel, t(run ? 'close' : 'cancel'));
  /* ระหว่างทำ/มีผลค้าง (รอแชต, ล้ม, ไม่ทราบผล) กล่องสถานะบอกเรื่องเดียวกันแล้ว — ซ่อนคำอธิบายไว้ ส่วนท้ายจะได้ไม่เบียดรายการโมเดล
     (ปุ่มบันทึกยังอ้างถึงผ่าน aria-describedby ได้ ข้อความที่ซ่อนยังถูกอ่านเป็นคำอธิบาย) */
  setHidden(GD.confirm, run || GD.job === 'busy' || GD.job === 'failed' || GD.job === 'unknown');
  [].forEach.call(GD.body.querySelectorAll('select, #gdRedetect'), function (x) { if (x.disabled !== run) x.disabled = run; });
  if (ready) setAttr(GD.body, 'aria-busy', run ? 'true' : null);
}
function gdReadable(s) {
  /* PowerShell 5.1 ส่งอักษรไทยลงไฟล์เป็น "?" (code page ของคอนโซล) — บรรทัดแบบนั้นไม่ต้องโชว์ระหว่างรอ */
  s = String(s || '');
  return !!s && (s.match(/\?/g) || []).length <= s.length * 0.2;
}
function gdTakeJob(j) {
  var was = GD.job, phase = GD.phase;
  GD.job = 'running'; GD.busy = false;
  GD.phase = j.phase || '';
  GD.tail = j.tail || []; GD.logName = j.log || GD.logName;
  var last = GD.tail.length ? GD.tail[GD.tail.length - 1] : '';
  GD.line = gdReadable(last) ? last : '';
  if (typeof j.elapsed_s === 'number') GD.t0 = Date.now() - j.elapsed_s * 1000;
  if (was !== 'running') gdPaintStatus();
  else {
    var l = document.getElementById('gdLine'), h = document.getElementById('gdHead');
    if (l) { setText(l, GD.line); setHidden(l, !GD.line); }
    if (h) setText(h, gdHeadText());
  }
  /* เข้า/ออกจากช่วงรอแชต — หัวข้อเปลี่ยนเงียบๆ บนจอ บอกโปรแกรมอ่านหน้าจอด้วย */
  if (was === 'running' && phase !== GD.phase && gpuOpen()) announce(gdHeadText());
  gdPaintFoot();
}
function gdPoll() {
  clearTimeout(GD.pollT);
  GD.pollT = setTimeout(function () {
    /* live=0: ไม่สั่งตรวจ GPU ระหว่างที่ตัวเปิดกำลังใช้การ์ดอยู่ — ขอแค่สถานะงาน */
    api(HUB + '/api/gpu?live=0').then(function (d) {
      GD.pollErr = 0;
      var j = (d && d.job) || {};
      if (j.state === 'running') { gdTakeJob(j); gdPoll(); return; }
      gdEnded(j, d);
    }, function () {
      if (++GD.pollErr < 40) { gdPoll(); return; }
      GD.watch = false; GD.job = null;
      gdPaintStatus(); gdPaintFoot();
      toast(t('hubdown'), true);
    });
  }, 1500);
}
/* งานจบ (หรือ hub ไม่รู้จักงานนั้นแล้ว) — done / busy / failed ตามรหัสจบของตัวเปิด
   สถานะอื่น (idle = hub ถูกเปิดใหม่และไม่พบสถานะงานเดิม, unknown = บันทึกไม่มีบรรทัดผลลัพธ์) = "ไม่ทราบผล" ไม่ใช่ "ล้ม"
   done ที่ไม่ได้รีสตาร์ตจริง (restarted: false = GPU และค่าตั้งเหมือนเดิม) ต้องไม่บอกว่า "ใช้การตั้งค่าใหม่แล้ว" */
function gdEnded(j, d) {
  var watched = GD.watch;
  GD.watch = false;
  if (d) GD.data = d;
  GD.tail = j.tail || []; GD.logName = j.log || GD.logName; GD.jobAt = Date.now();
  GD.phase = ''; GD.still = !!j.still_running;
  refreshHub();       // สถานะโมเดล + GPU ในแถบข้างตามผลใหม่ทันที ไม่ต้องรอรอบ 10 วินาที
  if (!watched) GD.job = null;
  else if (j.state === 'done') {
    GD.job = null;
    var same = j.restarted === false;
    /* ปิดหน้าต่างก่อน toast — ระหว่างที่หน้าต่างเปิดอยู่ toast ถูกส่งเข้ากล่องในหน้าต่าง (ซึ่งกำลังจะปิด) */
    closeGpu();
    toast(t(same ? 'gpu_done_same' : 'gpu_done'));
    if (!same) recoverFrame();
    return;
  } else {
    GD.job = j.state === 'busy' ? 'busy' : j.state === 'failed' ? 'failed' : 'unknown';
    var msg = t(GD.job === 'busy' ? 'gpu_busy' : GD.job === 'unknown' ? 'gpu_unknown' : gpuOpen() ? 'gpu_apply_failed' : 'gpu_failed_toast');
    if (gpuOpen()) announce(msg, GD.job === 'failed'); else toast(msg, GD.job !== 'unknown');
  }
  if (!gpuOpen()) return;
  gdRender(); gdPaintStatus(); gdPaintFoot();
}
function gdLoad(refresh, first) {
  var mine = ++GD.seq;
  if (first) { GD.data = null; GD.loadErr = false; gdRender(); gdPaintStatus(); }
  else if (refresh) {
    var rb = document.getElementById('gdRedetect');
    if (rb) { setAttr(rb, 'aria-busy', 'true'); var sp = rb.querySelector('span'); if (sp) setText(sp, t('gpu_detecting')); }
  }
  api(HUB + '/api/gpu' + (refresh ? '?refresh=1' : '')).then(function (d) {
    if (mine !== GD.seq || !gpuOpen() || !d) return;
    GD.loadErr = false;
    GD.data = d;
    if (first) GD.form = {};
    (d.models || []).forEach(function (r) { if (!own(GD.form, r.id)) GD.form[r.id] = gdVal(r.choice); });
    var j = d.job || {};
    if (j.state === 'running') { GD.watch = true; gdTakeJob(j); gdPoll(); }
    gdRender();
    if (first) gdFocusFirst();
    /* ตรวจ GPU ครั้งแรกยังไม่เสร็จ (eGPU ที่เพิ่งเสียบ init ช้า) — ถามซ้ำจนได้ผล โดยไม่สั่งตรวจซ้อน */
    if (d.live && d.live.detecting && GD.tries++ < 10) setTimeout(function () { if (gpuOpen() && mine === GD.seq) gdLoad(false); }, 2000);
  }).catch(function (e) {
    if (mine !== GD.seq || !gpuOpen()) return;
    if (!GD.data) {
      try { console.warn('[qwen]', e); } catch (x) {}
      GD.loadErr = true; gdRender();
      var rt = document.getElementById('gdRetry');
      if (rt) rt.focus();
    } else { failToast(t('gpu_err_load'), e); gdRender(); }
  });
}
function gdFocusFirst() {
  if (!gpuOpen()) return;
  var a = document.activeElement;
  if (a && a !== GD.box && GD.box.contains(a)) return;     // ผู้ใช้ย้ายโฟกัสเองระหว่างโหลดแล้ว
  var tgt = GD.focusApply && !GD.apply.disabled ? GD.apply : GD.body.querySelector('select:not(:disabled)') || GD.apply;
  if (tgt && !tgt.disabled) tgt.focus();
}
/* เปิดจาก: รายการ "เลือก GPU…" ในเมนูบัญชี, ก้อน GPU ในหัวเมนู, ปุ่ม "ใช้ GPU ใหม่" ในคำเตือน (apply: โฟกัสปุ่มบันทึก) */
function openGpu(opts) {
  opts = opts || {};
  if (!dlg.wrap.hidden || gpuOpen() || pdOpen()) return;
  if (artModal()) closeArt(true);
  var back = document.activeElement;
  closeMenu(); hideTip();
  /* เปิดจากรายการในเมนู: ปุ่มนั้นถูกซ่อนไปแล้ว — คืนโฟกัสให้ปุ่มที่เปิดเมนู (lastBack) แทน */
  if (!back || back === body || menu.contains(back) || !shown(back)) back = lastBack;
  if (isMobile()) closeDrawer();
  if (panelOpen()) closePanel(true);
  unpeek();
  GD.back = back;
  GD.focusApply = !!opts.apply;
  GD.tries = 0;
  if (GD.job && GD.job !== 'running' && Date.now() - GD.jobAt > 600000) GD.job = null;   // ผลเก่ากว่า 10 นาทีไม่ต้องโชว์ค้าง
  clearTimeout(GD.flashT); GD.flash = null;
  GD.wrap.hidden = false;
  /* เป็น modal จริง: หน้าข้างหลังทั้งหมด (แถบข้าง ส่วนหัว iframe) inert — Tab/โปรแกรมอ่านหน้าจอเข้าไม่ถึง */
  $('#app').inert = true;
  GD.box.focus();
  requestAnimationFrame(function () { GD.wrap.classList.add('on'); });
  gdLoad(false, true);
  clearInterval(GD.tick);
  GD.tick = setInterval(function () {
    if (!gpuOpen()) return;
    gdPaintFoot();
    var e = document.getElementById('gdElapsed');
    if (e) setText(e, gdElapsed());
  }, 1000);
}
function closeGpu() {
  if (!gpuOpen()) return;
  GD.seq++;                       // ผลโหลดที่ยังค้างอยู่ไม่ต้องวาดแล้ว (งานที่สั่งไปยังถูกติดตามต่อ แม้ปิดหน้าต่าง)
  clearTimeout(GD.flashT); GD.flash = null;
  GD.wrap.classList.remove('on');
  GD.wrap.hidden = true;
  $('#app').inert = false;
  clearInterval(GD.tick); GD.tick = 0;
  var back = GD.back;
  GD.back = null;
  /* visible ไม่ใช่ shown: เปิดจากเมนูในลิ้นชักบนจอแคบ ลิ้นชักปิดไปแล้ว ปุ่มบัญชีโฟกัสไม่ได้ — ไปปุ่มแฮมเบอร์เกอร์แทน */
  if (!back || back === body || !visible(back)) back = [$('#acctBtn'), $('#burger'), $('#hdrNew')].filter(visible)[0];
  if (back) { try { back.focus(); } catch (e) {} }
}
function gdSave() {
  if (!GD.data || GD.busy || GD.job === 'running') return;
  if (streaming()) { toast(t('gpu_wait_stream'), true); return; }
  var models = {};
  (GD.data.models || []).forEach(function (r) {
    var v = GD.form[r.id] || 'auto';
    if (v === 'cpu') models[r.id] = 'cpu';
    else { var k = gdKeys(v); if (k) models[r.id] = k; }
  });
  GD.busy = true; GD.job = null; GD.t0 = Date.now(); GD.line = ''; GD.phase = ''; GD.still = false;
  clearTimeout(GD.flashT); GD.flash = null;
  gdPaintStatus(); gdPaintFoot();
  announce(t('gpu_applying'));
  /* ปุ่มบันทึกเพิ่งถูกปิดใช้ — ย้ายโฟกัสไปปุ่ม "ปิด" ไม่ให้หล่นไป <body> */
  if (gpuOpen()) GD.cancel.focus();
  /* saved = PUT ผ่านแล้ว — ข้อผิดพลาดหลังจากนั้นเป็นของการสั่งรีสตาร์ต ไม่ใช่การบันทึก (เดิมขึ้น "บันทึกไม่สำเร็จ"
     ทั้งที่ตัวเลือกถูกเขียนลงไฟล์แล้ว ผู้ใช้จะกดบันทึกซ้ำโดยไม่จำเป็น) */
  var saved = false;
  api(HUB + '/api/gpu/choice', { method: 'PUT', json: { models: models } }).then(function (d) {
    saved = true;
    if (d && d.models) GD.data = d;       // ตัวเลือกที่บันทึกแล้ว (หมายเหตุ "ตอนเปิดครั้งล่าสุด" เทียบกับค่านี้)
    return api(HUB + '/api/gpu/apply', { method: 'POST', json: {} });
  }).then(function (d) {
    GD.busy = false; GD.watch = true;
    if (d && d.job) gdTakeJob(d.job);
    gdPoll();
  }).catch(function (e) {
    GD.busy = false;
    if (e && e.status === 409) {
      /* มีงานเดิมทำอยู่ (อีกแท็บกดไว้) — ตามดูงานนั้นแทน  PUT ถูกปฏิเสธ (409 ตั้งแต่บันทึก) = ตัวเลือกนี้ยังไม่ถูกบันทึก
         ต้องบอกให้ชัด ไม่งั้นผู้ใช้เข้าใจว่างานที่กำลังทำคือของตัวเลือกใหม่ */
      /* ตัวเลือกยังไม่ถูกบันทึก = ไม่ "เฝ้า" งานนั้น (จบแล้วหน้าต่างไม่ปิดเอง ตัวเลือกในฟอร์มยังอยู่ให้กดบันทึกอีกครั้ง) */
      GD.watch = saved; GD.job = 'running';
      gdPaintStatus(); gdPaintFoot(); toast(t(saved ? 'gpu_err_running' : 'gpu_err_busy_save'), !saved); gdPoll();
      return;
    }
    GD.job = null;
    gdPaintStatus(); gdPaintFoot();
    if (saved) failToast(t('gpu_saved_not_started'), e);
    else failToast(t('gpu_err_save'), e, { 400: 'gpu_err_invalid' });
    if (gpuOpen()) { gdPaintHints(); GD.apply.focus(); }
  });
}
GD.apply.addEventListener('click', function () {
  if (GD.apply.getAttribute('aria-disabled') === 'true' || streaming()) { toast(t('gpu_wait_stream'), true); return; }
  gdSave();
});
GD.reset.addEventListener('click', function () {
  if (!GD.data) return;
  (GD.data.models || []).forEach(function (r) { GD.form[r.id] = 'auto'; });
  [].forEach.call(GD.body.querySelectorAll('.gm select'), function (s) { s.value = 'auto'; });
  gdPaintHints();
  announce(t('gpu_reset_done'));
});
GD.cancel.addEventListener('click', function () { closeGpu(); });
$('#gdClose').addEventListener('click', function () { closeGpu(); });
/* คลิกม่าน = ปิด (งานที่สั่งไปแล้วทำต่อเบื้องหลัง) — mousedown ไม่ใช่ click: ลากเลือกข้อความในกล่องแล้วปล่อยนอกกล่องต้องไม่ปิด */
GD.wrap.addEventListener('mousedown', function (e) { if (e.target === GD.wrap) { e.preventDefault(); closeGpu(); } });
/* กัน Tab หลุดออกไปหลังม่าน — วนเฉพาะสิ่งที่กดได้และมองเห็นในหน้าต่าง */
GD.wrap.addEventListener('keydown', function (e) {
  if (e.key !== 'Tab') return;
  var f = [].slice.call(GD.box.querySelectorAll('button, select, summary, [tabindex="0"]')).filter(function (x) {
    return !x.disabled && x.getAttribute('tabindex') !== '-1' && visible(x);
  });
  if (!f.length) { e.preventDefault(); return; }
  var i = f.indexOf(document.activeElement);
  if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
  else if (!e.shiftKey && (i < 0 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
});
/* หลังรีสตาร์ต router: WebUI ที่ถาม /props ไม่ได้ระหว่างนั้นค้างป้าย "Server unavailable" (มีปุ่ม Retry) เหนือช่องพิมพ์
   กด Retry ให้ก่อน (ไม่โหลดหน้าใหม่ แชตที่เปิดอยู่คงเดิม) ถ้ายังไม่หายค่อยโหลด iframe ใหม่ที่แชตเดิม — ข้ามถ้ากำลังตอบ
   ทดสอบแล้ว: Retry ของ WebUI วาดช่องพิมพ์ใหม่ทั้งอัน ข้อความที่พิมพ์ค้างหาย — จำไว้ก่อนกดแล้วเติมคืน
   (ทางโหลดใหม่ก็พกไปเติมคืนด้วยกลไกเดียวกับตอนสลับภาษา) ไฟล์ที่แนบค้างในช่องพิมพ์ WebUI ทิ้งเองตอนวาดใหม่ เก็บคืนไม่ได้
   ป้ายอาจโผล่หลังรีสตาร์ตเสร็จไม่กี่วินาที (WebUI ถามเซิร์ฟเวอร์เป็นรอบ) จึงดูซ้ำหลายรอบ */
var recoverT = 0;
function frameServerDown() {
  var d;
  try { d = frame.contentDocument; } catch (e) { return null; }
  if (!d || !d.body) return null;
  var al = d.querySelectorAll('[data-slot="alert"], [role="alert"]');
  for (var i = 0; i < al.length; i++) {
    /* ข้อความอาจถูก enhance แปลเป็นไทย และคำทับศัพท์ถูกแทรก U+2060 — ตัดออกก่อนเทียบ */
    var tx = (al[i].textContent || '').replace(/⁠/g, '');
    if (/Server unavailable|เซิร์ฟเวอร์ใช้งานไม่ได้/.test(tx)) return { retry: al[i].querySelector('button') };
  }
  return null;
}
function frameDraft() {
  var ta = composerEl();
  return ta && ta.value.trim() ? ta.value : '';
}
/* เติมข้อความที่พิมพ์ค้างคืนเฉพาะเมื่อช่องพิมพ์ว่าง — ตรวจซ้ำสองสามรอบ เพราะ Svelte อาจวาดช่องพิมพ์ใหม่อีกทีหลังจากนั้น */
function restoreDraft(text) {
  var tries = 0, filled = 0;
  (function step() {
    var ta = composerEl();
    if (!ta) { if (++tries < 30) setTimeout(step, 150); return; }
    if (!ta.value.trim() && filled < 3) { filled++; callEnh('prefill', text); }
    if (++tries < 6) setTimeout(step, 700);
  })();
}
function recoverFrame() {
  clearTimeout(recoverT);
  var waits = [600, 1500, 2500, 4000, 8000], n = 0, clicked = false, keep = '';
  (function check() {
    var down = frameServerDown();
    if (down && !clicked && down.retry && !down.retry.disabled) {
      clicked = true;
      keep = frameDraft();
      try { down.retry.click(); } catch (e) {}
      recoverT = setTimeout(check, 3000);
      return;
    }
    if (down && (clicked || !down.retry)) {
      if (streaming()) return;
      var draft = frameDraft() || keep;
      carryLeft = draft ? { hash: '', draft: draft, focus: '' } : null;
      reloadFrame(currentHash());
      return;
    }
    if (keep) { restoreDraft(keep); keep = ''; }
    if (n < waits.length) recoverT = setTimeout(check, waits[n++]);
  })();
}
/* ---------------------------------------------------------------- สลับภาษา (หัวหน้า + เมนูบัญชี + Alt+Shift+L) */
/* ภาษาเก็บที่ hub จึงมีผลทุกโปรเจกต์ — ข้อความทั้งหน้าเติมจากเซิร์ฟเวอร์ ต้องโหลดหน้าใหม่ทั้งหน้า
   ห้ามทำระหว่างกำลังตอบ (คำตอบที่สตรีมอยู่จะขาดกลางคัน) */
var langSw = $('#langSw'), langBusy = false;
var CARRY_KEY = 'qwen-lang-carry';
/* hash ที่ยอมพากลับหลังโหลดใหม่ — ตรวจเข้มทั้งตอนเก็บและตอนอ่าน: ค่านี้ถูกต่อเข้า src ของ iframe
   ห้ามให้ข้อความอื่น (เช่นที่ถูกแก้ใน sessionStorage) กลายเป็น URL ที่ iframe เปิด */
var CARRY_HASH = /^#\/(chat\/[A-Za-z0-9_-]+|search)?$/;
function langBtns() { return [].slice.call(langSw.querySelectorAll('button[data-lang]')); }
/* ทาสถานะให้ทุกที่ที่แสดงภาษา: สวิตช์บนหัว + แถวภาษาในเมนูบัญชี (ถ้าเปิดค้างอยู่) ให้ตรงกันเสมอ */
function paintLang(v) {
  langBtns().forEach(function (b) {
    var on = b.getAttribute('data-lang') === v;
    setAttr(b, 'aria-pressed', String(on));
    /* คีย์ลัดมีผลเท่ากับกดปุ่มของอีกภาษา — ติด aria-keyshortcuts และป้ายชื่อไว้ที่ปุ่มนั้นปุ่มเดียว */
    setAttr(b, 'aria-keyshortcuts', on ? null : 'Alt+Shift+L');
    setAttr(b, 'data-tip', on ? null : b.getAttribute('data-tip-text'));
  });
  var mb = menu.querySelector('.seg [data-v="th"]');
  if (mb) segSet(mb.closest('.seg'), v);
}
function composerEl() {
  try {
    var d = frame.contentDocument;
    return d.querySelector('.chat-screen-form-wrapper form.conversation-chat-form textarea') || d.querySelector('form textarea');
  } catch (e) { return null; }
}
/* how = ที่มาของคำสั่ง ใช้ตัดสินว่าหลังโหลดใหม่ควรคืนโฟกัสไปที่ใด
   'sw' กดสวิตช์ด้วยคีย์บอร์ด → กลับมาที่สวิตช์ · 'frame' คีย์ลัดจากในหน้าแชต → กลับไปช่องพิมพ์ · '' ไม่ย้าย */
function setLang(v, seg, how) {
  if ((v !== 'th' && v !== 'en') || v === LANG || langBusy) return;
  var had = langSw.contains(document.activeElement);
  var back = function () {
    paintLang(LANG);
    if (seg) segSet(seg, LANG);
    /* จอแคบซ่อนปุ่มของภาษาที่เลือกอยู่ — สลับกลับแล้วปุ่มที่ถือโฟกัสอาจถูกซ่อนไป ให้โฟกัสปุ่มที่ยังเห็น */
    if (had && focusLost()) { var b = langBtns().filter(visible)[0]; if (b) b.focus(); }
  };
  if (streaming()) { back(); toast(t('wait_streaming'), true); return; }
  /* คำสั่งโปรเจกต์ที่แก้ค้างในแผงยังไม่ได้บันทึก — โหลดหน้าใหม่จะทิ้งข้อความนั้นไปเงียบๆ */
  if (instrDirty()) { back(); toast(t('lang_unsaved'), true); return; }
  langBusy = true;
  paintLang(v);
  setAttr(langSw, 'aria-busy', 'true');
  api(HUB + '/api/settings', { method: 'PATCH', json: { lang: v } })
    .then(function () { reloadForLang(how); })
    .catch(function (e) {
      langBusy = false;
      setAttr(langSw, 'aria-busy', null);
      back();
      failToast(t('errlang'), e);
    });
}
/* ก่อนโหลดหน้าใหม่ จำตำแหน่งของผู้ใช้ไว้ใน sessionStorage (ของแท็บนี้เท่านั้น): แชตที่เปิดอยู่ + ข้อความที่พิมพ์ค้าง
   เปลี่ยนภาษาแล้วต้องไม่หลุดกลับไปหน้าแรก หรือทำประโยคที่พิมพ์ไว้ครึ่งหนึ่งหาย */
function reloadForLang(how) {
  var h = frameHash();
  if (!CARRY_HASH.test(h)) h = currentHash();
  var carry = { at: Date.now(), hash: CARRY_HASH.test(h) ? h : '', draft: '', focus: how || '' };
  var ta = composerEl();
  if (ta && ta.value.trim()) carry.draft = ta.value;
  try { sessionStorage.setItem(CARRY_KEY, JSON.stringify(carry)); }
  catch (e) {
    /* ข้อความค้างยาวเกินโควตา — อย่างน้อยพากลับแชตเดิมให้ได้ */
    carry.draft = '';
    try { sessionStorage.setItem(CARRY_KEY, JSON.stringify(carry)); } catch (e2) {}
  }
  /* ?lang= ในลิงก์คือโหมดดูตัวอย่าง (ไม่บันทึก) — ถ้าคงไว้ หน้าจะโหลดกลับมาเป็นภาษาเดิมทั้งที่เพิ่งบันทึกภาษาใหม่ */
  try {
    var u = new URL(location.href);
    if (u.searchParams.has('lang')) {
      u.searchParams.delete('lang');
      history.replaceState(null, '', u.pathname + u.search + u.hash);
    }
  } catch (e) {}
  location.reload();
}
/* อ่านแล้วลบทันที — โหลดหน้าเองครั้งถัดไป (F5) ต้องไม่ถูกพากลับหรือเติมข้อความซ้ำ
   ทิ้งค่าที่เก่ากว่า 2 นาที (เช่นโหลดใหม่ไม่สำเร็จ แล้วผู้ใช้กลับมาเปิดทีหลัง) */
function takeCarry() {
  var raw = null, c = null;
  try { raw = sessionStorage.getItem(CARRY_KEY); sessionStorage.removeItem(CARRY_KEY); } catch (e) {}
  if (!raw) return null;
  try { c = JSON.parse(raw); } catch (e) { return null; }
  if (!c || typeof c !== 'object' || !(Math.abs(Date.now() - (+c.at || 0)) < 120000)) return null;
  return {
    hash: typeof c.hash === 'string' && CARRY_HASH.test(c.hash) ? c.hash : '',
    draft: typeof c.draft === 'string' ? c.draft : '',
    focus: c.focus === 'sw' || c.focus === 'frame' ? c.focus : ''
  };
}
/* เรียกหลัง qwenEnhance พร้อม: เติมข้อความค้างคืน (เฉพาะเมื่อช่องพิมพ์ว่าง — WebUI อาจมีของตัวเองอยู่แล้ว)
   แล้วคืนโฟกัส  ช่องพิมพ์อาจยังไม่ถูกวาดตอน qwenEnhance พร้อม จึงรอดูสั้นๆ */
var carryLeft = null;
function applyCarry(e) {
  var c = carryLeft;
  carryLeft = null;
  if (!c || (!c.draft && !c.focus)) return;
  var tries = 0, filled = 0;
  (function step() {
    var ta = composerEl();
    if (!ta && ++tries < 40) { setTimeout(step, 150); return; }
    if (ta && c.draft && !ta.value.trim() && filled < 3) {
      filled++;
      try { e.prefill(c.draft); } catch (err) {}
      /* Svelte อาจวาดช่องพิมพ์ใหม่ตอนแชตโหลดเสร็จ (ข้อความที่เติมหาย) — ตรวจซ้ำอีกรอบก่อนเลิก */
      setTimeout(step, 700);
    } else if (c.focus === 'frame' && !c.draft) {
      callEnh('focusComposer');
    }
    if (c.focus === 'sw') {
      var b = langBtns().filter(visible);
      b = b.filter(function (x) { return x.getAttribute('aria-pressed') === 'true'; })[0] || b[0];
      if (b) b.focus();
    }
  })();
}
function isLangKey(e) {
  /* เช็ก e.code ด้วย — แป้นพิมพ์ภาษาไทยให้ e.key เป็นอักษรไทย (ศ) ไม่ใช่ L */
  return e.altKey && e.shiftKey && !e.ctrlKey && !e.metaKey && (e.code === 'KeyL' || (!e.code && /^l$/i.test(e.key || '')));
}
function langHotkey(e, fromFrame) {
  if (e.repeat) return;
  /* กล่องยืนยันของ shell หรือหน้าต่างของ WebUI เปิดอยู่ = ผู้ใช้ทำอะไรค้างอยู่ โหลดหน้าใหม่ตอนนี้จะทำให้งานนั้นหาย */
  if (!dlg.wrap.hidden || gpuOpen() || pdOpen() || body.classList.contains('frame-modal')) return;
  setLang(LANG === 'th' ? 'en' : 'th', null, fromFrame ? 'frame' : '');
}
langSw.addEventListener('click', function (e) {
  var b = e.target.closest('button[data-lang]');
  if (!b) return;
  hideTip();
  /* detail === 0 = กดด้วย Enter/Space — ผู้ใช้คีย์บอร์ดต้องได้โฟกัสคืนที่เดิมหลังโหลด */
  setLang(b.getAttribute('data-lang'), null, e.detail === 0 ? 'sw' : '');
});
paintLang(LANG);

/* ---------------------------------------------------------------- แผงโปรเจกต์ */
var ppInstr = $('#ppInstr'), ppSave = $('#ppInstrSave'), ppState = $('#ppInstrState');
var ppModel = $('#ppModel'), ppThink = $('#ppThink'), ppExt = $('#ppExt');
function panelOpen() { return pp.classList.contains('open'); }
/* panelBack = ตัวที่เปิดแผง (ปุ่มหัว, ชื่อโปรเจกต์, แถบไอคอน หรือป้ายโปรเจกต์ใน iframe) — ปิดแล้วคืนโฟกัสที่เดิม */
var panelBack = null, panelBackInner = null;
function openPanel() {
  closeMenu();
  hideTip();
  unpeek();
  if (artModal()) closeArt(true);   // จอแคบ: แผงแสดงผลเต็มจอเป็น modal อีกตัว — ปิดก่อน
  panelBack = document.activeElement;
  panelBackInner = null;
  if (panelBack === frame) { try { panelBackInner = frame.contentDocument.activeElement; } catch (e) {} }
  if (isMobile()) closeDrawer();
  pp.classList.add('open');
  $('#projBtn').setAttribute('aria-expanded', 'true');
  /* แผงเป็น modal: ทั้งหน้าข้างหลัง (แถบข้าง ส่วนหัว iframe) inert — Tab/โปรแกรมอ่านหน้าจอเข้าไม่ถึง */
  $('#app').inert = true;
  scrimSync();
  paintPanel();
  loadFiles();
  /* รอบ 4: ความจำ (โมเดลอาจจดเพิ่มระหว่างแชต) และไฟล์ที่สร้าง — อ่านใหม่ทุกครั้งที่เปิดแผง */
  loadMemory();
  loadOutputs();
  /* batch 2a (B5): งานค้นคว้า — ถามซ้ำเองระหว่างแผงเปิดและยังมีงานที่ทำอยู่ (resSchedule) */
  loadResearch();
  setTimeout(function () { $('#ppClose').focus(); }, 60);
}
function closePanel(noFocus) {
  if (!panelOpen()) return;
  /* หน้าข้างหลังถูก inert — โฟกัสที่ <body> แปลว่าหล่นมาจากในแผง (กดที่ว่างในแผง) ยังต้องคืนให้ตัวที่เปิด */
  var had = pp.contains(document.activeElement) || focusLost();
  pp.classList.remove('open');
  $('#projBtn').setAttribute('aria-expanded', 'false');
  $('#app').inert = false;
  scrimSync();
  if (!had || noFocus) return;
  if (panelBack === frame) {
    /* เปิดจากป้ายโปรเจกต์ใน iframe — โฟกัส iframe แล้วคืนให้ป้ายนั้น (ถ้ายังอยู่) ไม่งั้นช่องพิมพ์ */
    frame.focus();
    try { if (panelBackInner && panelBackInner.isConnected && panelBackInner !== frame.contentDocument.body) { panelBackInner.focus(); return; } } catch (e) {}
    if (callEnh('focusComposer')) return;
  }
  /* visible ไม่ใช่ shown: เปิดจากแถวในลิ้นชักบนจอแคบ ลิ้นชักปิดไปแล้ว (visibility:hidden) แถวนั้นโฟกัสไม่ได้ */
  (visible(panelBack) && panelBack !== body ? panelBack : [$('#projBtn')].filter(visible)[0] || $('#hdrNew')).focus();
}
/* instrBase = ค่าที่ช่องแก้ไขเริ่มต้นจากเซิร์ฟเวอร์ครั้งล่าสุด — "ยังไม่ได้บันทึก" เทียบกับค่านี้
   ไม่ใช่กับ PROJ ที่ refreshHub อัปเดตทุก 10 วินาที ไม่งั้นค่าใหม่จากแท็บอื่นดูเหมือนผู้ใช้แก้เอง
   แล้วกดบันทึกก็เขียนค่าเก่าทับค่าใหม่ */
var instrBase = null;
function instrDirty() { return instrBase != null && ppInstr.value !== instrBase; }
function paintInstrState() {
  var dirty = instrDirty();
  /* แก้ค้างอยู่ แต่ค่าบนเซิร์ฟเวอร์เปลี่ยนไปจากตอนเริ่มแก้ — เตือนว่าบันทึกจะทับของใหม่ */
  var conflict = dirty && (PROJ.system_prompt || '') !== instrBase;
  ppSave.disabled = !dirty;
  setText(ppState, conflict ? t('instr_conflict') : dirty ? t('unsaved') : t('save_hint'));
  ppState.classList.toggle('dirty', dirty);
}
var lastModelSig = '';
function paintPanel(fresh) {
  setText($('#ppTitle'), PROJ.name || '');
  var server = PROJ.system_prompt || '';
  /* ข้อความที่กำลังแก้ต้องไม่ถูกทับ — แต่ถ้ายังไม่ได้แก้อะไร รับค่าใหม่จากเซิร์ฟเวอร์ได้เลย */
  if (fresh || !instrDirty()) {
    if (ppInstr.value !== server) ppInstr.value = server;
    instrBase = server;
  }
  paintInstrState();
  var cur = PROJ.model || S.primaryModel || MODELS[0] || '';
  var opts = MODELS.slice();
  if (cur && opts.indexOf(cur) < 0) opts.unshift(cur);
  var msig = JSON.stringify([opts, cur]);
  if (document.activeElement !== ppModel && msig !== lastModelSig) {
    lastModelSig = msig;
    ppModel.replaceChildren.apply(ppModel, opts.length ? opts.map(function (m) {
      return el('option', { value: m, text: m, selected: m === cur });
    }) : [el('option', { value: '', text: '—' })]);
    ppModel.disabled = !opts.length;
  }
  var th = thinkPending || PROJ.think || 'off';
  [].forEach.call(ppThink.querySelectorAll('button'), function (b) {
    var on = b.getAttribute('data-v') === th;
    b.classList.toggle('on', on);
    setAttr(b, 'aria-checked', String(on));
    /* radiogroup = จุดหยุด Tab เดียว (ตัวที่เลือกอยู่) ลูกศรเลื่อนภายในกลุ่ม */
    setAttr(b, 'tabindex', on ? '0' : '-1');
  });
  setText($('#ppThinkH'), t('think_' + th + '_h'));
  setAttr(ppExt, 'aria-checked', PROJ.extend === false ? 'false' : 'true');
  if (!akbBusy) setAttr(ppAkb, 'aria-checked', autoKbOn() ? 'true' : 'false');
  setText($('#ppDirTxt'), FILEDIR);
  setAttr($('#ppDir'), 'aria-label', t('copydir') + ': ' + FILEDIR);
  setHidden($('#ppDir'), !FILEDIR);
}
ppInstr.addEventListener('input', paintInstrState);
ppInstr.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); if (!ppSave.disabled) saveInstr(); }
});
ppSave.addEventListener('click', saveInstr);
/* บันทึกคำสั่ง: PATCH → ขอ system message ที่ประกอบแล้ว → เขียนลง config ของ WebUI → โหลดหน้าแชตใหม่
   WebUI อ่าน config แค่ตอนเริ่ม ถ้าไม่โหลดใหม่ แชตใหม่ยังได้คำสั่งเก่า */
function saveInstr() {
  var v = ppInstr.value.trim();
  ppSave.disabled = true;
  ppState.textContent = t('saving'); ppState.classList.remove('dirty');
  patchProject(PROJ.slug, { system_prompt: v }).then(function (d) {
    Object.assign(PROJ, d || {}, { system_prompt: v });
    return api('/_qwen/project');
  }).then(function (p) {
    try {
      var cfg = JSON.parse(localStorage.getItem('LlamaUi.config') || '{}') || {};
      cfg.systemMessage = p.systemMessage || '';
      localStorage.setItem('LlamaUi.config', JSON.stringify(cfg));
    } catch (e) {}
    if (p.uiSrc) UI = p.uiSrc;
    /* ผู้ใช้อาจพิมพ์ต่อระหว่างรอบันทึก — ถ้าข้อความยังตรงกับที่ส่งไป (ไม่นับช่องว่างหัวท้าย) ค่อยแทนด้วยค่าที่บันทึก */
    if (ppInstr.value.trim() === v) ppInstr.value = v;
    instrBase = v;
    paintInstrState();
    if (!instrDirty()) setText(ppState, t('saved'));
    toast(t('instr_saved'));
    reloadFrameSoon();
  }).catch(function (e) {
    failToast(t('errsave'), e);
    paintInstrState();
  });
}
ppModel.addEventListener('change', function () {
  var v = ppModel.value;
  patchProject(PROJ.slug, { model: v }).then(function (d) {
    Object.assign(PROJ, d || {}, { model: v });
    return api('/_qwen/project');
  }).then(function (p) {
    if (p && p.uiSrc) UI = p.uiSrc;
    /* ผู้ใช้เลือกโมเดลเริ่มต้นเองแล้ว — ?model= ในลิงก์ของแท็บนี้หมดความหมาย (ไม่งั้นแชตใหม่ยังได้โมเดลจากลิงก์) */
    dropUrlModel();
    /* ให้มีผลทันทีถ้าอยู่หน้าเริ่มแชตเปล่าๆ (ไม่มีข้อความค้าง ไม่ได้กำลังตอบ)
       ไม่งั้นจำไว้ แล้วแชตใหม่ครั้งถัดไปจะโหลดด้วย ?model= ใหม่ */
    if (ROUTE.name === 'start' && !streaming() && !hasDraft()) reloadFrame('#/');
    else uiStale = true;
    toast(t('model_saved'));
  }).catch(function (e) {
    failToast(t('errmodel'), e);
    lastModelSig = '';
    ppModel.blur(); paintPanel();
  });
});
/* โหมดคิด — เก็บต่อโปรเจกต์ที่ hub, proxy ฉีดให้ทุกคำขอ ไม่ต้องโหลดหน้าใหม่
   กดลูกศรเลือกทันทีตามแบบ radio แต่หน่วงการบันทึก — กดผ่านสามตัวรวดเดียว = PATCH ครั้งเดียว toast เดียว */
var thinkPending = null, thinkTimer = 0;
function pickThink(want, now) {
  var base = PROJ.think || 'off';
  thinkPending = want === base ? null : want;
  paintPanel();
  clearTimeout(thinkTimer);
  if (!thinkPending) return;
  thinkTimer = setTimeout(function () {
    var w = thinkPending;
    if (!w) return;
    patchProject(PROJ.slug, { think: w }).then(function () {
      PROJ.think = w;
      if (thinkPending === w) thinkPending = null;
      paintPanel(); toast(t('thinkset'));
    }).catch(function (err) {
      if (thinkPending === w) thinkPending = null;
      paintPanel(); failToast(t('errthink'), err);
    });
  }, now ? 0 : 450);
}
ppThink.addEventListener('click', function (e) {
  var b = e.target.closest('button[data-v]');
  if (b) pickThink(b.getAttribute('data-v'), true);
});
ppThink.addEventListener('keydown', function (e) {
  var prev = e.key === 'ArrowLeft' || e.key === 'ArrowUp', next = e.key === 'ArrowRight' || e.key === 'ArrowDown';
  if (!prev && !next) return;
  var bs = [].slice.call(ppThink.querySelectorAll('button')), i = bs.indexOf(document.activeElement);
  if (i < 0) return;
  e.preventDefault();
  var nx = bs[(i + (next ? 1 : -1) + bs.length) % bs.length];
  nx.focus();
  pickThink(nx.getAttribute('data-v'), false);   // paintPanel ย้าย tabindex=0 ตามตัวที่เลือก
});
/* ต่อคำตอบอัตโนมัติ — proxy เป็นคนต่อให้ เพราะหน้าแชตของ llama.cpp ไม่มีปุ่มต่อคำตอบ */
ppExt.addEventListener('click', function () {
  var want = !(PROJ.extend !== false);
  patchProject(PROJ.slug, { extend: want }).then(function () {
    PROJ.extend = want; paintPanel(); toast(want ? t('extendon') : t('extendoff'));
  }).catch(function (err) { failToast(t('errextend'), err); });
});
/* batch 2b (C4): ค้นเอกสารของโปรเจกต์อัตโนมัติ — ฟิลด์ auto_kb ของโปรเจกต์ (ไม่มีฟิลด์ = เปิด ตามค่าเริ่มต้นของสัญญา)
   hub เป็นคนค้น kb ด้วยข้อความล่าสุดแล้วแนบผลต่อท้ายข้อความนั้น ที่นี่แค่เปิด/ปิด
   PATCH ของ hub ข้ามคีย์ที่ไม่รู้จักเงียบๆ แล้วตอบ 200 พร้อมข้อมูลโปรเจกต์ — hub รุ่นที่ยังไม่มีฟีเจอร์นี้จึงดูเหมือน "สำเร็จ"
   ต้องดูค่าที่ได้กลับมา: ไม่มี/ไม่ตรง = บอกผู้ใช้ตรงๆ ว่ายังใช้ไม่ได้ แล้วคืนสวิตช์ (ไม่หลอกว่าเปลี่ยนแล้ว)
   auto_knowledge = ชื่อสำรอง เผื่อฝั่ง hub ตั้งชื่อฟิลด์ต่างไป (อ่านจากข้อมูลโปรเจกต์ว่ามีตัวไหน) */
var ppAkb = $('#ppAkb'), akbBusy = false, AKB_KEYS = ['auto_kb', 'auto_knowledge'];
function akbKey() {
  for (var i = 0; i < AKB_KEYS.length; i++) if (own(PROJ, AKB_KEYS[i])) return AKB_KEYS[i];
  return AKB_KEYS[0];
}
function autoKbOn() { var k = akbKey(); return !own(PROJ, k) || PROJ[k] !== false; }
ppAkb.addEventListener('click', function () {
  if (akbBusy) return;
  var k = akbKey(), want = !autoKbOn(), data = {};
  data[k] = want;
  akbBusy = true;
  setAttr(ppAkb, 'aria-checked', String(want));
  setAttr(ppAkb, 'aria-busy', 'true');
  patchProject(PROJ.slug, data).then(function (hit) {
    akbBusy = false;
    if (!hit || typeof hit !== 'object' || hit[k] !== want) { paintPanel(); toast(t('autokb_unsupported'), true); return; }
    PROJ[k] = want;
    if (S.project) S.project[k] = want;
    paintPanel();
    toast(want ? t('autokb_on') : t('autokb_off'));
  }).catch(function (err) {
    akbBusy = false;
    paintPanel();
    failToast(t('errautokb'), err);
  }).then(function () { setAttr(ppAkb, 'aria-busy', null); });
});
/* ห่อฟังก์ชัน — ส่ง closePanel ตรงๆ event จะถูกรับเป็น noFocus (truthy) กด X แล้วโฟกัสหล่นไป <body> */
$('#ppClose').addEventListener('click', function () { closePanel(); });
$('#ppMore').addEventListener('click', function () { projectMenu(this, PROJ.slug, 'end'); });
$('#ppManage').addEventListener('click', openManage);
$('#projBtn').addEventListener('click', function () { panelOpen() ? closePanel() : openPanel(); });
/* กัน Tab หลุดออกจากแผงไปที่หน้าข้างหลังซึ่งถูกม่านบังอยู่ */
pp.addEventListener('keydown', function (e) {
  if (e.key !== 'Tab') return;
  var f = [].slice.call(pp.querySelectorAll('button:not([disabled]):not([hidden]):not([tabindex="-1"]), textarea, select, input:not([type=file])'))
    .filter(function (x) { return x.offsetParent !== null; });
  if (!f.length) return;
  var first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
});

/* ไฟล์ของโปรเจกต์ — เก็บลงโฟลเดอร์ของโปรเจกต์บนดิสก์ (MCP ของโปรเจกต์อ่านได้)
   ต่างจากไฟล์แนบในแชตที่อยู่ใน IndexedDB และหายเมื่อล้างแคช
   ชื่อไฟล์ส่งทาง header เป็น base64 ของ UTF-8 เพราะ header เป็น latin-1 ชื่อไทยจะพัง */
var ppFiles = $('#ppFiles'), ppFileIn = $('#ppFileIn'), ppKnow = $('#ppKnow');
function loadFiles() {
  return api('/_qwen/files').then(function (d) {
    FILEDIR = d.dir || FILEDIR;
    renderFiles(d.files || []);
  }).catch(function () { renderFiles([]); });
}
function renderFiles(files) {
  setHidden($('#ppDrop'), files.length > 0);
  setText($('#ppDirTxt'), FILEDIR);
  setAttr($('#ppDir'), 'aria-label', t('copydir') + ': ' + FILEDIR);
  /* ลบไฟล์แล้วรายการถูกวาดใหม่ — คืนโฟกัสให้แถวถัดไป (หรือปุ่มเพิ่มไฟล์) ไม่ให้หล่นไป <body> */
  var a = document.activeElement, fr = a && ppFiles.contains(a) ? a.closest('.file') : null;
  var memo = fr ? { key: fr.getAttribute('data-key'), del: a.classList.contains('icon-btn'), idx: [].indexOf.call(ppFiles.children, fr) } : null;
  if (!files.length) ppFiles.replaceChildren();
  else ppFiles.replaceChildren.apply(ppFiles, files.map(function (f) {
    return el('div', { class: 'file', role: 'listitem', 'data-key': f.name }, [
      el('span', { class: 'ib', 'aria-hidden': 'true' }, [icon('file', 'ic-sm')]),
      el('button', { type: 'button', class: 'file-name', 'aria-label': t('copypath') + ': ' + f.name, 'data-tip': t('copypath') + ' — ' + f.name, text: f.name, onclick: function () { copyPath(f.name); } }),
      el('span', { class: 'file-sz', text: fmtSize(f.size) }),
      el('button', { type: 'button', class: 'icon-btn xs', 'aria-label': t('delfile') + ': ' + f.name, 'data-tip': t('delfile'), onclick: function () { delFile(f.name); } }, [icon('trash', 'ic-sm')])
    ]);
  }));
  if (!memo) return;
  var rows = [].slice.call(ppFiles.children), row = null;
  rows.forEach(function (r) { if (!row && r.getAttribute('data-key') === memo.key) row = r; });
  var same = !!row;
  if (!row && rows.length) row = rows[Math.min(memo.idx, rows.length - 1)];
  var target = row ? ((same && memo.del && row.querySelector('.icon-btn')) || row.querySelector('.file-name')) : $('#ppUpload');
  if (target) target.focus({ preventScroll: true });
}
function copyPath(name) {
  var full = name ? FILEDIR + '\\' + name : FILEDIR;
  copyText(full).then(function () { toast(t('copied') + ': ' + full); }, function () { toast(full); });
}
function delFile(name) {
  confirmBox(t('delfile_title'), fmt(t('confirmdelfile'), name)).then(function (yes) {
    if (!yes) return;
    api('/_qwen/files/' + encodeURIComponent(name), { method: 'DELETE' })
      .then(function () { toast(t('filedeleted')); loadFiles(); })
      .catch(function (e) { failToast(t('errdelete'), e); });
  });
}
function b64name(s) {
  var bytes = new TextEncoder().encode(s), bin = '';
  for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
/* ต้องตรงกับ MAX_ATTACH ใน hub.py — เช็กก่อนส่ง ไฟล์หลาย GB (pcap, โมเดล) จะไม่ถูกอ่านทั้งก้อนจนแท็บค้าง */
var MAX_UPLOAD = 64 * 1024 * 1024;
function uploadFiles(list) {
  var files = [].slice.call(list || []);
  if (!files.length) return;
  var chain = Promise.resolve(), okN = 0;
  files.forEach(function (f) {
    chain = chain.then(function () {
      if (f.size > MAX_UPLOAD) { toast(t('errupload') + ': ' + f.name + ' — ' + t('err_filesize'), true); return; }
      toast(t('uploading') + ' ' + f.name);
      /* ส่ง File ตรงๆ ให้เบราว์เซอร์สตรีมจากดิสก์ ไม่ต้องคัดลอกทั้งไฟล์ไว้ในหน่วยความจำก่อน */
      return api('/_qwen/files', { method: 'POST', body: f, headers: { 'X-Filename': b64name(f.name), 'Content-Type': 'application/octet-stream' } })
        .then(function () { okN++; }, function (err) { toast(t('errupload') + ': ' + f.name + ' — ' + errText(err, { 413: 'err_filesize' }), true); });
    });
  });
  chain.then(function () {
    if (okN) toast(t('uploaded') + (okN > 1 ? ' (' + okN + ')' : ''));
    loadFiles();
  });
}
$('#ppUpload').addEventListener('click', function () { ppFileIn.click(); });
$('#ppDrop').addEventListener('click', function () { ppFileIn.click(); });
$('#ppDir').addEventListener('click', function () { copyPath(''); });
ppFileIn.addEventListener('change', function () { var fl = ppFileIn.files; uploadFiles(fl); ppFileIn.value = ''; });
ppKnow.addEventListener('dragover', function (e) {
  if (e.dataTransfer && [].indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) { e.preventDefault(); ppKnow.classList.add('drag'); }
});
ppKnow.addEventListener('dragleave', function (e) { if (!ppKnow.contains(e.relatedTarget)) ppKnow.classList.remove('drag'); });
ppKnow.addEventListener('drop', function (e) {
  e.preventDefault(); ppKnow.classList.remove('drag');
  if (e.dataTransfer) uploadFiles(e.dataTransfer.files);
});

/* ---------------------------------------------------------------- สถานะ hub/โมเดล */
/* ดึงรายชื่อโปรเจกต์ใหม่ด้วย — เปิดหลายแท็บแล้วแก้ที่แท็บอื่น ที่นี่ต้องเห็นตาม */
function refreshHub() {
  return api(HUB + '/api/projects').then(function (d) {
    PROJECTS = d.projects || PROJECTS;
    if (d.models && d.models.length) MODELS = d.models;
    var me = PROJECTS.find(function (p) { return p.port === ME; });
    /* ข้อความที่ผู้ใช้กำลังแก้ในแผงไม่หาย — paintPanel เทียบกับ instrBase ไม่ใช่ PROJ */
    if (me) {
      var oldName = PROJ.name;
      Object.assign(PROJ, me);
      /* qwenShell คือสิ่งที่ iframe อ่าน (ป้ายโปรเจกต์ใต้คำทักทาย) — ต้องตามค่าใหม่ด้วย
         ชื่อเปลี่ยน (แก้ที่แท็บนี้หรือแท็บอื่น) สั่ง enhance อ่านใหม่ ไม่ต้องรอโหลดหน้า */
      S.project = Object.assign(S.project || {}, me);
      S.projects = PROJECTS.map(function (p) { return { name: p.name, port: p.port, slug: p.slug }; });
      if (me.name !== oldName) callEnh('refresh');
    }
    var was = HEALTH.state, genBefore = GPU && GPU.generated_at;
    HEALTH = { state: d.upstream ? 'ok' : 'down', model: d.model || HEALTH.model };
    GPU = d.gpu || null;
    SVC = d.services && typeof d.services === 'object' ? d.services : null;
    /* batch 2a: มีงานค้นคว้ากำลังทำอยู่ (ที่ไหนก็ได้) ระหว่างแผงปิด — ถามรายการของโปรเจกต์นี้เงียบๆ เพื่อแจ้งเมื่องานเสร็จ */
    resHubTick();
    /* router ถูกรีสตาร์ต (จากแท็บอื่น / หน้าต่างเลือก GPU ของโปรเจกต์อื่น / ไอคอน) — แท็บนี้ไม่ได้เป็นคนสั่ง จึงไม่มีใครบอก
       WebUI ในแท็บนี้ที่ถาม /props ระหว่างนั้นค้างป้าย "Server unavailable" — กลับมาพร้อม (down → ok) หรือแผน GPU ถูกเขียนใหม่
       (generated_at เปลี่ยน: รีสตาร์ตเร็วจนรอบนี้ไม่ทันเห็น down) ให้ตรวจป้ายแล้วกู้ (recoverFrame ไม่ทำอะไรถ้าไม่มีป้าย) */
    if (HEALTH.state === 'ok' && (was === 'down' || was === 'hub' || (genBefore && GPU && GPU.generated_at && GPU.generated_at !== genBefore))) recoverFrame();
  }).catch(function () {
    HEALTH = { state: 'hub', model: HEALTH.model };
  }).then(function () {
    paintHealth();
    renderProjects();
    if (panelOpen()) paintPanel();   // ปิดอยู่ไม่ต้องวาด — openPanel วาดใหม่ทุกครั้งที่เปิด
    paintHeader();
  });
}

/* ---------------------------------------------------------------- คีย์ลัด */
document.addEventListener('keydown', function (e) {
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey && (e.code === 'KeyK' || e.key === 'k' || e.key === 'K')) {
    e.preventDefault(); focusSearch(); return;
  }
  if (isLangKey(e)) { e.preventDefault(); langHotkey(e, false); return; }
  if (e.key !== 'Escape' || e.defaultPrevented) return;
  hideTip();
  if (!dlg.wrap.hidden) { e.preventDefault(); closeDialog(dlgNo()); return; }
  if (gpuOpen()) { e.preventDefault(); closeGpu(); return; }
  if (pdOpen()) { e.preventDefault(); pdEscape(); return; }
  if (!menu.hidden) { e.preventDefault(); closeMenuFocus(); return; }
  if (panelOpen()) { e.preventDefault(); closePanel(); return; }
  /* แผงแสดงผล: จอแคบเป็น modal ปิดได้เสมอ · จอกว้างปิดเมื่อโฟกัสอยู่ในแผง (ไม่ปิดตอนกด Esc ที่อื่น) */
  if (artOpen() && (artModal() || art.contains(document.activeElement))) { e.preventDefault(); closeArt(); return; }
  if (body.classList.contains('sb-open')) { e.preventDefault(); closeDrawer(); $('#burger').focus(); return; }
  /* ออกจากการค้นหาขณะโฟกัสอยู่ที่ผลลัพธ์ — รายการถูกวาดใหม่ จึงส่งโฟกัสกลับปุ่มค้นหาให้ชัดเจน */
  if (body.classList.contains('searching')) { e.preventDefault(); endSearch(); if (shown(searchBtn)) searchBtn.focus(); return; }
  if (sbPeek) { e.preventDefault(); unpeek(); }
});

/* ---------------------------------------------------------------- ป้ายชื่อปุ่มไอคอน */
/* แสดงเมื่อชี้ค้าง (หน่วงเล็กน้อยแบบ title) หรือทันทีเมื่อโฟกัสด้วยคีย์บอร์ด — ป้ายเป็นแค่ภาพ (aria-hidden)
   ชื่อที่โปรแกรมอ่านหน้าจออ่านมาจาก aria-label ของปุ่มเอง  data-tip-rail = แสดงเฉพาะตอนเป็นแถบไอคอน */
var tipEl = $('#tip'), tipTimer = 0, tipFor = null, tipWant = null;
function hideTip() {
  if (!tipEl) return;   // ถูกเรียกก่อนส่วนนี้ของสคริปต์ทำงาน (ระหว่างเริ่มต้น)
  clearTimeout(tipTimer); tipFor = null; tipWant = null;
  tipEl.classList.remove('on'); tipEl.hidden = true;
}
function showTip(n, now) {
  var txt = n.getAttribute('data-tip') || '';
  var rail = !isMobile() && body.classList.contains('sb-min');
  if (!txt || (n.hasAttribute('data-tip-rail') && !rail) || n.getAttribute('aria-expanded') === 'true') { hideTip(); return; }
  if (n === tipFor || n === tipWant) return;
  hideTip();
  tipWant = n;
  tipTimer = setTimeout(function () {
    tipWant = null;
    if (!shown(n)) return;
    tipFor = n;
    tipEl.textContent = txt;
    /* วัดขนาดที่ตำแหน่ง 0,0 — ถ้าค้างตำแหน่งเดิมชิดขอบขวา กล่องถูกบีบแคบตอนวัด คำไทยหักกลางคำ (โปรเจ|กต์) */
    tipEl.style.left = '0px'; tipEl.style.top = '0px';
    tipEl.hidden = false;
    var r = n.getBoundingClientRect(), tw = tipEl.offsetWidth, th = tipEl.offsetHeight, x, y;
    if (rail && sb.contains(n)) { x = r.right + 8; y = r.top + (r.height - th) / 2; }
    else { x = r.left + (r.width - tw) / 2; y = r.bottom + 6; if (y + th > innerHeight - 8) y = r.top - th - 6; }
    tipEl.style.left = Math.round(Math.min(Math.max(8, x), innerWidth - tw - 8)) + 'px';
    tipEl.style.top = Math.round(Math.min(Math.max(8, y), innerHeight - th - 8)) + 'px';
    requestAnimationFrame(function () { if (tipFor === n) tipEl.classList.add('on'); });
  }, now ? 0 : 450);
}
document.addEventListener('pointerover', function (e) {
  if (e.pointerType === 'touch') return;
  var n = e.target.closest && e.target.closest('[data-tip]');
  if (n) showTip(n, false); else if (tipFor || tipWant) hideTip();
});
document.addEventListener('focusin', function (e) {
  var n = e.target.closest && e.target.closest('[data-tip]');
  var kb = false;
  try { kb = e.target.matches(':focus-visible'); } catch (err) {}
  if (n && kb) showTip(n, true); else hideTip();
});
document.addEventListener('focusout', function () { if (tipFor && !tipFor.matches(':hover')) hideTip(); });
document.addEventListener('pointerdown', hideTip, true);

/* =====================================================================================
   รอบ 4 (2026-09-30) — ความจำ (K3) · ไฟล์ที่สร้าง (K2) · ปรับให้เป็นของคุณ (K4) · แจ้งเตือน (K5)
   · แผงแสดงผล (K7) · ส่งออกแชต (K10)   ฟังก์ชันล้วน (qwMd, qwCsv, qwTurns …) อยู่ใน _LIB_JS ท้ายไฟล์ Python
   ===================================================================================== */

/* ---------------------------------------------------------------- ความจำของโปรเจกต์ (K3) */
/* hub อ่าน/เขียน memory.json ไฟล์เดียวกับเครื่องมือความจำของ MCP (โมเดลจดเองได้ระหว่างแชต):
     GET    /_qwen/memory      → {entries:[{id,kind,text,created,updated,tags,pinned,in_prompt}], prompt:{included,tokens_est,budget_tokens}, broken}
     POST   /_qwen/memory      {text, kind, pinned}            PATCH /_qwen/memory/<id> {text?, kind?, pinned?}
     DELETE /_qwen/memory/<id>
   ข้อผิดพลาดมาพร้อม error_th/error_en ที่ hub แปลไว้ (เช่น "ดูเหมือนมีรหัสผ่าน") — แสดงข้อความนั้นเลย (srvMsg)
   ข้อความของแต่ละรายการมาจากผู้ใช้หรือโมเดล → textContent เท่านั้น */
var MEM_KINDS = ['fact', 'decision', 'requirement', 'progress', 'todo'];
var MEM_SHOW = 12;          // แสดงเท่านี้ก่อน ที่เหลือกด "แสดงทั้งหมด" (ความจำมีได้ถึง 5,000 รายการ)
var MEM = { list: null, state: 'idle', info: null, all: false, edit: null, seq: 0, open: {} };
var memBox = $('#ppMemList'), memForm = $('#ppMemForm'), memIn = $('#ppMemText'), memKindSel = $('#ppMemKind');
var memAddBtn = $('#ppMemAdd'), memAllBtn = $('#ppMemAll'), memSum = $('#ppMemSum');
function memKindOptions(sel, cur) {
  sel.replaceChildren.apply(sel, MEM_KINDS.map(function (k) { return el('option', { value: k, text: t('mem_k_' + k) }); }));
  sel.value = cur;
}
memKindOptions(memKindSel, 'fact');
function memUrl(id) { return '/_qwen/memory' + (id ? '/' + encodeURIComponent(id) : ''); }
function memShort(s, n) { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function memKindOf(e) { return MEM_KINDS.indexOf(e.kind) >= 0 ? e.kind : 'fact'; }
function memDate(s) {
  var d = new Date(s || '');
  if (isNaN(d.getTime())) return '';
  try {
    return d.toLocaleDateString(LANG, d.getFullYear() === new Date().getFullYear()
      ? { day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short', year: 'numeric' });
  } catch (e) { return String(s).slice(0, 10); }
}
/* เขียนไม่สำเร็จ: ข้อความที่ hub แปลไว้ถ้ามี (ดูเหมือนความลับ / ยาวเกิน / ไฟล์เสีย) ไม่งั้นข้อความกลาง
   404 = รายการถูกลบไปแล้ว (อีกแท็บ หรือโมเดลลบเอง) — อ่านรายการใหม่ให้ตรงกับไฟล์ */
function memFail(prefix) {
  return function (e) {
    var s = srvMsg(e);
    if (s) toast(glue(s), true); else failToast(prefix, e);
    if (e && e.status === 404) loadMemory();
  };
}
function loadMemory() {
  var mine = ++MEM.seq;
  if (!MEM.list) { MEM.state = 'loading'; renderMemory(); }
  return api(memUrl()).then(function (d) {
    if (mine !== MEM.seq) return;
    var arr = d && Array.isArray(d.entries) ? d.entries : null;
    if (!arr) { MEM.state = 'na'; MEM.list = null; renderMemory(); return; }
    MEM.list = arr.filter(function (x) { return x && typeof x.id === 'string' && typeof x.text === 'string'; });
    MEM.info = { prompt: d.prompt || null, broken: !!d.broken };
    MEM.state = 'ok';
    renderMemory();
  }).catch(function (e) {
    if (mine !== MEM.seq) return;
    /* hub รุ่นเก่าไม่มีเส้นทางนี้ (ถูกส่งต่อไป llama-server → 404) = "ยังใช้ไม่ได้" ไม่ใช่ "โหลดพลาด"
       มีรายการเดิมอยู่แล้วและแค่อ่านซ้ำไม่ผ่าน: คงรายการเดิมไว้เงียบๆ */
    if (MEM.list && !(e && e.status === 404)) return;
    MEM.list = null;
    MEM.state = e && (e.status === 404 || e.status === 405 || e.status === 501) ? 'na' : 'err';
    try { console.warn('[qwen] memory', e); } catch (x) {}
    renderMemory();
  });
}
function memFocusMemo() {
  var a = document.activeElement;
  if (!a || !memBox.contains(a)) return null;
  var row = a.closest('.mem');
  return { key: row && row.getAttribute('data-key'), act: a.getAttribute('data-act') || '', idx: [].indexOf.call(memBox.children, row) };
}
/* วาดใหม่แล้วคืนโฟกัสให้ปุ่มเดิมของแถวเดิม (หรือแถวที่มาแทนถ้าแถวนั้นถูกลบ) ไม่ให้หล่นไป <body> */
function memFocusRestore(m) {
  if (!m) return;
  var rows = [].slice.call(memBox.querySelectorAll('.mem')), row = null;
  rows.forEach(function (r) { if (!row && r.getAttribute('data-key') === m.key) row = r; });
  var same = !!row;
  if (!row && rows.length) row = rows[Math.min(Math.max(m.idx, 0), rows.length - 1)];
  var tgt = row ? (same && m.act && row.querySelector('[data-act="' + m.act + '"]')) || row.querySelector('textarea') ||
    row.querySelector('[data-act="edit"]') : (shown(memAddBtn) ? memAddBtn : null);
  if (!tgt) return;
  tgt.focus({ preventScroll: true });
  if (tgt.tagName === 'TEXTAREA') tgt.setSelectionRange(tgt.value.length, tgt.value.length);
}
function memRow(e) {
  if (MEM.edit === e.id) return memEditor(e);
  var short = memShort(e.text, 60), open = !!MEM.open[e.id];
  var off = e.in_prompt === false && MEM.info && MEM.info.prompt;
  var txt = el('div', { class: 'mem-text' + (open ? ' open' : ''), id: 'memt-' + e.id, text: e.text });
  /* ข้อความยาวถูกตัดที่ 4 บรรทัด — ปุ่มอ่านต่อ/ย่อ (ประมาณจากความยาว ไม่ต้องวัด DOM ทุกแถว) */
  var long = e.text.length > 180 || e.text.split('\n').length > 4;
  var tog = long ? el('button', { type: 'button', class: 'mem-link', 'data-act': 'more', 'aria-expanded': String(open), 'aria-controls': 'memt-' + e.id,
    text: open ? t('mem_less_text') : t('mem_more_text'), onclick: function () { MEM.open[e.id] = !open; renderMemory(); } }) : null;
  return el('div', { class: 'mem' + (e.pinned ? ' pinned' : '') + (off ? ' out' : ''), role: 'listitem', 'data-key': e.id }, [
    el('div', { class: 'mem-top' }, [
      e.pinned ? el('span', { class: 'mem-pin', 'data-tip': t('mem_pinned_tip') }, [icon('pin', 'ic-xs')]) : null,
      el('span', { class: 'mem-kind', text: t('mem_k_' + memKindOf(e)) }),
      el('span', { class: 'mem-date', text: memDate(e.updated || e.created) }),
      off ? el('span', { class: 'mem-off', text: t('mem_off'), 'data-tip': t('mem_off_tip') }) : null,
      el('span', { class: 'mem-acts' }, [
        /* ปุ่มสลับ: ชื่อคงที่ "ปักหมุด" + aria-pressed บอกสถานะ ป้ายชื่อบอกสิ่งที่จะเกิดเมื่อกด */
        el('button', { type: 'button', class: 'icon-btn xs', 'data-act': 'pin', 'aria-pressed': String(!!e.pinned), 'aria-label': t('mem_pin') + ': ' + short,
          'data-tip': e.pinned ? t('mem_unpin') : t('mem_pin'), onclick: function () { memPin(e); } }, [icon('pin', 'ic-sm')]),
        el('button', { type: 'button', class: 'icon-btn xs', 'data-act': 'edit', 'aria-label': t('mem_edit') + ': ' + short,
          'data-tip': t('mem_edit'), onclick: function () { memStartEdit(e.id); } }, [icon('pencil', 'ic-sm')]),
        el('button', { type: 'button', class: 'icon-btn xs del', 'data-act': 'del', 'aria-label': t('mem_delete') + ': ' + short,
          'data-tip': t('mem_delete'), onclick: function () { memDelete(e); } }, [icon('trash', 'ic-sm')])
      ])
    ]),
    txt, tog
  ]);
}
function memEditor(e) {
  var ta = el('textarea', { class: 'input', rows: '3', maxlength: '8000', 'aria-label': t('mem_edit_label') });
  var sel = el('select', { 'aria-label': t('mem_kind') });
  /* รายการถูกวาดใหม่ระหว่างแก้ได้ (ปักหมุด/ลบแถวอื่น, อ่านใหม่) — ข้อความที่พิมพ์ค้างต้องตามมาด้วย ไม่กลับเป็นค่าเดิม */
  var dr = MEM.draft && MEM.draft.id === e.id ? MEM.draft : null;
  ta.value = dr ? dr.text : e.text;
  memKindOptions(sel, dr ? dr.kind : memKindOf(e));
  var keep = function () { MEM.draft = { id: e.id, text: ta.value, kind: sel.value }; };
  ta.addEventListener('input', keep);
  ta.addEventListener('input', function () { memGrow(ta); });
  sel.addEventListener('change', keep);
  var save = el('button', { type: 'button', class: 'btn btn-ink sm', text: t('save') });
  var cancel = el('button', { type: 'button', class: 'btn btn-ghost sm', text: t('cancel'), onclick: function () { memEndEdit(e.id); } });
  save.addEventListener('click', function () {
    var text = ta.value.trim(), data = {};
    if (!text) { ta.focus(); return; }
    if (text !== e.text) data.text = text;
    if (sel.value !== memKindOf(e)) data.kind = sel.value;
    if (!Object.keys(data).length) { memEndEdit(e.id); return; }
    save.disabled = true;
    api(memUrl(e.id), { method: 'PATCH', json: data }).then(function (d) {
      if (d && d.entry) Object.assign(e, d.entry);
      toast(t('mem_saved'));
      memEndEdit(e.id);
      return loadMemory();
    }).catch(function (err) { save.disabled = false; memFail(t('mem_err_save'))(err); });
  });
  var escN = el('p', { class: 'mem-note warn mem-esc', id: 'memEsc-' + e.id, text: t('mem_esc_edit'), hidden: true });
  setAttr(ta, 'aria-describedby', escN.id);
  ta.addEventListener('input', function () { if (memEscNote === escN) memEscArm(null, false); });
  ta.addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); save.click(); }
    /* Esc ยกเลิกการแก้ — ไม่ปล่อยให้ถึงตัวจัดการของหน้า (ซึ่งจะปิดแผงโปรเจกต์ทั้งแผง)
       แก้ข้อความไปแล้ว: Esc ครั้งแรกเตือนก่อน (ดู memEscape) */
    else if (ev.key === 'Escape') {
      ev.preventDefault(); ev.stopPropagation();
      if (!memEscape(escN, ta.value.trim() !== e.text.trim() || sel.value !== memKindOf(e))) memEndEdit(e.id);
    }
  });
  return el('div', { class: 'mem editing', role: 'listitem', 'data-key': e.id }, [ta, escN,
    el('div', { class: 'mem-form-row' }, [el('div', { class: 'sel sel-sm' }, [sel, icon('chevron', 'ic-sm')]), el('span', { class: 'mem-grow' }), cancel, save])]);
}
/* ช่องแก้สูงตามข้อความ (สูงสุด ~14 บรรทัด) — เห็นทั้งรายการตอนเริ่มแก้ ไม่ต้องเลื่อนในช่องเล็กๆ */
function memGrow(ta) {
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight + 2, 340) + 'px';
}
function memStartEdit(id) {
  MEM.edit = id;
  MEM.draft = null;
  renderMemory();
  var ta = memBox.querySelector('.mem.editing textarea');
  if (ta) { memGrow(ta); ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length); }
}
function memEndEdit(id) {
  MEM.edit = null;
  MEM.draft = null;
  renderMemory();
  var b = memBox.querySelector('.mem[data-key="' + CSS.escape(id) + '"] [data-act="edit"]');
  if (b) b.focus({ preventScroll: true });
}
function renderMemory() {
  var st = MEM.state, list = MEM.list || [], kids = [];
  setHidden(memAddBtn, st === 'na' || (st === 'err' && !MEM.list));
  if (st === 'na' && !memForm.hidden) closeMemForm(true);
  var memo = memFocusMemo();
  if (st === 'loading' || st === 'idle') kids.push(el('div', { class: 'mem-note', text: t('loading') }));
  else if (st === 'na') kids.push(el('div', { class: 'mem-note', text: t('mem_unavail') }));
  else if (st === 'err') {
    kids.push(el('div', { class: 'mem-note' }, [el('span', { text: t('mem_err_load') }),
      el('button', { type: 'button', class: 'mem-link', text: t('retry'), onclick: function () { loadMemory(); } })]));
  } else {
    if (MEM.info && MEM.info.broken) kids.push(el('div', { class: 'mem-note warn' }, [icon('alert', 'ic-xs'), el('span', { text: t('mem_broken') })]));
    if (!list.length) kids.push(el('div', { class: 'mem-empty', text: t('mem_empty') }));
    var rows = MEM.all || list.length <= MEM_SHOW ? list : list.slice(0, MEM_SHOW);
    /* กำลังแก้รายการที่อยู่นอก N แรก (เพิ่งกด "แสดงน้อยลง") — ตัวแก้ยังต้องอยู่ ไม่งั้นข้อความที่พิมพ์หาย */
    if (MEM.edit && !rows.some(function (x) { return x.id === MEM.edit; })) {
      var ed = list.filter(function (x) { return x.id === MEM.edit; })[0];
      if (ed) rows = rows.concat([ed]); else MEM.edit = null;
    }
    rows.forEach(function (e) { kids.push(memRow(e)); });
  }
  /* role=list เฉพาะตอนมีรายการจริง — ข้อความสถานะ (ว่าง/โหลด/ใช้ไม่ได้) ไม่ใช่ listitem */
  setAttr(memBox, 'role', kids.some(function (k) { return k.getAttribute('role') === 'listitem'; }) ? 'list' : null);
  memBox.replaceChildren.apply(memBox, kids);
  var p = MEM.info && MEM.info.prompt, sum = st === 'ok' && list.length && p && p.budget_tokens;
  setText(memSum, sum ? fmtN(t('mem_sum'), p.included || 0, list.length, (+p.tokens_est || 0).toLocaleString(LANG), (+p.budget_tokens).toLocaleString(LANG)) : '');
  var more = st === 'ok' && list.length > MEM_SHOW;
  setHidden(memAllBtn, !more);
  if (more) setText(memAllBtn, MEM.all ? t('mem_show_less') : fmt(t('mem_show_all'), list.length.toLocaleString(LANG)));
  setHidden(memSum.parentNode, !sum && !more);
  var eta = memBox.querySelector('.mem.editing textarea');
  if (eta) memGrow(eta);
  memFocusRestore(memo);
}
function memPin(e) {
  var want = !e.pinned;
  e.pinned = want;
  renderMemory();                       // เห็นผลทันที ล้มค่อยคืน
  api(memUrl(e.id), { method: 'PATCH', json: { pinned: want } }).then(function () {
    toast(t(want ? 'mem_pinned_t' : 'mem_unpinned_t'));
    return loadMemory();                // ลำดับใหม่ (หมุดขึ้นก่อน) + ใส่ในแชตหรือไม่ มาจาก hub
  }).catch(function (err) { e.pinned = !want; renderMemory(); memFail(t('mem_err_save'))(err); });
}
function memDelete(e) {
  confirmBox(t('mem_del_title'), fmt(t('mem_del_body'), memShort(e.text, 80))).then(function (yes) {
    if (!yes) return;
    api(memUrl(e.id), { method: 'DELETE' }).then(function () {
      MEM.list = (MEM.list || []).filter(function (x) { return x.id !== e.id; });
      renderMemory();
      toast(t('mem_deleted'));
      loadMemory();
    }).catch(memFail(t('mem_err_save')));
  });
}
function openMemForm() {
  memForm.hidden = false;
  setAttr(memAddBtn, 'aria-expanded', 'true');
  memIn.focus();
}
function closeMemForm(silent) {
  memForm.hidden = true;
  memIn.value = '';
  memKindSel.value = 'fact';
  memEscArm(null, false);
  setAttr(memAddBtn, 'aria-expanded', 'false');
  if (!silent && shown(memAddBtn)) memAddBtn.focus();
}
/* Esc ในช่องความจำ (เพิ่มใหม่/แก้) ตอนมีข้อความที่ยังไม่ได้บันทึก: ครั้งแรกขึ้นคำเตือน ครั้งที่สองจึงทิ้ง — เดิมทิ้งทันที
   ผู้ใช้ที่กด Esc เพื่อปิด tooltip/เมนูค้างหรือกดพลาดเสียข้อความยาวๆ ไป (ปุ่มยกเลิกยังทิ้งทันที — กดตั้งใจแล้ว)
   note = ย่อหน้าคำเตือนของช่องนั้น · on=false ซ่อน · คืน true ถ้ารอบนี้แค่เตือน (ผู้เรียกไม่ต้องปิด) */
var memEscNote = null;
function memEscArm(note, on) {
  if (memEscNote && memEscNote !== note) setHidden(memEscNote, true);
  memEscNote = on ? note : null;
  if (note) setHidden(note, !on);
  if (on) announce(note.textContent);
}
function memEscape(note, dirty) {
  if (dirty && !(memEscNote === note && note && !note.hidden)) { memEscArm(note, true); return true; }
  memEscArm(null, false);
  return false;
}
function memAdd() {
  var text = memIn.value.trim(), btn = $('#ppMemSave');
  if (!text) { memIn.focus(); return; }
  if (btn.disabled) return;
  btn.disabled = true;
  api(memUrl(), { method: 'POST', json: { text: text, kind: memKindSel.value, pinned: false } }).then(function () {
    closeMemForm();
    toast(t('mem_saved'));
    return loadMemory();
  }).catch(memFail(t('mem_err_save'))).then(function () { btn.disabled = false; });
}
memAddBtn.addEventListener('click', function () { memForm.hidden ? openMemForm() : closeMemForm(); });
$('#ppMemCancel').addEventListener('click', function () { closeMemForm(); });
$('#ppMemSave').addEventListener('click', memAdd);
memIn.addEventListener('keydown', function (e) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); memAdd(); }
  else if (e.key === 'Escape') {
    e.preventDefault(); e.stopPropagation();
    if (!memEscape($('#ppMemEsc'), !!memIn.value.trim())) closeMemForm();
  }
});
/* พิมพ์ต่อ = ยังไม่ได้ตั้งใจทิ้ง — ล้างคำเตือน Esc ต้องกด Esc สองครั้งใหม่ */
memIn.addEventListener('input', function () { if (memEscNote === $('#ppMemEsc')) memEscArm(null, false); });
memAllBtn.addEventListener('click', function () { MEM.all = !MEM.all; renderMemory(); memAllBtn.focus(); });

/* ---------------------------------------------------------------- ไฟล์ที่ Qwen สร้าง (K2) */
/* GET /_qwen/out/ → {dir, files:[{name,size,mtime,url,type,inline}], total} (ใหม่สุดก่อน)
   ชื่อไฟล์มาจากโมเดล → textContent / encodeURIComponent เท่านั้น  เปิดในแท็บใหม่ = hub ส่งพร้อม nosniff + CSP sandbox
   รูป/ตาราง/เอกสาร/HTML/SVG เปิดในแผงแสดงผลได้ (ผ่านกติกาเดียวกับของจากแชต) */
var OUT = { list: null, all: false, seq: 0 };
var OUT_SHOW = 8;
function outUrl(f) { return typeof f.url === 'string' && /^\/_qwen\/out\/[^\/?#\\]+$/.test(f.url) ? f.url : '/_qwen/out/' + encodeURIComponent(f.name); }
function outKind(name) {
  var x = (/\.([a-z0-9]+)$/i.exec(name) || [])[1];
  return { png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', svg: 'svg', csv: 'csv', md: 'markdown', html: 'html', htm: 'html' }[(x || '').toLowerCase()] || '';
}
function loadOutputs() {
  var mine = ++OUT.seq;
  return api('/_qwen/out/').then(function (d) {
    if (mine !== OUT.seq) return;
    var a = d && Array.isArray(d.files) ? d.files : null;
    OUT.list = a ? a.filter(function (x) { return x && typeof x.name === 'string' && x.name && !/[\/\\]/.test(x.name); }) : null;
    renderOutputs();
  }).catch(function () { if (mine === OUT.seq) { OUT.list = null; renderOutputs(); } });
}
function renderOutputs() {
  var l = OUT.list, box = $('#ppOutList'), allB = $('#ppOutAll');
  setHidden($('#ppOut'), !(l && l.length));
  if (!l || !l.length) { box.replaceChildren(); return; }
  var rows = OUT.all ? l : l.slice(0, OUT_SHOW);
  box.replaceChildren.apply(box, rows.map(function (f) {
    var k = outKind(f.name);
    return el('div', { class: 'file', role: 'listitem', 'data-key': f.name }, [
      el('span', { class: 'ib', 'aria-hidden': 'true' }, [icon(k === 'image' ? 'image' : 'file', 'ic-sm')]),
      el('a', { class: 'file-name', href: outUrl(f), target: '_blank', rel: 'noopener', text: f.name, 'data-tip': t('out_open') + ' — ' + f.name }),
      el('span', { class: 'file-sz', text: fmtSize(f.size) }),
      /* ชนิดที่เปิดในแผงไม่ได้ (docx, xlsx …) เว้นที่เท่าปุ่มไว้ ขนาดไฟล์ทุกแถวจึงตรงคอลัมน์เดียวกัน */
      k ? el('button', { type: 'button', class: 'icon-btn xs', 'aria-label': t('out_panel') + ': ' + f.name, 'data-tip': t('out_panel'),
        onclick: function () { openOutput(f, k); } }, [icon('panel', 'ic-sm')]) : el('span', { class: 'out-sp', 'aria-hidden': 'true' })
    ]);
  }));
  setHidden(allB, l.length <= OUT_SHOW);
  if (l.length > OUT_SHOW) setText(allB, OUT.all ? t('mem_show_less') : fmt(t('mem_show_all'), l.length.toLocaleString(LANG)));
}
$('#ppOutAll').addEventListener('click', function () { OUT.all = !OUT.all; renderOutputs(); this.focus(); });
function openOutput(f, kind) {
  var url = outUrl(f), id = 'out:' + f.name;
  if (panelOpen()) closePanel(true);
  /* ปุ่มที่กดอยู่ในแผงโปรเจกต์ซึ่งเพิ่งปิดไป — ปิดแผงแสดงผลแล้วโฟกัสจะหล่นไป <body> ของ iframe
     ให้กลับไปที่ปุ่มเปิดแผงโปรเจกต์แทน (กด Enter ก็กลับมาที่รายการไฟล์ได้) */
  var open = function (o) { if (openArtifact(o)) { ART.back = $('#projBtn'); ART.backInner = null; } };
  if (kind === 'image') { open({ id: id, kind: 'image', title: f.name, code: url }); return; }
  if ((+f.size || 0) > ART_MAX) { toast(t('art_too_big'), true); return; }
  fetch(url, { cache: 'no-store' }).then(function (r) {
    if (!r.ok) { var er = new Error('HTTP ' + r.status); er.status = r.status; throw er; }
    return r.text();
  }).then(function (text) { open({ id: id, kind: kind, title: f.name, code: text }); })
    .catch(function (e) { failToast(t('art_bad'), e); });
}

/* ---------------------------------------------------------------- งานค้นคว้าเชิงลึก (batch 2a, สัญญา B5) */
/* GET /_qwen/research → {jobs:[{id, question, status, phase, phase_text, progress, sources_read, sources_total, depth,
   created, updated, finished, eta_s, note, error, files:[{name,url,size,kind}], report, cancel_requested, active, stale}], running}
   POST /_qwen/research/<id>/cancel (application/json) — hub เขียนธงยกเลิก + สั่ง MCP (research_cancel)
   ข้อความทุกช่องมาจากไฟล์งานที่ MCP เขียน (บางส่วนมาจากเว็บภายนอก) → textContent เท่านั้น, ลิงก์ผ่าน outUrl() อีกชั้น
   ถามซ้ำทุก 4 วินาทีเฉพาะตอนแผงเปิดและมีงานที่ยังทำอยู่ · แผงปิด: ถามเมื่อ hub บอกว่ามีงานกำลังทำ (resHubTick ทุก 10 วินาที)
   เพื่อแจ้งเมื่องานเสร็จ (toast + การแจ้งเตือนของเดสก์ท็อปเมื่อแท็บถูกซ่อน) */
var RES = { list: null, state: 'idle', all: false, seq: 0, timer: 0, known: {}, primed: false, sig: '', busy: {}, stopped: {} };
var RES_SHOW = 5, RES_POLL = 4000;
var resBox = $('#ppResList'), resAllBtn = $('#ppResAll');
function resUrl(id, act) { return '/_qwen/research' + (id ? '/' + encodeURIComponent(id) + (act ? '/' + act : '') : ''); }
function resActive() { return (RES.list || []).some(function (j) { return j.active && !j.stale; }); }
function loadResearch(quiet) {
  var mine = ++RES.seq;
  if (!quiet && !RES.list) { RES.state = 'loading'; renderResearch(); }
  return api(resUrl(), { cache: 'no-store' }).then(function (d) {
    if (mine !== RES.seq) return;
    var jobs = d && Array.isArray(d.jobs) ? d.jobs.filter(function (j) { return j && typeof j.id === 'string' && j.id; }) : [];
    resTransitions(jobs);
    RES.list = jobs; RES.state = 'ok';
    renderResearch(); resSchedule();
  }).catch(function (e) {
    if (mine !== RES.seq) return;
    /* 404 = hub รุ่นก่อน (ยังไม่ได้เริ่มใหม่หลังอัปเดต) ส่งเส้นทางนี้ต่อไปที่ llama-server */
    RES.state = e && e.status === 404 ? 'na' : 'err';
    if (RES.state === 'na') RES.list = null;
    renderResearch(); resSchedule();
  });
}
function resSchedule() {
  clearTimeout(RES.timer); RES.timer = 0;
  if (panelOpen() && RES.state === 'ok' && resActive()) RES.timer = setTimeout(function () { loadResearch(true); }, RES_POLL);
}
function resHubTick() {
  if (panelOpen()) return;                       // แผงเปิดอยู่ = ถามเองทุก 4 วินาทีแล้ว
  var n = SVC && SVC.research ? +SVC.research.running || 0 : 0;
  if (n > 0 || resActive()) loadResearch(true);
}
/* งานที่เคยเห็นว่ายังทำอยู่ แล้วรอบนี้จบ — บอกผู้ใช้ครั้งเดียว (รอบแรกหลังเปิดหน้าแค่จำสถานะ ไม่แจ้งงานเก่า) */
function resTransitions(jobs) {
  var prev = RES.known, next = {};
  jobs.forEach(function (j) {
    next[j.id] = j.status;
    var was = prev[j.id];
    if (!RES.primed || !was || was === j.status) return;
    if (was !== 'queued' && was !== 'running' && was !== 'cancelling') return;
    /* ผู้ใช้กดหยุดเองจากแผงนี้ (หรือสถานะเป็นยกเลิก) — ไม่ต้องบอกว่า "ไม่สำเร็จ" (งานที่ไม่มีเจ้าของแล้ว MCP ปิดเป็น interrupted) */
    if (RES.stopped[j.id] || was === 'cancelling' || j.status === 'cancelled') return;
    var q = memShort(j.question || '', 60);
    if (j.status === 'done') {
      toast(fmt(t('res_done_t'), q));
      try { notify({ kind: 'done', title: t('res_done_title'), body: j.question || '', tag: 'qw-res-' + j.id }); } catch (e) {}
    } else if (j.status === 'failed') {
      toast(fmt(t('res_failed_t'), q), true);
    } else if (j.status === 'interrupted') {
      toast(fmt(t('res_intr_t'), q));
    }
  });
  RES.known = next; RES.primed = true;
}
function resAgo(sec) {
  sec = +sec || 0;
  if (!sec) return '';
  var d = Math.round(Date.now() / 1000 - sec);
  try {
    var rtf = new Intl.RelativeTimeFormat(LANG, { numeric: 'auto' });
    if (d < 45) return rtf.format(0, 'second');
    if (d < 3600) return rtf.format(-Math.max(1, Math.round(d / 60)), 'minute');
    if (d < 86400) return rtf.format(-Math.round(d / 3600), 'hour');
    if (d < 7 * 86400) return rtf.format(-Math.round(d / 86400), 'day');
  } catch (e) {}
  try { return new Date(sec * 1000).toLocaleString(LANG, { dateStyle: 'medium', timeStyle: 'short' }); } catch (e) { return ''; }
}
function resDur(s) {
  s = Math.max(0, Math.round(+s || 0));
  if (s < 90) return fmt(t('res_min'), '1');
  var m = Math.round(s / 60);
  if (m < 60) return fmt(t('res_min'), m.toLocaleString(LANG));
  return fmtN(t('res_hr_min'), Math.floor(m / 60).toLocaleString(LANG), (m % 60).toLocaleString(LANG));
}
function resSvcText(rs) {
  return rs === 'missing' ? t('svc_res_missing') : rs === 'broken' ? t('svc_res_broken') : t('svc_res_down');
}
var RES_STATES = ['queued', 'running', 'cancelling', 'done', 'failed', 'cancelled', 'interrupted'];
function resRow(j) {
  var st = RES_STATES.indexOf(j.status) >= 0 ? j.status : 'unknown', active = !!j.active;
  var cls = st === 'done' ? 'ok' : st === 'failed' ? 'bad' : (st === 'interrupted' || j.stale) ? 'warn' : active ? 'run' : '';
  var q = typeof j.question === 'string' && j.question ? j.question : t('res_noq');
  var when = resAgo(active ? (j.created || j.updated) : (j.finished || j.updated || j.created));
  var top = el('div', { class: 'res-top' }, [
    el('span', { class: 'res-st ' + cls }, [el('i', { class: 'res-dot', 'aria-hidden': 'true' }), el('span', { text: t('res_st_' + st) })]),
    when ? el('span', { class: 'res-time', text: when }) : null,
    active && st !== 'cancelling' && !j.cancel_requested ? el('button', { type: 'button', class: 'mem-link', 'data-act': 'cancel',
      text: t('res_cancel'), 'aria-label': t('res_cancel') + ': ' + memShort(q, 60), disabled: RES.busy[j.id] ? true : null,
      onclick: function () { resCancel(j); } }) : null
  ]);
  var kids = [top, el('div', { class: 'res-q', text: q })];
  /* meta = [ข้อความ, ห้ามตัดบรรทัดกลางวลี] — วลีสั้นที่มีตัวเลข ("อีกราว 7 นาที", "อ่านแล้ว 3 จาก 8 แหล่ง") ต้องอยู่บรรทัดเดียว
     (no-break space ไม่พอ: ตัวตัดคำไทยของเบราว์เซอร์ตัดกลาง "อีก|ราว" ได้) */
  var meta = [];
  if (j.depth === 'quick' || j.depth === 'standard') meta.push([t('res_depth_' + j.depth), true]);
  if (active) {
    var ph = j.phase ? t('res_ph_' + j.phase) : (typeof j.phase_text === 'string' ? j.phase_text : '');
    if (ph && ph.indexOf('res_ph_') !== 0) meta.push([ph, false]);
  }
  var nr = +j.sources_read, nt = +j.sources_total;
  if (j.sources_read != null && isFinite(nr)) meta.push([nt > 0 && active ? fmtN(t('res_read_of'), nr.toLocaleString(LANG), nt.toLocaleString(LANG)) : fmt(t('res_read'), nr.toLocaleString(LANG)), true]);
  if (active && st === 'running' && +j.eta_s > 0) meta.push([fmt(t('res_eta'), resDur(j.eta_s)), true]);
  if (j.stale) meta.push([t('res_stale'), false]);
  if (meta.length) {
    var mk = [];
    meta.forEach(function (m, i) {
      if (i) mk.push(' · ');
      mk.push(m[1] ? el('span', { class: 'res-mp', text: m[0] }) : m[0]);
    });
    kids.push(el('div', { class: 'res-meta' }, mk));
  }
  /* บรรทัดบันทึกล่าสุดของงาน ("อ่านแล้ว: <เว็บ>") แยกบรรทัด จางกว่า และตัด … — มาจากหน้าเว็บภายนอกได้ จึงไม่ให้เด่น */
  if (active && typeof j.note === 'string' && j.note) kids.push(el('div', { class: 'res-note', text: j.note }));
  if (active) {
    var p = typeof j.progress === 'number' && isFinite(j.progress) ? Math.max(0, Math.min(1, j.progress)) : null;
    var bar = el('div', { class: 'res-bar' + (p == null ? ' ind' : ''), role: 'progressbar', 'aria-label': t('res_progress') + ': ' + memShort(q, 40),
      'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': p == null ? null : String(Math.round(p * 100)) }, [el('i')]);
    if (p != null) bar.firstChild.style.width = Math.round(p * 100) + '%';
    kids.push(bar);
  }
  /* ข้อผิดพลาดแดงเฉพาะงานที่ล้ม — หยุดกลางทาง (MCP รีสตาร์ต) / ยกเลิก ไม่ใช่ความผิดพลาดของงาน ใช้สีข้อความรอง */
  if (typeof j.error === 'string' && j.error) kids.push(el('div', { class: 'res-err' + (st === 'failed' ? '' : ' soft'), text: j.error }));
  var files = (Array.isArray(j.files) ? j.files : []).filter(function (f) {
    return f && typeof f.name === 'string' && f.name && !/[\/\\]/.test(f.name);
  });
  if (files.length) {
    var md = files.filter(function (f) { return f.kind === 'md'; })[0], fk = [];
    if (md) fk.push(el('button', { type: 'button', class: 'btn btn-ghost sm', 'data-act': 'open', 'aria-label': t('res_open') + ': ' + md.name,
      onclick: function () { openOutput({ name: md.name, url: outUrl(md), size: md.size }, 'markdown'); } }, [icon('panel', 'ic-sm'), el('span', { text: t('res_open') })]));
    files.forEach(function (f) {
      if (f === md) return;
      var docx = f.kind === 'docx';
      fk.push(el('a', { class: 'btn btn-ghost sm', href: outUrl(f), target: '_blank', rel: 'noopener', 'data-act': 'file-' + f.name,
        'aria-label': (docx ? t('res_docx') : t('out_open')) + ': ' + f.name }, [icon(docx ? 'download' : 'file', 'ic-sm'), el('span', { text: docx ? t('res_docx') : f.name })]));
    });
    kids.push(el('div', { class: 'res-files' }, fk));
  }
  return el('div', { class: 'res' + (active ? ' active' : ''), role: 'listitem', 'data-key': j.id }, kids);
}
function renderResearch() {
  var rs = SVC && SVC.research ? SVC.research.state : '';
  /* วาดใหม่เฉพาะเมื่อข้อมูลเปลี่ยน (หรือผ่านไปหนึ่งนาที ให้เวลา "…ที่แล้ว" ขยับ) — ถามทุก 4 วินาทีแต่ไม่ให้ DOM/โฟกัสกระตุก */
  var sig = JSON.stringify([RES.state, RES.all, RES.list, rs, Math.floor(Date.now() / 60000)]);
  if (sig === RES.sig) return;
  RES.sig = sig;
  var a = document.activeElement, keep = null;
  if (a && resBox.contains(a)) {
    var row = a.closest('.res');
    keep = { key: row && row.getAttribute('data-key'), act: a.getAttribute('data-act') };
  }
  var kids = [], list = RES.list || [];
  if (rs && rs !== 'ok' && RES.state !== 'na') {
    kids.push(el('div', { class: 'mem-note warn' }, [icon('alert', 'ic-xs'), el('span', { text: fmt(t('res_svc_note'), resSvcText(rs)) })]));
  }
  if (RES.state === 'loading' || RES.state === 'idle') kids.push(el('div', { class: 'mem-note', text: t('loading') }));
  else if (RES.state === 'na') kids.push(el('div', { class: 'mem-note', text: t('res_unavail') }));
  else if (RES.state === 'err') {
    kids.push(el('div', { class: 'mem-note' }, [el('span', { text: t('res_err_load') }),
      el('button', { type: 'button', class: 'mem-link', 'data-act': 'retry', text: t('retry'), onclick: function () { loadResearch(); } })]));
  } else if (!list.length) kids.push(el('div', { class: 'mem-empty', text: t('res_empty') }));
  var rows = RES.all || list.length <= RES_SHOW ? list : list.slice(0, RES_SHOW);
  if (RES.state === 'ok') rows.forEach(function (j) { kids.push(resRow(j)); });
  setAttr(resBox, 'role', kids.some(function (k) { return k.getAttribute('role') === 'listitem'; }) ? 'list' : null);
  resBox.replaceChildren.apply(resBox, kids);
  var more = RES.state === 'ok' && list.length > RES_SHOW;
  setHidden(resAllBtn, !more);
  if (more) setText(resAllBtn, RES.all ? t('mem_show_less') : fmt(t('mem_show_all'), list.length.toLocaleString(LANG)));
  /* ปุ่มที่โฟกัสอยู่ถูกวาดใหม่ — คืนโฟกัสให้ปุ่มเดียวกันของงานเดิม ไม่มีแล้ว (เช่นกดยกเลิกแล้วปุ่มหาย) ไปที่ "ค้นคว้าใหม่" */
  if (keep && !resBox.contains(document.activeElement)) {
    var n = keep.key && keep.act ? resBox.querySelector('.res[data-key="' + CSS.escape(keep.key) + '"] [data-act="' + CSS.escape(keep.act) + '"]') : null;
    (n || $('#ppResNew')).focus({ preventScroll: true });
  }
}
function resCancel(j) {
  var q = memShort(j.question || t('res_noq'), 90);
  openDialog({ title: t('res_cancel_title'), body: fmt(t('res_cancel_body'), q), okLabel: t('res_cancel_ok'),
    cancelLabel: t('res_cancel_keep'), danger: true }).then(function (yes) {
    if (!yes || RES.busy[j.id]) return;
    RES.busy[j.id] = true; RES.stopped[j.id] = true; RES.sig = ''; renderResearch();
    /* ปุ่ม "ยกเลิก" ที่เปิดกล่องนี้ถูกปิด/หายไป — กล่องคืนโฟกัสไม่ได้ ให้โฟกัสอยู่ที่รายการงาน (ไม่เลื่อนหน้า) */
    if (panelOpen() && !resBox.contains(document.activeElement)) resBox.focus({ preventScroll: true });
    api(resUrl(j.id, 'cancel'), { method: 'POST', json: {} }).then(function () {
      toast(t('res_cancel_sent'));
    }).catch(function (e) {
      if (e && e.status === 409) toast(t('res_not_running'));
      else failToast(t('res_cancel_err'), e);
    }).then(function () {
      delete RES.busy[j.id];
      return loadResearch(true);
    });
  });
}
/* "ค้นคว้าใหม่": เติมคำขอลงช่องพิมพ์ (ไม่ส่งเอง) — มีข้อความพิมพ์ค้างอยู่ = ใช้ข้อความนั้นเป็นหัวข้อ (เติมคำนำหน้าให้) */
function startResearch() {
  var pre = t('res_prefill'), draft = frameDraft().trim();
  var text = !draft ? pre : (draft.indexOf(pre.trim()) === 0 ? draft : pre + draft);
  if (panelOpen()) closePanel(true);
  if (isMobile()) closeDrawer();
  unpeek();
  var r = callEnhR('prefill', text);
  if (r.ok && r.value !== false) return true;
  /* ยังไม่มีช่องพิมพ์ (หน้าค้นหาของ WebUI บนจอแคบ / iframe ยังโหลดไม่เสร็จ) — เปิดแชตใหม่แล้วเติมเมื่อช่องพิมพ์มา */
  newChat();
  restoreDraft(text);
  return true;
}
$('#ppResNew').addEventListener('click', function () { startResearch(); });
resAllBtn.addEventListener('click', function () { RES.all = !RES.all; RES.sig = ''; renderResearch(); this.focus(); });

/* ---------------------------------------------------------------- ปรับให้เป็นของคุณ (K4) */
/* เกี่ยวกับคุณ (≤1,500 ตัวอักษร) + รูปแบบการตอบ — hub เก็บใน settings.json แล้วใส่ท้ายคำสั่งพื้นฐานของทุกแชตจากหน้าเว็บ
   GET/PATCH http://127.0.0.1:8100/api/settings {about_me, style, style_custom} (hub ส่ง about_me ให้เฉพาะหน้าของเรา)
   hub รุ่นก่อนหน้า: GET ไม่มี about_me — กรอกได้แต่ปุ่มบันทึกปิดพร้อมบอกเหตุผล (ไม่ทำเป็นบันทึกสำเร็จ) */
var PD_STYLES = ['normal', 'concise', 'explanatory', 'formal', 'learning', 'custom'];
var PD = {
  wrap: $('#pdWrap'), box: $('#pd'), about: $('#pdAbout'), custom: $('#pdCustom'), styles: $('#pdStyles'), save: $('#pdSave'),
  status: $('#pdStatus'), msg: $('#pdMsg'), base: null, style: 'normal', back: null, seq: 0, esc: false, ok: false,
  limits: { about_me: 1500, style_custom: 800 }
};
function pdOpen() { return !PD.wrap.hidden; }
PD_STYLES.forEach(function (s) {
  /* ชื่อของตัวเลือก = ชื่อสไตล์ คำอธิบายแยกเป็น description (ไม่อ่านรวมเป็นชื่อยาวๆ) */
  var b = el('button', { type: 'button', role: 'radio', class: 'pd-style', 'data-v': s, 'aria-checked': 'false', tabindex: '-1',
    'aria-labelledby': 'pdSt-' + s, 'aria-describedby': 'pdStD-' + s },
    [el('span', { class: 'pd-st-n', id: 'pdSt-' + s, text: t('pers_st_' + s) }), el('span', { class: 'pd-st-d', id: 'pdStD-' + s, text: t('pers_st_' + s + '_d') })]);
  b.addEventListener('click', function () { pdPick(s, false); });
  PD.styles.append(b);
});
/* radiogroup: จุดหยุด Tab เดียว (ตัวที่เลือก) ลูกศรเลื่อนแล้วเลือกทันทีตามแบบ radio */
PD.styles.addEventListener('keydown', function (e) {
  var step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  if (!step) return;
  var bs = [].slice.call(PD.styles.children), i = bs.indexOf(document.activeElement);
  if (i < 0) return;
  e.preventDefault();
  pdPick(bs[(i + step + bs.length) % bs.length].getAttribute('data-v'), true);
});
function pdPick(s, focus) {
  PD.style = PD_STYLES.indexOf(s) >= 0 ? s : 'normal';
  PD.esc = false;
  [].forEach.call(PD.styles.children, function (b) {
    var on = b.getAttribute('data-v') === PD.style;
    setAttr(b, 'aria-checked', String(on));
    setAttr(b, 'tabindex', on ? '0' : '-1');
    if (on && focus) b.focus();
  });
  setHidden($('#pdCustomWrap'), PD.style !== 'custom');
  pdPreview();
}
function pdPreview() {
  var a = $('#pdPvA'), custom = PD.style === 'custom';
  a.classList.toggle('custom', custom);
  setText(a, t('pers_pv_' + PD.style));
}
function pdCount() {
  [[PD.about, $('#pdAboutN'), PD.limits.about_me], [PD.custom, $('#pdCustomN'), PD.limits.style_custom]].forEach(function (x) {
    var n = x[0].value.length;
    setText(x[1], n.toLocaleString(LANG) + ' / ' + x[2].toLocaleString(LANG));
    x[1].classList.toggle('near', n > x[2] * 0.9);
  });
}
function pdVal() { return { about_me: PD.about.value.trim(), style: PD.style, style_custom: PD.custom.value.trim() }; }
function pdIsDirty() {
  if (!PD.base) return false;
  var v = pdVal();
  return v.about_me !== PD.base.about_me || v.style !== PD.base.style || v.style_custom !== PD.base.style_custom;
}
/* ข้อความในแถบล่างของหน้าต่าง (แทน toast ที่ลอยทับปุ่ม) — เสียงอ่านผ่านช่องเดียวกับ toast */
function pdFlash(msg, bad) {
  if (!msg) { PD.status.replaceChildren(); return; }
  PD.status.replaceChildren(el('div', { class: 'gd-msg' + (bad ? ' bad' : '') }, [icon(bad ? 'alert' : 'info', 'ic-sm'), el('span', { class: 'gd-msg-c', text: msg })]));
  announce(msg, bad);
}
function pdFill(d) {
  d = d || {};
  var lim = d.limits || {};
  PD.limits = { about_me: +lim.about_me || 1500, style_custom: +lim.style_custom || 800 };
  PD.about.maxLength = PD.limits.about_me;
  PD.custom.maxLength = PD.limits.style_custom;
  PD.base = {
    about_me: typeof d.about_me === 'string' ? d.about_me : '',
    style: PD_STYLES.indexOf(d.style) >= 0 ? d.style : 'normal',
    style_custom: typeof d.style_custom === 'string' ? d.style_custom : ''
  };
  PD.about.value = PD.base.about_me;
  PD.custom.value = PD.base.style_custom;
  pdPick(PD.base.style, false);
  pdCount();
}
function openPers() {
  if (!dlg.wrap.hidden || gpuOpen() || pdOpen()) return;
  var back = document.activeElement;
  closeMenu(); hideTip();
  /* เปิดจากรายการในเมนูบัญชี: ปุ่มนั้นถูกซ่อนไปแล้ว — คืนโฟกัสให้ปุ่มที่เปิดเมนู (lastBack) แทน */
  if (!back || back === body || menu.contains(back) || !shown(back)) back = lastBack;
  if (isMobile()) closeDrawer();
  if (panelOpen()) closePanel(true);
  if (artModal()) closeArt(true);
  unpeek();
  PD.back = back; PD.esc = false; PD.ok = false;
  pdFlash('');
  setHidden(PD.msg, true);
  PD.about.disabled = PD.custom.disabled = true;
  PD.save.disabled = true;
  PD.wrap.hidden = false;
  $('#app').inert = true;               // modal จริง: หน้าข้างหลังทั้งหมด (แถบข้าง ส่วนหัว iframe) เข้าไม่ถึง
  PD.box.focus();
  requestAnimationFrame(function () { PD.wrap.classList.add('on'); });
  var mine = ++PD.seq;
  api(HUB + '/api/settings').then(function (d) {
    if (mine !== PD.seq || !pdOpen()) return;
    PD.ok = !!(d && typeof d.style === 'string' && typeof d.about_me === 'string');
    pdFill(d);
    PD.about.disabled = PD.custom.disabled = false;
    PD.save.disabled = !PD.ok;
    if (!PD.ok) { setText($('#pdMsgT'), t('pers_unsupported')); setHidden(PD.msg, false); }
    /* จอสัมผัสไม่โฟกัสช่องพิมพ์เอง — แป้นพิมพ์จะเด้งขึ้นมาบังหน้าต่างทันทีที่เปิด */
    if (!isMobile() && (document.activeElement === PD.box || !PD.box.contains(document.activeElement))) PD.about.focus();
  }).catch(function (e) {
    if (mine !== PD.seq || !pdOpen()) return;
    pdFill({});
    PD.about.disabled = PD.custom.disabled = false;
    PD.save.disabled = true;
    pdFlash(t('pers_err_load') + ': ' + errText(e), true);
  });
}
function closePers() {
  if (!pdOpen()) return;
  PD.seq++;
  PD.wrap.classList.remove('on');
  PD.wrap.hidden = true;
  $('#app').inert = false;
  var back = PD.back;
  PD.back = null;
  if (!back || back === body || !visible(back)) back = [$('#acctBtn'), $('#burger'), $('#hdrNew')].filter(visible)[0];
  if (back) { try { back.focus(); } catch (e) {} }
}
/* Esc / คลิกม่าน ตอนมีข้อความที่ยังไม่ได้บันทึก: ครั้งแรกเตือน ครั้งที่สองปิด (ปุ่มยกเลิก/X ปิดทันที — ตั้งใจแล้ว) */
function pdEscape() {
  if (pdIsDirty() && !PD.esc) { PD.esc = true; pdFlash(t('pers_esc_again'), false); return; }
  closePers();
}
function pdSave() {
  if (!PD.ok || PD.save.disabled) return;
  var v = pdVal();
  if (v.style === 'custom' && !v.style_custom) { pdFlash(t('pers_need_custom'), true); PD.custom.focus(); return; }
  PD.save.disabled = true;
  api(HUB + '/api/settings', { method: 'PATCH', json: v }).then(function (d) {
    if (!d || typeof d.about_me !== 'string') { PD.ok = false; pdFlash(t('pers_unsupported'), true); return; }
    PD.base = { about_me: d.about_me, style: d.style || 'normal', style_custom: d.style_custom || '' };
    closePers();
    toast(t('pers_saved'));
  }).catch(function (e) {
    var s = srvMsg(e);
    pdFlash(t('errsave') + ': ' + (s ? glue(s) : errText(e)), true);
  }).then(function () { if (pdOpen() && PD.ok) PD.save.disabled = false; });
}
PD.about.addEventListener('input', function () { PD.esc = false; pdCount(); });
PD.custom.addEventListener('input', function () { PD.esc = false; pdCount(); });
[PD.about, PD.custom].forEach(function (ta) {
  ta.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); pdSave(); } });
});
PD.save.addEventListener('click', pdSave);
$('#pdCancel').addEventListener('click', function () { closePers(); });
$('#pdClose').addEventListener('click', function () { closePers(); });
/* mousedown ไม่ใช่ click: ลากเลือกข้อความในกล่องแล้วปล่อยนอกกล่องต้องไม่ปิด */
PD.wrap.addEventListener('mousedown', function (e) { if (e.target === PD.wrap) { e.preventDefault(); pdEscape(); } });
PD.wrap.addEventListener('keydown', function (e) {
  if (e.key !== 'Tab') return;
  var f = [].slice.call(PD.box.querySelectorAll('button, textarea, [tabindex="0"]')).filter(function (x) {
    return !x.disabled && x.getAttribute('tabindex') !== '-1' && visible(x);
  });
  if (!f.length) { e.preventDefault(); return; }
  var i = f.indexOf(document.activeElement);
  if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
  else if (!e.shiftKey && (i < 0 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
});

/* ---------------------------------------------------------------- แจ้งเตือน (K5) */
/* enhance เรียก qwenShellApi.notify({kind, title, body}) เมื่อคำตอบจบ (done) / ขออนุญาตใช้เครื่องมือ (permission)
   / รอให้กดทำต่อ (continue)  แสดงเฉพาะตอนแท็บถูกซ่อน: ชื่อแท็บขึ้น "(n) " เสมอ, การแจ้งเตือนของเดสก์ท็อป (+ เสียงสั้น)
   เฉพาะเมื่อผู้ใช้เปิดไว้ในเมนูบัญชีและเบราว์เซอร์อนุญาต  สิทธิ์ของเบราว์เซอร์ผูกกับ origin (ต่อพอร์ตโปรเจกต์)
   ค่าที่เลือกจึงเก็บใน localStorage ของโปรเจกต์นั้น (qwen-notify = off|on|sound) */
var NTF_KEY = 'qwen-notify';
var NTF = { badge: 0, last: {}, audio: null, icon: '', open: [], chimeAt: 0 };
function ntfPref() { var v = lsGet(NTF_KEY); return v === 'on' || v === 'sound' ? v : 'off'; }
function ntfPerm() { try { return window.Notification ? Notification.permission : 'unsupported'; } catch (e) { return 'unsupported'; } }
/* ค่าที่ใช้ได้จริง = ที่ผู้ใช้เลือก และเบราว์เซอร์ยังอนุญาตอยู่ — สิทธิ์ถูกถอน/รีเซ็ตโปรไฟล์ทีหลังได้โดยที่ qwen-notify ยังเป็น on
   เมนูแสดงค่านี้ (ไม่แสดง "เปิด" ทั้งที่ไม่มีอะไรขึ้น) ส่วนค่าที่เลือกไว้เก็บต่อ: อนุญาตคืนเมื่อไรก็กลับมาทำงานเอง */
function ntfEff() { return qwNtfState(ntfPref(), ntfPerm()).shown; }
/* คำเตือนใต้แถว "แจ้งเตือน" ในเมนูบัญชี: เลือกเปิดไว้แต่เบราว์เซอร์ไม่อนุญาต — บอกเหตุผลและทางแก้ */
function ntfWarnText() { var k = qwNtfState(ntfPref(), ntfPerm()).warn; return k ? t(k) : ''; }
function ntfPaintWarn(node, seg) {
  if (!node) return;
  var s = ntfWarnText();
  setText(node.querySelector('.ntf-warn-t'), s);
  setHidden(node, !s);
  if (seg) setAttr(seg.closest('.menu-row'), 'aria-describedby', s ? node.id : null);
}
function paintDocTitle() {
  var n = typeof NTF !== 'undefined' && NTF ? NTF.badge : 0;
  var want = (n ? '(' + n + ') ' : '') + (baseTitle || document.title);
  if (document.title !== want) document.title = want;
}
/* WebAudio ต้องถูกสร้าง/ปลุกระหว่างที่ผู้ใช้กดอะไรสักอย่าง (นโยบายเล่นเสียงอัตโนมัติ) — เรียกตอนเลือก "มีเสียง" */
function ntfAudio() {
  try {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!NTF.audio) NTF.audio = new AC();
    if (NTF.audio.state === 'suspended') NTF.audio.resume();
    return NTF.audio;
  } catch (e) { return null; }
}
/* เสียงสองโน้ตสั้นๆ (~0.35 วินาที) สร้างเอง ไม่มีไฟล์เสียง ไม่โหลดอะไรจากเน็ต — เว้นอย่างน้อย 4 วินาทีระหว่างครั้ง */
function ntfChime() {
  var ac = ntfAudio();
  if (!ac || Date.now() - NTF.chimeAt < 4000) return;
  NTF.chimeAt = Date.now();
  try {
    var t0 = ac.currentTime + 0.02;
    [[880, 0], [1318.5, 0.13]].forEach(function (n) {
      var o = ac.createOscillator(), g = ac.createGain();
      o.type = 'sine';
      o.frequency.value = n[0];
      g.gain.setValueAtTime(0.0001, t0 + n[1]);
      g.gain.exponentialRampToValueAtTime(0.12, t0 + n[1] + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + n[1] + 0.22);
      o.connect(g); g.connect(ac.destination);
      o.start(t0 + n[1]); o.stop(t0 + n[1] + 0.26);
    });
  } catch (e) {}
}
/* ไอคอนของการแจ้งเตือน: ตัว Q บนสี่เหลี่ยมมุมมนสีส้ม วาดเป็น PNG ครั้งเดียว (บางระบบแสดงไอคอน SVG ไม่ได้) */
function ntfIcon() {
  if (NTF.icon) return NTF.icon;
  try {
    var c = document.createElement('canvas'), g;
    c.width = c.height = 64;
    g = c.getContext('2d');
    g.fillStyle = '#d97757';
    if (g.roundRect) { g.beginPath(); g.roundRect(0, 0, 64, 64, 18); g.fill(); } else g.fillRect(0, 0, 64, 64);
    g.fillStyle = '#fff';
    g.font = '700 40px Georgia, "Times New Roman", serif';
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.fillText('Q', 32, 35);
    NTF.icon = c.toDataURL('image/png');
  } catch (e) {}
  return NTF.icon;
}
function setNotifyPref(v, seg, warn) {
  var prev = ntfPref();
  var paint = function () { ntfPaintWarn(warn, seg); };
  if (v === 'off') { lsSet(NTF_KEY, 'off'); if (prev !== 'off') toast(t('ntf_off_t')); paint(); return; }
  var ok = function () { lsSet(NTF_KEY, v); if (v === 'sound') { NTF.chimeAt = 0; ntfChime(); } toast(t('ntf_enabled')); paint(); };
  /* ไม่ได้รับอนุญาต: ปุ่มกลับไปที่ค่าที่ใช้ได้จริง (ปกติคือ "ปิด") ไม่ใช่ค่าที่เก็บไว้ ซึ่งอาจเป็น on ที่ใช้ไม่ได้ */
  var fail = function (key) { if (seg) segSet(seg, ntfEff()); toast(t(key), true); paint(); };
  var p = ntfPerm();
  if (v === 'sound') ntfAudio();        // ปลุกเสียงไว้ก่อน ระหว่างที่ยังเป็นการกดของผู้ใช้
  if (p === 'unsupported') { fail('ntf_unsupported'); return; }
  if (p === 'granted') { ok(); return; }
  if (p === 'denied') { fail('ntf_denied'); return; }
  try {
    Promise.resolve(Notification.requestPermission()).then(function (x) {
      if (x === 'granted') ok(); else fail(x === 'denied' ? 'ntf_denied' : 'ntf_not_granted');
    }, function () { fail('ntf_unsupported'); });
  } catch (e) { fail('ntf_unsupported'); }
}
function notify(o) {
  o = o && typeof o === 'object' ? o : {};
  var kind = /^(done|permission|continue)$/.test(o.kind) ? o.kind : 'other';
  if (document.visibilityState !== 'hidden') return false;
  var now = Date.now();
  /* enhance อาจรายงานเหตุการณ์เดียวกันซ้ำจากหลาย mutation ติดกัน */
  if (NTF.last[kind] && now - NTF.last[kind] < 2500) return false;
  NTF.last[kind] = now;
  NTF.badge = Math.min(NTF.badge + 1, 99);
  paintDocTitle();
  var pref = ntfPref();
  if (pref === 'off' || ntfPerm() !== 'granted') return false;
  var clip = function (s, n) { s = String(s == null ? '' : s).replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };
  var title = clip(o.title, 90) || tRaw({ done: 'ntf_done', permission: 'ntf_perm', 'continue': 'ntf_cont' }[kind] || 'ntf_generic');
  var text = clip(o.body, 180);
  /* tag จาก enhance (ต่อแชต) = การแจ้งเตือนใหม่ของแชตเดียวกันแทนอันเก่า ไม่กองเป็นตั้ง — นำหน้าด้วยพอร์ตกันชนข้ามโปรเจกต์
     chatId = กดการแจ้งเตือนแล้วพาไปแชตนั้น (รับเฉพาะรูปแบบ id ของ WebUI) */
  var tag = typeof o.tag === 'string' && /^[\w:.-]{1,120}$/.test(o.tag) ? o.tag : kind;
  var chatId = typeof o.chatId === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(o.chatId) ? o.chatId : '';
  try {
    /* silent: เสียงของเราเองเล่นแยก (ตั้ง renotify พร้อม silent ไม่ได้ — เบราว์เซอร์โยน TypeError) */
    var n = new Notification(title, { body: (text ? text + '\n' : '') + (PROJ.name || ''), tag: 'qwen-' + ME + '-' + tag,
      silent: true, icon: ntfIcon() || undefined, lang: LANG });
    n.onclick = function () {
      try { window.focus(); } catch (e) {}
      try { n.close(); } catch (e) {}
      if (chatId && !(ROUTE.name === 'chat' && ROUTE.id === chatId)) openChat(chatId);
      if (kind === 'permission' || kind === 'continue') { try { frame.focus(); } catch (e) {} }
    };
    NTF.open.push(n);
    if (NTF.open.length > 8) NTF.open.shift();
  } catch (e) { return false; }
  if (pref === 'sound') ntfChime();
  return true;
}
/* กลับมาที่แท็บ: ล้าง "(n)" และปิดการแจ้งเตือนเก่าของแท็บนี้ (เรื่องที่เห็นแล้วไม่ต้องค้างในศูนย์แจ้งเตือน)
   แผงโปรเจกต์เปิดค้างอยู่: อ่านความจำ/ไฟล์ที่สร้างใหม่ (โมเดลอาจเพิ่มระหว่างที่ไปทำอย่างอื่น) — ข้ามถ้ากำลังแก้ความจำ */
function ntfSeen() {
  if (NTF.badge) { NTF.badge = 0; paintDocTitle(); }
  NTF.open.forEach(function (n) { try { n.close(); } catch (e) {} });
  NTF.open = [];
}
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState !== 'visible') return;
  ntfSeen();
  if (panelOpen()) {
    if (!MEM.edit && memForm.hidden) loadMemory();
    loadOutputs();
  }
});
window.addEventListener('focus', ntfSeen);

/* ---------------------------------------------------------------- แผงแสดงผล (K7) */
/* enhance เรียก qwenShellApi.openArtifact({id, kind, title, code}) จากปุ่ม "เปิดในแผง" ของบล็อกโค้ด/รูปกราฟ
     kind: html | svg | mermaid | markdown | csv | image  (image: code = URL ของรูป /_qwen/out/… , data:image หรือ blob: ของหน้านี้)
     mermaid: ส่ง svg (ที่ WebUI วาดแล้ว) มาด้วยได้ — ถ้าไม่ส่ง shell หาเองจากบล็อกในแชตที่มีต้นฉบับตรงกัน
     id เดิม + code ใหม่ = เวอร์ชันใหม่ของชิ้นเดิม (ย้อนดูได้ในแผง)
   ความปลอดภัย — เนื้อหามาจากโมเดล (ถูก prompt injection ได้) ส่วน origin นี้ถือโทเคน MCP กับประวัติแชตอยู่:
   * แสดงใน iframe srcdoc ที่ sandbox ไม่มี allow-same-origin → origin ทึบ แตะ localStorage/IndexedDB/หน้า shell ไม่ได้
   * HTML: สคริปต์ปิดเป็นค่าเริ่มต้น (sandbox ว่าง + CSP ไม่มี script-src) — ผู้ใช้กด "เรียกใช้สคริปต์" เองต่อเวอร์ชัน
     จึงได้ allow-scripts  เหตุผล: สคริปต์สั่ง location = 'https://…?d=<ข้อมูล>' พาเฟรมตัวเองออกไปได้ และไม่มี sandbox flag
     หรือ CSP ข้อไหนห้ามได้ — โมเดลที่ถูก prompt injection ใส่เนื้อไฟล์ที่เพิ่งอ่านไว้ในบล็อก HTML แล้วแค่กด "เปิดในแผง"
     ข้อมูลก็ออกจากเครื่อง  ชนิดอื่น (svg/markdown/mermaid) sandbox ว่างเสมอ
   * CSP default-src 'none' เป็น <meta> ตัวแรกใน <head> (HTML ของโมเดลแยกด้วย DOMParser ซึ่งไม่รันอะไร แล้วแทรกไว้หน้าสุด)
     → fetch/XHR/WebSocket/รูป/ฟอนต์/iframe ซ้อน ออกเน็ตไม่ได้ + ตัด meta refresh, <base>, link prefetch/preconnect ทิ้ง
   * ลิงก์ (<a>/<area> ทั้ง HTML และ SVG) ถูกถอด href ที่ไม่ใช่ #anchor ออกตอนแยก — ไม่มีสคริปต์ก็ไม่มีตัวกันคลิก
     คลิกลิงก์คือการนำเฟรมออกไปพร้อม URL ที่มีข้อมูล; <animate>/<set> ที่เปลี่ยน href ก็ถูกตัด (สร้างลิงก์คืนได้โดยไม่ใช้สคริปต์)
   * ตอนเปิดสคริปต์: ตัวกันในเฟรมปิด RTCPeerConnection (CSP ไม่ครอบคลุม) กันคลิกลิงก์/ส่งฟอร์ม และบอกหน้า shell เมื่อหน้า
     กำลังถูกพาออกไป (beforeunload → postMessage พร้อมโทเคนของรอบที่แสดง) → shell ดึงเฟรมกลับ ปิดสคริปต์ และเตือน
     คำขอที่ออกไปแล้วเรียกคืนไม่ได้ — ตัวที่กันได้จริงคือสคริปต์ปิดเป็นค่าเริ่มต้น */
var art = $('#art'), artFrame = $('#artFrame'), artGrip = $('#artGrip');
var ART_MAX = 2000000;
var ART = { items: [], cur: null, vi: 0, mode: 'preview', back: null, backInner: null, autoMin: false, w: 0, modal: false, tok: '', doc: null, sb: null };
var ART_CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; form-action 'none'; base-uri 'none'";
var ART_CSP_JS = ART_CSP + "; script-src 'unsafe-inline'";
function artGuard(tok) {
  return "(function(){try{['RTCPeerConnection','webkitRTCPeerConnection','RTCDataChannel','RTCIceCandidate','RTCSessionDescription']" +
    ".forEach(function(k){try{Object.defineProperty(window,k,{value:undefined,writable:false,configurable:false})}catch(e){}});" +
    "addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[href]');" +
    "if(a&&(a.getAttribute('href')||'').charAt(0)!=='#')e.preventDefault()},true);" +
    "addEventListener('submit',function(e){e.preventDefault()},true);" +
    "var P=parent,T=" + JSON.stringify(String(tok || '')) + ";addEventListener('beforeunload',function(){try{P.postMessage({qwArt:'leave',tok:T},'*')}catch(e){}})" +
    "}catch(e){}})();";
}
/* โทเคนของการแสดงแต่ละรอบ — ข้อความ "กำลังออก" จากหน้าที่ shell แทนที่เองแล้ว (โทเคนเก่า) ไม่นับ */
function artTok() {
  var b = new Uint8Array(12), s = '';
  crypto.getRandomValues(b);
  for (var i = 0; i < b.length; i++) s += ('0' + b[i].toString(16)).slice(-2);
  return s;
}
function artOpen() { return !art.hidden; }
function artModal() { return artOpen() && isMobile(); }
/* สีของธีมปัจจุบัน ส่งเข้าไปใน srcdoc (เฟรมทึบอ่าน CSS ของเราไม่ได้) — ค่าจาก tokens.css ของเราเอง ตรวจรูปแบบกันไว้อีกชั้น */
function artVars() {
  var cs = getComputedStyle(document.documentElement);
  var g = function (k, d) { var v = cs.getPropertyValue(k).trim(); return /^[#\w(),.%\s-]+$/.test(v) ? v : d; };
  var dark = true;
  try { dark = window.qwenBoot.resolvedTheme() !== 'light'; } catch (e) {}
  return { bg: g('--qw-bg', '#262624'), text: g('--qw-text', '#f4f2ec'), text2: g('--qw-text-2', '#d8d6cd'), text3: g('--qw-text-3', '#b0ada3'),
    border: g('--qw-border-strong', 'rgba(128,128,128,.3)'), code: g('--qw-bg-code', '#1c1b1a'), icode: g('--qw-bg-inline-code', '#353431'),
    head: g('--qw-bg-elev', '#30302e'), dark: dark };
}
function artBaseCss(v, kind) {
  /* เฟรมทึบโหลดฟอนต์ของเรา (/_qwen/static/fonts) ไม่ได้ — ใช้ฟอนต์ของ Windows: Cambria (ตัวเลขสูงเท่าตัวพิมพ์ใหญ่ ต่างจาก
     Georgia ที่ตัวเลขห้อย "ST-002" อ่านยาก) ไทยตกไปที่ Leelawadee UI */
  var ui = '"Segoe UI","Leelawadee UI",Tahoma,system-ui,sans-serif', serif = 'Cambria,"Leelawadee UI","Noto Serif Thai",Georgia,Tahoma,serif';
  var mono = '"Cascadia Code","Cascadia Mono",Consolas,monospace';
  var css = ':root{color-scheme:' + (v.dark ? 'dark' : 'light') + '}html,body{margin:0;background:' + v.bg + ';color:' + v.text + '}' +
    'body{font:15px/1.7 ' + ui + '}';
  if (kind === 'svg' || kind === 'mermaid') {
    /* แผนภาพของ mermaid ตั้ง max-width เล็กไว้ในตัว (ขนาดในแชต) — ขยายให้เต็มแผงแต่ไม่เกิน 760px อ่านชื่อกล่องได้สบาย */
    css += 'body{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px;box-sizing:border-box}' +
      'body>svg{width:min(100%,760px)!important;max-width:100%!important;height:auto!important}';
  }
  if (kind === 'markdown') {
    css += '.md{max-width:760px;margin:0 auto;padding:22px 26px 56px;font:16px/1.7 ' + serif + '}' +
      '.md>:first-child{margin-top:0}.md h1,.md h2,.md h3,.md h4{font-weight:600;line-height:1.35;margin:1.2em 0 .5em}' +
      '.md h1{font-size:1.5em}.md h2{font-size:1.25em}.md h3{font-size:1.1em}.md p{margin:.6em 0}' +
      '.md ul,.md ol{padding-left:1.5em;margin:.5em 0}.md li{margin:.2em 0}' +
      '.md code{font:.88em ' + mono + ';background:' + v.icode + ';border-radius:5px;padding:.1em .3em}' +
      '.md pre{background:' + v.code + ';border:.5px solid ' + v.border + ';border-radius:12px;padding:12px 14px;overflow:auto;font:13px/1.55 ' + mono + '}' +
      '.md pre code{background:none;padding:0;font-size:inherit}' +
      '.md blockquote{margin:.8em 0;padding:0 0 0 14px;border-left:3px solid ' + v.border + ';color:' + v.text2 + '}' +
      '.md hr{border:0;border-top:.5px solid ' + v.border + ';margin:1.2em 0}' +
      '.md .tbl{overflow-x:auto;margin:.8em 0}.md table{border-collapse:collapse;font:14px/1.5 ' + ui + '}' +
      '.md th,.md td{border:.5px solid ' + v.border + ';padding:6px 10px;text-align:left;vertical-align:top}.md th{background:' + v.head + '}' +
      '.md .al-c{text-align:center}.md .al-r{text-align:right}.md img{max-width:100%}' +
      '.md .md-a{text-decoration:underline;text-underline-offset:2px;text-decoration-color:' + v.text3 + '}.md .md-img{color:' + v.text3 + '}';
  }
  return css;
}
function artStaticDoc(bodyHtml, css) {
  return '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + ART_CSP + '">' +
    '<meta http-equiv="x-dns-prefetch-control" content="off"><meta name="referrer" content="no-referrer"><style>' + css + '</style></head><body>' +
    bodyHtml + '</body></html>';
}
/* HTML จากโมเดล: DOMParser แยกเป็นเอกสาร (ไม่รันสคริปต์ ไม่โหลดอะไร) ตัดสิ่งที่พาออกเน็ตทิ้ง แล้วแทรก CSP + ตัวกัน
   ไว้หน้าสุดของ <head> — ต่อให้ต้นฉบับมี <head> ของตัวเองหรือไม่มีเลย CSP ก็ถูกอ่านก่อนเนื้อหาทุกส่วน */
/* run = ผู้ใช้กดเรียกใช้สคริปต์ของเวอร์ชันนี้แล้ว (ได้ CSP ที่มี script-src + ตัวกัน) · คืน {html, scripted}
   scripted = หน้านี้มีสคริปต์ (แท็ก <script>, on…= หรือ javascript:) — ไม่มีก็ไม่ต้องแสดงปุ่มเรียกใช้สคริปต์ */
function artHtmlDoc(code, run, tok) {
  var doc = new DOMParser().parseFromString(code, 'text/html');
  [].forEach.call(doc.querySelectorAll('base, meta[http-equiv], link[rel]'), function (n) {
    var he = (n.getAttribute('http-equiv') || '').toLowerCase(), rel = ' ' + (n.getAttribute('rel') || '').toLowerCase() + ' ';
    if (n.localName === 'base' || he === 'refresh' || he === 'set-cookie' ||
      /\s(dns-prefetch|preconnect|prefetch|prerender|preload|modulepreload|manifest|icon|stylesheet)\s/.test(rel)) n.remove();
  });
  var scripted = !!doc.querySelector('script');
  /* กติกาว่าตัดอะไร อยู่ใน qwArtDropEl / qwArtDropAttr / qwArtScriptAttr (_LIB_JS — ทดสอบใน node ได้) ตรงนี้แค่เดิน DOM */
  [].forEach.call(doc.querySelectorAll('*'), function (n) {
    var ln = n.localName;
    if (qwArtDropEl(ln, n.getAttribute('attributeName'))) { n.remove(); return; }
    [].slice.call(n.attributes).forEach(function (a) {
      var nm = a.name.toLowerCase();
      if (qwArtScriptAttr(nm, a.value)) scripted = true;
      if (!qwArtDropAttr(ln, nm, a.value)) return;
      /* ปลายทางของลิงก์ยังดูได้ใน title (ชี้ค้าง) แต่คลิกแล้วไม่พาเฟรมไปไหน */
      if ((ln === 'a' || ln === 'area') && nm !== 'ping' && !n.hasAttribute('title')) n.setAttribute('title', a.value.trim().slice(0, 300));
      n.removeAttribute(a.name);
    });
  });
  var mk = function (attrs) { var m = doc.createElement('meta'); Object.keys(attrs).forEach(function (k) { m.setAttribute(k, attrs[k]); }); return m; };
  var st = doc.createElement('style');
  st.textContent = 'html{background:#fff;color-scheme:light}';   // ก่อนสไตล์ของต้นฉบับ — ต้นฉบับทับได้
  var head = [mk({ charset: 'utf-8' }), mk({ 'http-equiv': 'Content-Security-Policy', content: run ? ART_CSP_JS : ART_CSP }),
    mk({ 'http-equiv': 'x-dns-prefetch-control', content: 'off' }), mk({ name: 'referrer', content: 'no-referrer' }), st];
  if (run) { var sc = doc.createElement('script'); sc.textContent = artGuard(tok); head.push(sc); }
  doc.head.prepend.apply(doc.head, head);
  return { html: '<!doctype html>\n' + doc.documentElement.outerHTML, scripted: scripted };
}
/* tok = โทเคนของรอบนี้ (เฉพาะ HTML ที่เปิดสคริปต์) — ตั้งใหม่ทุกครั้งก่อนเปลี่ยนเนื้อหา ข้อความจากเฟรมเก่าจึงหมดอายุทันที
   เนื้อหาและ sandbox เดิมทุกอย่าง = ไม่ต้องโหลดซ้ำ (หน้าที่มีสคริปต์ไม่ถูกเริ่มใหม่ตอนวาดแผงซ้ำ) */
function artSetFrame(sandbox, html, tok) {
  if (ART.doc === html && ART.sb === sandbox && artFrame.getAttribute('sandbox') === sandbox) return;
  ART.tok = tok || '';
  ART.doc = html;
  ART.sb = sandbox;
  ART.loadOk = true;
  /* sandbox มีผลตอนนำทางครั้งถัดไป — ตั้งก่อน srcdoc เสมอ (การตั้ง srcdoc คือการนำทาง) */
  if (artFrame.getAttribute('sandbox') !== sandbox) artFrame.setAttribute('sandbox', sandbox);
  artFrame.srcdoc = html;
}
function artShow(which) {
  setHidden(artFrame, which !== 'frame');
  setHidden($('#artTable'), which !== 'table');
  setHidden($('#artImgWrap'), which !== 'img');
  setHidden($('#artCode'), which !== 'code');
}
/* act = {label, run} → ปุ่มท้ายแถบ (เช่นสลับสคริปต์ของหน้า HTML) */
function artNote(text, warn, act) {
  var n = $('#artNote');
  n.replaceChildren(el('span', { class: 'art-note-t', text: text || '' }),
    act ? el('button', { type: 'button', class: 'art-note-b', id: 'artNoteB', text: act.label, onclick: act.run }) : null);
  n.classList.toggle('warn', !!warn);
  setHidden(n, !text);
}
/* สลับสคริปต์ของหน้า HTML เวอร์ชันที่ดูอยู่ (จำต่อเวอร์ชัน — เวอร์ชันใหม่ของชิ้นเดิมเริ่มที่ปิดเสมอ ต้องกดใหม่) */
function artRunJs(on) {
  var it = ART.cur, v = it && it.versions[ART.vi];
  if (!v || it.kind !== 'html') return;
  v.run = !!on;
  v.left = false;
  renderArt();
  var b = $('#artNoteB');
  if (b) b.focus();
  announce(t(on ? 'art_js_on' : 'art_js_off'));
}
/* หน้า HTML (ที่เปิดสคริปต์) กำลังพาเฟรมออกไปที่อื่น — ตัวกันในเฟรมส่งมาพร้อมโทเคนของรอบที่แสดงอยู่
   ดึงกลับเป็นแบบไม่มีสคริปต์ + เตือน (คำขอที่ออกไปแล้วเรียกคืนไม่ได้ แต่หน้าปลายทางไม่ค้างอยู่ในแผง และไม่ทำซ้ำ) */
window.addEventListener('message', function (e) {
  var d = e.data;
  if (e.source !== artFrame.contentWindow || !d || typeof d !== 'object' || d.qwArt !== 'leave') return;
  if (!ART.tok || d.tok !== ART.tok || !artOpen()) return;
  var it = ART.cur, v = it && it.versions[ART.vi];
  ART.tok = '';
  if (!v || it.kind !== 'html') { artSetFrame('', ''); return; }
  /* ปุ่มที่ผู้ใช้เพิ่งกด (เรียกใช้สคริปต์) ถูกวาดใหม่ — โฟกัสอยู่ในแผงก็ให้ไปอยู่ที่ปุ่มตัวใหม่ ไม่หล่นไป <body> */
  var had = art.contains(document.activeElement) || focusLost();
  v.run = false;
  v.left = true;
  renderArt();
  var nb = $('#artNoteB');
  if (had && nb) nb.focus({ preventScroll: true });
  announce(t('art_js_left'), true);
});
/* เฟรมโหลดครั้งที่สองโดยที่เราไม่ได้สั่ง (หน้าพาตัวเองไปที่อื่น/รีโหลด) — ลืมเนื้อหาที่จำไว้ รอบหน้าที่วาดจะโหลดใหม่เสมอ */
artFrame.addEventListener('load', function () { if (ART.loadOk) { ART.loadOk = false; return; } ART.doc = null; });
/* แผนภาพ mermaid ที่ WebUI วาดไว้แล้วในแชต: บล็อกที่ต้นฉบับ (data-mermaid-syntax) ตรงกับโค้ดที่ขอ — เลือก <svg> ใหญ่สุด
   ที่ไม่ใช่ไอคอนในปุ่ม  ไม่ตรงเป๊ะ = ไม่เดา (แสดงผิดแผนภาพแย่กว่าบอกว่ายังวาดไม่ได้) */
function findMermaidSvg(code) {
  var want = String(code || '').trim(), d;
  try { d = frame.contentDocument; } catch (e) { return ''; }
  if (!d || !want) return '';
  var roots = [];
  [].forEach.call(d.querySelectorAll('[data-mermaid-syntax]'), function (n) {
    if ((n.getAttribute('data-mermaid-syntax') || '').trim() === want) roots.push(n.closest('.mermaid-block-wrapper') || n);
  });
  [].forEach.call(d.querySelectorAll('.mermaid-block-wrapper'), function (w) {
    var c = w.querySelector('pre code, code, pre');
    if (roots.indexOf(w) < 0 && c && (c.textContent || '').trim() === want) roots.push(w);
  });
  var best = '', area = 0;
  roots.forEach(function (root) {
    [].forEach.call(root.querySelectorAll('svg'), function (s) {
      if (s.closest('button') || !s.querySelector('g')) return;
      var r = s.getBoundingClientRect(), a = Math.max(1, r.width * r.height);
      if (a > area) { area = a; best = s.outerHTML; }
    });
  });
  return best;
}
function renderCsv(text) {
  var r = qwCsv(text, 1001), box = $('#artTable');
  if (!r.rows.length) { box.replaceChildren(); return; }
  var head = r.rows[0], rows = r.rows.slice(1), ncol = 0, c, num = [];
  r.rows.forEach(function (x) { if (x.length > ncol) ncol = x.length; });
  /* คอลัมน์ตัวเลข (≥80% ของช่องที่ไม่ว่าง) ชิดขวา ตัวเลขกว้างเท่ากัน — อ่านเทียบค่าแนวตั้งได้ */
  for (c = 0; c < ncol; c++) {
    var cnt = 0, ok = 0;
    rows.forEach(function (x) { var s = (x[c] || '').trim(); if (s) { cnt++; if (/^[-+]?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?%?$/.test(s)) ok++; } });
    num.push(cnt > 0 && ok / cnt >= 0.8);
  }
  var th = [el('th', { class: 'rn', scope: 'col', text: '#' })];
  for (c = 0; c < ncol; c++) th.push(el('th', { scope: 'col', class: num[c] ? 'num' : null, text: head[c] || '', title: head[c] || null }));
  box.replaceChildren(el('table', null, [el('thead', null, [el('tr', null, th)]), el('tbody', null, rows.map(function (x, k) {
    var tds = [el('td', { class: 'rn', text: String(k + 1) })];
    for (var j = 0; j < ncol; j++) {
      var v = x[j] == null ? '' : x[j];
      tds.push(el('td', { class: num[j] ? 'num' : null, text: v, title: v.length > 40 ? v : null }));
    }
    return el('tr', null, tds);
  }))]));
  if (r.total > r.rows.length) artNote(fmtN(t('art_rows'), rows.length.toLocaleString(LANG), (r.total - 1).toLocaleString(LANG)));
}
function renderArt() {
  var it = ART.cur;
  if (!it) return;
  var v = it.versions[ART.vi], n = it.versions.length, kind = it.kind, name = it.title || t('art_k_' + kind);
  art.classList.remove('k-html', 'k-svg', 'k-mermaid', 'k-markdown', 'k-csv', 'k-image');
  art.classList.add('k-' + kind);
  setText($('#artKind'), t('art_k_' + kind));
  setAttr($('#artKind'), 'data-tip', kind === 'image' || kind === 'csv' ? null : t('art_sandbox'));
  setText($('#artTitle'), name);
  setAttr($('#artTitle'), 'title', name);
  setAttr(artFrame, 'title', fmt(t('art_frame'), name));
  setHidden($('#artList'), ART.items.length < 2);
  setHidden($('#artVer'), n < 2);
  setText($('#artVerT'), (ART.vi + 1) + ' / ' + n);
  setAttr($('#artVerT'), 'aria-label', fmtN(t('art_ver'), ART.vi + 1, n));
  $('#artPrev').disabled = ART.vi <= 0;
  $('#artNext').disabled = ART.vi >= n - 1;
  var canCode = kind !== 'image', mode = canCode ? ART.mode : 'preview';
  setHidden($('#artMode'), !canCode);
  [].forEach.call($('#artMode').children, function (b) {
    var on = b.getAttribute('data-v') === mode;
    b.classList.toggle('on', on);
    setAttr(b, 'aria-checked', String(on));
    setAttr(b, 'tabindex', on ? '0' : '-1');
  });
  setHidden($('#artCopy'), kind === 'image');
  artNote('');
  if (mode === 'code') { setText($('#artCodeC'), v.code); artShow('code'); artSetFrame('', ''); return; }
  var vars = artVars();
  if (kind === 'html') {
    /* สคริปต์ปิดเป็นค่าเริ่มต้น — เปิดได้เฉพาะเมื่อผู้ใช้กดปุ่มในแถบนี้ (v.run ถูกตั้งที่ artRunJs เท่านั้น) */
    var run = v.run === true, tok = run ? artTok() : '', hd = artHtmlDoc(v.code, run, tok);
    artSetFrame(run ? 'allow-scripts' : '', hd.html, tok);
    artShow('frame');
    if (run) artNote(t('art_js_on_note'), true, { label: t('art_js_stop'), run: function () { artRunJs(false); } });
    else if (v.left) artNote(t('art_js_left'), true, { label: t('art_js_run'), run: function () { artRunJs(true); } });
    else if (hd.scripted) artNote(t('art_js_off_note'), false, { label: t('art_js_run'), run: function () { artRunJs(true); } });
  }
  else if (kind === 'svg') { artSetFrame('', artStaticDoc(v.code, artBaseCss(vars, 'svg'))); artShow('frame'); }
  else if (kind === 'mermaid') {
    if (!v.svg) v.svg = findMermaidSvg(v.code);
    if (v.svg) { artSetFrame('', artStaticDoc(v.svg, artBaseCss(vars, 'mermaid'))); artShow('frame'); }
    else { artNote(t('art_mermaid_na'), true); setText($('#artCodeC'), v.code); artShow('code'); artSetFrame('', ''); }
  } else if (kind === 'markdown') {
    /* ลิงก์ในแผงเป็นแค่ข้อความขีดเส้นใต้ (links:false) — กดแล้วเฟรมจะวิ่งออกเน็ต ส่วนรูปได้เฉพาะ data:image ที่ฝังมา */
    artSetFrame('', artStaticDoc('<article class="md">' + qwMd(v.code, { images: true, links: false }) + '</article>', artBaseCss(vars, 'markdown')));
    artShow('frame');
  } else if (kind === 'csv') { renderCsv(v.code); artShow('table'); artSetFrame('', ''); }
  else if (kind === 'image') {
    var img = $('#artImg');
    img.alt = name;
    if (img.getAttribute('src') !== v.code) img.src = v.code;
    artShow('img');
    artSetFrame('', '');
  }
}
function artDefaultW() { return Math.round(Math.min(720, Math.max(380, (innerWidth - 56) * 0.42))); }
/* กว้างสุด = เหลือแชตอย่างน้อย 480px ข้างแถบข้าง (เดิม 360 — กด End/ลากสุดแล้วแชตเหลือแคบจนอ่านไม่ได้), แคบสุด 320px */
function artClampW(w) {
  var sbw = body.classList.contains('sb-min') ? 56 : 288, max = Math.max(320, innerWidth - sbw - 480);
  return Math.round(Math.min(Math.max(+w || 0, 320), max));
}
function artApplyW(w) {
  ART.w = artClampW(w);
  body.style.setProperty('--art-w', ART.w + 'px');
  setAttr(artGrip, 'aria-valuemin', '320');
  setAttr(artGrip, 'aria-valuemax', String(artClampW(1e6)));
  setAttr(artGrip, 'aria-valuenow', String(ART.w));
}
/* จอแคบ: แผงเต็มจอเป็น modal (หน้าข้างหลัง inert) · จอกว้าง: เป็นส่วนหนึ่งของหน้า ไม่ใช่ modal */
function artSyncModal() {
  var m = artModal();
  if (m) {
    art.setAttribute('role', 'dialog');
    art.setAttribute('aria-modal', 'true');
    $('#app').inert = true;
    ART.modal = true;
  } else {
    art.removeAttribute('role');
    art.removeAttribute('aria-modal');
    if (ART.modal) { ART.modal = false; if (!panelOpen() && !gpuOpen() && !pdOpen()) $('#app').inert = false; }
  }
}
function showArt() {
  ART.back = document.activeElement;
  ART.backInner = null;
  if (ART.back === frame) { try { ART.backInner = frame.contentDocument.activeElement; } catch (e) {} }
  closeMenu(); hideTip();
  if (!isMobile()) {
    var saved = parseInt(lsGet('qwen-art-w') || '', 10), w0 = saved > 0 ? saved : artDefaultW();
    /* แผงกว้าง + แถบข้างกางเต็ม = แชตเหลือต่ำกว่า 768px แล้ว WebUI สลับเป็นหน้ามือถือ — พับแถบข้างเป็นแถบไอคอน
       ชั่วคราว (ไม่บันทึกเป็นค่าที่ผู้ใช้เลือก) ปิดแผงแล้วกางคืนตามค่าเดิม */
    if (!body.classList.contains('sb-min') && innerWidth - 288 - w0 < 768 && innerWidth - 56 - artClampW(w0) >= 360) {
      unpeek();
      body.classList.add('sb-min');
      ART.autoMin = true;
      syncToggle();
    }
    artApplyW(w0);
  }
  art.hidden = false;
  body.classList.add('art-open');
  artSyncModal();
  requestAnimationFrame(function () { art.classList.add('on'); });
}
function closeArt(noFocus) {
  if (!artOpen()) return;
  var had = art.contains(document.activeElement) || focusLost();
  art.classList.remove('on');
  art.hidden = true;
  body.classList.remove('art-open');
  artSetFrame('', '');                  // หยุดสคริปต์ของหน้า HTML ที่แสดงอยู่ (ตัวจับเวลา/แอนิเมชัน)
  if (ART.autoMin) { ART.autoMin = false; applySidebarPref(); }
  artSyncModal();
  closeMenu();
  if (!had || noFocus) return;
  var b = ART.back;
  if (b === frame) {
    frame.focus();
    try { if (ART.backInner && ART.backInner.isConnected && ART.backInner !== frame.contentDocument.body) { ART.backInner.focus(); return; } } catch (e) {}
    if (callEnh('focusComposer')) return;
  }
  if (b && b !== body && visible(b)) { b.focus(); return; }
  frame.focus();
}
function openArtifact(o) {
  /* enhance ส่งรูปเป็น img.src (URL เต็ม http://127.0.0.1:81xx/_qwen/out/…) — ของ origin นี้เท่านั้นที่ตัดเหลือ path แล้วตรวจต่อ */
  if (o && typeof o === 'object') {
    var abs = location.origin + '/_qwen/out/';
    ['code', 'src'].forEach(function (k) {
      if (typeof o[k] === 'string' && o[k].indexOf(abs) === 0) { o = Object.assign({}, o); o[k] = o[k].slice(location.origin.length); }
    });
  }
  var a = qwArtNorm(o, ART_MAX);
  if (a && a.tooBig) { toast(t('art_too_big'), true); return false; }
  /* blob: ต้องเป็นของ origin นี้เท่านั้น (ของที่ iframe เพิ่งสร้าง) — qwArtNorm ตรวจแค่รูปแบบ */
  if (a && a.kind === 'image' && /^blob:/i.test(a.code) && a.code.indexOf('blob:' + location.origin + '/') !== 0) a = null;
  if (!a) { toast(t('art_bad'), true); return false; }
  var it = null;
  ART.items.forEach(function (x) { if (x.id === a.id) it = x; });
  if (!it) {
    it = { id: a.id, kind: a.kind, title: a.title, versions: [] };
    ART.items.push(it);
    /* จำไว้ไม่เกิน 30 ชิ้นต่อหน้า (อยู่ในหน่วยความจำของแท็บเท่านั้น) — ทิ้งชิ้นเก่าสุดที่ไม่ได้เปิดอยู่ */
    if (ART.items.length > 30) ART.items.splice(ART.items[0] === ART.cur ? 1 : 0, 1);
  }
  it.kind = a.kind;
  if (a.title) it.title = a.title;
  var last = it.versions[it.versions.length - 1];
  if (!last || last.code !== a.code || (a.svg && last.svg !== a.svg)) {
    it.versions.push({ code: a.code, svg: a.svg, at: Date.now() });
    if (it.versions.length > 20) it.versions.shift();
  }
  var same = artOpen() && ART.cur === it;
  ART.cur = it;
  ART.vi = it.versions.length - 1;
  if (!same) ART.mode = 'preview';
  if (!artOpen()) showArt();
  renderArt();
  if (!same) {
    /* ย้ายโฟกัสไปหัวเรื่องของแผง (อ่านชื่อชิ้นงาน) — อัปเดตชิ้นเดิมที่เปิดอยู่ไม่แย่งโฟกัส
       และไม่ดึงโฟกัสออกจากกล่อง modal ที่เปิดค้างอยู่ (ยืนยัน / เลือก GPU / ปรับให้เป็นของคุณ / แผงโปรเจกต์) */
    if (dlg.wrap.hidden && !gpuOpen() && !pdOpen() && !panelOpen()) { try { $('#artTitle').focus({ preventScroll: true }); } catch (e) {} }
    announce(fmt(t('art_opened'), it.title || t('art_k_' + it.kind)));
  }
  return true;
}
/* บันทึกไฟล์จาก Blob ในเครื่อง (ดาวน์โหลดของเบราว์เซอร์) — ใช้ทั้งแผงแสดงผลและการส่งออกแชต */
function saveBlob(blob, name) {
  var u = URL.createObjectURL(blob), a = el('a', { href: u, download: name, hidden: true });
  body.append(a);
  a.click();
  a.remove();
  setTimeout(function () { URL.revokeObjectURL(u); }, 60000);
}
var ART_EXT = { html: 'html', svg: 'svg', mermaid: 'mmd', markdown: 'md', csv: 'csv' };
var ART_TYPE = { html: 'text/html', svg: 'image/svg+xml', mermaid: 'text/plain', markdown: 'text/markdown', csv: 'text/csv' };
function artDownload() {
  var it = ART.cur;
  if (!it) return;
  var v = it.versions[ART.vi];
  var base = qwFileName(it.title || t('art_k_' + it.kind), '').replace(/\.(html?|svg|mmd|md|csv|png|jpe?g|gif|webp)$/i, '') || 'qwen';
  if (it.kind === 'image') {
    fetch(v.code).then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.blob(); }).then(function (b) {
      var ext = ((/image\/(png|jpeg|gif|webp)/.exec(b.type) || [0, 'png'])[1]).replace('jpeg', 'jpg');
      saveBlob(b, base + '.' + ext);
    }).catch(function (e) { failToast(t('art_img_err'), e); });
    return;
  }
  /* แผนภาพที่กำลังดูเป็นรูป → ได้ .svg ของรูปนั้น · ดูโค้ดอยู่ → ได้ต้นฉบับ .mmd */
  if (it.kind === 'mermaid' && ART.mode === 'preview' && v.svg) { saveBlob(new Blob([v.svg], { type: 'image/svg+xml' }), base + '.svg'); return; }
  /* CSV ได้ BOM นำหน้า (qwDlText) — Excel ที่เปิดด้วยการดับเบิลคลิกอ่านไฟล์ไม่มี BOM เป็น ANSI แล้วภาษาไทยเพี้ยน
     ปุ่มคัดลอกยังให้ข้อความเดิม (วางในที่อื่นไม่ต้องมีอักขระแฝง) */
  saveBlob(new Blob([qwDlText(it.kind, v.code)], { type: (ART_TYPE[it.kind] || 'text/plain') + ';charset=utf-8' }), base + '.' + (ART_EXT[it.kind] || 'txt'));
}
$('#artClose').addEventListener('click', function () { closeArt(); });
$('#artCopy').addEventListener('click', function () {
  var it = ART.cur;
  if (!it) return;
  copyText(it.versions[ART.vi].code).then(function () { toast(t('copied')); }, function () { toast(t('err_generic'), true); });
});
$('#artDl').addEventListener('click', artDownload);
$('#artPrev').addEventListener('click', function () { if (ART.cur && ART.vi > 0) { ART.vi--; renderArt(); if (this.disabled) $('#artNext').focus(); } });
$('#artNext').addEventListener('click', function () { if (ART.cur && ART.vi < ART.cur.versions.length - 1) { ART.vi++; renderArt(); if (this.disabled) $('#artPrev').focus(); } });
$('#artMode').addEventListener('click', function (e) {
  var b = e.target.closest('button[data-v]');
  if (!b || !ART.cur) return;
  ART.mode = b.getAttribute('data-v');
  renderArt();
});
$('#artMode').addEventListener('keydown', function (e) {
  if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(e.key) < 0 || !ART.cur) return;
  e.preventDefault();
  ART.mode = ART.mode === 'code' ? 'preview' : 'code';
  renderArt();
  var on = $('#artMode').querySelector('[aria-checked="true"]');
  if (on) on.focus();
});
$('#artList').addEventListener('click', function () {
  openMenu(this, ART.items.slice().reverse().map(function (x) {
    return { label: (x.title || t('art_k_' + x.kind)) + ' · ' + t('art_k_' + x.kind), icon: x.kind === 'image' ? 'image' : x.kind === 'csv' ? 'grid' : 'code',
      run: function () { ART.cur = x; ART.vi = x.versions.length - 1; ART.mode = 'preview'; renderArt(); $('#artTitle').focus(); } };
  }), 'end', { label: t('art_list') });
});
$('#artImg').addEventListener('error', function () { if (artOpen() && ART.cur && ART.cur.kind === 'image') artNote(t('art_img_err'), true); });
/* ลากขอบซ้ายของแผงเพื่อปรับความกว้าง (จำไว้ใน qwen-art-w) · คีย์บอร์ด: ← กว้างขึ้น → แคบลง
   Home = แคบสุด (aria-valuemin) End = กว้างสุด (aria-valuemax) ตามแบบ window splitter ของ ARIA — ค่าที่อ่านออกเสียงคือความกว้างแผง */
artGrip.addEventListener('pointerdown', function (e) {
  if (isMobile() || e.button) return;
  e.preventDefault();
  try { artGrip.setPointerCapture(e.pointerId); } catch (x) {}
  body.classList.add('art-drag');
  var move = function (ev) { artApplyW(innerWidth - ev.clientX); };
  var up = function () {
    artGrip.removeEventListener('pointermove', move);
    artGrip.removeEventListener('pointerup', up);
    artGrip.removeEventListener('pointercancel', up);
    body.classList.remove('art-drag');
    lsSet('qwen-art-w', String(ART.w));
  };
  artGrip.addEventListener('pointermove', move);
  artGrip.addEventListener('pointerup', up);
  artGrip.addEventListener('pointercancel', up);
});
artGrip.addEventListener('keydown', function (e) {
  var w = ART.w || artDefaultW(), nw = e.key === 'ArrowLeft' ? w + 32 : e.key === 'ArrowRight' ? w - 32 : e.key === 'Home' ? 0 : e.key === 'End' ? 1e6 : null;
  if (nw == null) return;
  e.preventDefault();
  artApplyW(nw);
  lsSet('qwen-art-w', String(ART.w));
});
/* จอแคบ (modal): Tab วนอยู่ในแผง */
art.addEventListener('keydown', function (e) {
  if (e.key !== 'Tab' || !artModal()) return;
  var f = [].slice.call(art.querySelectorAll('button, [tabindex="0"]')).filter(function (x) { return !x.disabled && visible(x); });
  if (!f.length) return;
  var i = f.indexOf(document.activeElement);
  if (e.shiftKey && i <= 0) { e.preventDefault(); f[f.length - 1].focus(); }
  else if (!e.shiftKey && (i < 0 || i === f.length - 1)) { e.preventDefault(); f[0].focus(); }
});
NARROW.addEventListener('change', function () { if (artOpen()) { artSyncModal(); if (!isMobile()) artApplyW(ART.w || artDefaultW()); } });
window.addEventListener('resize', function () { if (artOpen() && !isMobile()) artApplyW(ART.w || artDefaultW()); });

/* ---------------------------------------------------------------- ส่งออกแชต (K10) */
/* อ่านบทสนทนาจาก IndexedDB ของ WebUI (origin เดียวกัน) → กิ่งที่เปิดอยู่ → รอบสนทนา → ไฟล์ .md / .html หรือหน้าพิมพ์
   ความคิดของโมเดลพับไว้ (<details>) การเรียกเครื่องมือสรุปเป็นชื่อ + อาร์กิวเมนต์ + ผลลัพธ์ (ตัดเมื่อยาว)
   ข้อความของเราในไฟล์ใช้ tRaw (ไม่มี U+2060 ที่ glue ใส่ — ไฟล์ส่งต่อได้ ค้นหา/คัดลอกแล้วตรง) */
function loadConvFull(id) {
  return withDB(function (db) {
    if (!db.objectStoreNames.contains('conversations') || !db.objectStoreNames.contains('messages')) return null;
    var tx = db.transaction(['conversations', 'messages']), ms = tx.objectStore('messages');
    var msgs = ms.indexNames.contains('convId') ? reqP(ms.index('convId').getAll(IDBKeyRange.only(id)))
      : reqP(ms.getAll()).then(function (a) { return (a || []).filter(function (m) { return m && m.convId === id; }); });
    return Promise.all([reqP(tx.objectStore('conversations').get(id)), msgs]).then(function (r) { return { conv: r[0], msgs: r[1] || [] }; });
  });
}
function exportLabels() {
  return {
    lang: LANG, you: tRaw('exp_you'), reasoning: tRaw('exp_reasoning'), tool: tRaw('exp_tool'), args: tRaw('exp_args'),
    result: tRaw('exp_result'), noResult: tRaw('exp_no_result'), attach: tRaw('exp_attach'), cut: tRaw('exp_cut'),
    printHint: tRaw('exp_print_hint'),
    time: function (ms) {
      try { return new Date(ms).toLocaleString(LANG, { dateStyle: 'medium', timeStyle: 'short' }); }
      catch (e) { return new Date(ms).toISOString(); }
    }
  };
}
/* รูปที่ Qwen สร้างในโปรเจกต์ (![fig](/_qwen/out/…) เช่นกราฟจาก python) — ไฟล์ HTML/หน้าพิมพ์เปิดนอก origin นี้
   และ CSP ของไฟล์รับรูปแค่ data: จึงอ่านรูปจาก hub (origin เดียวกัน) แล้วฝังเป็น data URL
   เฉพาะ png/jpeg/gif/webp (ไม่รับ svg — มีสคริปต์ได้) รูปละ ≤ 2 MB รวม ≤ 20 MB ไม่เกิน 40 รูป และรอไม่เกิน 3 วินาที
   (หน้าพิมพ์เปิดแท็บใหม่หลังรอนี้ — นานเกินไปเบราว์เซอร์จะไม่นับว่าเป็นการกดของผู้ใช้แล้วบล็อกป๊อปอัป)
   รูปที่ฝังไม่ได้ขึ้นเป็นชื่อไฟล์แทน [fig] เปล่าๆ (qwMdInline) */
var EXP_IMG_MAX = 2000000, EXP_IMG_TOTAL = 20000000;
function expInlineImgs(turns) {
  var urls = qwOutImgs(turns, 40), map = {}, total = 0;
  if (!urls.length) return Promise.resolve(map);
  var ctl = window.AbortController ? new AbortController() : null, done = false;
  var toData = function (b) {
    return new Promise(function (res) {
      var fr = new FileReader();
      fr.onload = function () { res(String(fr.result || '')); };
      fr.onerror = function () { res(''); };
      fr.readAsDataURL(b);
    });
  };
  var all = Promise.all(urls.map(function (u) {
    return fetch(u, { cache: 'no-store', credentials: 'same-origin', signal: ctl ? ctl.signal : undefined }).then(function (r) {
      if (!r.ok || (+r.headers.get('content-length') || 0) > EXP_IMG_MAX) return null;
      return r.blob();
    }).then(function (b) {
      if (!b || done || b.size > EXP_IMG_MAX || total + b.size > EXP_IMG_TOTAL || !/^image\/(png|jpeg|gif|webp)$/i.test(b.type)) return;
      total += b.size;
      return toData(b).then(function (d) { if (!done && qwSafeImg(d)) map[u] = d; });
    }).catch(function () {});
  }));
  var late = new Promise(function (res) { setTimeout(res, 3000); });
  return Promise.race([all, late]).then(function () { done = true; if (ctl) { try { ctl.abort(); } catch (e) {} } return map; });
}
function exportChat(id, kind) {
  loadConvFull(id).then(function (d) {
    if (!d || !d.conv) throw new Error('not found');
    var turns = qwTurns(qwConvPath(d.conv, d.msgs));
    if (!turns.length) { toast(t('exp_empty'), true); return; }
    var title = convTitle(d.conv), L = exportLabels();
    L.meta = qwFmtN(tRaw('exp_meta'), PROJ.name || '', L.time(Date.now()));
    /* ลิงก์ /_qwen/out/… ในไฟล์ที่ส่งออกเป็นที่อยู่เต็มของพอร์ตโปรเจกต์นี้ — เปิดไฟล์นอกเบราว์เซอร์นี้แล้วยังกดถึงไฟล์ได้
       (เฉพาะบนเครื่องนี้ ตอน hub ทำงาน) */
    var base = location.origin;
    if (kind === 'md') {
      var mdName = qwFileName(title, 'md');
      saveBlob(new Blob([qwExportMd(title, turns, L, { base: base })], { type: 'text/markdown;charset=utf-8' }), mdName);
      toast(fmt(t('exp_done'), mdName));
      return;
    }
    return expInlineImgs(turns).then(function (imgs) {
      if (kind === 'html') {
        var htmlName = qwFileName(title, 'html');
        saveBlob(new Blob([qwExportHtml(title, turns, L, { imgs: imgs, base: base })], { type: 'text/html;charset=utf-8' }), htmlName);
        toast(fmt(t('exp_done'), htmlName));
        return;
      }
      /* หน้าพิมพ์: แท็บใหม่แบบ noopener (แยกจากหน้านี้ — กล่องพิมพ์ของเบราว์เซอร์ไม่ทำให้แชตที่กำลังสตรีมค้าง)
         สคริปต์เดียวในหน้านั้นคือคำสั่ง print() ที่มี nonce สุ่ม นอกนั้น CSP ปิดสคริปต์และการโหลดจากเน็ตทั้งหมด */
      var nonce = '', buf = new Uint8Array(16);
      crypto.getRandomValues(buf);
      for (var i = 0; i < buf.length; i++) nonce += ('0' + buf[i].toString(16)).slice(-2);
      var u = URL.createObjectURL(new Blob([qwExportHtml(title, turns, L, { print: true, nonce: nonce, imgs: imgs, base: base })], { type: 'text/html;charset=utf-8' }));
      window.open(u, '_blank', 'noopener');
      setTimeout(function () { URL.revokeObjectURL(u); }, 120000);
      toast(t('exp_print_opened'));
    });
  }).catch(function (e) { failToast(t('exp_err'), e); });
}

/* ---------------------------------------------------------------- API ให้ iframe เรียก */
window.qwenShellApi = {
  version: '1',
  newChat: newChat,
  openChat: openChat,
  focusSearch: focusSearch,
  toggleSidebar: toggleSidebar,
  openProjectPanel: openPanel,
  closeProjectPanel: closePanel,
  refreshRecents: function () { lastRecSig = ''; return refreshRecents(); },
  onRoute: function (r) { if (r && r.name) setRoute(r); },
  openGpu: function () { openGpu(); },
  toast: toast,
  /* ---- สัญญารอบ 4 (enhance เรียก) — ห่อ try: ข้อผิดพลาดฝั่ง shell ต้องไม่ลามไปพังหน้าแชต ----
     notify({kind: 'done'|'permission'|'continue', title?, body?, tag?, chatId?}) → true เมื่อขึ้นการแจ้งเตือนของเดสก์ท็อปจริง
       (แท็บที่มองเห็นอยู่ไม่ทำอะไร คืน false; แท็บที่ซ่อนได้ "(n)" ที่ชื่อแท็บเสมอ; กดการแจ้งเตือน = กลับมาที่แชต chatId)
     openArtifact({id, kind: 'html'|'svg'|'mermaid'|'markdown'|'csv'|'image', title?, code, svg?}) → true เมื่อแสดงในแผง
       (image: code = /_qwen/out/<ชื่อ> | data:image/…;base64 | blob: ของ origin นี้  · mermaid: svg = ที่ WebUI วาดแล้ว ถ้ามี) */
  notify: function (o) { try { return notify(o); } catch (e) { return false; } },
  openArtifact: function (o) {
    try { return openArtifact(o); } catch (e) { try { console.warn('[qwen] openArtifact', e); } catch (x) {} return false; }
  },
  closeArtifact: function () { closeArt(); },
  openPersonalize: function () { openPers(); },
  /* batch 2a (B5): เติมคำขอ "ค้นคว้าเชิงลึก" ลงช่องพิมพ์ (ใช้ข้อความที่พิมพ์ค้างเป็นหัวข้อ) — enhance เรียกจากเมนู "+" */
  startResearch: function () { try { return startResearch(); } catch (e) { return false; } },
  openResearch: function () { openPanel(); setTimeout(function () { try { $('#ppRes').scrollIntoView({ block: 'start' }); } catch (e) {} }, 80); },
  /* batch 2a (fix, owner stack): enhance เรียกตอนเริ่ม/จบการตอบ — ตั้งชื่อแชตที่เริ่มจากชิปสกิล → Promise<ชื่อใหม่|''> */
  nameSkillChat: function (id) { try { return nameSkillChat(id); } catch (e) { return Promise.resolve(''); } },
  /* batch 2b (C4, owner ui): สถานะบริการล่าสุดที่ hub รายงาน (สำเนา) — enhance ใช้ services().stt ตัดสินว่าปุ่มไมค์พร้อมไหม
     null = hub รุ่นก่อน / ยังไม่เคยตรวจ (enhance ถือว่าไม่รู้ ให้ลองกดได้) */
  services: function () { try { return SVC ? JSON.parse(JSON.stringify(SVC)) : null; } catch (e) { return null; } }
};

/* ---------------------------------------------------------------- เริ่มทำงาน */
renderProjects();
paintHealth();
paintPanel(true);
renderRecents();
/* เปิดแชตจากลิงก์ของ shell ได้ (#/chat/<id>) — ใช้กับ F5 และคลิกกลางที่รายการแชต
   เพิ่งสลับภาษามา: ใช้เส้นทางที่ iframe อยู่จริงก่อนโหลด (ผ่าน CARRY_HASH แล้วใน takeCarry) แทน hash ของ shell */
var carry = takeCarry();
carryLeft = carry;
var initHash = carry && carry.hash ? carry.hash : location.hash;
var initRoute = routeFromHash(initHash);
if (initRoute.name === 'chat') setRoute(initRoute);
else {
  /* iframe ไม่ได้อยู่ในแชต แต่ลิงก์ของ shell ยังค้าง #/chat/… — ล้างให้ตรงกัน กด F5 ครั้งหน้าจะได้ไม่เด้งไปแชตเก่า */
  if (carry && carry.hash && /^#\/chat\//.test(location.hash)) { try { history.replaceState(null, '', location.pathname + location.search); } catch (e) {} }
  paintHeader();
}
/* ตั้ง src หลัง boot.js เขียน LlamaUi.config เสร็จ (boot.js รันใน <head>)
   ถ้าให้ parser สร้าง iframe เอง เบราว์เซอร์อาจหยิบหน้าเดิมจากแคชมาอ่าน config ก่อนเราเขียน */
framePending = true;
frame.src = uiSrc() + (initRoute.name === 'chat' ? '#/chat/' + encodeURIComponent(initRoute.id)
  : carry && carry.hash === '#/search' ? carry.hash : '');
refreshRecents();
refreshHub();
/* แท็บที่ซ่อนอยู่ไม่ต้องถาม hub — ทุกครั้งที่ถาม hub ไปถาม llama-server ต่อ ซึ่งกำลังยุ่งอยู่แล้ว
   กลับมาที่แท็บเมื่อไร visibilitychange ข้างล่างดึงใหม่ทันที */
setInterval(function () { if (document.visibilityState === 'visible') refreshHub(); }, 10000);
setInterval(function () {
  if (document.visibilityState !== 'visible') return;
  if (!enh() && !wantRoute && !framePending) { var r = routeFromHash(frameHash()); if (frame.contentWindow && frameHash()) setRoute(r); }
  if (ROUTE.name === 'chat') pruneTabs(ROUTE.id);
  refreshRecents();
}, 3000);
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState === 'visible') { refreshRecents(); refreshHub(); }
});
})();
</script>
</body>
</html>"""


# --------------------------------------------------------------------------
# PAGE — หน้าจัดการโปรเจกต์ เสิร์ฟจาก hub พอร์ต 8100 (คนละ origin กับหน้าแชต)
# จึงอ่าน localStorage ของหน้าแชตไม่ได้ ธีมมาจากค่าที่ hub เก็บ (__THEME__) ?theme= จาก shell ทับได้
# --------------------------------------------------------------------------
PAGE = r"""<!doctype html>
<html lang="__LANG__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Qwen3.8 - __T_hubtitle__</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='9' fill='%23d97757'/%3E%3Ctext x='16' y='22.5' text-anchor='middle' font-family='Georgia,serif' font-size='20' font-weight='700' fill='white'%3EQ%3C/text%3E%3C/svg%3E">
<script>
/* ธีมที่ผู้ใช้เลือกเก็บที่ hub (__THEME__ = dark|light|system) — ไม่อ่าน localStorage ของพอร์ตนี้แล้ว
   เพราะค่าที่ค้างอยู่จะทับค่าจริงจาก hub  ?theme= จากเมนูของ shell ทับได้เฉพาะการเปิดครั้งนี้
   (เผื่อ PATCH ธีมที่เพิ่งกดยังไปไม่ถึง hub ตอนหน้านี้โหลด) */
(function () {
  var th = '__THEME__';
  try {
    var q = new URLSearchParams(location.search).get('theme');
    if (q === 'dark' || q === 'light' || q === 'system') th = q;
    if (th === 'system') th = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch (e) {}
  document.documentElement.setAttribute('data-theme', th === 'light' ? 'light' : 'dark');
})();
</script>
<link rel="stylesheet" href="/_qwen/static/fonts.css">
<link rel="stylesheet" href="/_qwen/static/tokens.css">
<style>
*,*::before,*::after{box-sizing:border-box}
html{background:var(--qw-bg)}
body{margin:0;min-height:100vh;background:var(--qw-bg);color:var(--qw-text);font-family:var(--qw-font-ui);
  font-size:var(--qw-fs-base);line-height:1.55;-webkit-font-smoothing:antialiased}
button,input,textarea{font:inherit;color:inherit}
button{cursor:pointer;background:none;border:0;padding:0}
:focus{outline:none}
:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:2px}
::selection{background:color-mix(in srgb,var(--qw-accent) 32%,transparent)}
[hidden]{display:none!important}
.ic{width:16px;height:16px;flex:none;fill:none;stroke:currentColor;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}
.wrap{max-width:880px;margin:0 auto;padding:22px 24px 64px}
.top{display:flex;align-items:center;gap:12px;height:44px}
/* โลโก้ไม่หด ป้ายสถานะเป็นตัวที่หดแทน (ตัด … ท้าย) — เดิมโลโก้หดจนป้ายสถานะทับคำว่า Qwen3.8 ที่ 390px */
.brand{display:flex;align-items:center;gap:10px;flex:none}
.mark{width:28px;height:28px;flex:none;border-radius:8px;background:var(--qw-accent);color:var(--qw-accent-fg);
  display:inline-flex;align-items:center;justify-content:center;font-family:var(--qw-font-serif);font-weight:600;font-size:17px;padding-bottom:1px}
.wordmark{font-family:var(--qw-font-serif);font-weight:600;font-size:17px;white-space:nowrap}
.status{display:inline-flex;align-items:center;gap:8px;height:30px;padding:0 12px;border-radius:999px;font-size:var(--qw-fs-xs);
  color:var(--qw-text-3);box-shadow:inset 0 0 0 .5px var(--qw-border-strong);flex:0 1 auto;min-width:0;margin-left:auto}
#st{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* ส่วนท้ายที่ตัดได้ (" · RTX 4090", " · พอร์ต 8099") — ถ้าป้ายไม่พอที่ (fitStatus) ซ่อนจากตาทีละท่อนจากท้าย
   (พอร์ตก่อน แล้วค่อย GPU) แทนการตัด … กลางตัวเลข ส่วนหลัก "พร้อมใช้งาน · 4 โมเดล" ไม่ถูกดันตกขอบ
   โปรแกรมอ่านหน้าจอยังอ่านครบ ข้อความเต็มอยู่ใน title ด้วย */
.status .st-opt.cut{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
/* "GPU เปลี่ยน" ในป้าย: warn ผสมสีตัวอักษร (warn ล้วนบนพื้นสว่างได้แค่ ~3:1) */
.st-warn{color:color-mix(in srgb,var(--qw-warn) 70%,var(--qw-text))}
/* คำเตือน GPU เปลี่ยนหลังเปิดครั้งล่าสุด — บรรทัดเดียวใต้หัว พื้นเหลืองอำพันจางๆ ชัดแต่ไม่ใช่สีแดงของข้อผิดพลาด */
.gpu-note{display:flex;align-items:flex-start;gap:9px;margin:12px 0 0;padding:9px 14px;border-radius:var(--qw-r-md);
  font-size:var(--qw-fs-sm);line-height:1.55;color:var(--qw-text-2);background:color-mix(in srgb,var(--qw-warn) 11%,transparent);
  box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 45%,transparent)}
.gpu-note .ic{color:var(--qw-warn);margin-top:2px}
/* สวิตช์ภาษา ไทย | EN — หน้าตาเดียวกับบนหัวของหน้าแชต (ดูคำอธิบายที่ .lsw ใน SHELL) */
.lsw{display:inline-flex;align-items:center;gap:2px;height:28px;padding:2px;flex:none;border-radius:var(--qw-r-full);
  box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.lsw button{position:relative;display:inline-flex;align-items:center;justify-content:center;height:24px;min-width:34px;padding:0 9px;
  border-radius:var(--qw-r-full);color:var(--qw-text-3);font-size:var(--qw-fs-xs);font-weight:500;line-height:1;white-space:nowrap;
  transition:background-color var(--qw-dur) var(--qw-ease),color var(--qw-dur) var(--qw-ease)}
.lsw button[lang="th"]{font-size:var(--qw-fs-sm)}
.lsw button:hover{background:color-mix(in srgb,var(--qw-bg-hover) 55%,transparent);color:var(--qw-text)}
.lsw button[aria-pressed="true"]{background:var(--qw-bg-active);color:var(--qw-text);cursor:default;
  box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px var(--qw-border)}
.lsw[aria-busy="true"] button{cursor:progress}
/* หน้านี้ไม่มีระบบป้ายชื่อแบบ shell (#tip) — ใช้ ::after หน้าตาเดียวกัน หน่วง 450ms ตอนชี้ ขึ้นทันทีตอนโฟกัสด้วยคีย์บอร์ด
   ชิดขวาใต้ปุ่ม เพราะสวิตช์อยู่ขอบขวาของหัว ถ้าจัดกึ่งกลาง ป้ายยาวจะล้นจอ */
.lsw button[data-tip]::after{content:attr(data-tip);position:absolute;right:0;top:calc(100% + 8px);z-index:5;padding:5px 9px;
  border-radius:var(--qw-r-xs);background:var(--qw-text);color:var(--qw-bg);font-size:var(--qw-fs-xs);font-weight:500;line-height:1.4;
  white-space:nowrap;box-shadow:var(--qw-shadow-md);opacity:0;pointer-events:none;transition:opacity var(--qw-dur) var(--qw-ease)}
.lsw button[data-tip]:hover::after{opacity:1;transition-delay:.45s}
.lsw button[data-tip]:focus-visible::after{opacity:1}
@media (max-width:639.98px){
  .lsw{height:32px;padding:0;box-shadow:none}
  .lsw button[aria-pressed="true"]{display:none}
  .lsw button{height:28px;min-width:32px;padding:0 9px;color:var(--qw-text-2);box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
}
.dot{width:8px;height:8px;border-radius:50%;background:var(--qw-text-4);flex:none}
.dot.ok{background:var(--qw-ok)} .dot.bad{background:var(--qw-danger)}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:34px;padding:0 14px;border-radius:var(--qw-r-sm);
  font-size:var(--qw-fs-base);font-weight:500;white-space:nowrap;transition:background-color var(--qw-dur),opacity var(--qw-dur),color var(--qw-dur)}
.btn.sm{height:30px;padding:0 11px;font-size:var(--qw-fs-sm)}
.btn-ink{background:var(--qw-text);color:var(--qw-bg)}
.btn-ink:hover{opacity:.86}
.btn-ghost{color:var(--qw-text-2);box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.btn-ghost:hover{background:var(--qw-bg-hover);color:var(--qw-text)}
.btn-ghost.danger:hover{color:var(--qw-danger)}
/* พื้นทึบ + ตัวอักษรขาว = danger-bg (≥5.3:1) — --qw-danger เป็นสีตัวอักษร ธีมมืดสว่างเกินรองขาว */
.btn-danger{background:var(--qw-danger-bg);color:#fff}
.btn-danger:hover{background:color-mix(in srgb,var(--qw-danger-bg) 88%,#000)}
h1{margin:40px 0 6px;font-family:var(--qw-font-serif);font-weight:400;font-size:clamp(28px,4vw,36px);line-height:1.25;letter-spacing:-.01em}
.sub{margin:0 0 28px;color:var(--qw-text-3);font-size:var(--qw-fs-base);max-width:620px}
.card{background:var(--qw-bg-elev);border-radius:var(--qw-r-lg);box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px var(--qw-border)}
.new{padding:18px 18px 16px;margin-bottom:36px}
.new h2,.list-h h2{margin:0;font-size:var(--qw-fs-base);font-weight:600}
.new h2{margin-bottom:12px}
.new-row{display:flex;gap:10px;flex-wrap:wrap}
.input{flex:1;min-width:200px;padding:9px 12px;border:0;border-radius:var(--qw-r-md);background:var(--qw-bg);color:var(--qw-text);
  box-shadow:inset 0 0 0 .5px var(--qw-border-strong);transition:box-shadow var(--qw-dur)}
.input::placeholder{color:var(--qw-text-4)}
.input:focus{box-shadow:inset 0 0 0 1px var(--qw-border-focus),0 0 0 3px var(--qw-accent-soft)}
textarea.input{display:block;width:100%;min-height:72px;margin-top:10px;resize:vertical;line-height:1.6}
.err{margin-top:8px;font-size:var(--qw-fs-sm);color:var(--qw-danger)}
.err:empty{display:none}
.list-h{display:flex;align-items:baseline;gap:8px;margin-bottom:12px}
.count{font-size:var(--qw-fs-sm);color:var(--qw-text-4)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.pcard{display:flex;flex-direction:column;gap:8px;padding:16px 16px 14px;transition:box-shadow var(--qw-dur)}
.pcard:hover{box-shadow:var(--qw-shadow-md),inset 0 0 0 .5px var(--qw-border-strong)}
.pc-top{display:flex;align-items:center;gap:10px;min-width:0}
.pc-ic{width:30px;height:30px;flex:none;border-radius:var(--qw-r-sm);display:inline-flex;align-items:center;justify-content:center;
  background:var(--qw-bg-sidebar);color:var(--qw-text-3)}
.pc-top h3{margin:0;flex:1;min-width:0;font-size:15px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pc-sp{margin:0;min-height:3.1em;color:var(--qw-text-2);font-size:var(--qw-fs-sm);line-height:1.55;overflow:hidden;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow-wrap:anywhere}
.pc-sp.none{color:var(--qw-text-4)}
.pc-meta{font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
.pc-act{display:flex;gap:8px;margin-top:4px}
.notes{margin-top:40px;padding-top:18px;border-top:.5px solid var(--qw-border);color:var(--qw-text-3);font-size:var(--qw-fs-xs);line-height:1.8}
.notes p{margin:0 0 4px}
.dlg-wrap{position:fixed;inset:0;z-index:90;display:flex;align-items:center;justify-content:center;padding:16px;background:var(--qw-scrim)}
.dlg{width:min(430px,100%);padding:22px 22px 18px;border-radius:var(--qw-r-lg);background:var(--qw-bg-elev);
  box-shadow:var(--qw-shadow-lg),inset 0 0 0 .5px var(--qw-border-strong)}
.dlg h2{margin:0 0 8px;font-family:var(--qw-font-serif);font-weight:500;font-size:20px}
.dlg p{margin:0 0 18px;color:var(--qw-text-2);line-height:1.65;overflow-wrap:break-word}
.dlg-actions{display:flex;justify-content:flex-end;gap:8px}
/* ==== batch 3 (2026-10-06, owner ui) — สัญญา D4(a): แท็บ "โปรเจกต์ | การใช้งาน | ตรวจระบบ" ====
   สีของชุดข้อมูล --ch-1..5 = ชุดสีที่ผ่านตัวตรวจ (dataviz validate_palette.js บนพื้นการ์ดจริง #fff / #30302e:
   คู่ติดกัน CVD ΔE ≥ 8.4, ตาปกติ ≥ 19) — tokens.css ยังไม่มีสีกราฟ จึงประกาศไว้ที่หน้านี้ที่เดียว
   สีตามโมเดล (ลำดับคงที่) ไม่ใช่ตามอันดับ · ธีมสว่างมี 3 สีที่ต่ำกว่า 3:1 บนพื้นขาว → ทุกกราฟมีค่าเป็นตัวหนังสือ +
   "ดูเป็นตาราง" (ไม่ใช้สีอย่างเดียว) · ตัวอักษรใช้สีหมึกเสมอ ไม่ใช้สีของชุดข้อมูล */
:root{--ch-1:#2a78d6;--ch-2:#eb6834;--ch-3:#1baf7a;--ch-4:#eda100;--ch-5:#e87ba4;--ch-o:var(--qw-text-4)}
:root[data-theme="dark"]{--ch-1:#3987e5;--ch-2:#d95926;--ch-3:#199e70;--ch-4:#c98500;--ch-5:#d55181}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
.tabs{display:flex;gap:2px;margin:14px 0 0;border-bottom:.5px solid var(--qw-border-strong);overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tab{position:relative;display:inline-flex;align-items:center;gap:7px;height:42px;padding:0 12px;flex:none;color:var(--qw-text-3);
  font-weight:500;white-space:nowrap;border-radius:var(--qw-r-sm) var(--qw-r-sm) 0 0;transition:color var(--qw-dur),background-color var(--qw-dur)}
.tab:hover{color:var(--qw-text);background:color-mix(in srgb,var(--qw-bg-hover) 55%,transparent)}
.tab[aria-selected="true"]{color:var(--qw-text)}
.tab[aria-selected="true"]::after{content:"";position:absolute;left:8px;right:8px;bottom:-.5px;height:2px;border-radius:2px;background:var(--qw-accent)}
.tab[aria-selected="true"] .ic{color:var(--qw-accent)}
.tab:focus-visible{outline-offset:-3px}
.pane>h1:first-child{margin-top:30px}
.pane:focus{outline:none}
/* แถบตัวเลือกช่วงเวลา (radiogroup) — หน้าตาเดียวกับสวิตช์ภาษา (.lsw) */
.u-bar,.d-bar{display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px;margin:0 0 16px}
.seg{display:inline-flex;gap:2px;padding:2px;border-radius:var(--qw-r-full);box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.seg button{height:28px;padding:0 13px;border-radius:var(--qw-r-full);color:var(--qw-text-3);font-size:var(--qw-fs-sm);font-weight:500;white-space:nowrap}
.seg button:hover{color:var(--qw-text);background:color-mix(in srgb,var(--qw-bg-hover) 55%,transparent)}
.seg button[aria-checked="true"]{background:var(--qw-bg-active);color:var(--qw-text);box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px var(--qw-border)}
.upd{margin-left:auto;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
.note-box{display:flex;align-items:center;flex-wrap:wrap;gap:8px 12px;margin:0 0 16px;padding:12px 14px;border-radius:var(--qw-r-md);
  color:var(--qw-text-2);font-size:var(--qw-fs-sm);line-height:1.55;background:var(--qw-bg-elev);box-shadow:inset 0 0 0 .5px var(--qw-border)}
.note-box.warn{background:color-mix(in srgb,var(--qw-warn) 11%,transparent);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 45%,transparent)}
.note-box>span{flex:1 1 240px}
[aria-busy="true"] .u-body,[aria-busy="true"] .d-body{opacity:.62;transition:opacity var(--qw-dur)}
.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:12px}
.tile{padding:14px 16px 13px;min-width:0}
.tile-l{font-size:var(--qw-fs-xs);color:var(--qw-text-3);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile-v{margin-top:3px;font-size:26px;font-weight:600;line-height:1.2;letter-spacing:-.01em;white-space:nowrap}
.tile-s{margin-top:3px;font-size:var(--qw-fs-xs);color:var(--qw-text-3);line-height:1.45}
.ch{padding:16px 18px 14px;margin-bottom:12px;min-width:0}
.ch-h{display:flex;align-items:baseline;flex-wrap:wrap;gap:2px 10px}
.ch h2,.dcard h2{margin:0;font-size:var(--qw-fs-base);font-weight:600}
.ch-s{margin:0;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
.lg{display:flex;flex-wrap:wrap;gap:4px 16px;margin:10px 0 2px;padding:0;list-style:none;font-size:var(--qw-fs-xs);color:var(--qw-text-2)}
.lg li{display:inline-flex;align-items:center;gap:6px;min-width:0}
.lg-sw{width:10px;height:10px;border-radius:3px;flex:none}
.lg-ln{width:14px;height:2px;border-radius:1px;flex:none}
.lg-v{color:var(--qw-text-3);font-variant-numeric:tabular-nums}
.plot{position:relative;margin-top:8px;border-radius:var(--qw-r-sm)}
.plot svg{display:block;overflow:visible}
.plot:focus-visible{outline:2px solid var(--qw-focus-ring);outline-offset:3px}
.ax{fill:var(--qw-text-3);font-size:11px;font-family:var(--qw-font-ui)}
.grid-l{stroke:var(--qw-border);stroke-width:1;shape-rendering:crispEdges}
.base-l{stroke:var(--qw-border-strong);stroke-width:1;shape-rendering:crispEdges}
.band{fill:transparent}
.band.on{fill:var(--qw-bg-hover);fill-opacity:.7}
.xh{stroke:var(--qw-border-focus);stroke-width:1;shape-rendering:crispEdges}
.ln{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.dotm{stroke:var(--qw-bg-elev);stroke-width:2}
.tip{position:absolute;z-index:5;top:0;left:0;pointer-events:none;min-width:150px;max-width:270px;padding:8px 10px;border-radius:var(--qw-r-sm);
  background:var(--qw-bg-elev);box-shadow:var(--qw-shadow-md),inset 0 0 0 .5px var(--qw-border-strong);font-size:var(--qw-fs-xs);line-height:1.55}
.tip-h{color:var(--qw-text-3);margin-bottom:3px;white-space:nowrap}
.tip-r{display:flex;align-items:center;gap:8px;min-width:0}
.tip-k{width:12px;height:2px;border-radius:1px;flex:none}
.tip-v{font-weight:600;color:var(--qw-text);font-variant-numeric:tabular-nums;white-space:nowrap}
.tip-n{color:var(--qw-text-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.tip-f{margin-top:3px;padding-top:3px;border-top:.5px solid var(--qw-border);color:var(--qw-text-2)}
.tv{margin-top:10px;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
.tv summary{cursor:pointer;width:max-content;max-width:100%;padding:3px 0;border-radius:4px}
.tv summary:hover{color:var(--qw-text)}
.tv[open] summary{margin-bottom:6px}
.tbl{overflow-x:auto;max-width:100%}
table.dt{width:100%;border-collapse:collapse;font-size:var(--qw-fs-sm);color:var(--qw-text-2)}
table.dt th,table.dt td{padding:6px 10px;text-align:left;border-bottom:.5px solid var(--qw-border);white-space:nowrap}
table.dt th{font-size:var(--qw-fs-xs);font-weight:500;color:var(--qw-text-3)}
table.dt th:first-child,table.dt td:first-child{padding-left:0}
table.dt .n{text-align:right;font-variant-numeric:tabular-nums}
#uR td:last-child{white-space:normal;min-width:130px}
.rc-n{display:inline-flex;flex-wrap:wrap;align-items:center;gap:4px 6px}
.rc-t{color:var(--qw-text-3);font-size:var(--qw-fs-xs)}
/* คำขอล่าสุดแบบรายการสองบรรทัด — b3RcFit ใส่ .rc-narrow เมื่อตารางกว้างกว่าการ์ด (ซ่อนตาราง ไม่ต้องเลื่อนแนวนอน) */
.rc-list{display:none;list-style:none;margin:0;padding:0}
#uR.rc-narrow>table{display:none}
#uR.rc-narrow>.rc-list{display:block}
.rc-list li{padding:9px 0 10px;border-top:.5px solid var(--qw-border)}
.rc-list li:first-child{border-top:0;padding-top:2px}
.rc-h{display:flex;align-items:baseline;gap:10px;min-width:0;font-size:var(--qw-fs-sm)}
.rc-p{flex:1;min-width:0;color:var(--qw-text);font-weight:500;overflow-wrap:anywhere}
.rc-w{flex:none;font-size:var(--qw-fs-xs);color:var(--qw-text-3);font-variant-numeric:tabular-nums;white-space:nowrap}
.rc-v{margin-top:2px;font-size:var(--qw-fs-xs);line-height:1.55;color:var(--qw-text-2);font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.rc-v .nw{white-space:nowrap}
.rc-list .rc-n{display:flex;margin-top:6px}
.mini-g{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 22px;margin-top:12px}
.mini{min-width:0}
.mini-h{display:flex;align-items:center;gap:7px;min-width:0;font-size:var(--qw-fs-sm);color:var(--qw-text-2)}
.mini-h span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mini-v{margin-top:2px;font-size:20px;font-weight:600;line-height:1.25;white-space:nowrap}
.mini-s{font-size:var(--qw-fs-xs);color:var(--qw-text-3);min-height:1.45em}
.mini .plot{margin-top:4px}
.ch-empty{margin:10px 0 0;font-size:var(--qw-fs-sm);color:var(--qw-text-3)}
.pj{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-direction:column;gap:11px}
.pj-t{display:flex;align-items:baseline;gap:10px;min-width:0;font-size:var(--qw-fs-sm)}
.pj-n{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--qw-text)}
.pj-v{flex:none;color:var(--qw-text-3);font-variant-numeric:tabular-nums;font-size:var(--qw-fs-xs)}
.pj svg{display:block;margin-top:5px}
.pill{display:inline-flex;align-items:center;gap:4px;height:20px;padding:0 7px;border-radius:999px;font-size:11px;font-weight:500;white-space:nowrap;
  color:var(--qw-text-2);box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.pill.bad{color:var(--qw-danger);box-shadow:inset 0 0 0 .5px color-mix(in srgb,var(--qw-danger) 55%,transparent)}
.dot.warn{background:var(--qw-warn)} .dot.off{background:transparent;box-shadow:inset 0 0 0 1.5px var(--qw-text-4)}
.sum{display:inline-flex;align-items:center;gap:8px;min-height:30px;padding:4px 12px;border-radius:999px;font-size:var(--qw-fs-sm);font-weight:500;
  box-shadow:inset 0 0 0 .5px var(--qw-border-strong)}
.d-bar .btn{margin-left:0}
.d-bar .sp{flex:1}
.dcard{padding:16px 18px;margin-bottom:12px;min-width:0}
.dcard h2{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.fx{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}
.fx li{display:flex;align-items:flex-start;gap:9px;font-size:var(--qw-fs-sm);line-height:1.6;color:var(--qw-text);overflow-wrap:anywhere}
.fx .ic{margin-top:3px;color:var(--qw-warn)} .fx li.bad .ic{color:var(--qw-danger)} .fx li.info .ic{color:var(--qw-text-3)}
.fixes{box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px color-mix(in srgb,var(--qw-warn) 50%,transparent)}
/* มีแค่คำแนะนำทั่วไป (Brave key/Docker ที่รอผู้ใช้) = การ์ดธรรมดา ไม่ใช้ขอบอำพันที่สื่อว่ามีปัญหา */
.fixes.tips{box-shadow:var(--qw-shadow-sm),inset 0 0 0 .5px var(--qw-border)}
.fx .nw{white-space:nowrap}
.svc{display:flex;flex-direction:column;font-size:var(--qw-fs-sm)}
.svc-r{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(92px,.6fr) 74px minmax(0,1.9fr);gap:4px 14px;align-items:baseline;padding:9px 0;
  border-top:.5px solid var(--qw-border)}
.svc-hd{border-top:0;padding-top:0;font-size:var(--qw-fs-xs);color:var(--qw-text-3);font-weight:500}
.svc-name{display:block;color:var(--qw-text);font-weight:500}
.svc-port{display:block;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
.svc-st{display:inline-flex;align-items:center;gap:7px;color:var(--qw-text)}
.svc-st .dot{transform:translateY(-1px)}
.svc-lat{color:var(--qw-text-2);font-variant-numeric:tabular-nums;white-space:nowrap}
.svc-d{color:var(--qw-text-2);font-size:var(--qw-fs-xs);line-height:1.55;overflow-wrap:anywhere}
.dgrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.dgrid>.dcard{margin-bottom:0}
.dgrid+*{margin-top:12px}
.mt{margin-top:12px} .mt:first-of-type{margin-top:0}
.mt-t{display:flex;align-items:baseline;gap:10px;font-size:var(--qw-fs-sm);min-width:0}
.mt-l{flex:1;min-width:0;color:var(--qw-text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mt-v{flex:none;color:var(--qw-text-2);font-size:var(--qw-fs-xs);font-variant-numeric:tabular-nums}
/* "เหลือน้อย": warn ล้วนบนพื้นสว่างได้แค่ ~3:1 — ผสมสีหมึก (กติกาเดียวกับ .st-warn) */
.mt-v b{font-weight:600;color:color-mix(in srgb,var(--qw-warn) 70%,var(--qw-text))} .mt-v b.bad{color:var(--qw-danger)}
.mt-s{margin-top:2px;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
.mt-b{--m:var(--qw-text-3);height:6px;margin-top:6px;border-radius:3px;background:color-mix(in srgb,var(--m) 20%,transparent);overflow:hidden}
.mt-b>i{display:block;height:100%;border-radius:3px;background:var(--m)}
.mt-b.warn{--m:var(--qw-warn)} .mt-b.bad{--m:var(--qw-danger-bg)}
.kv{display:grid;grid-template-columns:minmax(0,auto) minmax(0,1fr);gap:7px 14px;margin:0;font-size:var(--qw-fs-sm)}
.kv dt{color:var(--qw-text-3)} .kv dd{margin:0;color:var(--qw-text);overflow-wrap:anywhere;min-width:0}
.kv dd .ic{width:14px;height:14px;margin-right:5px;vertical-align:-2px}
.yes .ic{color:var(--qw-ok)} .no{color:var(--qw-text-3)} .no .ic{color:var(--qw-text-4)}
.kv ul{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:3px}
.kv .sz{color:var(--qw-text-3);font-variant-numeric:tabular-nums;margin-left:6px;white-space:nowrap}
.sub2{margin:14px 0 6px;font-size:var(--qw-fs-xs);font-weight:600;color:var(--qw-text-3)}
details.dd>summary{cursor:pointer;display:flex;align-items:center;gap:8px;font-size:var(--qw-fs-base);font-weight:600;list-style:none;border-radius:4px}
details.dd>summary::-webkit-details-marker{display:none}
details.dd>summary::before{content:"";width:6px;height:6px;flex:none;border-right:1.5px solid currentColor;border-bottom:1.5px solid currentColor;
  transform:rotate(-45deg);transition:transform var(--qw-dur);margin:0 3px 0 1px}
details.dd[open]>summary::before{transform:rotate(45deg)}
details.dd>summary .cnt{font-weight:400;font-size:var(--qw-fs-xs);color:var(--qw-text-3)}
pre.errs{margin:10px 0 0;max-height:340px;overflow:auto;padding:10px 12px;border-radius:var(--qw-r-sm);background:var(--qw-bg-code);
  font-family:var(--qw-font-mono);font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word;color:var(--qw-text-2)}
pre.errs b{font-weight:500;color:var(--qw-text-3)}
textarea.rep{display:block;width:100%;min-height:200px;margin-top:10px;font-family:var(--qw-font-mono);font-size:12px}
@media (max-width:720px){
  .tiles{grid-template-columns:repeat(2,minmax(0,1fr))}
  .dgrid{grid-template-columns:1fr}
}
@media (max-width:640px){
  .mini-g{grid-template-columns:1fr}
  .tab{padding:0 10px;gap:6px}
  .ch,.dcard{padding:14px 14px 12px}
  .tile{padding:12px 13px}
  .tile-v{font-size:22px}
  /* แถวบริการ: ชื่อ + สถานะบรรทัดแรก เวลาตอบ + รายละเอียดบรรทัดถัดไป — หัวตารางซ่อนจากตาแต่ยังอยู่สำหรับโปรแกรมอ่านจอ */
  .svc-r{grid-template-columns:minmax(0,1fr) auto;gap:2px 12px}
  .svc-hd{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
  .svc-lat{grid-column:2;grid-row:2;text-align:right;font-size:var(--qw-fs-xs)}
  .svc-d{grid-column:1;grid-row:2}
  .upd{margin-left:0;width:100%}
}
@media (max-width:560px){.wrap{padding:14px 16px 48px}h1{margin-top:28px}.top{gap:8px}.status{padding:0 10px}}
@media (forced-colors:active){
  .input,.btn-ghost,.btn-ink,.status,.card,.dlg,.lsw,.gpu-note,.seg,.sum,.note-box,.tip{border:1px solid CanvasText}
  .lsw button[aria-pressed="true"],.seg button[aria-checked="true"]{outline:2px solid Highlight;outline-offset:-2px}
  .tab[aria-selected="true"]::after{background:Highlight}
  .dot.ok,.dot.bad,.dot.warn,.mark,.plot svg,.lg-sw,.lg-ln,.tip-k,.mt-b,.pj svg{forced-color-adjust:none}
}
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false">
  <symbol id="i-folder" viewBox="0 0 24 24"><path d="M3.5 7.5a2 2 0 0 1 2-2h3.6l2 2.2h7.4a2 2 0 0 1 2 2v7.8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/></symbol>
  <symbol id="i-globe" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.4 2.5 3.4 5.3 3.4 8.5s-1 6-3.4 8.5c-2.4-2.5-3.4-5.3-3.4-8.5s1-6 3.4-8.5z"/></symbol>
  <symbol id="i-external" viewBox="0 0 24 24"><path d="M14 4.5h5.5V10M19.5 4.5 11 13M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/></symbol>
  <symbol id="i-alert" viewBox="0 0 24 24"><path d="M10.3 4.9 3.4 17a2 2 0 0 0 1.7 3h13.8a2 2 0 0 0 1.7-3L13.7 4.9a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4"/><circle cx="12" cy="16.8" r=".9" fill="currentColor" stroke="none"/></symbol>
  <!-- batch 3 (D4): ไอคอนของแท็บ/ปุ่มในหน้าตรวจระบบ (วาดเอง เส้น 1.75 ชุดเดียวกับไอคอนอื่นของหน้า) -->
  <symbol id="i-grid" viewBox="0 0 24 24"><rect x="4" y="4" width="7" height="7" rx="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.6"/><rect x="4" y="13" width="7" height="7" rx="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.6"/></symbol>
  <symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 19.5h16"/><path d="M7 16.5v-5"/><path d="M12 16.5V7"/><path d="M17 16.5v-8"/></symbol>
  <symbol id="i-pulse" viewBox="0 0 24 24"><path d="M3.5 12h4l2-5 4 10 2-5h5"/></symbol>
  <symbol id="i-refresh" viewBox="0 0 24 24"><path d="M19.5 12a7.5 7.5 0 1 1-2.3-5.4"/><path d="M19.5 4.5v4.2h-4.2"/></symbol>
  <symbol id="i-copy" viewBox="0 0 24 24"><rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5v-2a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/></symbol>
  <symbol id="i-check" viewBox="0 0 24 24"><path d="m5 12.5 4.5 4.5L19 7.5"/></symbol>
  <symbol id="i-minus" viewBox="0 0 24 24"><path d="M6 12h12"/></symbol>
  <symbol id="i-info" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/><path d="M12 11v5"/><circle cx="12" cy="8" r=".9" fill="currentColor" stroke="none"/></symbol>
</svg>
<div class="wrap">
  <header class="top">
    <div class="brand"><span class="mark" aria-hidden="true">Q</span><span class="wordmark">Qwen3.8</span></div>
    <span class="status" id="status"><span class="dot" id="dot" aria-hidden="true"></span><span id="st">__T_checking__</span></span>
    <div class="lsw" id="lang" role="group" aria-label="__T_lang_group__">
      <button type="button" data-lang="th" lang="th" aria-pressed="false" data-tip-text="__T_lang_tip_th__">ไทย</button>
      <button type="button" data-lang="en" lang="en" aria-label="English" aria-pressed="false" data-tip-text="__T_lang_tip_en__">EN</button>
    </div>
    <script>
    /* ทาปุ่มของภาษาปัจจุบันก่อนวาดภาพแรก (สคริปต์หลักอยู่ท้ายหน้า) — กติกาเดียวกับหน้าแชต */
    (function () { var l = document.documentElement.lang; [].forEach.call(document.querySelectorAll('#lang button'), function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-lang') === l)); }); })();
    </script>
  </header>
  <!-- role=status: เสียบ/ถอด eGPU ขณะหน้านี้เปิดอยู่ โปรแกรมอ่านหน้าจอได้ยินคำเตือนเมื่อมันโผล่ขึ้นมา -->
  <div role="status"><p class="gpu-note" id="gpuNote" hidden><svg class="ic" aria-hidden="true"><use href="#i-alert"/></svg><span id="gpuNoteT"></span></p></div>
  <!-- batch 3 (D4): แท็บของหน้า — ลิงก์ตรง #usage / #doctor (เมนูบัญชีในหน้าแชตเปิดมาที่แท็บนั้นเลย)
       ARIA tabs แบบเลือกทันทีที่เลื่อน: ลูกศรซ้าย/ขวา/Home/End ย้ายแท็บ, Tab ออกไปที่เนื้อหา -->
  <div class="tabs" id="tabs" role="tablist" aria-label="__T_b3_tabs__">
    <button type="button" class="tab" role="tab" id="tab-projects" data-tab="projects" aria-controls="pn-projects" aria-selected="true"><svg class="ic" aria-hidden="true"><use href="#i-grid"/></svg><span>__T_b3_tab_projects__</span></button>
    <button type="button" class="tab" role="tab" id="tab-usage" data-tab="usage" aria-controls="pn-usage" aria-selected="false" tabindex="-1"><svg class="ic" aria-hidden="true"><use href="#i-chart"/></svg><span>__T_b3_tab_usage__</span></button>
    <button type="button" class="tab" role="tab" id="tab-doctor" data-tab="doctor" aria-controls="pn-doctor" aria-selected="false" tabindex="-1"><svg class="ic" aria-hidden="true"><use href="#i-pulse"/></svg><span>__T_b3_tab_doctor__</span></button>
  </div>
  <script>
  /* เลือกแท็บตาม #hash ก่อนวาดภาพแรก (สคริปต์หลักอยู่ท้ายหน้า) — ไม่งั้นเปิด #doctor แล้วเห็นหน้าโปรเจกต์แวบหนึ่ง */
  (function () {
    var h = String(location.hash || '').replace(/^#/, '');
    if (h !== 'usage' && h !== 'doctor') return;
    document.documentElement.setAttribute('data-b3-tab', h);
  })();
  </script>
  <style>
  html[data-b3-tab="usage"] #pn-projects,html[data-b3-tab="doctor"] #pn-projects{display:none}
  </style>
  <section class="pane" id="pn-projects" role="tabpanel" aria-labelledby="tab-projects" tabindex="-1">
  <h1>__T_hubtitle__</h1>
  <p class="sub">__T_hubsub__</p>
  <section class="card new" aria-labelledby="newH">
    <h2 id="newH">__T_newproj__</h2>
    <div class="new-row">
      <input class="input" id="name" placeholder="__T_hubnewph__" maxlength="60" autocomplete="off" aria-label="__T_hubnewph__">
      <button type="button" class="btn btn-ink" id="add">__T_create__</button>
    </div>
    <textarea class="input" id="sys" placeholder="__T_sysph__" aria-label="__T_sysph__"></textarea>
    <div class="err" id="err" role="alert"></div>
  </section>
  <div class="list-h"><h2>__T_projects__</h2><span class="count" id="count"></span></div>
  <div class="grid" id="list"></div>
  <footer class="notes"><p>__T_note1__</p><p>__T_note2__</p><p>__T_note3__</p><p>__T_note4__</p></footer>
  </section>
  <!-- batch 3 (D4): การใช้งาน — ทุกอย่างในกล่องเหล่านี้สร้างด้วย JS จากคำตอบของ /api/usage (textContent เท่านั้น) -->
  <section class="pane" id="pn-usage" role="tabpanel" aria-labelledby="tab-usage" tabindex="-1" hidden>
    <h1>__T_b3_use_title__</h1>
    <p class="sub">__T_b3_use_sub__</p>
    <div class="u-bar">
      <div class="seg" id="uRange" role="radiogroup" aria-label="__T_b3_use_range__">
        <button type="button" role="radio" data-days="7" aria-checked="true">__T_b3_use_7d__</button>
        <button type="button" role="radio" data-days="30" aria-checked="false" tabindex="-1">__T_b3_use_30d__</button>
      </div>
      <span class="upd" id="uUpd"></span>
    </div>
    <div class="note-box" id="uMsg" role="status" hidden></div>
    <div class="u-body" id="uBody" hidden>
      <div class="tiles" id="uTiles"></div>
      <section class="card ch" aria-labelledby="uC1h">
        <div class="ch-h"><h2 id="uC1h">__T_b3_c_tokens__</h2><p class="ch-s">__T_b3_c_tokens_s__</p></div>
        <ul class="lg" id="uC1lg"></ul>
        <div class="plot" id="uC1" tabindex="0" aria-describedby="uKeys"></div>
        <details class="tv"><summary>__T_b3_table__</summary><div class="tbl" id="uC1t"></div></details>
      </section>
      <section class="card ch" aria-labelledby="uC2h">
        <div class="ch-h"><h2 id="uC2h">__T_b3_c_speed__</h2><p class="ch-s">__T_b3_c_speed_s__</p></div>
        <div class="mini-g" id="uC2"></div>
        <details class="tv"><summary>__T_b3_table__</summary><div class="tbl" id="uC2t"></div></details>
      </section>
      <section class="card ch" aria-labelledby="uC3h">
        <div class="ch-h"><h2 id="uC3h">__T_b3_c_proj__</h2><p class="ch-s">__T_b3_c_proj_s__</p></div>
        <div id="uC3"></div>
        <details class="tv"><summary>__T_b3_table__</summary><div class="tbl" id="uC3t"></div></details>
      </section>
      <section class="card ch" aria-labelledby="uRh">
        <div class="ch-h"><h2 id="uRh">__T_b3_recent__</h2><p class="ch-s" id="uRs"></p></div>
        <div class="tbl" id="uR"></div>
      </section>
    </div>
    <p class="sr" id="uKeys">__T_b3_chart_keys__</p>
    <div class="sr" id="uLive" aria-live="polite"></div>
  </section>
  <!-- batch 3 (D4): ตรวจระบบ — /api/doctor (hub แคช 10 วินาที) ไม่มีค่าคีย์/โทเค็นในหน้า มีแค่ "มี/ไม่มี" -->
  <section class="pane" id="pn-doctor" role="tabpanel" aria-labelledby="tab-doctor" tabindex="-1" hidden>
    <h1>__T_b3_doc_title__</h1>
    <p class="sub">__T_b3_doc_sub__</p>
    <div class="d-bar">
      <span class="sum" id="dSum" hidden><span class="dot" id="dDot" aria-hidden="true"></span><span id="dSumT"></span></span>
      <span class="upd" id="dUpd"></span>
      <button type="button" class="btn btn-ghost sm" id="dRe"><svg class="ic" aria-hidden="true"><use href="#i-refresh"/></svg><span>__T_b3_doc_recheck__</span></button>
      <button type="button" class="btn btn-ink sm" id="dCopy" disabled><svg class="ic" aria-hidden="true"><use href="#i-copy"/></svg><span id="dCopyT">__T_b3_doc_copy__</span></button>
    </div>
    <div class="note-box" id="dMsg" role="status" hidden></div>
    <div class="d-body" id="dBody" hidden></div>
    <div class="sr" id="dLive" aria-live="polite"></div>
  </section>
</div>
<div class="dlg-wrap" id="dlg" hidden>
  <div class="dlg" role="alertdialog" aria-modal="true" aria-labelledby="dlgT" aria-describedby="dlgB">
    <h2 id="dlgT">__T_delproj_title__</h2>
    <p id="dlgB"></p>
    <div class="dlg-actions">
      <button type="button" class="btn btn-ghost" id="dlgNo">__T_cancel__</button>
      <button type="button" class="btn btn-danger" id="dlgYes">__T_delete_btn__</button>
    </div>
  </div>
</div>
<script>
(function () {
'use strict';
var LANG = "__LANG__";
__QW_GLUE__
__QW_GPU__
var T = glueAll(__T_JSON__);
function t(k) { return T[k] != null ? String(T[k]) : k; }
/* คำอธิบายที่เติมจากเซิร์ฟเวอร์ลงหน้าโดยตรง (ไม่ผ่าน t()) — ข้อความของเราล้วน ไม่มีชื่อที่ผู้ใช้ตั้ง */
glueText(document.querySelectorAll('.sub, .notes p'));
var $ = function (s) { return document.querySelector(s); };
function api(p, o) {
  return fetch(p, o).then(function (r) {
    return r.json().catch(function () { return null; }).then(function (d) {
      if (!r.ok) { var er = new Error((d && d.error) || ('HTTP ' + r.status)); er.status = r.status; throw er; }
      return d;
    });
  }, function (e) { var er = new Error((e && e.message) || 'network'); er.net = true; throw er; });
}
/* ไม่โชว์ข้อความดิบ ('Failed to fetch', 'HTTP 500', ข้อความอังกฤษจากเซิร์ฟเวอร์) ในหน้าภาษาไทย — ใช้ข้อความที่แปลแล้ว
   (กติกาเดียวกับ errText ของ shell) ตัวจริงเก็บใน title ของช่องข้อผิดพลาด (ชี้ค้างอ่านได้) และ console */
function showErr(prefix, e, byStatus) {
  try { console.warn('[qwen]', e); } catch (x) {}
  var k = e && e.net ? 'hubdown' : (byStatus && e && byStatus[e.status]) || 'err_retry';
  $('#err').textContent = prefix + ': ' + t(k);
  $('#err').title = (e && e.message) || '';
}
/* ชื่อ/คำสั่งของโปรเจกต์เป็นข้อความจากผู้ใช้ — สร้าง DOM ด้วย textContent เท่านั้น */
function el(tag, cls, text, attrs) {
  var n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
  return n;
}
function svg(name) {
  var NS = 'http://www.w3.org/2000/svg', s = document.createElementNS(NS, 'svg'), u = document.createElementNS(NS, 'use');
  s.setAttribute('class', 'ic'); s.setAttribute('aria-hidden', 'true'); u.setAttribute('href', '#i-' + name); s.append(u);
  return s;
}
/* ---- สลับภาษา: สวิตช์บนหัว + Alt+Shift+L (กติกาเดียวกับหน้าแชต) ----
   โหลดหน้าใหม่แล้วชื่อ/คำสั่งโปรเจกต์ที่พิมพ์ค้างในฟอร์มต้องไม่หาย — พากลับผ่าน sessionStorage ของแท็บนี้ */
var langSw = $('#lang'), langBusy = false, CARRY_KEY = 'qwen-lang-carry';
function langBtns() { return [].slice.call(langSw.querySelectorAll('button[data-lang]')); }
function paintLang(v) {
  langBtns().forEach(function (b) {
    var on = b.getAttribute('data-lang') === v;
    b.setAttribute('aria-pressed', String(on));
    if (on) { b.removeAttribute('aria-keyshortcuts'); b.removeAttribute('data-tip'); }
    else { b.setAttribute('aria-keyshortcuts', 'Alt+Shift+L'); b.setAttribute('data-tip', b.getAttribute('data-tip-text') || ''); }
  });
}
function setLang(v, how) {
  if ((v !== 'th' && v !== 'en') || v === LANG || langBusy) return;
  var had = langSw.contains(document.activeElement);
  langBusy = true;
  paintLang(v);
  langSw.setAttribute('aria-busy', 'true');
  api('/api/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ lang: v }) })
    .then(function () {
      try {
        sessionStorage.setItem(CARRY_KEY, JSON.stringify({ at: Date.now(), name: $('#name').value, sys: $('#sys').value, focus: how || '' }));
      } catch (e) {}
      /* ?lang= คือโหมดดูตัวอย่าง (ไม่บันทึก) — ถ้าคงไว้ หน้าจะโหลดกลับมาเป็นภาษาเดิม */
      try {
        var u = new URL(location.href);
        if (u.searchParams.has('lang')) { u.searchParams.delete('lang'); history.replaceState(null, '', u.pathname + u.search + u.hash); }
      } catch (e) {}
      location.reload();
    })
    .catch(function (e) {
      langBusy = false;
      langSw.removeAttribute('aria-busy');
      paintLang(LANG);
      /* จอแคบซ่อนปุ่มของภาษาที่เลือกอยู่ — ปุ่มที่ถือโฟกัสอาจถูกซ่อนไประหว่างรอ (โฟกัสหล่นไป <body>) */
      var ae = document.activeElement;
      if (had && (!ae || ae === document.body || ae.offsetParent === null)) {
        var b = langBtns().filter(function (x) { return x.offsetParent !== null; })[0];
        if (b) b.focus();
      }
      showErr(t('errlang'), e);
    });
}
langSw.addEventListener('click', function (e) {
  var b = e.target.closest('button[data-lang]');
  if (b) setLang(b.getAttribute('data-lang'), e.detail === 0 ? 'sw' : '');
});
document.addEventListener('keydown', function (e) {
  /* e.code: แป้นพิมพ์ภาษาไทยให้ e.key เป็นอักษรไทย */
  if (!e.altKey || !e.shiftKey || e.ctrlKey || e.metaKey || e.repeat || e.code !== 'KeyL' || !$('#dlg').hidden) return;
  e.preventDefault();
  setLang(LANG === 'th' ? 'en' : 'th', '');
});
paintLang(LANG);
/* อ่านแล้วลบทันที (F5 ครั้งถัดไปต้องไม่เติมซ้ำ) และเติมเฉพาะช่องที่ยังว่าง */
(function () {
  var c = null;
  try { c = JSON.parse(sessionStorage.getItem(CARRY_KEY) || 'null'); sessionStorage.removeItem(CARRY_KEY); } catch (e) {}
  if (!c || typeof c !== 'object' || !(Math.abs(Date.now() - (+c.at || 0)) < 120000)) return;
  if (typeof c.name === 'string' && !$('#name').value) $('#name').value = c.name.slice(0, 60);
  if (typeof c.sys === 'string' && !$('#sys').value) $('#sys').value = c.sys;
  if (c.focus === 'sw') {
    var b = langBtns().filter(function (x) { return x.offsetParent !== null; });
    b = b.filter(function (x) { return x.getAttribute('aria-pressed') === 'true'; })[0] || b[0];
    if (b) b.focus();
  }
})();
var lastSig = '';
/* หน้าแชตของแต่ละโปรเจกต์ — ใช้ชื่อโฮสต์เดียวกับหน้านี้ (127.0.0.1/localhost) ไม่งั้นเป็นคนละ origin
   ประวัติแชตและธีมที่เก็บในเบราว์เซอร์จะไม่ตามไป */
function portUrl(port) { return location.protocol + '//' + location.hostname + ':' + port + '/'; }
function openPort(port) { window.open(portUrl(port), '_blank', 'noopener'); }
/* parts = ส่วนท้ายที่ยอมหายได้เมื่อที่ไม่พอ เรียงจากสำคัญมากไปน้อย [{text, cls}] = [GPU, เลขพอร์ต]
   ภาษาไทยยาวกว่า ที่ 390px ป้ายเคยถูกตัดเหลือ "พอร์ต 8…"  tip = บรรทัดเพิ่มใน title (โมเดลไหนใช้ GPU ไหน) */
function setStatus(txt, parts, tip) {
  parts = parts || [];
  var st = $('#st'), full = txt + parts.map(function (p) { return p.text; }).join('');
  var sig = JSON.stringify([txt, parts]);
  if (st.getAttribute('data-sig') !== sig) {
    st.setAttribute('data-sig', sig);
    st.replaceChildren(txt);
    parts.forEach(function (p) { st.append(el('span', 'st-opt' + (p.cls ? ' ' + p.cls : ''), p.text)); });
  }
  if (tip) full += '\n\n' + tip;
  /* จอแคบตัดข้อความด้วย … — ชี้ค้างเพื่ออ่านเต็ม  (title เป็นป้ายของระบบ ไม่ต้องมี U+2060 จาก glue()) */
  $('#status').title = full.replace(/\u2060/g, '');
  fitStatus();
}
/* วัดจริงแทนการเดาจุดตัดความกว้าง: ภาษาอังกฤษพอดีที่ 390px แต่ไทยล้น — ซ่อนส่วนท้ายทีละท่อนจากท้ายสุด
   เฉพาะเมื่อข้อความยังล้นอยู่ (อ่าน scrollWidth ทุกรอบ = วัดใหม่หลังซ่อนแต่ละท่อน) */
function fitStatus() {
  var s = $('#status'), st = $('#st'), opt = st.querySelectorAll('.st-opt');
  s.classList.remove('fit');
  [].forEach.call(opt, function (o) { o.classList.remove('cut'); });
  for (var i = opt.length - 1; i >= 0 && st.scrollWidth > st.clientWidth; i--) {
    opt[i].classList.add('cut');
    s.classList.add('fit');
  }
}
/* คำเตือน GPU เปลี่ยน — แสดงเฉพาะตอนเซิร์ฟเวอร์ทำงาน (ถ้าไม่ทำงาน ป้ายบอกให้เปิดจากไอคอนอยู่แล้ว ไม่ต้องซ้ำ) */
function paintGpuNote(g) {
  var on = !!(g && g.stale);
  if (on) { var s = t('gpu_changed'); if ($('#gpuNoteT').textContent !== s) $('#gpuNoteT').textContent = s; }
  if ($('#gpuNote').hidden !== !on) $('#gpuNote').hidden = !on;
}
var fitRaf = 0;
addEventListener('resize', function () { cancelAnimationFrame(fitRaf); fitRaf = requestAnimationFrame(fitStatus); });
/* ฟอนต์ไทยโหลดทีหลังได้ ความกว้างจริงเปลี่ยน — วัดใหม่อีกรอบเมื่อฟอนต์พร้อม */
try { document.fonts.ready.then(fitStatus); } catch (e) {}
function refresh() {
  return api('/api/projects').then(function (d) {
    b3SawProjects(d);
    $('#dot').className = 'dot ' + (d.upstream ? 'ok' : 'bad');
    var n = /^(\d+) models$/.exec(d.model || '');
    var model = n ? t('nmodels').replace('%d', n[1]) : (d.model || 'llama-server');
    /* GPU ของโมเดลหลักมาก่อนเลขพอร์ต — พอร์ตถูกซ่อนก่อนเมื่อที่ไม่พอ (d.gpu = null: ไม่มีไฟล์โปรไฟล์ แสดงเหมือนเดิม) */
    var g = d.upstream ? d.gpu || null : null, gs = gpuShort(g);
    if (d.upstream) setStatus(t('ready') + ' · ' + model,
      [gs ? { text: ' · ' + gs, cls: g.stale ? 'st-warn' : '' } : null, { text: ' · ' + t('port') + ' ' + d.upstream_port }]
        .filter(Boolean), gpuTip(g));
    else setStatus(t('offline'));
    paintGpuNote(g);
    var sig = JSON.stringify(d.projects);
    if (sig === lastSig) return;
    lastSig = sig;
    $('#count').textContent = String(d.projects.length);
    var list = $('#list');
    list.replaceChildren.apply(list, d.projects.map(function (p) {
      var card = el('article', 'card pcard');
      var top = el('div', 'pc-top');
      var ic = el('span', 'pc-ic'); ic.append(svg('folder'));
      top.append(ic, el('h3', null, p.name, { title: p.name }));
      var sp = el('p', 'pc-sp' + (p.system_prompt ? '' : ' none'), p.system_prompt || t('noinstr'));
      var meta = el('div', 'pc-meta', t('port') + ' ' + p.port + ' · ' + t('created') + ' ' + String(p.created || '').slice(0, 10) +
        ' · ' + t('think') + ' ' + t('think_' + (p.think || 'off')));
      var act = el('div', 'pc-act');
      /* ทุกการ์ดมีปุ่ม "เปิด"/"ลบ" ชื่อซ้ำกัน — ใส่ชื่อโปรเจกต์ในชื่อปุ่มให้รายการปุ่มของโปรแกรมอ่านหน้าจอแยกออก */
      var open = el('button', 'btn btn-ink sm', t('open'), { type: 'button', 'data-open': String(p.port), 'aria-label': t('open') + ' ' + p.name });
      open.append(svg('external'));
      act.append(open);
      if (d.projects.length > 1) act.append(el('button', 'btn btn-ghost sm danger', t('del'),
        { type: 'button', 'data-del': p.slug, 'data-name': p.name, 'aria-label': t('del') + ' ' + p.name }));
      card.append(top, sp, meta, act);
      return card;
    }));
    /* ลบการ์ดที่โฟกัสอยู่ไปแล้ว — ส่งโฟกัสไปการ์ดแรกแทน ไม่ให้หล่นไป <body> */
    var ae = document.activeElement;
    if (askBack && !askBack.isConnected && (!ae || ae === document.body)) {
      var first = list.querySelector('[data-open]');
      (first || $('#name')).focus();
      askBack = null;
    }
  }).catch(function () {
    $('#dot').className = 'dot bad';
    setStatus(t('hubdown'));
    paintGpuNote(null);
  });
}
/* ยืนยันก่อนลบด้วยกล่องในหน้า (ไม่ใช้ confirm() ของเบราว์เซอร์ ให้หน้าตาเป็นชุดเดียวกัน)
   เป็น modal จริง: Tab วนแค่สองปุ่มในกล่อง และปิดแล้วคืนโฟกัสให้ปุ่มที่เปิด */
var dlgCb = null, askBack = null;
function ask(name, cb) {
  askBack = document.activeElement;
  $('#dlgB').textContent = t('delproj_body').replace('%s', function () { return name; });
  $('#dlg').hidden = false; dlgCb = cb; $('#dlgNo').focus();
}
function closeAsk(yes) {
  if ($('#dlg').hidden) return;
  $('#dlg').hidden = true;
  var cb = dlgCb; dlgCb = null;
  if (askBack && askBack.isConnected) askBack.focus();
  if (!yes) askBack = null;   // เก็บไว้เฉพาะตอนลบจริง เพื่อรู้ว่าต้องย้ายโฟกัสหลังการ์ดหายไป
  if (yes && cb) cb();
}
$('#dlgNo').onclick = function () { closeAsk(false); };
$('#dlgYes').onclick = function () { closeAsk(true); };
$('#dlg').addEventListener('mousedown', function (e) { if (e.target === this) closeAsk(false); });
$('#dlg').addEventListener('keydown', function (e) {
  if (e.key !== 'Tab') return;
  e.preventDefault();
  (document.activeElement === $('#dlgNo') ? $('#dlgYes') : $('#dlgNo')).focus();
});
document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeAsk(false); });
document.addEventListener('click', function (e) {
  var o = e.target.closest('[data-open]');
  if (o) { openPort(o.getAttribute('data-open')); return; }
  var d = e.target.closest('[data-del]');
  if (!d) return;
  ask(d.getAttribute('data-name') || '', function () {
    api('/api/projects/' + encodeURIComponent(d.getAttribute('data-del')), { method: 'DELETE' })
      .then(refresh).catch(function (err) { showErr(t('errdelete'), err, { 409: 'cant_delete_last' }); });
  });
});
$('#add').onclick = function () {
  var name = $('#name').value.trim();
  $('#err').textContent = ''; $('#err').title = '';
  if (!name) { $('#err').textContent = t('needname'); $('#name').focus(); return; }
  api('/api/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name, system_prompt: $('#sys').value.trim() }) })
    .then(function (p) {
      $('#name').value = ''; $('#sys').value = '';
      return refresh().then(function () { openPort(p.port); });
    })
    .catch(function (e) { showErr(t('errcreate'), e, { 409: 'err_exists', 507: 'err_noport' }); });
};
$('#name').addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.isComposing) $('#add').click(); });
refresh();
/* แท็บที่ซ่อนอยู่ไม่ต้องถาม hub (hub ถาม llama-server ต่อทุกครั้ง) — กลับมาแล้วดึงใหม่ทันที */
setInterval(function () { if (document.visibilityState === 'visible') refresh(); }, 5000);
document.addEventListener('visibilitychange', function () { if (document.visibilityState === 'visible') refresh(); });

/* ======================================================================================
   batch 3 (2026-10-06, owner ui) — สัญญา D4(a): แท็บ "การใช้งาน" (GET /api/usage?days=7|30) และ "ตรวจระบบ" (GET /api/doctor)
   ข้อมูลผ่านตัวแปลงในก้อน _B3_JS (ฟังก์ชันล้วน รับรูปแบบ JSON ได้หลายแบบ) — hub ที่ยังไม่มีเส้นทาง (404) = บอกตรงๆ ว่าต้อง
   เปิด hub รุ่นใหม่ ไม่โชว์ข้อผิดพลาดดิบ · ทุกค่าจากเซิร์ฟเวอร์ (ชื่อโปรเจกต์/โมเดล/บรรทัด log) เข้า DOM ด้วย textContent เท่านั้น
   กราฟเป็น SVG ที่วาดตามความกว้างจริงของกล่อง (ตัวอักษรบนแกนคงขนาด ไม่ย่อตามจอแบบ viewBox) วาดใหม่เมื่อกล่องเปลี่ยนขนาด
   ====================================================================================== */
__QW_B3__
var B3 = { tab: '', models: [], names: {}, days: 7,
  useRaw: null, useM: null, useDays: 0, useAt: 0, useTry: 0, useSeq: 0, useErr: null, useW: 0, rcW: 0,
  docRaw: null, docN: null, docAt: 0, docTry: 0, docSeq: 0, docErr: null, copyT: 0 };
var B3_TABS = ['projects', 'usage', 'doctor'], SVGNS = 'http://www.w3.org/2000/svg';
/* title/aria-label/คลิปบอร์ด ต้องไม่มี word joiner ที่ glue() ใส่ให้ข้อความบนจอ */
function b3T(k) { return t(k).replace(/⁠/g, ''); }
/* %s = ค่าแรก, %1 %2 %3 = ตามลำดับ (แทนด้วยฟังก์ชัน ชื่อที่มี $& ไม่ถูกตีความ) */
function b3F(s) {
  var a = arguments;
  return String(s).replace(/%(\d)|%s/g, function (m, i) { var v = a[i ? +i : 1]; return v != null ? String(v) : m; });
}
function b3Int(n) { return b3Fmt(Math.round(b3Num(n)), LANG, 0, true); }
function b3Units() { return { ms: t('b3_u_ms'), s: t('b3_u_s'), min: t('b3_u_min'), h: t('b3_u_h') }; }
function b3Loc() { return LANG === 'th' ? 'th-TH' : 'en-GB'; }
function b3Clock(ms) {
  try { return new Date(ms).toLocaleTimeString(b3Loc(), { hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; }
}
function b3DayLabel(k, long) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(k || '');
  if (!m) return String(k || '');
  try {
    return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString(b3Loc(),
      long ? { weekday: 'short', day: 'numeric', month: 'short' } : { day: 'numeric', month: 'short' });
  } catch (e) { return k.slice(5); }
}
function b3Stamp(ms) {
  if (!isFinite(ms)) return '—';
  try { return new Date(ms).toLocaleString(b3Loc(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }); }
  catch (e) { return ''; }
}
function sv(tag, a) {
  var n = document.createElementNS(SVGNS, tag);
  if (a) Object.keys(a).forEach(function (k) {
    n.setAttribute(k, typeof a[k] === 'number' ? String(Math.round(a[k] * 100) / 100) : String(a[k]));
  });
  return n;
}
function svText(x, y, s, anchor) {
  var n = sv('text', { x: x, y: y, class: 'ax' });
  if (anchor) n.setAttribute('text-anchor', anchor);
  n.textContent = s;
  return n;
}
function b3Color(slot) { return slot >= 0 && slot < 5 ? 'var(--ch-' + (slot + 1) + ')' : 'var(--ch-o)'; }
function b3SName(s) { return s.other ? t('b3_other') : s.model ? b3Short(s.model) : t('b3_unknown_model'); }
/* ชื่อโปรเจกต์: ชื่อปัจจุบันจาก /api/projects ก่อน → ชื่อที่ hub จดไว้ในสถิติ (โปรเจกต์ที่ลบไปแล้ว) → slug */
function b3PName(slug, name) { return slug === '*' ? t('b3_other') : B3.names[slug] || name || slug || '—'; }
/* คำที่มีใน T เท่านั้น (t() คืนชื่อคีย์เมื่อไม่มี — ใช้ตัดสินไม่ได้) · ชื่อห้ามซ้ำกับ b3Has(o, k) ของก้อนฟังก์ชันล้วน */
function b3HasT(k) { return Object.prototype.hasOwnProperty.call(T, k); }
/* คำสถานะ: คำเฉพาะของ hub (โทเคนไม่ตรง/ไม่ขยับ/ตรวจไม่ทัน …) ถ้ามีคำแปล ไม่งั้นคำของกลุ่ม (ปกติ/ควรตรวจดู/ไม่ทำงาน/ปิดอยู่) */
function b3StWord(s) { return s.raw && b3HasT('b3_st_' + s.raw) ? t('b3_st_' + s.raw) : t('b3_st_' + s.state); }
function b3KeyName(k) { return b3HasT('b3_key_' + k) ? t('b3_key_' + k) : k; }
/* live region: ล้างก่อนแล้วค่อยใส่ ข้อความเดิมซ้ำก็ยังถูกอ่าน */
function b3Say(id, msg) { var n = $(id); n.textContent = ''; setTimeout(function () { n.textContent = msg; }, 40); }
function b3ErrKind(e) {
  return e && e.net ? 'down' : e && (e.status === 404 || e.status === 405 || e.status === 501) ? 'unsupported' : 'error';
}
function b3Msg(box, kind, retry, loadKey) {
  box.replaceChildren();
  box.hidden = !kind;
  if (!kind) return;
  box.className = 'note-box' + (kind === 'loading' || kind === 'empty' ? '' : ' warn');
  box.append(el('span', null, t(kind === 'loading' ? loadKey || 'b3_loading' : kind === 'empty' ? 'b3_use_empty'
    : kind === 'unsupported' ? 'b3_unsupported' : kind === 'down' ? 'hubdown' : 'err_retry')));
  if (retry && kind !== 'loading' && kind !== 'empty') {
    var b = el('button', 'btn btn-ghost sm', t('b3_retry'), { type: 'button' });
    b.addEventListener('click', retry);
    box.append(b);
  }
}

/* ---- แท็บ ---- */
function b3TabFromHash() { var h = String(location.hash || '').replace(/^#/, ''); return B3_TABS.indexOf(h) >= 0 ? h : 'projects'; }
function b3Show(name, how) {
  if (B3_TABS.indexOf(name) < 0) name = 'projects';
  B3.tab = name;
  document.documentElement.removeAttribute('data-b3-tab');
  B3_TABS.forEach(function (x) {
    var b = $('#tab-' + x), on = x === name;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
    $('#pn-' + x).hidden = !on;
  });
  document.title = 'Qwen3.8 - ' + b3T(name === 'usage' ? 'b3_tab_usage' : name === 'doctor' ? 'b3_tab_doctor' : 'hubtitle');
  if (how === 'key') $('#tab-' + name).focus();
  /* replaceState ไม่ทำให้เกิด hashchange และไม่เพิ่มประวัติ (ปุ่มย้อนกลับไม่ต้องไล่ทีละแท็บ) */
  if (how === 'key' || how === 'click') {
    var h = name === 'projects' ? '' : '#' + name;
    if (location.hash !== h) { try { history.replaceState(null, '', location.pathname + location.search + h); } catch (e) {} }
  }
  if (name === 'usage') b3UseLoad(false);
  else if (name === 'doctor') b3DocLoad(false);
}
$('#tabs').addEventListener('click', function (e) {
  var b = e.target.closest('[role="tab"]');
  if (b) b3Show(b.getAttribute('data-tab'), 'click');
});
$('#tabs').addEventListener('keydown', function (e) {
  var i = B3_TABS.indexOf(B3.tab), n = B3_TABS.length, j = -1;
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  if (e.key === 'ArrowRight') j = (i + 1) % n;
  else if (e.key === 'ArrowLeft') j = (i - 1 + n) % n;
  else if (e.key === 'Home') j = 0;
  else if (e.key === 'End') j = n - 1;
  if (j < 0) return;
  e.preventDefault();
  b3Show(B3_TABS[j], 'key');
});
addEventListener('hashchange', function () { b3Show(b3TabFromHash(), 'hash'); });
/* จาก refresh() ทุก 5 วินาที: ลำดับโมเดลของ router (สีของกราฟผูกกับตำแหน่งนี้) + ชื่อโปรเจกต์ของแต่ละ slug */
function b3SawProjects(d) {
  var before = JSON.stringify([B3.models, B3.names]);
  if (d && Array.isArray(d.models)) B3.models = d.models.map(String);
  var nm = {};
  ((d && d.projects) || []).forEach(function (p) { if (p && p.slug) nm[p.slug] = String(p.name || p.slug); });
  B3.names = nm;
  /* ข้อมูลการใช้งานมาถึงก่อนรายชื่อโมเดล/โปรเจกต์ (เปิด #usage ตรงๆ) = สีถูกจัดตามชื่อชั่วคราว และชื่อโปรเจกต์เป็น slug
     — วาดใหม่เมื่อสองรายการนี้เปลี่ยนจริงเท่านั้น (refresh() ทุก 5 วินาทีที่ได้ค่าเดิมไม่ทำให้กราฟกระพริบ) */
  if (before !== JSON.stringify([B3.models, B3.names]) && B3.tab === 'usage' && B3.useRaw) b3UseRender();
}

/* ---- การใช้งาน ---- */
function b3SetDays(n, focus) {
  if (n !== 7 && n !== 30) return;
  B3.days = n;
  [].forEach.call($('#uRange').querySelectorAll('[data-days]'), function (b) {
    var on = +b.getAttribute('data-days') === n;
    b.setAttribute('aria-checked', String(on));
    b.tabIndex = on ? 0 : -1;
    if (on && focus) b.focus();
  });
  b3UseLoad(false);
}
$('#uRange').addEventListener('click', function (e) {
  var b = e.target.closest('[data-days]');
  if (b) b3SetDays(+b.getAttribute('data-days'), false);
});
$('#uRange').addEventListener('keydown', function (e) {
  if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].indexOf(e.key) < 0) return;
  e.preventDefault();
  b3SetDays(B3.days === 7 ? 30 : 7, true);
});
/* โหลดใหม่ = ภาพเดิมยังอยู่ (จางลงด้วย aria-busy) ไม่กระพริบเป็นหน้าว่าง · คำตอบที่มาช้ากว่าคำขอล่าสุดถูกทิ้ง (seq) */
function b3UseLoad(force) {
  if (!force && B3.useRaw && B3.useDays === B3.days && Date.now() - B3.useAt < 60000) { b3UseRender(); return; }
  var seq = ++B3.useSeq, days = B3.days, pane = $('#pn-usage');
  B3.useTry = Date.now();
  pane.setAttribute('aria-busy', 'true');
  if (!B3.useRaw) b3UseRender();
  api('/api/usage?days=' + days).then(function (d) {
    if (seq !== B3.useSeq) return;
    B3.useRaw = d && typeof d === 'object' ? d : {};
    B3.useDays = days; B3.useAt = Date.now(); B3.useErr = null;
  }, function (e) {
    if (seq !== B3.useSeq) return;
    B3.useErr = e;
    if (B3.useDays !== days) B3.useRaw = null;      // ข้อมูลเดิมเป็นของอีกช่วง — ห้ามแสดงคู่กับปุ่มช่วงใหม่
  }).then(function () {
    if (seq !== B3.useSeq) return;
    pane.removeAttribute('aria-busy');
    b3UseRender();
  });
}
function b3UseRender() {
  var body = $('#uBody'), msg = $('#uMsg'), retry = function () { b3UseLoad(true); };
  if (!B3.useRaw) {
    body.hidden = true;
    $('#uUpd').textContent = '';
    b3Msg(msg, B3.useErr ? b3ErrKind(B3.useErr) : 'loading', retry);
    return;
  }
  var M = b3Usage(B3.useRaw, { days: B3.useDays, models: B3.models });
  B3.useM = M;
  $('#uUpd').textContent = b3F(t('b3_use_updated'), b3Clock(B3.useAt));
  b3Msg(msg, B3.useErr ? b3ErrKind(B3.useErr) : M.empty ? 'empty' : '', retry);
  body.hidden = M.empty;
  if (M.empty) return;
  b3Tiles(M);
  b3Charts(M);
  b3Recent(M);
}
function b3Tile(label, value, sub, title) {
  var c = el('div', 'card tile');
  c.append(el('div', 'tile-l', label), el('div', 'tile-v', value, title ? { title: title } : null), el('div', 'tile-s', sub || ''));
  return c;
}
function b3Tiles(M) {
  var T0 = M.totals, u = b3Units(), tok = T0.prompt + T0.completion;
  /* prompt_tokens ของ hub อาจรวมหรือไม่รวมส่วนที่มาจากแคช — ถ้าแคชมากกว่า prompt แปลว่าไม่รวม ใช้ผลรวมเป็นตัวหาร */
  var den = T0.cached <= T0.prompt ? T0.prompt : T0.prompt + T0.cached;
  var pct = den > 0 ? Math.round(T0.cached / den * 100) + '%' : '—';
  $('#uTiles').replaceChildren(
    b3Tile(t('b3_t_tokens'), b3Fmt(tok, LANG), b3F(t('b3_t_tokens_s'), b3Fmt(T0.prompt, LANG), b3Fmt(T0.completion, LANG)), b3Int(tok)),
    b3Tile(t('b3_t_req'), b3Int(T0.requests), b3F(t('b3_t_req_s'), b3Int(T0.errors), b3Int(T0.compacted))),
    b3Tile(t('b3_t_cache'), pct, b3F(t('b3_t_cache_s'), b3Fmt(T0.cached, LANG))),
    b3Tile(t('b3_t_time'), b3Dur(T0.wall, u) || '—', T0.requests && T0.wall ? b3F(t('b3_t_time_s'), b3Dur(T0.wall / T0.requests, u)) : ''));
}
function b3Charts(M) {
  B3.useW = $('#uBody').clientWidth;
  b3Stack($('#uC1'), M);
  b3Legend($('#uC1lg'), M);
  b3Table($('#uC1t'), [t('b3_day')].concat(M.stack.map(b3SName), [t('b3_total')]), M.days.map(function (d, i) {
    var sum = 0;
    return [b3DayLabel(d, true)].concat(M.stack.map(function (s) { sum += s.tokens[i]; return b3Int(s.tokens[i]); }), [b3Int(sum)]);
  }), 'num');
  b3Speed($('#uC2'), M);
  var sp = M.series.filter(function (s) { return s.avgTps != null; });
  b3Table($('#uC2t'), [t('b3_day')].concat(sp.map(b3SName)), M.days.map(function (d, i) {
    return [b3DayLabel(d, true)].concat(sp.map(function (s) { return s.tps[i] == null ? '—' : b3Fmt(s.tps[i], LANG, 1); }));
  }), 'num');
  b3Proj($('#uC3'), M);
  b3Table($('#uC3t'), [t('b3_col_project'), t('b3_t_tokens'), t('b3_col_prompt'), t('b3_col_reply'), t('b3_t_req')],
    M.projects.map(function (p) { return [b3PName(p.project, p.name), b3Int(p.tokens), b3Int(p.prompt), b3Int(p.completion), b3Int(p.requests)]; }), 'num');
}
function b3Legend(ul, M) {
  ul.replaceChildren.apply(ul, M.stack.map(function (s) {
    var sw = el('span', 'lg-sw', null, { 'aria-hidden': 'true' }), li = el('li');
    sw.style.background = b3Color(s.slot);
    li.append(sw, el('span', null, b3SName(s), s.model && !s.other ? { title: s.model } : null), el('span', 'lg-v', b3Fmt(s.total, LANG)));
    return li;
  }));
}
/* ตาราง: คอลัมน์แรกเป็นหัวแถว · nums = 'num' → ทุกคอลัมน์ยกเว้นแรกชิดขวา หรือรายการเลขคอลัมน์ */
function b3Table(box, head, rows, nums) {
  var isNum = function (i) { return nums === 'num' ? i > 0 : (nums || []).indexOf(i) >= 0; };
  var tb = el('table', 'dt'), thead = el('thead'), tr = el('tr'), tbody = el('tbody');
  head.forEach(function (h, i) { tr.append(el('th', isNum(i) ? 'n' : null, h, { scope: 'col' })); });
  thead.append(tr);
  rows.forEach(function (r) {
    var row = el('tr');
    r.forEach(function (c, i) {
      var cell = el(i ? 'td' : 'th', isNum(i) ? 'n' : null, null, i ? null : { scope: 'row' });
      if (c && c.nodeType) cell.append(c); else cell.textContent = c == null ? '' : String(c);
      row.append(cell);
    });
    tbody.append(row);
  });
  tb.append(thead, tbody);
  box.replaceChildren(tb);
}
/* ป้ายลอย (หนึ่งอันต่อกราฟ) — aria-hidden เพราะค่าเดียวกันอ่านได้จาก live region (คีย์บอร์ด) และตาราง */
function b3TipEl(plot) {
  var tip = plot.querySelector(':scope > .tip');
  if (!tip) { tip = el('div', 'tip', null, { 'aria-hidden': 'true' }); tip.hidden = true; plot.append(tip); }
  return tip;
}
function b3TipFill(tip, head, rows, foot) {
  tip.replaceChildren(el('div', 'tip-h', head));
  rows.forEach(function (r) {
    var line = el('div', 'tip-r'), k = el('span', 'tip-k');
    k.style.background = r.color;
    line.append(k, el('span', 'tip-v', r.value), el('span', 'tip-n', r.name));
    tip.append(line);
  });
  if (foot) tip.append(el('div', 'tip-f', foot));
}
function b3TipPlace(plot, tip, x, y) {
  tip.hidden = false;
  var pw = plot.clientWidth, tw = tip.offsetWidth, left = x + 14;
  if (left + tw > pw) left = x - 14 - tw;
  if (left < 0) left = Math.max(0, Math.min(pw - tw, x - tw / 2));
  tip.style.left = Math.round(left) + 'px';
  tip.style.top = Math.round(y) + 'px';
}
/* ลูกศรซ้าย/ขวา/Home/End เลื่อนทีละวัน, Esc ซ่อน — คืน null = ไม่ใช่ปุ่มของกราฟ */
function b3Step(e, cur, n) {
  if (e.altKey || e.ctrlKey || e.metaKey) return null;
  if (e.key === 'ArrowRight') return cur < 0 ? n - 1 : Math.min(n - 1, cur + 1);
  if (e.key === 'ArrowLeft') return cur < 0 ? n - 1 : Math.max(0, cur - 1);
  if (e.key === 'Home') return 0;
  if (e.key === 'End') return n - 1;
  if (e.key === 'Escape') return -1;
  return null;
}
function b3Hover(svg, plot, n, x0, bw, show) {
  function at(e) {
    var r = svg.getBoundingClientRect(), i = Math.floor((e.clientX - r.left - x0) / bw);
    show(i >= 0 && i < n ? i : -1);
  }
  svg.addEventListener('pointermove', at);
  svg.addEventListener('pointerdown', at);
  svg.addEventListener('pointerleave', function () { if (document.activeElement !== plot) show(-1); });
  plot.onblur = function () { show(-1); };
}
function b3R2(v) { return Math.round(v * 100) / 100; }
/* แท่งตั้ง: ปลายบนมน (ปลายข้อมูล) ฐานเหลี่ยมชนเส้นศูนย์ */
function b3Col(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, w / 2, h));
  return sv('path', { d: 'M' + b3R2(x) + ',' + b3R2(y + h) + 'V' + b3R2(y + r) + 'Q' + b3R2(x) + ',' + b3R2(y) + ' ' + b3R2(x + r) + ',' + b3R2(y) +
    'H' + b3R2(x + w - r) + 'Q' + b3R2(x + w) + ',' + b3R2(y) + ' ' + b3R2(x + w) + ',' + b3R2(y + r) + 'V' + b3R2(y + h) + 'Z' });
}
/* แท่งนอน: ปลายขวามน ฐานซ้ายเหลี่ยม */
function b3Bar(x, y, w, h, r) {
  r = Math.max(0, Math.min(r, h / 2, w));
  return sv('path', { d: 'M' + b3R2(x) + ',' + b3R2(y) + 'H' + b3R2(x + w - r) + 'Q' + b3R2(x + w) + ',' + b3R2(y) + ' ' + b3R2(x + w) + ',' + b3R2(y + r) +
    'V' + b3R2(y + h - r) + 'Q' + b3R2(x + w) + ',' + b3R2(y + h) + ' ' + b3R2(x + w - r) + ',' + b3R2(y + h) + 'H' + b3R2(x) + 'Z' });
}
/* กราฟ 1: โทเค็นต่อวัน แท่งซ้อนตามโมเดล — แท่งกว้าง ≤ 24px, ช่องว่างสีพื้น 2px ระหว่างชั้น (ไม่ใช้เส้นขอบ), แกน y เลขกลม */
function b3Stack(plot, M) {
  var W = Math.max(240, Math.floor(plot.clientWidth || 0)), H = W < 520 ? 190 : 230;
  var padL = 46, padR = 6, padT = 10, padB = 24, pw = W - padL - padR, ph = H - padT - padB, base = padT + ph;
  var n = M.days.length, S = M.stack;
  var tot = M.days.map(function (_, i) { return S.reduce(function (a, s) { return a + s.tokens[i]; }, 0); });
  var ticks = b3Ticks(Math.max.apply(null, tot.concat([0])), H < 200 ? 3 : 4), top = ticks[ticks.length - 1] || 1;
  var bw = pw / n, cw = Math.max(3, Math.min(24, bw * 0.62)), all = tot.reduce(function (a, b) { return a + b; }, 0);
  var svg = sv('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img',
    'aria-label': b3T('b3_c_tokens') + ' — ' + b3F(b3T('b3_aria_total'), n, b3Int(all)) });
  ticks.forEach(function (v) {
    var y = Math.round(base - v / top * ph) + .5;
    if (v) svg.append(sv('line', { x1: padL, x2: W - padR, y1: y, y2: y, class: 'grid-l' }));
    svg.append(svText(padL - 8, y + 4, b3Fmt(v, LANG), 'end'));
  });
  var bands = [], every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor(pw / 54))));
  for (var i = 0; i < n; i++) {
    var x0 = padL + i * bw, cx = x0 + bw / 2, y = base, band = sv('rect', { x: x0, y: padT, width: bw, height: ph, class: 'band' });
    svg.append(band);
    bands.push(band);
    var segs = S.filter(function (s) { return s.tokens[i] > 0; });
    for (var k = 0; k < segs.length; k++) {
      var s = segs[k], h = segs[k].tokens[i] / top * ph, mk;
      if (k === segs.length - 1) mk = b3Col(cx - cw / 2, y - h, cw, h, Math.min(4, h));
      else mk = sv('rect', { x: cx - cw / 2, y: y - h + 2, width: cw, height: Math.max(.5, h - 2) });
      mk.style.fill = b3Color(s.slot);
      svg.append(mk);
      y -= h;
    }
    /* ป้ายวันที่: วันล่าสุดมีเสมอ แล้วนับถอยหลังทีละ every วัน (30 วันบนจอแคบไม่ทับกัน) */
    if ((n - 1 - i) % every === 0) svg.append(svText(cx, H - 6, b3DayLabel(M.days[i]), 'middle'));
  }
  svg.append(sv('line', { x1: padL, x2: W - padR, y1: base + .5, y2: base + .5, class: 'base-l' }));
  plot.replaceChildren(svg);
  var tip = b3TipEl(plot), cur = -1;
  function show(j, kb) {
    if (cur >= 0 && bands[cur]) bands[cur].classList.remove('on');
    cur = j;
    if (j < 0) { tip.hidden = true; return; }
    bands[j].classList.add('on');
    var rows = S.filter(function (s) { return s.tokens[j] > 0; }).reverse().map(function (s) {
      return { color: b3Color(s.slot), value: b3Int(s.tokens[j]), name: b3SName(s) };
    });
    var head = b3DayLabel(M.days[j], true), foot = rows.length ? b3F(t('b3_total_v'), b3Int(tot[j])) : t('b3_no_use_day');
    b3TipFill(tip, head, rows, foot);
    b3TipPlace(plot, tip, padL + (j + .5) * bw, padT);
    if (kb) b3Say('#uLive', head + ': ' + rows.map(function (r) { return r.name + ' ' + r.value; }).concat([foot]).join(', ').replace(/⁠/g, ''));
  }
  b3Hover(svg, plot, n, padL, bw, show);
  plot.onkeydown = function (e) { var j = b3Step(e, cur, n); if (j == null) return; e.preventDefault(); show(j, true); };
}
/* กราฟ 2: ความเร็ว (tok/s) — กราฟเล็กแยกโมเดลละช่อง สเกลของใครของมัน (27B ~1 tok/s กับ 4B ~28 tok/s บนแกนเดียวกัน
   เส้นของ 27B จะแบนติดศูนย์ และห้ามใช้สองแกน) */
function b3Speed(wrap, M) {
  var list = M.series.filter(function (s) { return s.avgTps != null; });
  if (!list.length) { wrap.replaceChildren(el('p', 'ch-empty', t('b3_c_speed_none'))); return; }
  var cells = list.map(function (s) {
    var cell = el('div', 'mini'), head = el('div', 'mini-h'), key = el('span', 'lg-ln', null, { 'aria-hidden': 'true' });
    var plot = el('div', 'plot', null, { tabindex: '0', 'aria-describedby': 'uKeys' });
    key.style.background = b3Color(s.slot);
    head.append(key, el('span', null, b3SName(s), s.model ? { title: s.model } : null));
    cell.append(head, el('div', 'mini-v', b3F(t('b3_c_speed_v'), b3Fmt(s.avgTps, LANG, 1))),
      el('div', 'mini-s', s.avgPtps != null ? b3F(t('b3_c_speed_p'), b3Fmt(s.avgPtps, LANG, 0)) : ''), plot);
    return [cell, plot, s];
  });
  wrap.replaceChildren.apply(wrap, cells.map(function (c) { return c[0]; }));
  /* วาดหลังใส่ลงหน้าแล้ว — ต้องรู้ความกว้างจริงของแต่ละช่อง */
  cells.forEach(function (c) { b3Line(c[1], M.days, c[2]); });
}
function b3Line(plot, days, s) {
  var W = Math.max(160, Math.floor(plot.clientWidth || 0)), H = 92, padL = 4, padR = 4, padT = 18, padB = 20;
  var pw = W - padL - padR, ph = H - padT - padB, n = days.length, bw = pw / n, base = padT + ph, vals = s.tps;
  var top = b3Ticks(Math.max.apply(null, vals.map(function (v) { return v || 0; }).concat([0])), 2);
  top = top[top.length - 1] || 1;
  function X(i) { return padL + (i + .5) * bw; }
  function Y(v) { return base - v / top * ph; }
  var col = b3Color(s.slot), gy = Math.round(Y(top)) + .5, d = '', prev = false;
  var svg = sv('svg', { width: W, height: H, viewBox: '0 0 ' + W + ' ' + H, role: 'img',
    'aria-label': b3SName(s) + ' — ' + b3F(b3T('b3_c_speed_v'), b3Fmt(s.avgTps, LANG, 1)) });
  var xh = sv('line', { x1: 0, x2: 0, y1: padT, y2: base, class: 'xh', visibility: 'hidden' });
  svg.append(xh, sv('line', { x1: padL, x2: W - padR, y1: gy, y2: gy, class: 'grid-l' }),
    svText(W - padR, gy - 5, b3Fmt(top, LANG) + ' tok/s', 'end'),
    sv('line', { x1: padL, x2: W - padR, y1: base + .5, y2: base + .5, class: 'base-l' }));
  /* เส้นต่อเฉพาะวันที่ติดกัน — วันที่ไม่มีข้อมูล = เส้นขาด ไม่ลากผ่านศูนย์ปลอมๆ */
  vals.forEach(function (v, i) {
    if (v == null) { prev = false; return; }
    d += (prev ? 'L' : 'M') + b3R2(X(i)) + ',' + b3R2(Y(v));
    prev = true;
  });
  if (d) { var p = sv('path', { d: d, class: 'ln' }); p.style.stroke = col; svg.append(p); }
  vals.forEach(function (v, i) {
    if (v == null) return;
    var lone = (i === 0 || vals[i - 1] == null) && (i === n - 1 || vals[i + 1] == null);
    var last = !vals.slice(i + 1).some(function (x) { return x != null; });
    if (lone || last || n <= 7) { var c = sv('circle', { cx: X(i), cy: Y(v), r: 4, class: 'dotm' }); c.style.fill = col; svg.append(c); }
  });
  svg.append(svText(padL, H - 5, b3DayLabel(days[0]), 'start'), svText(W - padR, H - 5, b3DayLabel(days[n - 1]), 'end'));
  plot.replaceChildren(svg);
  var tip = b3TipEl(plot), cur = -1;
  function show(j, kb) {
    cur = j;
    if (j < 0) { tip.hidden = true; xh.setAttribute('visibility', 'hidden'); return; }
    xh.setAttribute('x1', b3R2(X(j)));
    xh.setAttribute('x2', b3R2(X(j)));
    xh.setAttribute('visibility', 'visible');
    var v = vals[j], head = b3DayLabel(days[j], true);
    var val = v == null ? t('b3_no_use_day') : b3F(t('b3_c_speed_v'), b3Fmt(v, LANG, 1));
    b3TipFill(tip, head, v == null ? [] : [{ color: col, value: val, name: b3SName(s) }], v == null ? val : '');
    b3TipPlace(plot, tip, X(j), 0);
    if (kb) b3Say('#uLive', (b3SName(s) + ', ' + head + ': ' + val).replace(/⁠/g, ''));
  }
  b3Hover(svg, plot, n, padL, bw, show);
  plot.onkeydown = function (e) { var j = b3Step(e, cur, n); if (j == null) return; e.preventDefault(); show(j, true); };
}
/* กราฟ 3: โปรเจกต์ที่ใช้มากที่สุด — แท่งนอนชุดเดียว สีหมึกกลางๆ (ไม่ใช่สีของโมเดลใด จะได้ไม่ชวนให้คิดว่าเกี่ยวกัน)
   ชื่อ + ค่าเป็นตัวหนังสือเหนือแท่ง (ชื่อไทยยาวตัด … ได้ ชื่อเต็มอยู่ใน title) · เกิน 8 = รวมเป็น "อื่นๆ" */
function b3Proj(box, M) {
  var P = M.projects.slice(0, 8), rest = M.projects.slice(8);
  if (rest.length) {
    P.push(rest.reduce(function (a, p) {
      a.tokens += p.tokens; a.prompt += p.prompt; a.completion += p.completion; a.requests += p.requests;
      return a;
    }, { project: '*', tokens: 0, prompt: 0, completion: 0, requests: 0 }));
  }
  if (!P.length) { box.replaceChildren(el('p', 'ch-empty', t('b3_c_proj_none'))); return; }
  var ul = el('ul', 'pj');
  box.replaceChildren(ul);
  var W = Math.max(120, Math.floor(ul.clientWidth || box.clientWidth || 0));
  var max = Math.max.apply(null, P.map(function (p) { return p.tokens; }).concat([1]));
  P.forEach(function (p) {
    var li = el('li'), top = el('div', 'pj-t'), name = b3PName(p.project, p.name), w = p.tokens > 0 ? Math.max(2, p.tokens / max * W) : 0;
    top.append(el('span', 'pj-n', name, { title: name }),
      el('span', 'pj-v', b3Fmt(p.tokens, LANG) + ' · ' + b3F(t('b3_req_unit'), b3Int(p.requests))));
    var svg = sv('svg', { width: W, height: 10, viewBox: '0 0 ' + W + ' 10', 'aria-hidden': 'true', focusable: 'false' });
    if (w > 0) {
      var r = b3Bar(0, 0, w, 10, Math.min(4, w));
      r.style.fill = 'color-mix(in srgb, var(--qw-text) 58%, transparent)';
      svg.append(r);
    }
    li.append(top, svg);
    li.title = name + ' — ' + b3F(b3T('b3_proj_tip'), b3Int(p.prompt), b3Int(p.completion), b3Int(p.requests));
    ul.append(li);
  });
}
function b3Recent(M) {
  var R = M.recent.slice(0, 20), box = $('#uR'), u = b3Units();
  $('#uRs').textContent = R.length ? b3F(t('b3_recent_s'), R.length) : '';
  if (!R.length) { box.replaceChildren(el('p', 'ch-empty', t('b3_recent_none'))); return; }
  /* 8 คอลัมน์ให้พอดีการ์ดที่ 1440px (เดิม 10 คอลัมน์ล้นจนคอลัมน์หมายเหตุต้องเลื่อนดู): แคชอยู่ในวงเล็บของพรอมต์,
     เครื่องมือ + ป้ายผิดพลาด/สรุปแล้ว รวมเป็นคอลัมน์สุดท้ายที่ขึ้นบรรทัดใหม่ได้ (จอแคบยังเลื่อนตารางในการ์ดได้) */
  function mkNote(r) {
    var note = el('span', 'rc-n');
    if (r.isError) note.append(el('span', 'pill bad', t('b3_flag_error')));
    if (r.isCompacted) note.append(el('span', 'pill', r.turns ? b3F(t('b3_flag_compacted_n'), r.turns) : t('b3_flag_compacted')));
    if (r.tools.length) note.append(el('span', 'rc-t', r.tools.join(', ')));
    return note.childNodes.length ? note : null;
  }
  b3Table(box, [t('b3_col_time'), t('b3_col_project'), t('b3_col_model'), t('b3_col_prompt_c'), t('b3_col_reply'),
    'tok/s', t('b3_col_wall'), t('b3_col_note')], R.map(function (r) {
    return [b3Stamp(r.t), b3PName(r.project, r.name), r.model ? b3Short(r.model) : '—',
      b3Int(r.prompt) + (r.cached ? ' (' + b3Fmt(r.cached, LANG) + ')' : ''), b3Int(r.completion),
      r.gen ? b3Fmt(r.gen, LANG, 1) : '—', b3Dur(r.wall, u) || '—', mkNote(r) || '—'];
  }), [3, 4, 5, 6]);
  /* รายการเดียวกันแบบสองบรรทัดต่อคำขอ (โปรเจกต์ + เวลา / โมเดล · ตัวเลขพร้อมคำกำกับ · ป้าย) — ใช้แทนตารางเมื่อตาราง
     กว้างกว่าการ์ด (b3RcFit) ทำไม (integ b3 2026-10-06): ที่ 390 px ตาราง 700 px เลื่อนอยู่ในการ์ด 330 px คอลัมน์โทเค็น/
     tok/s/เวลา/ป้าย "สรุปแล้ว" อยู่นอกจอ และจอสัมผัสไม่มีอะไรบอกว่าเลื่อนได้ · ตัวที่ซ่อน (display:none) หลุดจากโปรแกรมอ่านจอด้วย
     จึงไม่อ่านซ้ำ */
  var ul = el('ul', 'rc-list', null, { 'aria-labelledby': 'uRh' });
  R.forEach(function (r) {
    var li = el('li'), h = el('div', 'rc-h'), v = el('div', 'rc-v'), nums = [];
    h.append(el('span', 'rc-p', b3PName(r.project, r.name)), el('span', 'rc-w', b3Stamp(r.t)));
    nums.push(t('b3_col_prompt') + ' ' + b3Int(r.prompt) + (r.cached ? ' (' + b3F(t('b3_rc_cached'), b3Fmt(r.cached, LANG)) + ')' : ''));
    nums.push(t('b3_col_reply') + ' ' + b3Int(r.completion));
    if (r.gen) nums.push(b3Fmt(r.gen, LANG, 1) + ' tok/s');
    if (b3Dur(r.wall, u)) nums.push(t('b3_col_wall') + ' ' + b3Dur(r.wall, u));
    /* แต่ละค่าห้ามขาดกลางคำ ("2.9 | tok/s", "10 | นาที" ในภาพ 390 px) — ขึ้นบรรทัดใหม่ได้หลัง " ·" เท่านั้น (เว้นวรรคหน้าจุด
       เป็น nbsp: จุดติดท้ายบรรทัดบน ไม่ขึ้นต้นบรรทัดใหม่) · ชื่อโมเดลตัดได้ (ชื่อ gguf ที่ผู้ใช้ตั้งเองอาจยาวกว่าการ์ด) */
    if (r.model) v.append(el('span', 'rc-m', b3Short(r.model)));
    var sep = String.fromCharCode(160) + '· ';      // nbsp ในซอร์สมองไม่เห็นและแก้ไขผิดได้ง่าย — สร้างจากรหัสแทน
    nums.forEach(function (s) { if (v.childNodes.length) v.append(sep); v.append(el('span', 'nw', s)); });
    li.append(h, v);
    var note = mkNote(r);
    if (note) li.append(note);
    ul.append(li);
  });
  box.append(ul);
  B3.rcW = 0;
  b3RcFit();
}
/* ตารางคำขอล่าสุดกว้างกว่าการ์ด (จอแคบ, แท็บเล็ต, ชื่อโปรเจกต์/โมเดลยาว) → สลับเป็นรายการสองบรรทัด (.rc-narrow)
   วัดจากความกว้างจริงของตาราง ไม่ใช่ breakpoint ตายตัว (ตารางกว้างตามข้อมูล 600-900 px) · ถอด class ก่อนวัดแล้วใส่คืน
   ในเฟรมเดียวกัน = ไม่กระพริบ · ความกว้างของ #uR ไม่เปลี่ยนตามการสลับ จึงไม่วน ResizeObserver */
function b3RcFit() {
  var box = $('#uR'), tb = box.querySelector(':scope > table'), w = box.clientWidth;
  if (!tb || !w || w === B3.rcW) return;
  B3.rcW = w;
  box.classList.remove('rc-narrow');
  box.classList.toggle('rc-narrow', tb.offsetWidth > w + 1);
}
/* กล่องเปลี่ยนขนาด (หมุนจอ/ลากหน้าต่าง/แท็บเพิ่งถูกเปิด) = วาดกราฟใหม่ตามความกว้างจริง */
try {
  new ResizeObserver(function () {
    var w = $('#uBody').clientWidth;
    if (!w || w === B3.useW || !B3.useM || B3.tab !== 'usage' || B3.useM.empty) return;
    B3.useW = w;
    requestAnimationFrame(function () { if (B3.useM && !B3.useM.empty) b3Charts(B3.useM); });
  }).observe($('#uBody'));
} catch (e) {}
/* ตาราง/รายการคำขอล่าสุด: วัดใหม่เมื่อการ์ดเปลี่ยนกว้าง (หมุนจอ, แท็บการใช้งานเพิ่งถูกเปิด — ตอนซ่อนกว้าง 0 วัดไม่ได้) */
try { new ResizeObserver(function () { b3RcFit(); }).observe($('#uR')); } catch (e) {}

/* ---- ตรวจระบบ ---- */
/* lang = ภาษาของชื่อบริการ/เหตุผลของ Docker ที่ hub เติมให้ · fresh (ปุ่ม "ตรวจใหม่") = refresh=1 ข้ามแคช 10 วินาทีของ hub */
function b3DocLoad(force, fresh) {
  if (!force && B3.docRaw && Date.now() - B3.docAt < 10000) { b3DocRender(); return; }
  var seq = ++B3.docSeq, pane = $('#pn-doctor');
  B3.docTry = Date.now();
  pane.setAttribute('aria-busy', 'true');
  $('#dRe').setAttribute('aria-disabled', 'true');
  if (!B3.docRaw) b3DocRender();
  api('/api/doctor?lang=' + LANG + (fresh ? '&refresh=1' : '')).then(function (d) {
    if (seq !== B3.docSeq) return;
    B3.docRaw = d && typeof d === 'object' ? d : {};
    B3.docAt = Date.now(); B3.docErr = null;
  }, function (e) {
    if (seq !== B3.docSeq) return;
    B3.docErr = e;
  }).then(function () {
    if (seq !== B3.docSeq) return;
    pane.removeAttribute('aria-busy');
    $('#dRe').removeAttribute('aria-disabled');
    b3DocRender();
  });
}
function b3DocRender() {
  var body = $('#dBody'), msg = $('#dMsg'), retry = function () { b3DocLoad(true); };
  if (!B3.docRaw) {
    body.hidden = true;
    $('#dSum').hidden = true;
    $('#dCopy').disabled = true;
    $('#dUpd').textContent = '';
    b3Msg(msg, B3.docErr ? b3ErrKind(B3.docErr) : 'loading', retry, 'b3_doc_checking');
    return;
  }
  var N = b3Doctor(B3.docRaw, LANG);
  N.services.forEach(function (s) { s.label = s.kind ? b3T('b3_svc_' + s.kind) : s.name || s.id; s.word = b3StWord(s).replace(/⁠/g, ''); });
  N.keys.forEach(function (k) { k.label = b3KeyName(k.name).replace(/⁠/g, ''); });
  B3.docN = N;
  b3Msg(msg, B3.docErr ? b3ErrKind(B3.docErr) : '', retry);
  $('#dSum').hidden = false;
  $('#dDot').className = 'dot ' + N.overall;
  $('#dSumT').textContent = N.issues ? b3F(t('b3_doc_issues'), N.issues) : N.tips ? b3F(t('b3_doc_ok_tips'), N.tips) : t('b3_doc_ok_all');
  var when = isFinite(N.ts) ? N.ts : B3.docAt;
  $('#dUpd').textContent = N.took != null ? b3F(t('b3_doc_checked'), b3Clock(when), b3Dur(N.took / 1000, b3Units()) || '0 ms')
    : b3F(t('b3_doc_checked_at'), b3Clock(when));
  $('#dCopy').disabled = false;
  /* วาดใหม่ทุกครั้งที่ตรวจ — กล่องพับที่ผู้ใช้เปิดไว้ต้องยังเปิดอยู่ */
  var open = {};
  [].forEach.call(body.querySelectorAll('details[data-k]'), function (d) { open[d.getAttribute('data-k')] = d.open; });
  body.hidden = false;
  body.replaceChildren.apply(body, [b3DocFixes(N), b3DocSvc(N), b3DocGrid(N), b3DocErrors(N, open.err), b3DocExtra(N, open.extra)]
    .filter(Boolean));
}
function b3H2(id, key, icon) {
  var h = el('h2', null, null, { id: id });
  if (icon) h.append(svg(icon));
  h.append(el('span', null, t(key)));
  return h;
}
function b3DocFixes(N) {
  if (!N.fixes.length) return null;
  var tipsOnly = N.fixes.every(function (f) { return f.level === 'info'; });
  var c = el('section', 'card dcard fixes' + (tipsOnly ? ' tips' : ''), null, { 'aria-labelledby': 'dFxH' }), ul = el('ul', 'fx');
  N.fixes.forEach(function (f) {
    var li = el('li', f.level), tx = el('span');
    /* สวิตช์ของคำสั่ง (-RestartStt, --unattended) ห้ามขาดตรงขีด — จอแคบเคยตัดเป็น "with -" / "RestartStt" (ข้อความยังคัดลอกได้ตรงตัว) */
    String(f.text).split(/(\s--?[A-Za-z][\w-]*)/).forEach(function (part, i) {
      if (!part) return;
      if (i % 2) { tx.append(part.charAt(0)); tx.append(el('span', 'nw', part.slice(1))); } else tx.append(part);
    });
    li.append(svg(f.level === 'info' ? 'info' : 'alert'), tx);
    ul.append(li);
  });
  c.append(b3H2('dFxH', 'b3_doc_fixes'), ul);
  return c;
}
function b3SvcDetail(s) {
  var x = [], u = b3Units();
  if (s.loaded) x.push(s.loaded.length ? b3F(t('b3_loaded'), s.loaded.join(', ')) : t('b3_noloaded'));
  if (s.age != null) x.push(b3F(t('b3_heartbeat'), b3Dur(s.age, u) || b3F(t('b3_u_s'), 0)));
  if (s.ports && s.ports.length) x.push(b3F(t('b3_ports_ok'), s.ports.filter(function (p) { return p.state === 'ok'; }).length, s.ports.length));
  if (s.busy) x.push(b3F(t('b3_busy'), s.busy));
  if (s.provider) x.push(b3F(t('b3_provider'), s.provider === 'builtin' ? t('svc_web_builtin') : s.provider === 'brave' ? 'Brave Search' : s.provider));
  if (s.device) x.push(b3F(t('b3_device'), s.device));
  if (s.upstreamOk === false) x.push(t('b3_gw_noup'));
  if (s.modulesFailed.length) x.push(b3F(t('b3_mod_failed'), s.modulesFailed.join(', ')));
  if (s.version) x.push(s.version);
  if (s.detail) x.push(s.detail);
  return x.join(' · ') || '—';
}
/* ตารางบริการ: div + role table/row/cell (จอแคบจัดเป็นสองบรรทัดต่อบริการ — <table> ที่เปลี่ยน display เสียความหมายของตาราง) */
function b3DocSvc(N) {
  var c = el('section', 'card dcard', null, { 'aria-labelledby': 'dSvH' });
  c.append(b3H2('dSvH', 'b3_doc_svc'));
  if (!N.services.length) { c.append(el('p', 'ch-empty', t('b3_doc_nosvc'))); return c; }
  var tb = el('div', 'svc', null, { role: 'table', 'aria-labelledby': 'dSvH' }), hr = el('div', 'svc-r svc-hd', null, { role: 'row' });
  ['b3_doc_col_svc', 'b3_doc_col_state', 'b3_doc_col_lat', 'b3_doc_col_detail'].forEach(function (k) {
    hr.append(el('span', null, t(k), { role: 'columnheader' }));
  });
  tb.append(hr);
  N.services.forEach(function (s) {
    var r = el('div', 'svc-r', null, { role: 'row' }), c1 = el('span', null, null, { role: 'cell' }), c2 = el('span', 'svc-st', null, { role: 'cell' });
    c1.append(el('span', 'svc-name', s.label));
    if (s.port) c1.append(el('span', 'svc-port', b3F(t('b3_port'), s.port)));
    c2.append(el('span', 'dot ' + s.state, null, { 'aria-hidden': 'true' }), el('span', null, b3StWord(s)));
    /* แถว hub: เวลาตอบของ hub เองไม่มีความหมาย (hub_doctor ใส่ 0) — รายละเอียดบอกจำนวนพอร์ตที่ตอบแทน */
    var lat = s.latency != null && !(s.kind === 'hub' && s.ports) ? b3F(t('b3_u_ms'), Math.round(s.latency)) : '—';
    r.append(c1, c2, el('span', 'svc-lat', lat, { role: 'cell' }),
      el('span', 'svc-d', b3SvcDetail(s), { role: 'cell' }));
    tb.append(r);
  });
  c.append(tb);
  return c;
}
/* แถบความจุ: เต็ม = ส่วนที่ใช้ไป (สีกลาง) · lvl = 'warn' | 'bad' จาก b3MeterLv (คำตัดสินของ hub) = "เหลือน้อย" (สี + คำ
   ไม่ใช้สีอย่างเดียว) — หน้าไม่ตัดสินจาก % ที่ว่างเองแล้ว (เคยขึ้นแดงขณะที่ hub บอกว่าปกติ) · VRAM ส่ง '' เสมอ
   (โมเดลจองเต็มการ์ดโดยตั้งใจ ไม่ใช่ปัญหา) */
function b3Meter(label, free, total, sub, missing, lvl) {
  var row = el('div', 'mt'), top = el('div', 'mt-t'), v = el('span', 'mt-v');
  var ff = free != null && total > 0 ? free / total : null;
  lvl = !missing && (lvl === 'bad' || lvl === 'warn') ? lvl : '';
  if (missing) v.textContent = t('b3_doc_disk_missing');
  else if (free != null && total != null) v.textContent = b3F(t('b3_doc_free_of'), b3Bytes(free), b3Bytes(total));
  else if (free != null) v.textContent = b3F(t('b3_doc_free'), b3Bytes(free));
  else v.textContent = b3Bytes(total);
  if (lvl) { v.append(' · '); v.append(el('b', lvl === 'bad' ? 'bad' : null, t('b3_doc_low'))); }
  top.append(el('span', 'mt-l', label, { title: label }), v);
  row.append(top);
  if (ff != null && !missing) {
    var bar = el('div', 'mt-b' + (lvl ? ' ' + lvl : ''), null, { 'aria-hidden': 'true' }), fill = el('i');
    fill.style.width = Math.round(Math.max(0, Math.min(1, 1 - ff)) * 1000) / 10 + '%';
    bar.append(fill);
    row.append(bar);
  }
  if (sub) row.append(el('div', 'mt-s', sub));
  return row;
}
function b3DocGrid(N) {
  var g = el('div', 'dgrid');
  g.append(b3DocMachine(N), b3DocSoft(N));
  return g;
}
function b3DocMachine(N) {
  var c = el('section', 'card dcard', null, { 'aria-labelledby': 'dMcH' });
  c.append(b3H2('dMcH', 'b3_doc_machine'));
  N.gpus.forEach(function (g) {
    var sub = [g.driver ? b3F(t('b3_doc_driver'), g.driver) : '', g.temp != null ? Math.round(g.temp) + '°C' : '',
      g.util != null ? b3F(t('b3_doc_util'), Math.round(g.util)) : ''].filter(Boolean).join(' · ');
    c.append(b3Meter('GPU · ' + g.name, g.total != null && g.used != null ? Math.max(0, g.total - g.used) : null, g.total, sub, false, ''));
  });
  if (!N.gpus.length) c.append(el('p', 'ch-empty', N.gpuReason ? b3F(t('b3_doc_gpu_err'), N.gpuReason) : t('b3_doc_nogpu')));
  N.mem.forEach(function (m) {
    c.append(b3Meter(t(m.kind === 'ram' ? 'b3_doc_ram' : 'b3_doc_commit'), m.free, m.total, m.kind === 'commit' ? t('b3_doc_commit_hint') : '', false, m.level));
  });
  N.disks.forEach(function (k) { c.append(b3Meter(b3F(t('b3_doc_disk'), k.drive), k.free, k.total, k.note, k.missing, k.level)); });
  return c;
}
function b3YesNo(text, yes, inline) {
  var n = el(inline ? 'span' : 'li', yes ? 'yes' : 'no');
  n.append(svg(yes ? 'check' : 'minus'), el('span', null, text));
  if (!inline) n.append(el('span', 'sz', yes ? t('b3_doc_present') : t('b3_doc_missing')));
  return n;
}
function b3VerLabel(k) { return b3VerName(k, t); }
function b3TestsText(x) {
  var s = x.passed != null || x.failed != null ? b3F(t('b3_doc_tests_v'), b3Int(x.passed || 0), b3Int(x.skipped || 0), b3Int((x.failed || 0) + (x.errors || 0)))
    : x.text || (x.ok === true ? t('b3_st_ok') : x.ok === false ? t('b3_st_bad') : '—');
  var ms = b3Time(x.ts);
  /* เทสต์ที่ไม่ผ่าน (ชื่อจาก hub ล้างความลับแล้ว) — 3 ชื่อแรกพอให้รู้ว่าพังตรงไหน รายการเต็มอยู่ในรายงานที่คัดลอก */
  var bad = x.names && x.names.length ? ' — ' + x.names.slice(0, 3).join(', ') + (x.names.length > 3 ? ' …' : '') : '';
  return s + (isFinite(ms) ? ' · ' + b3Stamp(ms) : '') + bad;
}
function b3DocSoft(N) {
  var c = el('section', 'card dcard', null, { 'aria-labelledby': 'dSwH' }), dl = el('dl', 'kv');
  function row(k, v) {
    var dd = el('dd');
    if (v && v.nodeType) dd.append(v); else dd.textContent = v == null ? '' : String(v);
    dl.append(el('dt', null, k), dd);
  }
  N.versions.forEach(function (v) { row(b3VerLabel(v[0]), v[1]); });
  if (N.models.length) {
    var ul = el('ul');
    N.models.forEach(function (m) {
      var li = el('li');
      li.append(el('span', null, m.name));
      if (m.size != null) li.append(el('span', 'sz', b3Bytes(m.size)));
      ul.append(li);
    });
    row(t('b3_doc_models'), ul);
  }
  if (N.keys.length) {
    var ul2 = el('ul');
    N.keys.forEach(function (k) { ul2.append(b3YesNo(b3KeyName(k.name), k.present)); });
    row(t('b3_doc_keys'), ul2);
  }
  /* hub_doctor ส่ง brave_key ทั้งในรายการไฟล์คีย์และแยกเดี่ยว — แสดงแถวเดียวพอ */
  var braveListed = N.keys.some(function (k) { return /brave/i.test(k.name); });
  if (N.brave != null && !braveListed) row(t('b3_doc_brave'), b3YesNo(N.brave ? t('b3_doc_present') : t('b3_doc_missing'), N.brave, true));
  if (N.docker) row('Docker', b3YesNo((N.docker.ok ? t('b3_doc_usable') : t('b3_doc_unusable')) + (N.docker.reason ? ' — ' + N.docker.reason : ''), N.docker.ok, true));
  row(t('b3_doc_tests'), N.tests ? b3TestsText(N.tests) : t('b3_doc_notests'));
  c.append(b3H2('dSwH', 'b3_doc_soft'), dl);
  return c;
}
function b3DocErrors(N, wasOpen) {
  var c = el('section', 'card dcard');
  if (!N.errors.length) {
    c.append(el('h2', null, t('b3_doc_errors')), el('p', 'ch-empty', t('b3_doc_noerr')));
    return c;
  }
  var d = el('details', 'dd', null, { 'data-k': 'err' }), s = el('summary'), pre = el('pre', 'errs');
  if (wasOpen) d.open = true;
  s.append(el('span', null, t('b3_doc_errors')), el('span', 'cnt', b3F(t('b3_doc_errors_n'), N.errors.length)));
  N.errors.forEach(function (e, i) {
    if (i) pre.append('\n');
    if (e.file) pre.append(el('b', null, e.file + ' | '));
    pre.append(e.text);
  });
  d.append(s, pre);
  c.append(d);
  return c;
}
function b3DocExtra(N, wasOpen) {
  if (!N.extra.length) return null;
  var c = el('section', 'card dcard'), d = el('details', 'dd', null, { 'data-k': 'extra' }), dl = el('dl', 'kv');
  if (wasOpen) d.open = true;
  dl.style.marginTop = '12px';
  N.extra.forEach(function (x) {
    var dd = el('dd');
    if (x[1].yes != null) dd.append(b3YesNo(x[1].yes ? t('b3_doc_present') : t('b3_doc_missing'), x[1].yes, true));
    else dd.textContent = x[1].text;
    dl.append(el('dt', null, x[0]), dd);
  });
  d.append(el('summary', null, t('b3_doc_other')), dl);
  c.append(d);
  return c;
}
/* คัดลอก: Clipboard API (127.0.0.1 นับเป็น secure context) → สำรอง execCommand → สุดท้ายโชว์กล่องข้อความให้คัดลอกเอง */
function b3Copy(txt) {
  return new Promise(function (resolve, reject) {
    var back = document.activeElement;
    function legacy() {
      var ta = el('textarea', 'sr'), ok = false;
      ta.value = txt;
      ta.setAttribute('readonly', '');
      document.body.append(ta);
      ta.select();
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      ta.remove();
      if (back && back.focus) back.focus();
      if (ok) resolve(); else reject(new Error('copy'));
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText && window.isSecureContext) {
        navigator.clipboard.writeText(txt).then(resolve, legacy);
        return;
      }
    } catch (e) {}
    legacy();
  });
}
$('#dRe').addEventListener('click', function () { if (this.getAttribute('aria-disabled') !== 'true') b3DocLoad(true, true); });
$('#dCopy').addEventListener('click', function () {
  if (!B3.docN) return;
  var txt = b3Report(B3.docN, b3T, LANG, b3Units());
  B3.lastReport = txt;
  b3Copy(txt).then(function () {
    var old = $('#dRep');
    if (old) old.remove();
    $('#dCopyT').textContent = t('b3_doc_copied_short');
    b3Say('#dLive', b3T('b3_doc_copied'));
    clearTimeout(B3.copyT);
    B3.copyT = setTimeout(function () { $('#dCopyT').textContent = t('b3_doc_copy'); }, 2400);
  }, function () {
    var ta = $('#dRep') || el('textarea', 'input rep', null, { id: 'dRep', readonly: '', 'aria-label': b3T('b3_doc_copy') });
    ta.value = txt;
    if (!ta.isConnected) $('#dBody').before(ta);
    b3Say('#dLive', b3T('b3_doc_copy_fail'));
    ta.focus();
    ta.select();
  });
});

/* ตรวจซ้ำเอง: การใช้งานทุก ~60 วินาที, ตรวจระบบทุก ~30 วินาที เฉพาะแท็บที่เปิดดูอยู่ และไม่วาดทับขณะโฟกัสอยู่ในเนื้อหา
   (วาดใหม่ = ปุ่ม/กล่องที่ถือโฟกัสหายไป) */
setInterval(function () {
  if (document.visibilityState !== 'visible') return;
  var ae = document.activeElement;
  if (B3.tab === 'usage' && Date.now() - B3.useTry > 60000 && !$('#uBody').contains(ae)) b3UseLoad(true);
  if (B3.tab === 'doctor' && Date.now() - B3.docTry > 30000 && !$('#dBody').contains(ae)) b3DocLoad(true);
}, 5000);
document.addEventListener('visibilitychange', function () {
  if (document.visibilityState !== 'visible') return;
  if (B3.tab === 'usage') b3UseLoad(false); else if (B3.tab === 'doctor') b3DocLoad(false);
});
b3Show(b3TabFromHash(), 'hash');
})();
</script>
</body>
</html>"""


# --------------------------------------------------------------------------
# ข้อความของ UI ชุดใหม่ — ชุดคีย์ของ th กับ en ต้องตรงกันทุกตัว
# hub.py รวมเข้า STRINGS (ทับคีย์เดิมที่ชื่อซ้ำ) ใช้ได้ทั้ง __T_key__ และ T.key
# อักษรล่องหนในข้อความไทย: U+200B (ZWSP ที่มองไม่เห็นระหว่างคำ) = จุดที่ยอมให้ขึ้นบรรทัดใหม่
#   \u2060 (word joiner) = ห้ามตัดตรงนี้ — ใส่ในคำประสม/วลีที่ตัวตัดคำของเบราว์เซอร์แยกได้แต่อ่านแล้วขาด
#   (กู้|คืน, ไม่|ได้, ข้อ|ผิด|พลาด) ห้ามใส่ ZWSP กลางคำพวกนี้ ส่วนคำทับศัพท์ (โปรเจกต์ แชต …) glue() ของ SHELL/PAGE
#   ใส่ให้เองตอนโหลดหน้า (ดู _GLUE_WORDS ท้ายไฟล์) ไม่ต้องใส่ในข้อความ
# --------------------------------------------------------------------------
STRINGS_UI = {
    "th": {
        "sidebar": "แถบข้าง",
        "newchat": "แชตใหม่",
        "searchchats": "ค้นหาแชต",
        "searchph": "ค้นหาชื่อหรือข้อความในแชต…",
        "searching": "กำลังค้นหา…",
        "recents": "ล่าสุด",
        "results": "ผลการค้นหา",
        "noresults": "ไม่พบแชตที่ตรงกัน",
        "norecents": "ยัง​ไม่มี​แชต เริ่ม​แชต​ใหม่​ได้​เลย",
        "untitled": "แชตไม่มีชื่อ",
        "chat_options": "ตัวเลือกแชต",
        "proj_options": "ตัวเลือกโปรเจกต์",
        "rename_chat": "เปลี่ยนชื่อแชต",
        "delete_chat": "ลบแชต",
        "delchat_title": "ลบแชตนี้?",
        "delchat_body": "“%s” และ​ข้อความ​ทั้งหมด​ใน​แชต​นี้​จะ​ถูก​ลบ​ถาวร กู้\u2060คืน​ไม่\u2060ได้",
        "chat_renamed": "เปลี่ยนชื่อแชตแล้ว",
        "chat_deleted": "ลบแชตแล้ว",
        "rename_project": "เปลี่ยนชื่อโปรเจกต์",
        "delete_project": "ลบโปรเจกต์",
        "delproj_title": "ลบโปรเจกต์นี้?",
        "delproj_body": "“%s” จะ​ถูก​นำ\u2060ออก​และ​ปิด​พอร์ต ไฟล์​ของ​โปรเจกต์​จะ​ย้าย​ไป​โฟลเดอร์ _trash (ไม่\u2060ได้​ลบ\u2060ทิ้ง) ส่วน​ประวัติ​แชต​ใน​เบราว์เซอร์​ยัง​อยู่",
        "cant_delete_last": "ต้องเหลืออย่างน้อยหนึ่งโปรเจกต์",
        "delfile_title": "ลบไฟล์นี้?",
        "delete_btn": "ลบ",
        "cancel": "ยกเลิก",
        "save": "บันทึก",
        "saving": "กำลังบันทึก…",
        "saved": "บันทึกแล้ว",
        "unsaved": "ยังไม่ได้บันทึก",
        "save_hint": "Ctrl+Enter เพื่อบันทึก",
        "ok": "ตกลง",
        "close": "ปิด",
        "open_sidebar": "เปิดแถบข้าง",
        "project": "โปรเจกต์",
        "project_btn": "โปรเจกต์",
        "project_settings": "ตั้งค่าโปรเจกต์",
        "instructions": "คำสั่งของโปรเจกต์",
        "instructions_hint": "ใช้กับทุกแชตใหม่ในโปรเจกต์นี้ เช่น ภาษาที่ให้ตอบ น้ำเสียง หรือบริบทที่โมเดลควรรู้",
        "instructions_ph": "เช่น ตอบเป็นภาษาไทย กระชับ อ้างอิงมาตรฐานเมื่อเกี่ยวข้อง",
        "instr_saved": "บันทึกคำสั่งแล้ว — มีผลกับแชตใหม่",
        "knowledge": "ไฟล์ความรู้",
        "dropfiles": "ลากไฟล์มาวางที่นี่ หรือคลิกเพื่อเลือก",
        "copydir": "คัดลอกที่อยู่โฟลเดอร์",
        "settings": "การตั้งค่า",
        "default_model": "โมเดลเริ่มต้น",
        "default_model_hint": "ใช้ตอนเปิดหน้าแชตของโปรเจกต์นี้ เปลี่ยนเฉพาะแชตได้จากปุ่มชื่อโมเดลในช่องพิมพ์",
        "model_saved": "ตั้งโมเดลเริ่มต้นแล้ว — ใช้กับแชตใหม่",
        "think_off_h": "ตอบตรงทันที เร็วที่สุด",
        "think_on_h": "คิดก่อนตอบ ช้าลงแต่ดีกับโจทย์ยาก",
        "think_auto_h": "ปล่อยให้เป็นไปตามค่าเริ่มต้นของโมเดล",
        "manage_all": "จัดการโปรเจกต์ทั้งหมด",
        "local_account": "เครื่องนี้",
        "account_menu": "การตั้งค่าและสถานะ",
        "theme": "ธีม",
        "theme_dark": "มืด",
        "theme_light": "สว่าง",
        "theme_system": "ระบบ",
        "font": "ฟอนต์คำตอบ",
        "font_serif": "มีเชิง",
        "font_sans": "ไม่มีเชิง",
        "language": "ภาษา",
        "webui_settings": "ตั้งค่าหน้าแชต",
        "mcp_servers": "เซิร์ฟเวอร์ MCP",
        "manage_projects": "จัดการโปรเจกต์",
        "nmodels": "%d โมเดล",
        "err_generic": "ทำไม่สำเร็จ",
        "errlang": "สลับภาษาไม่สำเร็จ",
        "errsave": "บันทึกไม่สำเร็จ",
        "wait_streaming": "รอให้โมเดลตอบเสร็จก่อน",
        "reload_deferred": "จะ​รีเฟรช​หน้า\u2060แชต​เมื่อ​คำตอบ​เสร็จ​และ​ช่อง\u2060พิมพ์​ว่าง",
        "not_ready_yet": "หน้าแชตยังโหลดไม่เสร็จ ลองอีกครั้ง",
        "chat_frame": "หน้าแชต",
        "noinstr": "ยังไม่มีคำสั่งเฉพาะ",
        "main_nav": "เมนูหลัก",
        "skip_composer": "ข้ามไปที่ช่องพิมพ์ข้อความ",
        "row_keys_hint": "ลูกศรขึ้นลงเพื่อเลื่อน ลูกศรขวาหรือ Shift+F10 เพื่อเปิดตัวเลือก",
        "instr_conflict": "มีการแก้​คำสั่ง​นี้​จาก​ที่อื่น — บันทึก​จะ​เขียน\u2060ทับ",
        "err_retry": "เกิด​ข้อ\u2060ผิด\u2060พลาด ลอง​อีก\u2060ครั้ง",
        "err_exists": "มี​โปรเจกต์​ชื่อ​นี้​อยู่​แล้ว",
        "err_noport": "ไม่​เหลือ​พอร์ต​ว่าง​สำหรับ​โปรเจกต์​ใหม่",
        "err_filesize": "ขนาด​ไฟล์​ต้อง​อยู่​ระหว่าง 1 ไบต์ ถึง 64 MB",
        "errmodel": "ตั้ง​โมเดล​เริ่มต้น​ไม่\u2060สำเร็จ",
        "errextend": "เปลี่ยน​การ​ต่อ​คำตอบ​อัตโนมัติ​ไม่\u2060สำเร็จ",
        "lang_group": "ภาษาของหน้าจอ",
        # ป้ายชื่อของสวิตช์ภาษาเขียนเป็นภาษาของหน้าจอ (ข้อความอื่นทั้งหน้าก็เช่นนั้น) — ตัวปุ่มเขียนชื่อภาษาปลายทางเองอยู่แล้ว
        # (ไทย / EN) คนที่อ่านภาษาปัจจุบันไม่ออกก็ยังหาทางกลับได้ ไม่ต้องให้ป้ายชื่อปนอีกภาษาเข้ามาในหน้า
        "lang_tip_th": "เปลี่ยนเป็นภาษาไทย (Alt+Shift+L)",
        "lang_tip_en": "เปลี่ยนเป็นภาษาอังกฤษ (Alt+Shift+L)",
        "lang_unsaved": "บันทึก​คำสั่ง​ของ​โปรเจกต์​ที่​แก้​ค้าง​ไว้​ก่อน แล้ว​ค่อย​เปลี่ยน​ภาษา",
        # GPU ที่โมเดลใช้ (แถบข้าง + หน้าจัดการ) — ชื่อการ์ด (RTX 4090) และคำว่า GPU/CPU คงเป็นอังกฤษตามที่เรียกกันจริง
        "gpu_changed_short": "GPU เปลี่ยน",
        "gpu_changed": "พบ GPU เปลี่ยน — ในหน้าแชต เปิดเมนู “เครื่องนี้” แล้วกด “ใช้ GPU ใหม่”",
        "gpu_where": "GPU ของแต่ละโมเดล",
        "gpu_as_started": "(ตอนเปิดครั้งล่าสุด)",
        "gpu_found": "GPU ที่พบ",
        "gpu_none": "ไม่พบ GPU — ทุก​โมเดล​ทำงาน​บน CPU",
        # ตรวจ GPU ตอนเปิดไม่สำเร็จ: ไม่ได้แปลว่าไม่มี GPU (-fit ยังใช้การ์ดที่ CUDA เห็น) — ห้ามใช้ gpu_none แทน
        "gpu_failed_short": "ตรวจ GPU ไม่ได้",
        "gpu_failed": "ตรวจ GPU ไม่​สำเร็จ​ตอน​เปิด — llama-server เลือก GPU เอง​ตอน​โหลด​โมเดล",
        # nvidia-smi เห็นการ์ด แต่ llama-server ไม่เห็น (CUDA_VISIBLE_DEVICES=-1 หรือ CUDA เริ่มไม่ขึ้น) — การ์ดไม่ได้หาย
        "gpu_hidden": "llama-server มอง​ไม่​เห็น GPU — ทุก​โมเดล​ทำงาน​บน CPU",
        "gpu_auto": "อัตโนมัติ",
        "gpu_external": "ต่อภายนอก",
        "gpu_ctx": "บริบท %s",
        "gpu_vision": "รองรับภาพ",
        # หน้าต่างเลือก GPU (เปิดจากเมนูบัญชี) — %1 %2 … แทนด้วย fmtN() ส่วน %s ใช้ fmt()
        "gpu_choose": "เลือก GPU…",
        "gpu_edit": "เปลี่ยน",
        "gpu_use_new": "ใช้ GPU ใหม่",
        "gpu_changed_menu": "GPU ที่ต่ออยู่ไม่ตรงกับตอนเปิดครั้งล่าสุด",
        # ป้ายชื่อของปุ่มบัญชีตอน GPU เปลี่ยน — บอกทางที่เร็วที่สุด (ปุ่มในเมนูนี้) แทนการปิดแล้วเปิดจากไอคอน
        "gpu_changed_btn": "พบ GPU เปลี่ยน — เปิดเมนูนี้แล้วกด “ใช้ GPU ใหม่”",
        "gpu_title": "เลือก GPU ให้โมเดล",
        "gpu_sub": "กำหนดว่าแต่ละโมเดลใช้การ์ดใบไหน ถ้าไม่แน่ใจให้ใช้อัตโนมัติ ระบบจะจัดให้ตาม GPU ที่ต่ออยู่ตอนรีสตาร์ต",
        "gpu_devs_h": "GPU ที่ต่ออยู่",
        "gpu_redetect": "ตรวจใหม่",
        "gpu_detecting": "กำลังตรวจ…",
        "gpu_detecting_long": "กำลังตรวจ GPU ที่ต่ออยู่…",
        "gpu_detect_fail": "ยังตรวจ GPU ไม่ได้ — ตอนนี้เลือกได้แค่อัตโนมัติหรือ CPU",
        "gpu_no_gpu": "ไม่พบ GPU — เลือกได้แค่อัตโนมัติหรือ CPU",
        "gpu_internal": "ในเครื่อง",
        "gpu_models_h": "โมเดล",
        "gpu_no_models": "ยังไม่พบรายชื่อโมเดล",
        "gpu_primary": "หลัก",
        "gpu_opt_auto": "อัตโนมัติ (แนะนำ)",
        "gpu_opt_cpu": "CPU เท่านั้น",
        "gpu_not_connected": "ไม่ได้ต่ออยู่",
        "gpu_fit_ok": "ใส่ลง GPU ได้ทั้งตัว — ใช้ ~%1 จาก %2 GB",
        "gpu_fit_ok_auto": "ใส่ลง GPU ได้ทั้งตัว — ใช้ ~%1 GB",
        "gpu_fit_spill": "ล้นไป CPU ราว %1 GB — ช้าลง",
        "gpu_fit_cpu": "ทำงานบน CPU ทั้งหมด — ช้าที่สุด",
        "gpu_fit_auto": "ระบบเลือกให้ตอนรีสตาร์ต ตาม GPU ที่ต่ออยู่",
        "gpu_fit_unknown": "ไม่ทราบขนาดที่โมเดลนี้ต้องใช้",
        "gpu_fit_nodetect": "ยังตรวจ GPU ไม่ได้ จึงบอกไม่ได้ว่าพอดีหรือไม่",
        "gpu_fit_64kv": "บริบท 64K + รองรับภาพ",
        "gpu_fit_64k": "บริบท 64K",
        "gpu_now": "ตอนนี้: %s",
        "gpu_then": "ตอนเปิดครั้งล่าสุด: %s",
        "gpu_now_chosen": "ตามที่เลือก",
        "gpu_note_userini_dev": "ค่า device ใน models-preset.user.ini มีผลเหนือ GPU ที่เลือกไว้",
        "gpu_note_userini_devauto": "models-preset.user.ini กำหนด GPU ของโมเดลนี้ไว้ — ใช้ค่านั้นแทนอัตโนมัติ",
        "gpu_note_userini_opts": "models-preset.user.ini ตั้งบริบทหรือการรองรับภาพของโมเดลนี้ไว้ด้วย",
        "gpu_note_missing_now": "ตอนนี้ไม่พบ %s — รีสตาร์ตแล้วจะใช้อัตโนมัติแทน",
        "gpu_note_missing_part": "ตอนนี้ไม่พบ %s — จะใช้เฉพาะการ์ดที่ต่ออยู่",
        "gpu_note_missing_then": "ตอนเปิดครั้งล่าสุดไม่พบการ์ดที่เลือกไว้ จึงใช้อัตโนมัติแทน",
        "gpu_note_dropped_then": "ตอนเปิดครั้งล่าสุดไม่พบ %s จึงใช้เฉพาะการ์ดที่ต่ออยู่",
        "gpu_conflict": "%1 ใช้ %2 ร่วมกัน รวม ~%3 GB เกินที่มี ~%4 GB — ถ้าโหลดพร้อมกัน ส่วนที่เกินจะไปอยู่บน CPU",
        "gpu_and": " และ ",
        "gpu_stale_banner": "GPU ที่ต่ออยู่ตอนนี้ต่างจากตอนเปิดครั้งล่าสุด — กดบันทึกและรีสตาร์ตเพื่อใช้ชุดใหม่",
        "gpu_reset": "คืนค่าอัตโนมัติทั้งหมด",
        "gpu_reset_done": "ตั้งทุกโมเดลเป็นอัตโนมัติแล้ว — กดบันทึกเพื่อใช้",
        "gpu_apply": "บันทึกและรีสตาร์ตโมเดล",
        "gpu_confirm": "เซิร์ฟเวอร์โมเดลจะรีสตาร์ต และโมเดลที่โหลดอยู่จะโหลดใหม่ ถ้ามีแชตกำลังตอบ จะรอให้เสร็จก่อน (สูงสุด 3 นาที)",
        "gpu_applying": "กำลังรีสตาร์ตเซิร์ฟเวอร์โมเดล…",
        "gpu_applying_hint": "ปิดหน้าต่างนี้ได้ ระบบทำต่อเบื้องหลัง",
        "gpu_elapsed": "ผ่านไป %s",
        "gpu_done": "ใช้การตั้งค่า GPU ใหม่แล้ว",
        "gpu_busy": "ยังมีแชตกำลังตอบอยู่ จึงยังไม่ได้รีสตาร์ต — ตัวเลือกบันทึกไว้แล้ว ลองอีกครั้งเมื่อตอบเสร็จ",
        "gpu_apply_failed": "รีสตาร์ตไม่สำเร็จ — ตัวเลือกบันทึกไว้แล้ว ดูบันทึกด้านล่าง หรือเปิด Qwen3.8 จากไอคอนอีกครั้ง",
        "gpu_failed_toast": "รีสตาร์ตไม่สำเร็จ — เปิด “เลือก GPU…” อีกครั้งเพื่อดูบันทึก",
        "gpu_log": "บันทึก (%s)",
        "gpu_loading": "กำลังโหลด…",
        "gpu_retry": "ลองอีกครั้ง",
        "gpu_wait_stream": "รอให้โมเดลตอบเสร็จก่อน แล้วค่อยรีสตาร์ต",
        "gpu_err_load": "โหลดข้อมูล GPU ไม่สำเร็จ",
        "gpu_err_save": "บันทึกตัวเลือก GPU ไม่สำเร็จ",
        "gpu_err_invalid": "ตัวเลือกไม่ถูกต้อง ลองกดตรวจ GPU ใหม่",
        "gpu_err_running": "กำลังรีสตาร์ตอยู่แล้ว — กำลังติดตามงานนั้น",
        "gpu_waiting": "กำลังรอให้แชตที่ตอบอยู่เสร็จก่อนรีสตาร์ต…",
        "gpu_done_same": "ไม่มีอะไรต้องเปลี่ยน — ใช้การตั้งค่านี้อยู่แล้ว",
        "gpu_unknown": "ไม่ทราบผลของการรีสตาร์ต — ตัวเลือกบันทึกไว้แล้ว ดูบันทึก gpu-apply.log",
        "gpu_still_running": "ตัวเปิดรอบนั้นยังทำงานอยู่ — รอให้จบก่อนแล้วค่อยลองใหม่",
        "gpu_saved_not_started": "บันทึกตัวเลือกแล้ว แต่สั่งรีสตาร์ตไม่ได้",
        "gpu_err_busy_save": "กำลังรีสตาร์ตจากที่อื่นอยู่ — ตัวเลือกนี้ยังไม่ได้บันทึก รอให้เสร็จแล้วกดบันทึกอีกครั้ง",
        "gpu_fit_shared": "ใช้ %s ร่วมกับโมเดลหลัก",
        "gpu_primary_desc": "โมเดลหลัก",
        # ---- รอบ 4 (2026-09-30): ความจำ K3 · ไฟล์ผลลัพธ์ K2 · ปรับให้เป็นของคุณ K4 · แจ้งเตือน K5 · แผงแสดงผล K7 · ส่งออก K10
        "retry": "ลองอีกครั้ง",
        "mem_title": "ความจำของโปรเจกต์",
        "mem_hint": "สิ่งที่ Qwen จำไว้ ใส่ในทุกแชตของโปรเจกต์นี้ (ที่ปักหมุดก่อน แล้วตามด้วยรายการใหม่สุดเท่าที่พื้นที่พอ) บอกในแชตว่า “จำไว้ว่า…” หรือเพิ่มเองที่นี่",
        "mem_add": "เพิ่ม",
        "mem_new": "ความจำใหม่",
        "mem_ph": "เช่น ตู้รุ่น EV150 ใช้ OCPP 1.6J และส่ง Heartbeat ทุก 300 วินาที",
        "mem_kind": "ประเภท",
        "mem_k_fact": "ข้อเท็จจริง",
        "mem_k_decision": "การตัดสินใจ",
        "mem_k_requirement": "ความต้องการ",
        "mem_k_progress": "ความคืบหน้า",
        "mem_k_todo": "สิ่งที่ต้องทำ",
        "mem_pin": "ปักหมุด",
        "mem_unpin": "เลิกปักหมุด",
        "mem_pinned": "ปักหมุดไว้",
        "mem_pinned_tip": "ปักหมุด — ใส่ในทุกแชตเสมอ",
        "mem_edit": "แก้ไข",
        "mem_edit_label": "แก้ไขความจำ",
        "mem_delete": "ลบ",
        "mem_del_title": "ลบความจำนี้?",
        "mem_del_body": "Qwen จะไม่เห็น “%s” ในแชตอีก",
        "mem_empty": "ยังไม่มีความจำ — เพิ่มเอง หรือบอกในแชตว่า “จำไว้ว่า…”",
        "mem_unavail": "ความจำยังใช้ไม่ได้ — hub ต้องรีสตาร์ตเป็นรุ่นใหม่ก่อน",
        "mem_err_load": "โหลดความจำไม่สำเร็จ",
        "mem_saved": "บันทึกความจำแล้ว — ใช้ตั้งแต่ข้อความถัดไป",
        "mem_esc_again": "ยังไม่ได้บันทึก — กด Esc อีกครั้งเพื่อทิ้งข้อความนี้",
        "mem_esc_edit": "ยังไม่ได้บันทึกการแก้ไข — กด Esc อีกครั้งเพื่อยกเลิก",
        "mem_deleted": "ลบความจำแล้ว",
        "mem_pinned_t": "ปักหมุดแล้ว — ใส่ในทุกแชตเสมอ",
        "mem_unpinned_t": "เลิกปักหมุดแล้ว",
        "mem_err_save": "บันทึกความจำไม่สำเร็จ",
        "mem_show_all": "แสดงทั้งหมด (%s)",
        "mem_show_less": "แสดงน้อยลง",
        "mem_more_text": "อ่านต่อ",
        "mem_less_text": "ย่อ",
        "mem_off": "ไม่ได้ใส่ในแชต",
        "mem_off_tip": "เกินพื้นที่ความจำในแชต — ปักหมุดถ้าต้องการให้ใส่เสมอ",
        "mem_sum": "ใส่ในแชต %1 จาก %2 รายการ · ~%3 / %4 โทเค็น",
        "mem_broken": "ไฟล์ memory.json เสีย อ่านไม่ได้ — ยังไม่เขียนทับ ให้แก้ไฟล์ก่อน",
        "loading": "กำลังโหลด…",
        "out_title": "ไฟล์ที่ Qwen สร้าง",
        "out_hint": "รายงาน รูป และตารางที่สร้างจากแชต เก็บในโฟลเดอร์ outputs ของโปรเจกต์",
        "out_open": "เปิด",
        "out_panel": "เปิดในแผง",
        "pers_menu": "ปรับให้เป็นของคุณ…",
        "pers_title": "ปรับให้เป็นของคุณ",
        "pers_sub": "ใช้กับทุกแชตในทุกโปรเจกต์บนเครื่องนี้ มีผลตั้งแต่ข้อความถัดไป",
        "pers_about": "เกี่ยวกับคุณ",
        "pers_about_h": "สิ่งที่อยากให้ Qwen รู้ทุกครั้ง เช่น งานที่ทำ เครื่องมือที่ใช้ประจำ หรือระดับความรู้ที่มี",
        "pers_about_ph": "เช่น ผมเป็นวิศวกรดูแลตู้ชาร์จ EV อ่าน log OCPP และเขียน Python ทุกวัน ชอบคำตอบที่ลงรายละเอียดทางเทคนิค",
        "pers_style": "รูปแบบการตอบ",
        "pers_st_normal": "ปกติ",
        "pers_st_normal_d": "สมดุล ตอบตรงแล้วเสริมเท่าที่ช่วยได้",
        "pers_st_concise": "กระชับ",
        "pers_st_concise_d": "สั้น ได้ใจความ ไม่เกริ่น",
        "pers_st_explanatory": "อธิบายละเอียด",
        "pers_st_explanatory_d": "ให้เหตุผลและบริบท เป็นขั้นตอน",
        "pers_st_formal": "ทางการ",
        "pers_st_formal_d": "ภาษาสุภาพ พร้อมใส่รายงาน",
        "pers_st_learning": "สอนทีละขั้น",
        "pers_st_learning_d": "ชวนคิด ใบ้ก่อนเฉลย",
        "pers_st_custom": "กำหนดเอง",
        "pers_st_custom_d": "เขียนรูปแบบที่ต้องการเอง",
        "pers_custom": "รูปแบบที่ต้องการ",
        "pers_custom_ph": "เช่น ตอบเป็นข้อๆ ใส่หน่วยเสมอ และสรุปท้ายหนึ่งบรรทัด",
        "pers_preview": "ตัวอย่างคำตอบ",
        "pers_pv_q": "ทำไมตู้ชาร์จขึ้นสถานะ Faulted",
        "pers_pv_normal": "ตู้ตรวจพบความผิดปกติที่ทำให้จ่ายไฟต่อไม่ได้ เช่น ไฟรั่วลงดิน อุณหภูมิสูงเกิน หรือสื่อสารกับรถไม่ได้ เริ่มจากดู errorCode ใน StatusNotification แล้วไล่ต่อตามรหัสนั้น",
        "pers_pv_concise": "ตู้เจอความผิดปกติ — ดู errorCode ใน StatusNotification",
        "pers_pv_explanatory": "Faulted แปลว่าตู้หยุดจ่ายไฟเพราะตรวจพบปัญหา\n1. ดู errorCode ใน StatusNotification ล่าสุด — บอกหมวดของปัญหา\n2. เทียบเวลากับ log การชาร์จ ว่าเกิดระหว่างชาร์จหรือตอนว่าง\n3. ถ้าเป็น GroundFailure ให้ตรวจสายดินก่อน เพราะเป็นเรื่องความปลอดภัย",
        "pers_pv_formal": "สถานะ Faulted แสดงว่าตู้ชาร์จตรวจพบความผิดปกติซึ่งทำให้ไม่สามารถให้บริการได้ ขอแนะนำให้ตรวจสอบค่า errorCode ในข้อความ StatusNotification เพื่อระบุสาเหตุต่อไป",
        "pers_pv_learning": "ลองคิดก่อนว่าตอนสถานะเปลี่ยน ตู้ส่งข้อความอะไรมาบอกเรา? ใบ้ว่ามีฟิลด์หนึ่งที่บอกชนิดของปัญหา เจอแล้วลองบอกค่ามา เดี๋ยวเราไล่ต่อด้วยกัน",
        "pers_pv_custom": "คำตอบจะเป็นไปตามรูปแบบที่คุณเขียนไว้ด้านบน",
        "pers_privacy": "เก็บไว้ในเครื่องนี้เท่านั้น (settings.json ของ hub) และใส่ในคำสั่งของทุกแชต",
        "pers_saved": "บันทึกแล้ว — มีผลตั้งแต่ข้อความถัดไป",
        "pers_unsupported": "hub รุ่นที่ทำงานอยู่ยังไม่รองรับการตั้งค่านี้ — ต้องรีสตาร์ต hub ก่อน",
        "pers_err_load": "โหลดการตั้งค่าไม่สำเร็จ",
        "pers_need_custom": "เขียนรูปแบบที่ต้องการก่อนบันทึก",
        "pers_esc_again": "ยังไม่ได้บันทึก — กด Esc อีกครั้งเพื่อปิดโดยไม่บันทึก",
        "notify": "แจ้งเตือน",
        "ntf_off": "ปิด",
        "ntf_on": "เปิด",
        "ntf_sound": "มีเสียง",
        "ntf_denied": "เบราว์เซอร์บล็อกการแจ้งเตือนของหน้านี้ — อนุญาตได้ที่ไอคอนหน้าช่องที่อยู่เว็บ",
        "ntf_not_granted": "ยังไม่ได้อนุญาตการแจ้งเตือน",
        "ntf_unsupported": "เบราว์เซอร์นี้แจ้งเตือนไม่ได้",
        "ntf_enabled": "จะแจ้งเตือนเมื่อแท็บนี้ถูกซ่อน และ Qwen ตอบเสร็จหรือรอคุณ",
        "ntf_off_t": "ปิดการแจ้งเตือนแล้ว",
        "ntf_blocked": "เลือกเปิดไว้ แต่เบราว์เซอร์บล็อกการแจ้งเตือนของหน้านี้ — อนุญาตได้ที่ไอคอนหน้าช่องที่อยู่เว็บ",
        "ntf_ask_again": "เลือกเปิดไว้ แต่เบราว์เซอร์ยังไม่อนุญาต — กด “เปิด” อีกครั้งเพื่อขออนุญาต",
        "ntf_done": "Qwen ตอบเสร็จแล้ว",
        "ntf_perm": "Qwen ขออนุญาตใช้เครื่องมือ",
        "ntf_cont": "Qwen รอให้คุณกดทำต่อ",
        "ntf_generic": "Qwen รอคุณอยู่",
        "art_region": "แผงแสดงผล",
        "art_view": "มุมมอง",
        "art_preview": "แสดงผล",
        "art_code": "โค้ด",
        "art_copy": "คัดลอก",
        "art_download": "ดาวน์โหลด",
        "art_close": "ปิดแผง",
        "art_prev": "เวอร์ชันก่อนหน้า",
        "art_next": "เวอร์ชันถัดไป",
        "art_versions": "เวอร์ชัน",
        "art_ver": "เวอร์ชัน %1 จาก %2",
        "art_resize": "ปรับความกว้างแผง",
        "art_list": "ชิ้นงานอื่นในหน้านี้",
        "art_k_html": "HTML",
        "art_k_svg": "SVG",
        "art_k_mermaid": "แผนภาพ",
        "art_k_markdown": "เอกสาร",
        "art_k_csv": "ตาราง",
        "art_k_image": "รูปภาพ",
        "art_sandbox": "แสดงในกรอบแยก — ไม่มีเน็ต และแตะข้อมูลของหน้านี้ไม่ได้",
        "art_mermaid_na": "ยังวาดแผนภาพนี้ไม่ได้ — รอให้แผนภาพในแชตแสดงผลเสร็จ แล้วกด “เปิดในแผง” อีกครั้ง",
        "art_rows": "แสดง %1 จาก %2 แถว",
        "art_bad": "เปิดในแผงไม่ได้ — ชนิดหรือเนื้อหาไม่รองรับ",
        "art_too_big": "ใหญ่เกินกว่าจะแสดงในแผง (เกิน 2 MB)",
        "art_opened": "เปิด “%s” ในแผงแล้ว",
        "art_js_off_note": "สคริปต์ของหน้านี้ปิดอยู่ — หน้าที่รันสคริปต์ส่งข้อมูลออกนอกเครื่องได้ เปิดเฉพาะเมื่อไว้ใจเนื้อหา",
        "art_js_on_note": "สคริปต์กำลังทำงาน — หน้านี้ยังพาแผงไปเว็บอื่นพร้อมข้อมูลได้",
        "art_js_left": "หน้านี้พยายามพาแผงไปที่อยู่อื่น จึงดึงกลับและปิดสคริปต์แล้ว — ข้อมูลที่อยู่ในที่อยู่นั้นอาจถูกส่งออกไปแล้ว",
        "art_js_run": "เรียกใช้สคริปต์",
        "art_js_stop": "หยุดสคริปต์",
        "art_js_on": "เปิดสคริปต์ของหน้านี้แล้ว",
        "art_js_off": "ปิดสคริปต์ของหน้านี้แล้ว",
        "art_frame": "ผลลัพธ์ของ %s",
        "art_img_err": "โหลดรูปไม่สำเร็จ",
        "exp_md": "ส่งออก Markdown",
        "exp_html": "ส่งออก HTML",
        "exp_pdf": "ส่งออก PDF (พิมพ์)",
        "exp_done": "ส่งออกแล้ว: %s",
        "exp_err": "ส่งออกไม่สำเร็จ",
        "exp_empty": "แชตนี้ยังไม่มีข้อความ",
        "exp_print_opened": "เปิดหน้าพิมพ์ในแท็บใหม่แล้ว — เลือก “บันทึกเป็น PDF” (ถ้าไม่เห็นแท็บ ให้อนุญาตป๊อปอัปของหน้านี้)",
        "exp_print_hint": "ถ้าหน้าต่างพิมพ์ไม่ขึ้นเอง กด Ctrl+P แล้วเลือก “บันทึกเป็น PDF”",
        "exp_you": "คุณ",
        "exp_reasoning": "ความคิด",
        "exp_tool": "เครื่องมือ",
        "exp_args": "อาร์กิวเมนต์",
        "exp_result": "ผลลัพธ์",
        "exp_no_result": "(ไม่มีผลลัพธ์)",
        "exp_attach": "ไฟล์แนบ",
        "exp_meta": "ส่งออกจาก Qwen3.8 · โปรเจกต์ %1 · %2",
        "exp_cut": "… (ตัดเหลือ %1 จาก %2 ตัวอักษร)",
        # ---- batch 2a (B5): บริการของเครื่องนี้ (เมนูบัญชี) + งานค้นคว้า (แผงโปรเจกต์)
        "svc_head": "บริการ",
        "svc_embed": "ค้นเอกสารตามความหมาย",
        "svc_research": "ค้นคว้าเชิงลึก",
        "svc_web": "ค้นเว็บ",
        "svc_ok": "พร้อม",
        "svc_loading": "กำลังโหลด…",
        "svc_down": "ไม่ทำงาน",
        "svc_embed_down": "ไม่ทำงาน — ค้นด้วยคำแทน",
        "svc_embed_absent": "ไม่มีโมเดล — ค้นด้วยคำแทน",
        "svc_res_running": "กำลังทำ %s งาน",
        "svc_res_missing": "ยังไม่ได้ติดตั้ง",
        "svc_res_broken": "โหลดไม่ได้ (ดู log ของ MCP)",
        "svc_res_down": "MCP ไม่ทำงาน",
        "svc_auth": "โทเค็นไม่ตรง — เปิด Qwen3.8 ใหม่",
        "svc_web_builtin": "พื้นฐาน",
        "svc_web_hint": "ค้นจาก Wikipedia + DuckDuckGo ได้ผลจำกัด — ใส่ Brave Search key เพื่อผลที่ดีกว่า",
        "res_title": "งานค้นคว้า",
        "res_new": "ค้นคว้าใหม่",
        "res_hint": "Qwen ค้นเว็บ อ่านแหล่งข้อมูล แล้วเขียนรายงานพร้อมอ้างอิงลงในไฟล์ของโปรเจกต์ — ทำงานเบื้องหลัง ปิดหน้านี้ได้",
        "res_prefill": "ค้นคว้าเชิงลึกแล้วเขียนรายงานพร้อมอ้างอิงเรื่อง: ",
        "res_empty": "ยังไม่มีงานค้นคว้า — กด “ค้นคว้าใหม่” หรือพิมพ์ในแชตว่า “ค้นคว้าเชิงลึกเรื่อง …”",
        "res_unavail": "ใช้ได้หลังจากเริ่ม hub ใหม่ (ปิดด้วย stop-qwen38.ps1 แล้วเปิด Qwen3.8 จากไอคอนอีกครั้ง)",
        "res_err_load": "โหลดรายการงานค้นคว้าไม่ได้",
        "res_svc_note": "ค้นคว้าเชิงลึกยังไม่พร้อม: %s",
        "res_noq": "(ไม่มีหัวข้อ)",
        "res_st_queued": "รอคิว",
        "res_st_running": "กำลังค้นคว้า",
        "res_st_cancelling": "กำลังยกเลิก…",
        "res_st_done": "เสร็จแล้ว",
        "res_st_failed": "ไม่สำเร็จ",
        "res_st_cancelled": "ยกเลิกแล้ว",
        "res_st_interrupted": "หยุดกลางทาง",
        "res_st_unknown": "ไม่ทราบสถานะ",
        "res_ph_plan": "วางแผนคำถามย่อย",
        "res_ph_search": "ค้นเว็บ",
        "res_ph_pick": "เลือกแหล่งข้อมูล",
        "res_ph_read": "อ่านแหล่งข้อมูล",
        "res_ph_notes": "จดประเด็นจากแหล่ง",
        "res_ph_write": "เขียนรายงาน",
        "res_ph_save": "บันทึกไฟล์",
        "res_ph_done": "เสร็จ",
        "res_depth_quick": "แบบเร็ว",
        "res_depth_standard": "แบบมาตรฐาน",
        "res_read": "อ่านแล้ว %s แหล่ง",
        "res_read_of": "อ่านแล้ว %1 จาก %2 แหล่ง",
        "res_eta": "อีกราว %s",
        "res_min": "%s นาที",
        "res_hr_min": "%1 ชม. %2 นาที",
        "res_stale": "ไม่มีความคืบหน้านาน — อาจค้าง",
        "res_progress": "ความคืบหน้า",
        "res_open": "เปิดรายงาน",
        "res_docx": "Word (.docx)",
        "res_cancel": "ยกเลิก",
        "res_cancel_title": "หยุดงานค้นคว้านี้?",
        "res_cancel_body": "Qwen จะหยุดค้นคว้าเรื่อง “%s” — สิ่งที่ค้นได้ถึงตอนนี้อาจไม่ถูกเขียนเป็นรายงาน",
        "res_cancel_ok": "หยุดค้นคว้า",
        "res_cancel_keep": "ทำต่อ",
        "res_cancel_sent": "ส่งคำขอหยุดแล้ว — งานจะหยุดเมื่อจบขั้นที่ทำอยู่",
        "res_cancel_err": "หยุดงานค้นคว้าไม่สำเร็จ",
        "res_not_running": "งานนี้จบไปแล้ว",
        "res_done_title": "งานค้นคว้าเสร็จแล้ว",
        "res_done_t": "งานค้นคว้าเสร็จแล้ว: %s",
        "res_failed_t": "งานค้นคว้าไม่สำเร็จ: %s",
        "res_intr_t": "งานค้นคว้าหยุดกลางทาง (MCP เริ่มใหม่) — สั่งใหม่ได้: %s",
        # ---- batch 2b (C4, owner ui): ค้นเอกสารของโปรเจกต์อัตโนมัติ (แผงโปรเจกต์) + พูดแทนพิมพ์ (ก้อนบริการ)
        "autokb": "ค้นเอกสารของโปรเจกต์อัตโนมัติ",
        "autokb_hint": "ก่อน Qwen ตอบ ระบบจะค้นไฟล์ของโปรเจกต์ที่เกี่ยวกับข้อความของคุณ แล้วแนบส่วนที่พบให้ Qwen อ่านด้วย — ทำในเครื่องนี้ทั้งหมด · พิมพ์ @ ในช่องพิมพ์เพื่อเลือกไฟล์เอง",
        "autokb_on": "เปิดการค้นเอกสารอัตโนมัติแล้ว",
        "autokb_off": "ปิดการค้นเอกสารอัตโนมัติแล้ว",
        "autokb_unsupported": "hub ที่รันอยู่ยังไม่รองรับการค้นเอกสารอัตโนมัติ — เปิด Qwen3.8 จากไอคอนอีกครั้งแล้วลองใหม่",
        "errautokb": "เปลี่ยนการค้นเอกสารอัตโนมัติไม่สำเร็จ",
        "svc_stt": "พูดแทนพิมพ์",
        "svc_stt_dev": "พร้อม (%s)",
        "svc_stt_hint": "เปิด Qwen3.8 จากไอคอนอีกครั้งเพื่อเริ่มบริการถอดเสียง",
        # ---- batch 3 (D4, owner ui): แท็บ "การใช้งาน" / "ตรวจระบบ" ในหน้าจัดการ + ลิงก์จากเมนูบัญชี
        # คีย์ขึ้นต้น b3_ ทั้งหมด (กันชนกับคีย์ที่ owner hub อาจเพิ่มใน STRINGS ของ hub.py — STRINGS_UI ทับคีย์ชื่อซ้ำ)
        "b3_menu_usage": "การใช้งาน",
        "b3_menu_doctor": "ตรวจระบบ",
        "b3_tabs": "ส่วนของหน้า",
        "b3_tab_projects": "โปรเจกต์",
        "b3_tab_usage": "การใช้งาน",
        "b3_tab_doctor": "ตรวจระบบ",
        "b3_use_title": "การใช้งาน",
        "b3_use_sub": "สถิติของคำขอแชตที่ผ่าน hub ในเครื่องนี้ — เก็บแค่ตัวเลข (โทเค็น ความเร็ว เวลา ชื่อเครื่องมือ) ไม่เก็บข้อความแชต",
        "b3_use_range": "ช่วงเวลา",
        "b3_use_7d": "7 วัน",
        "b3_use_30d": "30 วัน",
        "b3_use_updated": "อัปเดตเมื่อ %s",
        "b3_loading": "กำลังโหลด…",
        "b3_use_empty": "ยังไม่มีการใช้งานในช่วงนี้ — คุยกับ Qwen สักพักแล้วกลับมาดูอีกครั้ง",
        "b3_unsupported": "hub ที่รันอยู่ยังไม่มีข้อมูลส่วนนี้ — เปิด Qwen3.8 จากไอคอนอีกครั้งเพื่อใช้ hub รุ่นใหม่",
        "b3_retry": "ลองใหม่",
        "b3_t_tokens": "โทเค็นทั้งหมด",
        "b3_t_tokens_s": "พรอมต์ %1 · คำตอบ %2",
        "b3_t_req": "คำขอ",
        "b3_t_req_s": "ผิดพลาด %1 · สรุปบทสนทนา %2 ครั้ง",
        "b3_t_cache": "พรอมต์จากแคช",
        "b3_t_cache_s": "%s โทเค็นไม่ต้องคำนวณใหม่",
        "b3_t_time": "เวลาที่โมเดลทำงาน",
        "b3_t_time_s": "เฉลี่ย %s ต่อคำขอ",
        "b3_c_tokens": "โทเค็นต่อวัน แยกตามโมเดล",
        "b3_c_tokens_s": "พรอมต์ + คำตอบ",
        "b3_c_speed": "ความเร็วในการตอบ",
        "b3_c_speed_s": "โทเค็นต่อวินาที เฉลี่ยรายวัน — แต่ละโมเดลมีสเกลของตัวเอง",
        "b3_c_speed_v": "%s tok/s",
        "b3_c_speed_p": "อ่านพรอมต์ %s tok/s",
        "b3_c_speed_none": "ยังไม่มีข้อมูลความเร็วในช่วงนี้",
        "b3_c_proj": "โปรเจกต์ที่ใช้มากที่สุด",
        "b3_c_proj_s": "โทเค็นรวมในช่วงนี้",
        "b3_c_proj_none": "ยังไม่มีข้อมูลแยกตามโปรเจกต์",
        "b3_other": "อื่นๆ",
        "b3_unknown_model": "ไม่ระบุโมเดล",
        "b3_total": "รวม",
        "b3_total_v": "รวม %s",
        "b3_no_use_day": "ไม่มีการใช้งาน",
        "b3_aria_total": "%1 วัน รวม %2 โทเค็น",
        "b3_table": "ดูเป็นตาราง",
        "b3_chart_keys": "กดลูกศรซ้ายหรือขวาเพื่อดูค่าทีละวัน",
        "b3_day": "วัน",
        "b3_recent": "คำขอล่าสุด",
        "b3_recent_s": "%s รายการล่าสุด",
        "b3_recent_none": "ยังไม่มีรายการ",
        "b3_col_time": "เวลา",
        "b3_col_project": "โปรเจกต์",
        "b3_col_model": "โมเดล",
        "b3_col_prompt": "พรอมต์",
        "b3_col_prompt_c": "พรอมต์ (แคช)",
        "b3_col_reply": "คำตอบ",
        "b3_col_wall": "ใช้เวลา",
        "b3_col_note": "เครื่องมือ / หมายเหตุ",
        "b3_flag_compacted": "สรุปแล้ว",
        "b3_flag_compacted_n": "สรุปแล้ว %s รอบ",
        "b3_flag_error": "ผิดพลาด",
        "b3_rc_cached": "แคช %s",
        "b3_req_unit": "%s คำขอ",
        "b3_proj_tip": "พรอมต์ %1 · คำตอบ %2 · %3 คำขอ",
        "b3_u_ms": "%s ms",
        "b3_u_s": "%s วิ",
        "b3_u_min": "%s นาที",
        "b3_u_h": "%s ชม.",
        "b3_doc_title": "ตรวจระบบ",
        "b3_doc_sub": "สถานะของบริการทุกตัวในเครื่องนี้ พร้อมวิธีแก้เมื่อมีอะไรผิดปกติ — ไม่แสดงค่าของคีย์หรือโทเค็น บอกแค่ว่ามีไฟล์หรือไม่",
        "b3_doc_recheck": "ตรวจใหม่",
        "b3_doc_copy": "คัดลอกรายงาน",
        "b3_doc_copied": "คัดลอกรายงานแล้ว (ซ่อนโทเค็นและคีย์ไว้แล้ว)",
        "b3_doc_copied_short": "คัดลอกแล้ว",
        "b3_doc_copy_fail": "คัดลอกอัตโนมัติไม่ได้ — เลือกข้อความในกล่องแล้วกด Ctrl+C",
        "b3_doc_checking": "กำลังตรวจระบบ…",
        "b3_doc_ok_all": "ทุกบริการทำงานปกติ",
        "b3_doc_issues": "พบปัญหา %s รายการ",
        "b3_doc_checked": "ตรวจเมื่อ %1 · ใช้เวลา %2",
        "b3_doc_checked_at": "ตรวจเมื่อ %s",
        "b3_doc_fixes": "วิธีแก้ที่แนะนำ",
        "b3_doc_svc": "บริการ",
        "b3_doc_nosvc": "hub ไม่ได้ส่งรายการบริการมา",
        "b3_doc_col_svc": "บริการ",
        "b3_doc_col_state": "สถานะ",
        "b3_doc_col_lat": "เวลาตอบ",
        "b3_doc_col_detail": "รายละเอียด",
        "b3_st_ok": "ปกติ",
        "b3_st_warn": "ควรตรวจดู",
        "b3_st_bad": "ไม่ทำงาน",
        "b3_st_off": "ปิดอยู่",
        "b3_port": "พอร์ต %s",
        "b3_loaded": "โหลดอยู่: %s",
        "b3_noloaded": "ยังไม่ได้โหลดโมเดล (โหลดเองเมื่อเริ่มแชต)",
        "b3_heartbeat": "สัญญาณล่าสุด %sที่แล้ว",
        "b3_ports_ok": "พอร์ตตอบ %1 จาก %2",
        "b3_svc_router": "เซิร์ฟเวอร์โมเดล (llama.cpp)",
        "b3_svc_mcp": "เครื่องมือในเครื่อง (MCP)",
        "b3_svc_web": "ค้นเว็บ (MCP)",
        "b3_svc_embed": "ค้นตามความหมาย (embedding)",
        "b3_svc_stt": "ถอดเสียง (พูดแทนพิมพ์)",
        "b3_svc_sched": "ตัวตั้งเวลางาน",
        "b3_svc_gateway": "เกตเวย์",
        "b3_svc_hub": "hub และพอร์ตโปรเจกต์",
        "b3_doc_machine": "เครื่อง",
        "b3_doc_driver": "ไดรเวอร์ %s",
        "b3_doc_util": "ใช้งาน %s%",
        "b3_doc_ram": "แรม",
        "b3_doc_commit": "หน่วยความจำ commit",
        "b3_doc_commit_hint": "แรม + pagefile ที่โปรแกรมยังจองได้",
        "b3_doc_disk": "ดิสก์ %s",
        "b3_doc_free_of": "ว่าง %1 จาก %2",
        "b3_doc_free": "ว่าง %s",
        "b3_doc_low": "เหลือน้อย",
        "b3_doc_disk_missing": "ไม่พบไดรฟ์นี้",
        "b3_doc_nogpu": "ไม่พบ GPU",
        "b3_doc_soft": "ซอฟต์แวร์และคีย์",
        "b3_doc_os": "ระบบปฏิบัติการ",
        "b3_doc_models": "ไฟล์โมเดล",
        "b3_doc_keys": "ไฟล์คีย์และโทเค็น",
        "b3_doc_present": "มี",
        "b3_doc_missing": "ไม่มี",
        "b3_doc_brave": "คีย์ Brave Search",
        "b3_doc_usable": "ใช้ได้",
        "b3_doc_unusable": "ใช้ไม่ได้",
        "b3_doc_tests": "ชุดทดสอบล่าสุด",
        "b3_doc_tests_v": "ผ่าน %1 · ข้าม %2 · ไม่ผ่าน %3",
        "b3_doc_notests": "ยังไม่มีบันทึกผล",
        "b3_doc_errors": "ข้อผิดพลาดล่าสุดใน log",
        "b3_doc_errors_n": "%s บรรทัด (ซ่อนโทเค็นแล้ว)",
        "b3_doc_noerr": "ไม่พบข้อผิดพลาดใน log",
        "b3_doc_other": "ข้อมูลอื่นจาก hub",
        "b3_doc_report_h": "รายงานตรวจระบบ Qwen3.8",
        # รายละเอียดต่อบริการที่ hub_doctor ส่งมา (keep_awake, provider ของค้นเว็บ, อุปกรณ์ของ STT, gateway, โมดูล MCP)
        "b3_busy": "กำลังตอบอยู่ %s แชต",
        "b3_provider": "ผู้ให้บริการ: %s",
        "b3_device": "รันบน %s",
        "b3_gw_noup": "ต่อเซิร์ฟเวอร์โมเดลไม่ได้",
        "b3_mod_failed": "โมดูลที่โหลดไม่ขึ้น: %s",
        "b3_doc_gpu_err": "ตรวจ GPU ไม่ได้ (%s)",
        "b3_doc_ok_tips": "ทุกบริการทำงานปกติ · มีคำแนะนำ %s ข้อ",
        # คำสถานะเฉพาะของ hub_doctor (หน้าใช้เมื่อมีคำแปล ไม่งั้นใช้คำของกลุ่ม ปกติ/ควรตรวจดู/ไม่ทำงาน)
        "b3_st_down": "ไม่ทำงาน",
        "b3_st_auth": "โทเค็นไม่ตรง",
        "b3_st_loading": "กำลังโหลด",
        "b3_st_missing": "ไม่พบไฟล์",
        "b3_st_absent": "ไม่มีไฟล์โมเดล",
        "b3_st_stale": "ไม่มีสัญญาณล่าสุด",
        "b3_st_timeout": "ตรวจไม่ทัน",
        "b3_st_error": "ตรวจไม่ได้",
        # ชื่อไฟล์คีย์ที่ hub_doctor รายงาน (มี/ไม่มี เท่านั้น)
        "b3_key_local_token": "โทเค็นของบริการในเครื่อง",
        "b3_key_brave_key": "คีย์ Brave Search",
        "b3_key_gateway_key": "คีย์ของเกตเวย์",
    },
    "en": {
        "sidebar": "Sidebar",
        "newchat": "New chat",
        "searchchats": "Search chats",
        "searchph": "Search titles and messages…",
        "searching": "Searching…",
        "recents": "Recents",
        "results": "Results",
        "noresults": "No matching chats",
        "norecents": "No chats yet. Start a new one.",
        "untitled": "Untitled chat",
        "chat_options": "Chat options",
        "proj_options": "Project options",
        "rename_chat": "Rename chat",
        "delete_chat": "Delete chat",
        "delchat_title": "Delete this chat?",
        "delchat_body": "“%s” and all of its messages will be permanently deleted. This can't be undone.",
        "chat_renamed": "Chat renamed",
        "chat_deleted": "Chat deleted",
        "rename_project": "Rename project",
        "delete_project": "Delete project",
        "delproj_title": "Delete this project?",
        "delproj_body": "“%s” will be removed and its port closed. Its files move to the _trash folder (not deleted); chat history in the browser is kept.",
        "cant_delete_last": "At least one project must remain",
        "delfile_title": "Delete this file?",
        "delete_btn": "Delete",
        "cancel": "Cancel",
        "save": "Save",
        "saving": "Saving…",
        "saved": "Saved",
        "unsaved": "Unsaved changes",
        "save_hint": "Ctrl+Enter to save",
        "ok": "OK",
        "close": "Close",
        "open_sidebar": "Open sidebar",
        "project": "Project",
        "project_btn": "Project",
        "project_settings": "Project settings",
        "instructions": "Project instructions",
        "instructions_hint": "Applied to every new chat in this project: reply language, tone, or background the model should know.",
        "instructions_ph": "e.g. Answer concisely and cite standards where relevant",
        "instr_saved": "Instructions saved — applies to new chats",
        "knowledge": "Knowledge",
        "dropfiles": "Drop files here or click to browse",
        "copydir": "Copy folder path",
        "settings": "Settings",
        "default_model": "Default model",
        "default_model_hint": "Used when this project's chat opens. Switch per chat from the model button in the composer.",
        "model_saved": "Default model saved — used for new chats",
        "think_off_h": "Answers directly, fastest",
        "think_on_h": "Reasons first — slower, better on hard problems",
        "think_auto_h": "Follows the model's own default",
        "manage_all": "Manage all projects",
        "local_account": "This computer",
        "account_menu": "Settings and status",
        "theme": "Theme",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "theme_system": "System",
        "font": "Reply font",
        "font_serif": "Serif",
        "font_sans": "Sans",
        "language": "Language",
        "webui_settings": "Chat settings",
        "mcp_servers": "MCP servers",
        "manage_projects": "Manage projects",
        "nmodels": "%d models",
        "err_generic": "Something went wrong",
        "errlang": "Could not switch language",
        "errsave": "Could not save",
        "wait_streaming": "Wait for the reply to finish",
        "reload_deferred": "The chat will refresh once the reply finishes and the composer is empty",
        "not_ready_yet": "The chat is still loading — try again",
        "chat_frame": "Chat",
        "noinstr": "No custom instructions",
        "main_nav": "Main",
        "skip_composer": "Skip to message box",
        "row_keys_hint": "Up and Down arrows move; Right arrow or Shift+F10 opens options",
        "instr_conflict": "Changed elsewhere — saving will overwrite it",
        "err_retry": "something went wrong, please try again",
        "err_exists": "a project with this name already exists",
        "err_noport": "no free port left for a new project",
        "err_filesize": "files must be between 1 byte and 64 MB",
        "errmodel": "Could not set the default model",
        "errextend": "Could not change auto-continue",
        "lang_group": "Interface language",
        "lang_tip_th": "Switch to Thai (Alt+Shift+L)",
        "lang_tip_en": "Switch to English (Alt+Shift+L)",
        "lang_unsaved": "Save your project instructions first, then switch language",
        "gpu_changed_short": "GPU changed",
        "gpu_changed": "GPU setup changed — in the chat page, open “This computer” and choose “Use new GPU setup”",
        "gpu_where": "GPU per model",
        "gpu_as_started": "(as last started)",
        "gpu_found": "GPUs found",
        "gpu_none": "No GPU found — every model runs on the CPU",
        "gpu_failed_short": "GPU unknown",
        "gpu_failed": "GPU detection failed at launch — llama-server picks the GPUs when a model loads",
        "gpu_hidden": "llama-server can't see any GPU — every model runs on the CPU",
        "gpu_auto": "auto",
        "gpu_external": "external",
        "gpu_ctx": "%s context",
        "gpu_vision": "vision",
        "gpu_choose": "Choose GPU…",
        "gpu_edit": "Change",
        "gpu_use_new": "Use new GPU setup",
        "gpu_changed_menu": "The connected GPUs differ from the last start",
        "gpu_changed_btn": "GPU setup changed — open this menu and choose “Use new GPU setup”",
        "gpu_title": "Choose GPUs for models",
        "gpu_sub": "Pick which card each model runs on. If unsure, keep Auto: it plans around the GPUs connected when the models restart.",
        "gpu_devs_h": "Connected GPUs",
        "gpu_redetect": "Re-detect",
        "gpu_detecting": "Detecting…",
        "gpu_detecting_long": "Detecting connected GPUs…",
        "gpu_detect_fail": "Couldn't detect GPUs yet — only Auto or CPU can be chosen for now",
        "gpu_no_gpu": "No GPU found — only Auto or CPU can be chosen",
        "gpu_internal": "internal",
        "gpu_models_h": "Models",
        "gpu_no_models": "No models found yet",
        "gpu_primary": "Main",
        "gpu_opt_auto": "Auto (recommended)",
        "gpu_opt_cpu": "CPU only",
        "gpu_not_connected": "not connected",
        "gpu_fit_ok": "Fits fully on the GPU — uses ~%1 of %2 GB",
        "gpu_fit_ok_auto": "Fits fully on the GPU — uses ~%1 GB",
        "gpu_fit_spill": "Spills ~%1 GB to the CPU — slower",
        "gpu_fit_cpu": "Runs entirely on the CPU — slowest",
        "gpu_fit_auto": "Decided at restart from the connected GPUs",
        "gpu_fit_unknown": "The size this model needs is unknown",
        "gpu_fit_nodetect": "GPUs not detected yet, so the fit can't be estimated",
        "gpu_fit_64kv": "64K context + vision",
        "gpu_fit_64k": "64K context",
        "gpu_now": "Now: %s",
        "gpu_then": "At last start: %s",
        "gpu_now_chosen": "as chosen",
        "gpu_note_userini_dev": "models-preset.user.ini sets this model's device, which overrides the GPU chosen here",
        "gpu_note_userini_devauto": "models-preset.user.ini sets this model's GPU; it is used instead of Auto",
        "gpu_note_userini_opts": "models-preset.user.ini also sets context or vision for this model",
        "gpu_note_missing_now": "%s isn't connected now — a restart will use Auto instead",
        "gpu_note_missing_part": "%s isn't connected now — only the connected cards will be used",
        "gpu_note_missing_then": "The chosen GPU wasn't connected at the last start, so Auto was used",
        "gpu_note_dropped_then": "%s wasn't connected at the last start, so only the connected cards were used",
        "gpu_conflict": "%1 share %2: ~%3 GB together, more than its ~%4 GB. If both are loaded, the rest spills to the CPU.",
        "gpu_and": " and ",
        "gpu_stale_banner": "The connected GPUs changed since the last start — save and restart to use them",
        "gpu_reset": "Reset all to Auto",
        "gpu_reset_done": "All models set to Auto — save to apply",
        "gpu_apply": "Save and restart models",
        "gpu_confirm": "This restarts the model server and reloads any loaded models. If a chat is still answering, it waits for it first (up to 3 minutes).",
        "gpu_applying": "Restarting the model server…",
        "gpu_applying_hint": "You can close this window; it keeps going in the background",
        "gpu_elapsed": "%s elapsed",
        "gpu_done": "The new GPU setup is in use",
        "gpu_busy": "A chat was still answering, so nothing was restarted. Your choice is saved; try again when it finishes.",
        "gpu_apply_failed": "Restart failed. Your choice is saved; see the log below, or reopen Qwen3.8 from its icon.",
        "gpu_failed_toast": "Restart failed — open “Choose GPU…” again to see the log",
        "gpu_log": "Log (%s)",
        "gpu_loading": "Loading…",
        "gpu_retry": "Try again",
        "gpu_wait_stream": "Wait for the reply to finish, then restart",
        "gpu_err_load": "Could not load GPU info",
        "gpu_err_save": "Could not save the GPU choice",
        "gpu_err_invalid": "the choice is not valid; re-detect the GPUs and try again",
        "gpu_err_running": "A restart is already running — following it",
        "gpu_waiting": "Waiting for a reply to finish before restarting…",
        "gpu_done_same": "Nothing to change — this setup is already in use",
        "gpu_unknown": "The restart result is unknown. Your choice is saved; see gpu-apply.log.",
        "gpu_still_running": "That launcher run is still going — wait for it to finish, then try again",
        "gpu_saved_not_started": "Choice saved, but the restart could not be started",
        "gpu_err_busy_save": "A restart is already running elsewhere, so this choice is not saved yet. Wait for it to finish, then save again.",
        "gpu_fit_shared": "shares %s with the main model",
        "gpu_primary_desc": "Main model",
        # ---- round 4 (2026-09-30): memory K3 · outputs K2 · personalize K4 · notifications K5 · preview panel K7 · export K10
        "retry": "Try again",
        "mem_title": "Project memory",
        "mem_hint": "What Qwen remembers, added to every chat in this project (pinned first, then the newest that fit). Say “remember that…” in a chat, or add one here.",
        "mem_add": "Add",
        "mem_new": "New memory",
        "mem_ph": "e.g. EV150 chargers speak OCPP 1.6J and send a Heartbeat every 300 s",
        "mem_kind": "Type",
        "mem_k_fact": "Fact",
        "mem_k_decision": "Decision",
        "mem_k_requirement": "Requirement",
        "mem_k_progress": "Progress",
        "mem_k_todo": "To-do",
        "mem_pin": "Pin",
        "mem_unpin": "Unpin",
        "mem_pinned": "Pinned",
        "mem_pinned_tip": "Pinned — always added to chats",
        "mem_edit": "Edit",
        "mem_edit_label": "Edit memory",
        "mem_delete": "Delete",
        "mem_del_title": "Delete this memory?",
        "mem_del_body": "Qwen will no longer see “%s” in chats.",
        "mem_empty": "Nothing remembered yet — add one, or say “remember that…” in a chat.",
        "mem_unavail": "Memory isn't available yet — the hub needs to restart on the new version.",
        "mem_err_load": "Couldn't load memory",
        "mem_saved": "Memory saved — used from your next message",
        "mem_esc_again": "Not saved — press Esc again to discard this note",
        "mem_esc_edit": "Changes not saved — press Esc again to discard them",
        "mem_deleted": "Memory deleted",
        "mem_pinned_t": "Pinned — always added to chats",
        "mem_unpinned_t": "Unpinned",
        "mem_err_save": "Couldn't save the memory",
        "mem_show_all": "Show all (%s)",
        "mem_show_less": "Show less",
        "mem_more_text": "More",
        "mem_less_text": "Less",
        "mem_off": "not in chats",
        "mem_off_tip": "Over the memory space for chats — pin it to always include it",
        "mem_sum": "In chats: %1 of %2 · ~%3 / %4 tokens",
        "mem_broken": "memory.json is damaged and can't be read — it won't be overwritten until the file is fixed",
        "loading": "Loading…",
        "out_title": "Files Qwen made",
        "out_hint": "Reports, images and tables made in chats, kept in this project's outputs folder.",
        "out_open": "Open",
        "out_panel": "Open in panel",
        "pers_menu": "Personalize…",
        "pers_title": "Personalize",
        "pers_sub": "Applies to every chat in every project on this computer, starting with your next message.",
        "pers_about": "About you",
        "pers_about_h": "What Qwen should always know — your work, the tools you use daily, how much background to assume.",
        "pers_about_ph": "e.g. I'm an EV-charger engineer. I read OCPP logs and write Python every day, and I like technical detail.",
        "pers_style": "Response style",
        "pers_st_normal": "Normal",
        "pers_st_normal_d": "Balanced: direct, then helpful detail",
        "pers_st_concise": "Concise",
        "pers_st_concise_d": "Short and to the point",
        "pers_st_explanatory": "Explanatory",
        "pers_st_explanatory_d": "Reasons, context and steps",
        "pers_st_formal": "Formal",
        "pers_st_formal_d": "Polished, report-ready wording",
        "pers_st_learning": "Learning",
        "pers_st_learning_d": "Hints first, then the answer",
        "pers_st_custom": "Custom",
        "pers_st_custom_d": "Describe your own style",
        "pers_custom": "Your style",
        "pers_custom_ph": "e.g. Use bullet points, always include units, end with a one-line summary",
        "pers_preview": "Sample reply",
        "pers_pv_q": "Why does a charger report Faulted?",
        "pers_pv_normal": "The charger detected a fault that stops it from delivering power — a ground fault, over-temperature or lost communication with the car. Start with the errorCode in StatusNotification and follow that code.",
        "pers_pv_concise": "It detected a fault — check errorCode in StatusNotification.",
        "pers_pv_explanatory": "Faulted means the charger stopped because it found a problem.\n1. Read errorCode in the latest StatusNotification — it names the category.\n2. Line it up with the charging log: during a session or while idle?\n3. For GroundFailure, check the earthing first — it's a safety issue.",
        "pers_pv_formal": "A Faulted status indicates that the charger has detected an abnormal condition that prevents service. It is recommended to review the errorCode in the StatusNotification message to determine the cause.",
        "pers_pv_learning": "First, which message does the charger send when its status changes? Hint: one field names the kind of problem. Find it, tell me its value, and we'll trace it together.",
        "pers_pv_custom": "Replies will follow the style you describe above.",
        "pers_privacy": "Stored only on this computer (the hub's settings.json) and added to the instructions of every chat.",
        "pers_saved": "Saved — applies from your next message",
        "pers_unsupported": "The running hub doesn't support these settings yet — restart the hub first.",
        "pers_err_load": "Couldn't load your settings",
        "pers_need_custom": "Describe your style before saving",
        "pers_esc_again": "Not saved — press Esc again to close without saving",
        "notify": "Notifications",
        "ntf_off": "Off",
        "ntf_on": "On",
        "ntf_sound": "Sound",
        "ntf_denied": "Notifications are blocked for this page — allow them from the icon beside the address bar",
        "ntf_not_granted": "Notification permission wasn't granted",
        "ntf_unsupported": "This browser can't show notifications",
        "ntf_enabled": "You'll be notified when this tab is hidden and Qwen finishes or needs you",
        "ntf_off_t": "Notifications off",
        "ntf_blocked": "Turned on, but the browser blocks notifications for this page — allow them from the icon beside the address bar",
        "ntf_ask_again": "Turned on, but the browser hasn't allowed it yet — choose On again to ask",
        "ntf_done": "Qwen finished replying",
        "ntf_perm": "Qwen needs permission to use a tool",
        "ntf_cont": "Qwen is waiting for you to continue",
        "ntf_generic": "Qwen needs your attention",
        "art_region": "Preview panel",
        "art_view": "View",
        "art_preview": "Preview",
        "art_code": "Code",
        "art_copy": "Copy",
        "art_download": "Download",
        "art_close": "Close panel",
        "art_prev": "Previous version",
        "art_next": "Next version",
        "art_versions": "Versions",
        "art_ver": "Version %1 of %2",
        "art_resize": "Resize panel",
        "art_list": "Other items on this page",
        "art_k_html": "HTML",
        "art_k_svg": "SVG",
        "art_k_mermaid": "Diagram",
        "art_k_markdown": "Document",
        "art_k_csv": "Table",
        "art_k_image": "Image",
        "art_sandbox": "Shown in an isolated frame — no network, no access to this page",
        "art_mermaid_na": "Can't draw this diagram yet — wait for it to render in the chat, then choose “Open in panel” again.",
        "art_rows": "Showing %1 of %2 rows",
        "art_bad": "Can't open this in the panel — unsupported type or content",
        "art_too_big": "Too large to show in the panel (over 2 MB)",
        "art_opened": "Opened “%s” in the panel",
        "art_js_off_note": "Scripts in this page are off — a page running scripts can send data off this computer. Run them only if you trust the content.",
        "art_js_on_note": "Scripts are running — this page can still take the panel to another site, with data.",
        "art_js_left": "This page tried to take the panel to another address, so it was brought back with scripts off. Data in that address may already have been sent.",
        "art_js_run": "Run scripts",
        "art_js_stop": "Stop scripts",
        "art_js_on": "Scripts on for this page",
        "art_js_off": "Scripts off for this page",
        "art_frame": "Rendered %s",
        "art_img_err": "Couldn't load the image",
        "exp_md": "Export Markdown",
        "exp_html": "Export HTML",
        "exp_pdf": "Export PDF (print)",
        "exp_done": "Exported: %s",
        "exp_err": "Couldn't export",
        "exp_empty": "This chat has no messages yet",
        "exp_print_opened": "Opened a print view in a new tab — choose “Save as PDF” (if no tab appears, allow pop-ups for this page)",
        "exp_print_hint": "If the print dialog doesn't open by itself, press Ctrl+P and choose “Save as PDF”.",
        "exp_you": "You",
        "exp_reasoning": "Reasoning",
        "exp_tool": "Tool",
        "exp_args": "Arguments",
        "exp_result": "Result",
        "exp_no_result": "(no result)",
        "exp_attach": "Attachments",
        "exp_meta": "Exported from Qwen3.8 · project %1 · %2",
        "exp_cut": "… (trimmed to %1 of %2 characters)",
        # ---- batch 2a (B5): services of this computer (account menu) + research jobs (project panel)
        "svc_head": "Services",
        "svc_embed": "Semantic document search",
        "svc_research": "Deep research",
        "svc_web": "Web search",
        "svc_ok": "Ready",
        "svc_loading": "Loading…",
        "svc_down": "Not running",
        "svc_embed_down": "Off — keyword search only",
        "svc_embed_absent": "No model — keyword search only",
        "svc_res_running": "%s running",
        "svc_res_missing": "Not installed",
        "svc_res_broken": "Failed to load (see the MCP log)",
        "svc_res_down": "MCP not running",
        "svc_auth": "Token mismatch — restart Qwen3.8",
        "svc_web_builtin": "Basic",
        "svc_web_hint": "Wikipedia + DuckDuckGo only, so results are limited — add a Brave Search key for better results",
        "res_title": "Research",
        "res_new": "New research",
        "res_hint": "Qwen searches the web, reads the sources and writes a cited report into this project's files. It runs in the background — you can close this page.",
        "res_prefill": "Do deep research and write a cited report on: ",
        "res_empty": "No research yet — press “New research”, or ask in chat: “Do deep research on …”",
        "res_unavail": "Available after the hub restarts (stop everything with stop-qwen38.ps1, then open Qwen3.8 from its icon)",
        "res_err_load": "Couldn't load research jobs",
        "res_svc_note": "Deep research isn't ready: %s",
        "res_noq": "(no topic)",
        "res_st_queued": "Queued",
        "res_st_running": "Researching",
        "res_st_cancelling": "Stopping…",
        "res_st_done": "Done",
        "res_st_failed": "Failed",
        "res_st_cancelled": "Stopped",
        "res_st_interrupted": "Interrupted",
        "res_st_unknown": "Unknown status",
        "res_ph_plan": "Planning sub-questions",
        "res_ph_search": "Searching the web",
        "res_ph_pick": "Choosing sources",
        "res_ph_read": "Reading sources",
        "res_ph_notes": "Taking notes",
        "res_ph_write": "Writing the report",
        "res_ph_save": "Saving files",
        "res_ph_done": "Done",
        "res_depth_quick": "Quick",
        "res_depth_standard": "Standard",
        "res_read": "%s sources read",
        "res_read_of": "%1 of %2 sources read",
        "res_eta": "about %s left",
        "res_min": "%s min",
        "res_hr_min": "%1 h %2 min",
        "res_stale": "No progress for a while — may be stuck",
        "res_progress": "Progress",
        "res_open": "Open report",
        "res_docx": "Word (.docx)",
        "res_cancel": "Stop",
        "res_cancel_title": "Stop this research?",
        "res_cancel_body": "Qwen will stop researching “%s”. What it found so far may not become a report.",
        "res_cancel_ok": "Stop research",
        "res_cancel_keep": "Keep going",
        "res_cancel_sent": "Stop requested — the job stops after its current step",
        "res_cancel_err": "Couldn't stop the research",
        "res_not_running": "This job has already finished",
        "res_done_title": "Research finished",
        "res_done_t": "Research finished: %s",
        "res_failed_t": "Research failed: %s",
        "res_intr_t": "Research was interrupted (the MCP restarted) — you can start it again: %s",
        # ---- batch 2b (C4, owner ui): automatic project-file search (project panel) + voice input (services)
        "autokb": "Search project files automatically",
        "autokb_hint": "Before Qwen answers, passages related to your message are found in this project's files and given to Qwen. Everything stays on this computer. Tip: type @ in the message box to pick a file yourself.",
        "autokb_on": "Automatic file search is on",
        "autokb_off": "Automatic file search is off",
        "autokb_unsupported": "The running hub doesn't support automatic file search yet — open Qwen3.8 again from its icon, then try again",
        "errautokb": "Could not change automatic file search",
        "svc_stt": "Voice input",
        "svc_stt_dev": "Ready (%s)",
        "svc_stt_hint": "Open Qwen3.8 again from its icon to start the speech service",
        # ---- batch 3 (D4, owner ui): Usage / Doctor tabs on the manage page + links in the account menu
        "b3_menu_usage": "Usage",
        "b3_menu_doctor": "Doctor",
        "b3_tabs": "Page sections",
        "b3_tab_projects": "Projects",
        "b3_tab_usage": "Usage",
        "b3_tab_doctor": "Doctor",
        "b3_use_title": "Usage",
        "b3_use_sub": "Statistics for chat requests that went through the hub on this computer. Only numbers are kept (tokens, speed, time, tool names), never the messages.",
        "b3_use_range": "Time range",
        "b3_use_7d": "7 days",
        "b3_use_30d": "30 days",
        "b3_use_updated": "Updated %s",
        "b3_loading": "Loading…",
        "b3_use_empty": "No usage in this period yet. Chat with Qwen for a while, then come back.",
        "b3_unsupported": "The running hub doesn't provide this yet. Open Qwen3.8 again from its icon to start the updated hub.",
        "b3_retry": "Try again",
        "b3_t_tokens": "Total tokens",
        "b3_t_tokens_s": "Prompt %1 · reply %2",
        "b3_t_req": "Requests",
        "b3_t_req_s": "Errors %1 · compacted %2",
        "b3_t_cache": "Prompt from cache",
        "b3_t_cache_s": "%s tokens reused",
        "b3_t_time": "Model time",
        "b3_t_time_s": "%s per request on average",
        "b3_c_tokens": "Tokens per day by model",
        "b3_c_tokens_s": "Prompt + reply",
        "b3_c_speed": "Reply speed",
        "b3_c_speed_s": "Tokens per second, daily average. Each model has its own scale.",
        "b3_c_speed_v": "%s tok/s",
        "b3_c_speed_p": "Prompt %s tok/s",
        "b3_c_speed_none": "No speed data in this period yet",
        "b3_c_proj": "Top projects",
        "b3_c_proj_s": "Total tokens in this period",
        "b3_c_proj_none": "No per-project data yet",
        "b3_other": "Other",
        "b3_unknown_model": "Unknown model",
        "b3_total": "Total",
        "b3_total_v": "Total %s",
        "b3_no_use_day": "No usage",
        "b3_aria_total": "%1 days, %2 tokens in total",
        "b3_table": "Show as table",
        "b3_chart_keys": "Use the left and right arrow keys to step through the days",
        "b3_day": "Day",
        "b3_recent": "Recent requests",
        "b3_recent_s": "Latest %s",
        "b3_recent_none": "Nothing yet",
        "b3_col_time": "Time",
        "b3_col_project": "Project",
        "b3_col_model": "Model",
        "b3_col_prompt": "Prompt",
        "b3_col_prompt_c": "Prompt (cached)",
        "b3_col_reply": "Reply",
        "b3_col_wall": "Took",
        "b3_col_note": "Tools / notes",
        "b3_flag_compacted": "Compacted",
        "b3_flag_compacted_n": "Compacted · %s turns",
        "b3_flag_error": "Error",
        "b3_rc_cached": "%s cached",
        "b3_req_unit": "%s requests",
        "b3_proj_tip": "prompt %1 · reply %2 · %3 requests",
        "b3_u_ms": "%s ms",
        "b3_u_s": "%s s",
        "b3_u_min": "%s min",
        "b3_u_h": "%s h",
        "b3_doc_title": "Doctor",
        "b3_doc_sub": "Health of every service on this computer, with a suggested fix when something is wrong. Keys and tokens are never shown, only whether the file exists.",
        "b3_doc_recheck": "Check again",
        "b3_doc_copy": "Copy report",
        "b3_doc_copied": "Report copied (tokens and keys removed)",
        "b3_doc_copied_short": "Copied",
        "b3_doc_copy_fail": "Couldn't copy automatically. Select the text in the box, then press Ctrl+C.",
        "b3_doc_checking": "Checking the system…",
        "b3_doc_ok_all": "Everything is running",
        "b3_doc_issues": "Issues found: %s",
        "b3_doc_checked": "Checked %1 · took %2",
        "b3_doc_checked_at": "Checked %s",
        "b3_doc_fixes": "Suggested fixes",
        "b3_doc_svc": "Services",
        "b3_doc_nosvc": "The hub didn't report any services",
        "b3_doc_col_svc": "Service",
        "b3_doc_col_state": "Status",
        "b3_doc_col_lat": "Response",
        "b3_doc_col_detail": "Details",
        "b3_st_ok": "Running",
        "b3_st_warn": "Check",
        "b3_st_bad": "Down",
        "b3_st_off": "Off",
        "b3_port": "port %s",
        "b3_loaded": "Loaded: %s",
        "b3_noloaded": "No model loaded (one loads when a chat starts)",
        "b3_heartbeat": "Last heartbeat %s ago",
        "b3_ports_ok": "%1 of %2 ports answering",
        "b3_svc_router": "Model server (llama.cpp)",
        "b3_svc_mcp": "Local tools (MCP)",
        "b3_svc_web": "Web search (MCP)",
        "b3_svc_embed": "Semantic search (embedding)",
        "b3_svc_stt": "Speech to text (voice input)",
        "b3_svc_sched": "Task scheduler",
        "b3_svc_gateway": "Gateway",
        "b3_svc_hub": "Hub and project ports",
        "b3_doc_machine": "Machine",
        "b3_doc_driver": "Driver %s",
        "b3_doc_util": "%s% busy",
        "b3_doc_ram": "RAM",
        "b3_doc_commit": "Commit memory",
        "b3_doc_commit_hint": "RAM + page file that programs can still reserve",
        "b3_doc_disk": "Disk %s",
        "b3_doc_free_of": "%1 free of %2",
        "b3_doc_free": "%s free",
        "b3_doc_low": "Low",
        "b3_doc_disk_missing": "Drive not found",
        "b3_doc_nogpu": "No GPU found",
        "b3_doc_soft": "Software and keys",
        "b3_doc_os": "Operating system",
        "b3_doc_models": "Model files",
        "b3_doc_keys": "Key and token files",
        "b3_doc_present": "Present",
        "b3_doc_missing": "Missing",
        "b3_doc_brave": "Brave Search key",
        "b3_doc_usable": "Usable",
        "b3_doc_unusable": "Not usable",
        "b3_doc_tests": "Last test run",
        "b3_doc_tests_v": "%1 passed · %2 skipped · %3 failed",
        "b3_doc_notests": "No result recorded",
        "b3_doc_errors": "Recent errors in the logs",
        "b3_doc_errors_n": "%s lines (tokens removed)",
        "b3_doc_noerr": "No errors in the logs",
        "b3_doc_other": "Other details from the hub",
        "b3_doc_report_h": "Qwen3.8 doctor report",
        "b3_busy": "Replies in progress: %s",
        "b3_provider": "Provider: %s",
        "b3_device": "Running on %s",
        "b3_gw_noup": "Can't reach the model server",
        "b3_mod_failed": "Modules that failed to load: %s",
        "b3_doc_gpu_err": "Couldn't check the GPU (%s)",
        "b3_doc_ok_tips": "Everything is running · suggestions: %s",
        "b3_st_down": "Down",
        "b3_st_auth": "Token rejected",
        "b3_st_loading": "Loading",
        "b3_st_missing": "File missing",
        "b3_st_absent": "Model file missing",
        "b3_st_stale": "No recent heartbeat",
        "b3_st_timeout": "Timed out",
        "b3_st_error": "Check failed",
        "b3_key_local_token": "Local services token",
        "b3_key_brave_key": "Brave Search key",
        "b3_key_gateway_key": "Gateway key",
    },
}


# --------------------------------------------------------------------------
# glue() ของ SHELL และ PAGE — เขียนที่เดียวแล้วแทน __QW_GLUE__ ในทั้งสองเทมเพลตตอนโหลดโมดูล
# คำทับศัพท์ที่พจนานุกรมตัดคำไทยของเบราว์เซอร์ไม่รู้จัก ถูกตัดกลางคำตอนขึ้นบรรทัดใหม่
# (เห็นจริงที่ 390px: คำอธิบายไฟล์ในแผงโปรเจกต์ "…ของโปรเจ|กต์นี้", และ "แช|ต", "พร|อมต์", "โท|เค็น")
# ใส่ U+2060 (word joiner) ระหว่างตัวอักษรของคำเหล่านี้ ยกเว้นหน้าสระ/วรรณยุกต์ที่ซ้อนบน-ล่าง
# (แยกออกจากพยัญชนะแล้วจะวาดเป็นวงกลมประ) — เทคนิคและรายการคำชุดเดียวกับ glue() ใน webui-enhance.js
# ใช้กับข้อความของเราเท่านั้น ชื่อแชต/โปรเจกต์/ไฟล์ที่ผู้ใช้ตั้งต้องคงตัวอักษรเดิม (คัดลอก/ค้นหาแล้วตรง)
# --------------------------------------------------------------------------
_GLUE_WORDS = ("โทเค็น", "พรอมต์", "เอเจนต์", "เซิร์ฟเวอร์", "อาร์กิวเมนต์", "เอาต์พุต", "อินพุต",
               "ไดนามิก", "เอนโทรปี", "แคช", "สวิตช์", "เวอร์ชัน", "บิลด์", "เรนเดอร์", "รีเซ็ต", "รีเฟรช",
               "พร็อกซี", "ไบนารี", "เทมเพลต", "โปรโตคอล", "เฟรมเวิร์ก", "ไลบรารี", "คลิปบอร์ด", "เดสก์ท็อป",
               "ไมโครโฟน", "พิกเซล", "ซอร์ส", "แฟล็ก", "ไบต์", "โปรเจกต์", "เบราว์เซอร์", "อัปโหลด",
               "ดาวน์โหลด", "อัปเดต", "แท็บ", "แท็ก", "พารามิเตอร์", "ไฟล์", "โมเดล", "แชต",
               # คำของหน้าเราเอง (ไม่มีในหน้าแชต)
               "พอร์ต", "โฟลเดอร์", "ดิสก์", "ฟอนต์", "ไอคอน", "รีสตาร์ต", "การ์ด",
               # รอบ 4 (แจ้งเตือน/ส่งออก)
               "ป๊อปอัป")
_GLUE_JS = r"""/* คำทับศัพท์ถูกตัดกลางคำตอนขึ้นบรรทัดใหม่ ("โปรเจ|กต์") — ใส่ U+2060 ระหว่างตัวอักษร (ดู _GLUE_WORDS ใน hub_i18n_parts.py) */
var GLUE_RE = new RegExp(__WORDS__.join('|'), 'g');
function glue(s) {
  return String(s).replace(GLUE_RE, function (w) { return w.replace(/(.)(?=[^\u0e31\u0e34-\u0e3a\u0e47-\u0e4e])/g, '$1\u2060'); });
}
/* ภาษาอังกฤษไม่มีคำเหล่านี้ — คืนสำเนาเดิม ไม่ต้องไล่ทุกข้อความ */
function glueAll(src) {
  var o = {};
  Object.keys(src || {}).forEach(function (k) { o[k] = LANG === 'th' && typeof src[k] === 'string' ? glue(src[k]) : src[k]; });
  return o;
}
/* ข้อความที่เซิร์ฟเวอร์เติมลง HTML โดยตรง (ไม่ผ่าน t()) — เรียกเฉพาะกับกล่องที่มีแต่ข้อความของเรา */
function glueText(nodes) {
  if (LANG !== 'th') return;
  [].forEach.call(nodes, function (root) {
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), n;
    while ((n = w.nextNode())) { var g = glue(n.nodeValue); if (g !== n.nodeValue) n.nodeValue = g; }
  });
}"""


# --------------------------------------------------------------------------
# GPU ที่โมเดลใช้ — ตัวช่วยชุดเดียวของ SHELL และ PAGE (แทน __QW_GPU__ ตอนโหลดโมดูล แบบเดียวกับ glue)
# ข้อมูลคือ d.gpu จาก /api/projects (hub.py gpu_status() อ่าน gpu-profile.json ที่ตัวเปิดเขียนตอนเปิด Qwen3.8)
# null = ไม่มีไฟล์ → ทุกฟังก์ชันคืน '' หน้าจอเหมือนก่อนมีฟีเจอร์นี้ทุกอย่าง
# ใช้ t() ของหน้านั้นๆ (ประกาศทีหลังได้ เพราะเรียกตอนทำงาน ไม่ใช่ตอนโหลดสคริปต์)
# --------------------------------------------------------------------------
_GPU_JS = r"""/* ชื่อการ์ดต่อกันด้วย " + " — แบบสั้น (full=false) ตัด "RTX " ซ้ำของใบที่สองเป็นต้นไป ("RTX 4090 + 4060 Ti")
   ให้พอดีบรรทัดเดียวในแถบข้าง ชื่อเต็มอยู่ในป้ายชื่อ/title  ไม่มีการ์ดเลย = CPU (ทั้งสองภาษาเรียกแบบนี้) */
function gpuJoin(list, full) {
  list = list || [];
  if (!list.length) return 'CPU';
  var rtx = !full && /^RTX /.test(list[0]);
  return list.map(function (s, i) { s = String(s); return i && rtx ? s.replace(/^RTX /, '') : s; }).join(' + ');
}
/* โมเดลที่ใส่ VRAM ไม่หมดมีบางชั้นอยู่บน CPU (ช้ากว่ามาก) — บอกไว้ท้ายชื่อการ์ด
   devices_short = null (ไม่ใช่ []) = ไม่ได้ระบุ GPU ไว้ (ตรวจ GPU ตอนเปิดไม่สำเร็จ) -fit เลือกเองตอนโหลด
   ห้ามเขียนว่า CPU เพราะถ้ามีการ์ดอยู่ llama-server ก็ใช้การ์ดนั้น */
function gpuDev(p, full) {
  var l = p.devices_short;
  if (!l) return t('gpu_auto');
  return gpuJoin(l, full) + (l.length && p.fits_fully === false ? ' + CPU' : '');
}
/* "RTX 4090 24 GB (ต่อภายนอก)" — ตัวเลข VRAM ปัดเป็น GB เต็มแบบที่เขียนบนกล่องการ์ด (6140 MiB = 6 GB) */
function gpuDevName(x) {
  return x.short + (x.total_gib ? ' ' + Math.round(x.total_gib) + ' GB' : '') + (x.external ? ' (' + t('gpu_external') + ')' : '');
}
/* รายการการ์ดว่างแปลได้สามแบบตาม g.detect (hub.py gpu_status): ไม่มี GPU จริง / ตรวจไม่สำเร็จ
   (-fit ยังใช้ GPU ที่มีได้) / llama-server มองไม่เห็นการ์ดที่ nvidia-smi เห็น — "ไม่พบ GPU" ถูกแค่แบบแรก */
function gpuNoDev(g) {
  return t(g.detect === 'failed' ? 'gpu_failed' : g.detect === 'hidden' ? 'gpu_hidden' : 'gpu_none');
}
function gpuDevs(g) {
  var d = g.devices || [];
  return d.length ? t('gpu_found') + ': ' + d.map(gpuDevName).join(', ') : gpuNoDev(g);
}
function gpuCtx(n) { return n >= 1024 ? Math.round(n / 1024) + 'K' : String(n); }
/* บรรทัดเต็มของแต่ละโมเดล: "Qwen3.8-27B: RTX 4090 · บริบท 64K · รองรับภาพ" */
function gpuLine(p) {
  return p.label + ': ' + gpuDev(p, true) + (p.ctx ? ' · ' + t('gpu_ctx').replace('%s', gpuCtx(p.ctx)) : '') +
    (p.vision ? ' · ' + t('gpu_vision') : '');
}
/* ป้ายสั้นท้ายสถานะ: การ์ดของโมเดลหลัก หรือ "GPU เปลี่ยน" เมื่อ GPU ที่ต่ออยู่ไม่ตรงกับตอนเปิดครั้งล่าสุด
   tight = แถบข้าง (กว้างราว 190px ต่อจาก "เครื่องนี้"): หลายใบเหลือใบหลัก + จำนวนที่เหลือ ("RTX 4060 Ti +1")
   แทนการถูกตัด … กลางชื่อใบที่สอง — ชื่อเต็มทุกใบอยู่ในเมนูที่เปิดจากปุ่มเดียวกัน */
function gpuShort(g, tight) {
  if (!g) return '';
  if (g.stale) return t('gpu_changed_short');
  if (g.detect === 'failed') return t('gpu_failed_short');
  if (!g.primary) return '';
  var l = g.primary.devices_short;
  if (!l) return t('gpu_auto');
  return tight && l.length > 1 ? l[0] + ' +' + (l.length - 1) : gpuJoin(l);
}
/* ข้อความเต็มหลายบรรทัด (title ของป้ายสถานะในหน้าจัดการ) */
function gpuTip(g) {
  if (!g) return '';
  var lines = (g.placement || []).map(gpuLine);
  lines.push(gpuDevs(g));
  if (g.stale) lines.unshift(t('gpu_changed'), '');
  return lines.join('\n');
}"""


def _inject_glue(tpl):
    import json
    js = _GLUE_JS.replace("__WORDS__", json.dumps(list(_GLUE_WORDS), ensure_ascii=False))
    assert tpl.count("__QW_GLUE__") == 1 and tpl.count("__QW_GPU__") == 1
    return tpl.replace("__QW_GLUE__", js).replace("__QW_GPU__", _GPU_JS)


SHELL = _inject_glue(SHELL)
PAGE = _inject_glue(PAGE)


# --------------------------------------------------------------------------
# รอบ 4 (2026-09-30) — ฟังก์ชันล้วนของ SHELL (แทน __QW_LIB__ ตอนโหลดโมดูล)
# แผงแสดงผล (K7) และการส่งออกแชต (K10) ใช้ร่วมกัน: Markdown → HTML แบบปลอดภัย, แยก CSV, ไล่ข้อความของกิ่งที่เปิดอยู่
# ใน IndexedDB แล้วประกอบเป็นไฟล์ Markdown/HTML  ไม่แตะ DOM/เบราว์เซอร์เลย ชุดทดสอบจึงรันก้อนนี้ใน node ได้ตรงๆ
# (tests/test_shell_features.py อ่าน _LIB_JS จากโมดูลนี้)
# กติกาความปลอดภัย: ทุกข้อความจากแชต/โมเดลผ่าน qwEsc ก่อนเสมอ แท็ก HTML ที่อยู่ในข้อความถูกแสดงเป็นตัวอักษร
# ลิงก์รับแค่ http(s)/mailto/#, รูปรับแค่ data:image (png/jpeg/gif/webp) แบบ base64 — ไม่มีอะไรโหลดจากเน็ต
# --------------------------------------------------------------------------
_LIB_JS = r"""/* ===== ฟังก์ชันล้วนของงานรอบ 4 (แผงแสดงผล + ส่งออกแชต) — ดู _LIB_JS ใน hub_i18n_parts.py ===== */
function qwEsc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : c === '"' ? '&quot;' : '&#39;';
  });
}
function qwUnesc(s) {
  return String(s).replace(/&(amp|lt|gt|quot|#39);/g, function (m, k) {
    return k === 'amp' ? '&' : k === 'lt' ? '<' : k === 'gt' ? '>' : k === 'quot' ? '"' : "'";
  });
}
/* %1 %2 … (ชื่อไม่ชนกับ fmtN ของหน้าต่างเลือก GPU) */
function qwFmtN(s) { var a = arguments; return String(s).replace(/%(\d)/g, function (m, i) { return a[+i] != null ? String(a[+i]) : m; }); }
/* href ที่ยอมรับ: http(s)/mailto และ #anchor เท่านั้น — javascript:, data:, file:, vbscript: และอื่นๆ ตกหมด */
function qwSafeHref(u) {
  u = String(u == null ? '' : u).trim();
  if (/^(https?:\/\/|mailto:)[^\s\u0000-\u001f\u007f]+$/i.test(u)) return u;
  return /^#[\w\-.]*$/.test(u) ? u : '';
}
/* รูปที่ยอมให้แสดง: data URL ของรูปบิตแมปแบบ base64 เท่านั้น (ไม่รับ svg — ภายในมีสคริปต์ได้) */
function qwSafeImg(u) {
  u = String(u == null ? '' : u).replace(/\s+/g, '');
  return /^data:image\/(png|jpe?g|gif|webp);base64,[a-z0-9+\/]+=*$/i.test(u) ? u : '';
}
/* ชื่อไฟล์ของรูป (ส่วนท้ายของ path ถอด %xx แล้ว) สำหรับป้ายแทนรูปที่แสดงไม่ได้ — data: ไม่มีชื่อ */
function qwImgName(u) {
  u = String(u == null ? '' : u).trim();
  if (!u || /^data:/i.test(u)) return '';
  var seg = u.replace(/[?#][\s\S]*$/, '').replace(/\/+$/, '').split('/').pop() || '';
  try { seg = decodeURIComponent(seg); } catch (e) {}
  seg = seg.replace(/[\u0000-\u001f\u007f⁠​]+/g, '').trim();
  return seg.length > 80 ? seg.slice(0, 79) + '…' : seg;
}
/* origin ของพอร์ตโปรเจกต์ในเครื่องเท่านั้น (http://127.0.0.1:81xx) — ค่าอื่นไม่ใช้ */
function qwBase(b) { b = String(b == null ? '' : b); return /^http:\/\/(127\.0\.0\.1|localhost|\[::1\]):\d{2,5}$/.test(b) ? b : ''; }
/* ลิงก์ไฟล์ที่ Qwen สร้าง (/_qwen/out/…) เป็นที่อยู่เต็ม — ไฟล์ส่งออกเปิดนอก origin นี้แล้วลิงก์แบบสัมพัทธ์ใช้ไม่ได้ */
function qwOutAbs(u, base) {
  base = qwBase(base);
  return base && /^\/_qwen\/out\/[^\s]*$/.test(u) && !/(^|\/)\.\.?(\/|$|[?#])/.test(u) ? base + u : u;
}
/* รูปใน /_qwen/out ที่ข้อความของแชตอ้างถึง (![..](/_qwen/out/…)) ไม่ซ้ำ ตามลำดับที่พบ ไม่เกิน max — ผู้เรียกไปอ่านมาฝัง */
function qwOutImgs(turns, max) {
  var seen = {}, out = [], re = /!\[[^\]\n]*\]\(\s*<?(\/_qwen\/out\/[^\s()<>]+?)>?(?:\s+"[^\n]*?")?\s*\)/g, m;
  max = max || 40;
  (turns || []).forEach(function (t) {
    (t.parts || []).forEach(function (p) {
      if (p.type !== 'text' && p.type !== 'reasoning') return;
      re.lastIndex = 0;
      while ((m = re.exec(String(p.text || ''))) && out.length < max) {
        if (!seen[m[1]] && qwImgSrc(m[1]) === m[1]) { seen[m[1]] = 1; out.push(m[1]); }
      }
    });
  });
  return out;
}
/* ข้อความของไฟล์ที่ดาวน์โหลดจากแผง: CSV ได้ BOM (Excel ดับเบิลคลิกแล้วภาษาไทยไม่เพี้ยน) ชนิดอื่นคงเดิม */
function qwDlText(kind, code) {
  code = String(code == null ? '' : code);
  return kind === 'csv' && code.charAt(0) !== '﻿' ? '﻿' + code : code;
}
/* ชื่อโมเดลแบบคนอ่าน — ตัดชนิด quantize ท้ายชื่อไฟล์ (สูตรเดียวกับ model_display_name ใน hub.py) */
function qwModelName(m) { return String(m || '').replace(/(-UD)?-(I?Q\d\w*|MXFP4\w*|F16|BF16|F32)$/i, '') || String(m || ''); }

/* ---- Markdown → HTML (ส่วนย่อยที่โมเดลใช้จริง: หัวข้อ รายการ ตาราง โค้ด คำพูด เส้นคั่น ตัวหนา/เอียง/ขีดฆ่า ลิงก์) ----
   o.images = แสดงรูป data:image ได้ (ไฟล์ส่งออก) · o.links = false → ลิงก์เป็นแค่ข้อความขีดเส้นใต้ (แผงแสดงผลไม่ให้ออกเน็ต) */
function qwMdInline(s, o) {
  o = o || {};
  var slots = [];
  function keep(h) { slots.push(h); return '\u0001' + (slots.length - 1) + '\u0002'; }
  s = qwEsc(String(s == null ? '' : s).replace(/[\u0001\u0002]/g, ''));
  /* โค้ดในบรรทัดก่อนอย่างอื่น — * _ ~ [ ] ข้างในต้องไม่ถูกตีความ */
  s = s.replace(/(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/g, function (m, t, c) { return keep('<code>' + c.replace(/^ ([\s\S]*\S) $/, '$1') + '</code>'); });
  /* <br> ที่โมเดลชอบใส่ในช่องตาราง — แท็กอื่นยังเป็นตัวอักษรตามเดิม */
  s = s.replace(/&lt;br\s*\/?&gt;/gi, function () { return keep('<br>'); });
  /* URL ในวงเล็บรับวงเล็บซ้อนได้หนึ่งชั้น (…/wiki/Foo_(bar))
     o.imgs = {URL ตามที่เขียน: data URL} รูปที่ผู้เรียกอ่านมาฝังไว้แล้ว (รูปใน /_qwen/out ของไฟล์ส่งออก — ผ่าน qwSafeImg อีกชั้น)
     รูปที่แสดงไม่ได้เป็นป้าย [alt: ชื่อไฟล์] — "[fig]" เปล่าๆ ไม่บอกว่าหายไปรูปไหน */
  s = s.replace(/!\[([^\]\n]*)\]\(\s*(?:&lt;)?((?:[^\s()]|\([^\s()]*\))+?)(?:&gt;)?(?:\s+&quot;[^\n]*?&quot;)?\s*\)/g, function (m, alt, url) {
    var u = qwUnesc(url), fix = o.imgs && Object.prototype.hasOwnProperty.call(o.imgs, u) ? o.imgs[u] : '';
    var src = o.images ? qwSafeImg(fix) || qwSafeImg(u) : '', name = qwImgName(u);
    return keep(src ? '<img src="' + qwEsc(src) + '" alt="' + alt + '">'
      : '<span class="md-img">[' + (alt || 'image') + (name && name !== qwUnesc(alt) ? ': ' + qwEsc(name) : '') + ']</span>');
  });
  s = s.replace(/\[([^\]\n]+)\]\(\s*(?:&lt;)?((?:[^\s()]|\([^\s()]*\))+?)(?:&gt;)?(?:\s+&quot;[^\n]*?&quot;)?\s*\)/g, function (m, text, url) {
    var u = qwOutAbs(qwUnesc(url), o.base), h = o.links === false ? '' : qwSafeHref(u), inner = qwMdEmph(text);
    return keep(h ? '<a href="' + qwEsc(h) + '" rel="noopener noreferrer" target="_blank">' + inner + '</a>'
      : '<span class="md-a" title="' + qwEsc(u) + '">' + inner + '</span>');
  });
  s = s.replace(/&lt;((?:https?:\/\/|mailto:)(?:[^\s<>&\u0001\u0002]|&amp;)+)&gt;/g, function (m, u) { return keep(qwLinkHtml(qwUnesc(u), o)); });
  s = s.replace(/(^|[\s(฀-๿])(https?:\/\/(?:[^\s<>&\u0001\u0002]|&amp;)+)/g, function (m, pre, u) {
    var tail = /[.,;:!?)\]}]+$/.exec(u), core = tail ? u.slice(0, -tail[0].length) : u;
    return pre + keep(qwLinkHtml(qwUnesc(core), o)) + (tail ? tail[0] : '');
  });
  s = qwMdEmph(s);
  for (var k = 0; k < 6 && /\u0001\d+\u0002/.test(s); k++) {
    s = s.replace(/\u0001(\d+)\u0002/g, function (m, i) { return slots[+i] != null ? slots[+i] : ''; });
  }
  return s;
}
function qwLinkHtml(u, o) {
  var h = o.links === false ? '' : qwSafeHref(u);
  return h ? '<a href="' + qwEsc(h) + '" rel="noopener noreferrer" target="_blank">' + qwEsc(u) + '</a>' : '<span class="md-a">' + qwEsc(u) + '</span>';
}
/* ตัวหนา/เอียง/ขีดฆ่า บนข้อความที่ escape แล้ว — ขีดล่างนับเฉพาะที่ไม่ติดตัวอักษรละติน/ตัวเลข (snake_case ไม่กลายเป็นตัวเอียง) */
function qwMdEmph(s) {
  return s
    .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^A-Za-z0-9_])__(?=\S)([\s\S]*?\S)__(?![A-Za-z0-9_])/g, '$1<strong>$2</strong>')
    .replace(/(^|[^*\\])\*(?=[^\s*])([^*\n]*?[^\s*\\])\*(?!\*)/g, '$1<em>$2</em>')
    .replace(/(^|[^A-Za-z0-9_])_(?=[^\s_])([^_\n]*?[^\s_])_(?![A-Za-z0-9_])/g, '$1<em>$2</em>')
    .replace(/~~(?=\S)([\s\S]*?\S)~~/g, '<del>$1</del>');
}
var QW_RE_LI = /^( *)([-*+]|\d{1,9}[.)])[ \t]+(.*)$/;
function qwIndent(s) { return /^ */.exec(s)[0].length; }
function qwBlank(s) { return /^\s*$/.test(s); }
function qwBlockStart(l) {
  return /^ {0,3}(`{3,}|~{3,})/.test(l) || /^ {0,3}#{1,6}(\s|$)/.test(l) || /^ {0,3}>/.test(l) ||
    /^ {0,3}([-*_])([ \t]*\1){2,}[ \t]*$/.test(l) || QW_RE_LI.test(l);
}
/* แยกช่องของแถวตาราง — | ในโค้ด `a|b` และ \| ไม่ใช่ตัวแบ่งช่อง */
function qwCells(l) {
  l = String(l).trim();
  if (l.charAt(0) === '|') l = l.slice(1);
  if (l.slice(-1) === '|' && l.slice(-2) !== '\\|') l = l.slice(0, -1);
  var cells = [], cur = '', code = false;
  for (var k = 0; k < l.length; k++) {
    var c = l.charAt(k);
    if (c === '\\' && l.charAt(k + 1) === '|') { cur += '|'; k++; continue; }
    if (c === '`') code = !code;
    if (c === '|' && !code) { cells.push(cur.trim()); cur = ''; continue; }
    cur += c;
  }
  cells.push(cur.trim());
  return cells;
}
function qwIsTable(L, i) {
  if (i + 1 >= L.length || L[i].indexOf('|') < 0 || L[i + 1].indexOf('|') < 0) return false;
  if (!/^ {0,3}\|?[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$/.test(L[i + 1])) return false;
  return qwCells(L[i]).length === qwCells(L[i + 1]).length;
}
function qwTable(L, i, o) {
  var head = qwCells(L[i]), al = qwCells(L[i + 1]).map(function (c) {
    return /^:-+:$/.test(c) ? 'c' : /^-+:$/.test(c) ? 'r' : '';
  });
  var rows = [], j = i + 2;
  while (j < L.length && !qwBlank(L[j]) && L[j].indexOf('|') >= 0) { rows.push(qwCells(L[j])); j++; }
  function cell(tag, c, k) { return '<' + tag + (al[k] ? ' class="al-' + al[k] + '"' : '') + '>' + qwMdInline(c, o) + '</' + tag + '>'; }
  var h = '<div class="tbl"><table><thead><tr>' + head.map(function (c, k) { return cell('th', c, k); }).join('') + '</tr></thead><tbody>' +
    rows.map(function (r) {
      var cs = [];
      for (var k = 0; k < head.length; k++) cs.push(cell('td', r[k] == null ? '' : r[k], k));
      return '<tr>' + cs.join('') + '</tr>';
    }).join('') + '</tbody></table></div>';
  return { html: h, next: j };
}
function qwList(L, i, o, depth) {
  var m = QW_RE_LI.exec(L[i]), base = m[1].length, ordered = /\d/.test(m[2]), start = ordered ? parseInt(m[2], 10) : 1;
  var items = [], cur = null, gap = false, n = L.length;
  while (i < n) {
    var l = L[i];
    if (qwBlank(l)) {
      /* บรรทัดว่าง: ยังเป็นรายการเดิมถ้าบรรทัดถัดไปเยื้องเข้าไป หรือเป็นข้อถัดไปของรายการชนิดเดียวกัน */
      var k = i + 1;
      while (k < n && qwBlank(L[k])) k++;
      if (k >= n) break;
      var mk = QW_RE_LI.exec(L[k]);
      if (qwIndent(L[k]) >= base + 2 || (mk && mk[1].length <= base + 1 && /\d/.test(mk[2]) === ordered)) {
        if (cur) cur.lines.push('');
        gap = true; i++; continue;
      }
      break;
    }
    var mm = QW_RE_LI.exec(l);
    if (mm && mm[1].length <= base + 1) {
      if (/\d/.test(mm[2]) !== ordered) break;
      cur = { lines: [mm[3]], cind: mm[1].length + mm[2].length + 1 };
      items.push(cur); gap = false; i++; continue;
    }
    if (!cur) break;
    var ind = qwIndent(l);
    if (ind >= base + 2) { cur.lines.push(l.slice(Math.min(ind, cur.cind))); gap = false; i++; continue; }
    if (!gap && !qwBlockStart(l)) { cur.lines.push(l.trim()); i++; continue; }
    break;
  }
  var tag = ordered ? 'ol' : 'ul';
  return {
    html: '<' + tag + (ordered && start !== 1 ? ' start="' + start + '"' : '') + '>' + items.map(function (it) {
      var rest = it.lines.slice(1), para = [it.lines[0]], j = 0;
      while (j < rest.length && rest[j] !== '' && !qwBlockStart(rest[j]) && !qwIsTable(rest, j)) { para.push(rest[j]); j++; }
      var tail = rest.slice(j);
      return '<li>' + para.map(function (x) { return qwMdInline(x.trim(), o); }).join('<br>') +
        (tail.join('').trim() ? qwMdBlocks(tail, o, depth + 1) : '') + '</li>';
    }).join('') + '</' + tag + '>',
    next: i
  };
}
function qwMdBlocks(L, o, depth) {
  if (depth > 12) return '<p>' + qwEsc(L.join('\n')) + '</p>';
  var out = [], i = 0, n = L.length, m;
  while (i < n) {
    var l = L[i];
    if (qwBlank(l)) { i++; continue; }
    /* ```code``` ทั้งบรรทัดคือโค้ดในบรรทัด ไม่ใช่รั้วเปิด (รั้วแบบ backtick ห้ามมี backtick ตามหลัง) */
    if ((m = /^( {0,3})(`{3,}|~{3,})[ \t]*([^\s`]*)/.exec(l)) && !(m[2].charAt(0) === '`' && l.slice(m[0].length).indexOf('`') >= 0)) {
      var ind = m[1].length, close = new RegExp('^ {0,3}' + (m[2].charAt(0) === '`' ? '`' : '~') + '{' + m[2].length + ',}[ \\t]*$'), buf = [];
      var lang = m[3].replace(/[^\w+#.\-]/g, '');
      i++;
      while (i < n && !close.test(L[i])) { buf.push(ind ? L[i].replace(new RegExp('^ {0,' + ind + '}'), '') : L[i]); i++; }
      i++;
      out.push('<pre><code' + (lang ? ' class="language-' + lang + '"' : '') + '>' + qwEsc(buf.join('\n')) + '</code></pre>');
      continue;
    }
    if ((m = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?(?:[ \t]+#+)?[ \t]*$/.exec(l))) {
      var lv = m[1].length;
      out.push('<h' + lv + '>' + qwMdInline(m[2] || '', o) + '</h' + lv + '>');
      i++; continue;
    }
    if (/^ {0,3}([-*_])([ \t]*\1){2,}[ \t]*$/.test(l)) { out.push('<hr>'); i++; continue; }
    if (/^ {0,3}>/.test(l)) {
      var q = [];
      while (i < n && !qwBlank(L[i]) && (/^ {0,3}>/.test(L[i]) || (q.length && !qwBlockStart(L[i])))) { q.push(L[i].replace(/^ {0,3}> ?/, '')); i++; }
      out.push('<blockquote>' + qwMdBlocks(q, o, depth + 1) + '</blockquote>');
      continue;
    }
    if (qwIsTable(L, i)) { var tb = qwTable(L, i, o); out.push(tb.html); i = tb.next; continue; }
    if (QW_RE_LI.test(l)) { var ls = qwList(L, i, o, depth); out.push(ls.html); i = ls.next; continue; }
    /* ย่อหน้า: ขึ้นบรรทัดเดี่ยว = <br> แบบเดียวกับที่หน้าแชตแสดง (โมเดลตั้งใจขึ้นบรรทัดจริง) */
    var p = [l];
    i++;
    while (i < n && !qwBlank(L[i]) && !qwBlockStart(L[i]) && !qwIsTable(L, i)) { p.push(L[i]); i++; }
    out.push('<p>' + p.map(function (x) { return qwMdInline(x.trim(), o); }).join('<br>') + '</p>');
  }
  return out.join('\n');
}
function qwMd(src, o) {
  var L = String(src == null ? '' : src).replace(/\r\n?/g, '\n').split('\n').map(function (l) {
    return l.replace(/^\t+/, function (t) { return new Array(t.length + 1).join('    '); });
  });
  return qwMdBlocks(L, o || {}, 0);
}

/* ---- CSV → แถว (RFC 4180: เครื่องหมายคำพูดครอบ, "" ข้างใน, ขึ้นบรรทัดในช่อง) ตัวคั่นเดาจากบรรทัดแรก , ; แท็บ | ----
   เก็บแค่ maxRows แถวแรก แต่นับทั้งไฟล์ (บอกผู้ใช้ได้ว่าแสดงกี่แถวจากทั้งหมด) */
function qwCsv(text, maxRows) {
  text = String(text == null ? '' : text).replace(/^﻿/, '');
  maxRows = maxRows || 2000;
  var first = text.slice(0, 8192).split(/\r?\n/)[0] || '', delim = ',', best = 0;
  [',', ';', '\t', '|'].forEach(function (d) { var c = first.split(d).length - 1; if (c > best) { best = c; delim = d; } });
  var rows = [], row = [], f = '', q = false, total = 0, n = text.length, c;
  function endRow() {
    row.push(f); f = '';
    if (!(row.length === 1 && row[0] === '')) { total++; if (rows.length < maxRows) rows.push(row); }
    row = [];
  }
  for (var i = 0; i < n; i++) {
    c = text.charAt(i);
    if (q) {
      if (c === '"') { if (text.charAt(i + 1) === '"') { f += '"'; i++; } else q = false; }
      else f += c;
      continue;
    }
    if (c === '"' && f === '') { q = true; continue; }
    if (c === delim) { row.push(f); f = ''; continue; }
    if (c === '\r') { if (text.charAt(i + 1) === '\n') i++; endRow(); continue; }
    if (c === '\n') { endRow(); continue; }
    f += c;
  }
  if (f !== '' || row.length) endRow();
  return { rows: rows, total: total, delim: delim };
}

/* ---- แผงแสดงผล: ตรวจ/ปรับข้อมูลจาก iframe ก่อนใช้ (K7) ---- */
var QW_ART_KINDS = { html: 'html', htm: 'html', svg: 'svg', mermaid: 'mermaid', mmd: 'mermaid', markdown: 'markdown', md: 'markdown',
  csv: 'csv', tsv: 'csv', image: 'image', img: 'image', png: 'image', jpg: 'image', jpeg: 'image', gif: 'image', webp: 'image', chart: 'image' };
/* รูปในแผง: ไฟล์ผลลัพธ์ของโปรเจกต์ (/_qwen/out/<ชื่อ>), data:image บิตแมป หรือ blob: ของพอร์ตในเครื่อง
   (shell ตรวจซ้ำว่า blob เป็นของ origin ตัวเอง) — ไม่รับ URL ภายนอก รูปจากเน็ตคือการส่งข้อมูลออก */
function qwImgSrc(u) {
  u = String(u == null ? '' : u).trim();
  if (/^\/_qwen\/out\/[^\/\\?#]+(\?download=1)?$/.test(u) && !/(^|\/)\.\.?(\/|$|\?)/.test(u)) return u;
  if (/^blob:http:\/\/(127\.0\.0\.1|localhost):\d{2,5}\/[0-9a-f\-]{36}$/i.test(u)) return u;
  return qwSafeImg(u);
}
function qwArtNorm(o, max) {
  if (!o || typeof o !== 'object') return null;
  var kind = QW_ART_KINDS[String(o.kind == null ? '' : o.kind).toLowerCase().trim()];
  var code = o.code != null ? String(o.code) : o.src != null ? String(o.src) : '';
  if (!kind || !code.trim()) return null;
  max = max || 2000000;
  if (code.length > max) return { tooBig: true };
  if (kind === 'image') { code = qwImgSrc(code); if (!code) return null; }
  var svg = kind === 'mermaid' && typeof o.svg === 'string' && o.svg.length <= max && /^\s*<svg[\s>]/i.test(o.svg) ? o.svg : '';
  var title = String(o.title == null ? '' : o.title).replace(/\s+/g, ' ').trim().slice(0, 200);
  var id = String(o.id == null ? '' : o.id).replace(/[\u0000-\u001f]/g, '').slice(0, 200);
  return { id: id || kind + ':' + title, kind: kind, title: title, code: code, svg: svg };
}
/* ---- หน้า HTML ในแผง: กติกาตัดสิ่งที่พาเฟรมออกนอกเครื่องโดยไม่ต้องใช้สคริปต์ (artHtmlDoc เดิน DOM แล้วถามฟังก์ชันพวกนี้) ----
   ln = localName ของ element, nm = ชื่อ attribute ตัวเล็ก
   * ลิงก์ <a>/<area> (HTML และ SVG) ที่ไม่ใช่ #anchor: คลิกแล้วเฟรมไปที่อยู่นั้นพร้อมข้อมูลใน URL — ถอด href/xlink:href
   * element อื่นที่มี href (use/image ของ SVG, href ของ MathML): เก็บเฉพาะ #… และ data: (อย่างอื่นโหลด/นำทางออกเน็ต)
   * ping: ส่งคำขอไปที่อยู่อื่นเองตอนคลิกลิงก์ */
function qwArtDropAttr(ln, nm, val) {
  ln = String(ln || '').toLowerCase(); nm = String(nm || '').toLowerCase(); val = String(val == null ? '' : val).trim();
  if (nm === 'ping') return true;
  if (nm !== 'href' && nm !== 'xlink:href') return false;
  if (val.charAt(0) === '#') return false;
  return ln === 'a' || ln === 'area' || !/^data:/i.test(val);
}
/* แอนิเมชันของ SVG ที่ตั้ง href ได้ (<animate attributeName="href" to="https://…"> สร้างลิงก์คืนหลังเราถอด) — ตัดทั้งตัว */
function qwArtDropEl(ln, attributeName) {
  return /^(animate|set|animatemotion|animatetransform)$/i.test(String(ln || '')) && /href/i.test(String(attributeName || ''));
}
/* หน้านี้มีสคริปต์ไหม (นอกจากแท็ก <script>): ตัวจัดการเหตุการณ์ on…= หรือ URL javascript: — ใช้ตัดสินว่าต้องแสดงปุ่มเรียกใช้สคริปต์ */
function qwArtScriptAttr(nm, val) {
  return String(nm || '').toLowerCase().slice(0, 2) === 'on' || /^\s*javascript:/i.test(String(val == null ? '' : val));
}
/* การแจ้งเตือน: pref = ค่าที่ผู้ใช้เลือก (off|on|sound), perm = Notification.permission (granted|denied|default|unsupported)
   shown = ค่าที่เมนูแสดง (ใช้ได้จริง) · warn = คีย์ข้อความเตือนใต้แถว ('' = ไม่เตือน) */
function qwNtfState(pref, perm) {
  var on = pref === 'on' || pref === 'sound';
  return {
    shown: on && perm === 'granted' ? pref : 'off',
    warn: !on || perm === 'granted' ? '' : perm === 'denied' ? 'ntf_blocked' : perm === 'unsupported' ? 'ntf_unsupported' : 'ntf_ask_again'
  };
}

/* ---- ส่งออกแชต (K10) ---- */
/* กิ่งที่เปิดอยู่: เดินจาก currNode ขึ้นไปหาราก (แบบเดียวกับที่ WebUI แสดง) — ไม่มี currNode ใช้ข้อความล่าสุด */
function qwConvPath(conv, msgs) {
  var by = {};
  (msgs || []).forEach(function (m) { if (m && m.id) by[m.id] = m; });
  var leaf = conv && conv.currNode ? by[conv.currNode] : null;
  if (!leaf) {
    (msgs || []).forEach(function (m) { if (m && m.type !== 'root' && (!leaf || (m.timestamp || 0) >= (leaf.timestamp || 0))) leaf = m; });
  }
  var path = [], seen = {};
  for (var m = leaf; m && !seen[m.id]; m = m.parent ? by[m.parent] : null) { seen[m.id] = 1; path.push(m); }
  return path.reverse().filter(function (x) { return x.type !== 'root'; });
}
function qwToolCalls(s) {
  if (!s) return [];
  if (Array.isArray(s)) return s;
  try { var a = JSON.parse(s); return Array.isArray(a) ? a : []; } catch (e) { return []; }
}
function qwFiles(extra) {
  return (Array.isArray(extra) ? extra : []).filter(function (x) { return x && (x.name || x.type); }).map(function (x) {
    var img = /image/i.test(String(x.type || '')) ? qwSafeImg(x.base64Url || x.url || '') : '';
    return { name: String(x.name || x.type || ''), image: img };
  });
}
/* ข้อความเป็นรอบสนทนา: ผู้ใช้หนึ่งรอบ แล้วคำตอบ — ข้อความผู้ช่วยต่อเนื่องในลูปเครื่องมือ (ผู้ช่วย → tool → ผู้ช่วย)
   รวมเป็นรอบเดียว ผลของเครื่องมือจับคู่กับการเรียกด้วย toolCallId  ข้อความระบบ (คำสั่งโปรเจกต์ + ที่อยู่ไฟล์) ไม่ส่งออก */
function qwTurns(path) {
  var turns = [], cur = null;
  (path || []).forEach(function (m) {
    if (!m || m.type === 'root' || m.type === 'system' || m.role === 'system') return;
    if (m.role === 'user') {
      var ut = String(m.content || '');
      cur = { role: 'user', at: m.timestamp || 0, model: '', parts: ut.trim() ? [{ type: 'text', text: ut }] : [], files: qwFiles(m.extra) };
      turns.push(cur);
      return;
    }
    if (m.role === 'tool') {
      if (!cur || cur.role !== 'assistant') return;
      var hit = null;
      cur.parts.forEach(function (p) { if (!hit && p.type === 'tool' && p.id && p.id === m.toolCallId && p.result == null) hit = p; });
      if (hit) hit.result = String(m.content || '');
      else cur.parts.push({ type: 'tool', id: String(m.toolCallId || ''), name: '', args: '', result: String(m.content || '') });
      return;
    }
    if (m.role !== 'assistant') return;
    if (!cur || cur.role !== 'assistant') { cur = { role: 'assistant', at: m.timestamp || 0, model: '', parts: [], files: [] }; turns.push(cur); }
    if (m.model && !cur.model) cur.model = String(m.model);
    var content = String(m.content || ''), think = String(m.reasoningContent || m.thinking || '');
    /* โมเดลที่ไม่ได้แยกความคิดออกมา ความคิดติดอยู่ในเนื้อความเป็น <think>…</think> */
    var tm = /^\s*<think>([\s\S]*?)(<\/think>|$)/.exec(content);
    if (tm) { think = (think ? think + '\n\n' : '') + tm[1]; content = content.slice(tm[0].length); }
    if (think.trim()) cur.parts.push({ type: 'reasoning', text: think });
    if (content.trim()) cur.parts.push({ type: 'text', text: content });
    qwToolCalls(m.toolCalls).forEach(function (c) {
      var f = (c && c.function) || {};
      cur.parts.push({ type: 'tool', id: String((c && c.id) || ''), name: String(f.name || ''),
        args: typeof f.arguments === 'string' ? f.arguments : JSON.stringify(f.arguments || {}), result: null });
    });
  });
  return turns.filter(function (t) { return t.parts.length || t.files.length; });
}
function qwPretty(s) { try { return JSON.stringify(JSON.parse(s), null, 2); } catch (e) { return String(s == null ? '' : s); } }
function qwCut(s, max, L) {
  s = String(s == null ? '' : s);
  return s.length <= max ? s : s.slice(0, max) + '\n' + qwFmtN(L.cut, max, s.length);
}
/* รั้วโค้ดยาวกว่าแถว ` ที่ยาวที่สุดในเนื้อหา — เนื้อหาที่มี ``` อยู่แล้วไม่ทำให้บล็อกปิดก่อนเวลา */
function qwFence(s) {
  var max = 2, re = /`+/g, m;
  while ((m = re.exec(String(s)))) if (m[0].length > max) max = m[0].length;
  return new Array(max + 2).join('`');
}
function qwFileName(s, ext) {
  s = String(s == null ? '' : s).replace(/[\u0000-\u001f\u007f<>:"\/\\|?*⁠​]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/^[.\s]+|[.\s]+$/g, '');
  if (!s || /^(con|prn|aux|nul|com\d|lpt\d)(\..*)?$/i.test(s)) s = 'chat';
  if (s.length > 80) s = s.slice(0, 80).replace(/[.\s]+$/, '');
  return s + (ext ? '.' + ext : '');
}
function qwWho(t, L) { return t.role === 'user' ? L.you : 'Qwen' + (t.model ? ' · ' + qwModelName(t.model) : ''); }
/* o.base = origin ของพอร์ตโปรเจกต์ → ลิงก์/รูป ](/_qwen/out/…) ในข้อความกลายเป็นที่อยู่เต็ม (ไฟล์ .md เปิดที่อื่นแล้วยังกดได้) */
function qwMdAbs(s, base) {
  base = qwBase(base);
  return base ? String(s).replace(/(\]\(\s*<?)(\/_qwen\/out\/[^\s()<>]*)/g, function (m, pre, u) { return pre + qwOutAbs(u, base); }) : String(s);
}
function qwExportMd(title, turns, L, o) {
  o = o || {};
  var out = ['# ' + String(title).replace(/\s+/g, ' '), '', '_' + L.meta + '_', ''];
  turns.forEach(function (t) {
    out.push('---', '', '### ' + qwWho(t, L) + (t.at ? ' · ' + L.time(t.at) : ''), '');
    t.parts.forEach(function (p) {
      if (p.type === 'text') out.push(qwMdAbs(p.text.replace(/\s+$/, ''), o.base), '');
      else if (p.type === 'reasoning') out.push('<details>', '<summary>' + qwEsc(L.reasoning) + '</summary>', '', qwMdAbs(p.text.trim(), o.base), '', '</details>', '');
      else if (p.type === 'tool') {
        var a = qwCut(qwPretty(p.args), 1500, L), r = p.result == null ? L.noResult : qwCut(p.result, 3000, L), fa = qwFence(a), fr = qwFence(r);
        out.push('<details>', '<summary>' + qwEsc(L.tool + ': ' + (p.name || '?')) + '</summary>', '',
          '**' + L.args + '**', '', fa + 'json', a, fa, '', '**' + L.result + '**', '', fr, r, fr, '', '</details>', '');
      }
    });
    if (t.files && t.files.length) out.push('_' + L.attach + ': ' + t.files.map(function (f) { return f.name; }).join(', ') + '_', '');
  });
  return out.join('\n') + '\n';
}
var QW_EXPORT_CSS = [
  ':root{color-scheme:light}',
  'body{margin:0;background:#faf9f5;color:#1f1e1d;font:16px/1.7 Cambria,"Leelawadee UI","Noto Serif Thai",Georgia,Tahoma,serif;-webkit-font-smoothing:antialiased}',
  'main{max-width:760px;margin:0 auto;padding:40px 24px 64px}',
  'h1.t{font-weight:500;font-size:28px;line-height:1.3;margin:0 0 6px;overflow-wrap:anywhere}',
  '.meta,.who,.files,summary,.hint{font-family:"Segoe UI","Leelawadee UI",Tahoma,system-ui,sans-serif}',
  '.meta{font-size:13px;color:#65635c;margin:0 0 8px}',
  '.hint{font-size:13px;color:#65635c;background:#f3f1ea;border-radius:10px;padding:8px 12px;margin:0 0 20px}',
  '.turn{margin:26px 0;padding-top:18px;border-top:.5px solid rgba(31,30,29,.12)}',
  '.who{font-size:13px;font-weight:600;color:#3d3d3a;margin:0 0 8px}',
  '.who time{font-weight:400;color:#65635c;margin-left:6px}',
  '.user .md{background:#efece3;border-radius:16px;padding:8px 16px;font-family:"Segoe UI","Leelawadee UI",Tahoma,sans-serif;font-size:15px}',
  '.md>:first-child{margin-top:0}.md>:last-child{margin-bottom:0}',
  '.md h1,.md h2,.md h3,.md h4{font-weight:600;line-height:1.35;margin:1.2em 0 .5em}',
  '.md h1{font-size:1.5em}.md h2{font-size:1.25em}.md h3{font-size:1.1em}.md h4{font-size:1em}',
  '.md p{margin:.6em 0}.md ul,.md ol{padding-left:1.5em;margin:.5em 0}.md li{margin:.2em 0}',
  'a{color:#b5573a;text-underline-offset:2px}.md-a{text-decoration:underline;text-underline-offset:2px}',
  '.md-img{font:13px "Segoe UI","Leelawadee UI",Tahoma,sans-serif;color:#65635c;overflow-wrap:anywhere}',
  'code{font-family:"Cascadia Code",Consolas,monospace;font-size:.88em;background:#ece9df;border-radius:5px;padding:.1em .3em}',
  'pre{background:#f3f1ea;border:.5px solid rgba(31,30,29,.12);border-radius:12px;padding:12px 14px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.55 "Cascadia Code",Consolas,monospace}',
  'pre code{background:none;padding:0;font-size:inherit}',
  'blockquote{margin:.8em 0;padding:0 0 0 14px;border-left:3px solid rgba(31,30,29,.2);color:#3d3d3a}',
  'hr{border:0;border-top:.5px solid rgba(31,30,29,.18);margin:1.2em 0}',
  '.tbl{overflow-x:auto;margin:.8em 0}table{border-collapse:collapse;font-size:.92em}',
  'th,td{border:.5px solid rgba(31,30,29,.18);padding:6px 10px;text-align:left;vertical-align:top}th{background:#f3f1ea;font-weight:600}',
  '.al-c{text-align:center}.al-r{text-align:right}img{max-width:100%;border-radius:8px}',
  'details{margin:10px 0;border:.5px solid rgba(31,30,29,.14);border-radius:10px;background:#fff;padding:0 12px}',
  'summary{cursor:pointer;padding:8px 0;font-size:13px;color:#65635c}details[open]>summary{border-bottom:.5px solid rgba(31,30,29,.1);margin-bottom:8px}',
  'details .md,details pre{margin-bottom:10px}.lbl{font:600 12px "Segoe UI",Tahoma,sans-serif;color:#65635c;margin:8px 0 4px}',
  '.files{font-size:13px;color:#65635c;margin-top:8px}.files img{display:block;max-width:320px;margin-top:6px}',
  '@media print{body{background:#fff}main{padding:0}.hint{display:none}.turn{break-inside:auto}pre,details,table,img{break-inside:avoid}a{color:inherit}}'
].join('\n');
/* ไฟล์ HTML ทั้งหน้า — CSP ในตัวไฟล์: ไม่รันสคริปต์ (ยกเว้นสคริปต์สั่งพิมพ์ที่มี nonce ของเราเอง) ไม่โหลดอะไรจากเน็ต
   รูปได้แค่ data: ที่ฝังในไฟล์ ไฟล์ที่ส่งต่อให้คนอื่นเปิดจึงไม่แอบเรียกออกไปไหน */
function qwExportHtml(title, turns, L, o) {
  o = o || {};
  var nonce = o.print && /^[A-Za-z0-9]{16,64}$/.test(o.nonce || '') ? o.nonce : '';
  var csp = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'" + (nonce ? "; script-src 'nonce-" + nonce + "'" : '');
  /* o.imgs = รูปจาก /_qwen/out ที่ผู้เรียกอ่านมาเป็น data URL แล้ว (CSP ของไฟล์รับรูปแค่ data:) · o.base = ลิงก์ไฟล์เป็นที่อยู่เต็ม */
  var md = { images: true, imgs: o.imgs && typeof o.imgs === 'object' ? o.imgs : null, base: o.base };
  var turnsHtml = turns.map(function (t) {
    var parts = t.parts.map(function (p) {
      if (p.type === 'text') return '<div class="md">' + qwMd(p.text, md) + '</div>';
      if (p.type === 'reasoning') return '<details><summary>' + qwEsc(L.reasoning) + '</summary><div class="md">' + qwMd(p.text, md) + '</div></details>';
      var a = qwCut(qwPretty(p.args), 1500, L), r = p.result == null ? L.noResult : qwCut(p.result, 3000, L);
      return '<details><summary>' + qwEsc(L.tool + ': ' + (p.name || '?')) + '</summary><div class="lbl">' + qwEsc(L.args) +
        '</div><pre><code>' + qwEsc(a) + '</code></pre><div class="lbl">' + qwEsc(L.result) + '</div><pre><code>' + qwEsc(r) + '</code></pre></details>';
    }).join('\n');
    var files = t.files && t.files.length ? '<div class="files">' + qwEsc(L.attach) + ': ' + t.files.map(function (f) {
      return qwEsc(f.name) + (f.image ? '<img src="' + qwEsc(f.image) + '" alt="' + qwEsc(f.name) + '">' : '');
    }).join(', ') + '</div>' : '';
    return '<section class="turn ' + (t.role === 'user' ? 'user' : 'bot') + '"><div class="who">' + qwEsc(qwWho(t, L)) +
      (t.at ? '<time>' + qwEsc(L.time(t.at)) + '</time>' : '') + '</div>' + parts + files + '</section>';
  }).join('\n');
  return '<!doctype html>\n<html lang="' + qwEsc(L.lang || 'en') + '"><head><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1">' +
    '<meta http-equiv="Content-Security-Policy" content="' + csp + '">' +
    '<meta name="referrer" content="no-referrer"><title>' + qwEsc(title) + '</title><style>' + QW_EXPORT_CSS + '</style></head>' +
    '<body><main><h1 class="t">' + qwEsc(title) + '</h1><p class="meta">' + qwEsc(L.meta) + '</p>' +
    (nonce && L.printHint ? '<p class="hint">' + qwEsc(L.printHint) + '</p>' : '') + turnsHtml + '</main>' +
    /* <\/script> — ก้อนนี้ถูกฝังในสคริปต์ inline ของหน้า shell ถ้าเขียนแท็กปิดตรงๆ ตัวแยก HTML จะปิดสคริปต์ของเรากลางคัน */
    (nonce ? '<script nonce="' + nonce + '">addEventListener("load",function(){setTimeout(function(){print()},300)})<\/script>' : '') +
    '</body></html>';
}"""


def _inject_lib(tpl):
    assert tpl.count("__QW_LIB__") == 1
    assert '"""' not in _LIB_JS and "__T_" not in _LIB_JS
    return tpl.replace("__QW_LIB__", _LIB_JS)


SHELL = _inject_lib(SHELL)


# --------------------------------------------------------------------------
# batch 3 (2026-10-06, owner ui) — สัญญา D4(a): ฟังก์ชันล้วนของแท็บ "การใช้งาน" และ "ตรวจระบบ" ในหน้าจัดการ (PAGE)
# แทน __QW_B3__ ตอนโหลดโมดูล ไม่แตะ DOM เลย — tests/test_b3_ui.py รันก้อนนี้ใน node ตรงๆ
# ทำไมต้องยืดหยุ่น: รูปแบบ JSON ของ GET /api/usage และ GET /api/doctor ยังไม่ตายตัวตอนเขียน (owner hub ทำคู่ขนาน
# ตามสัญญา D2/D3 ที่กำหนดแค่ "มีอะไร" ไม่ได้กำหนดชื่อฟิลด์) ตัวแปลงจึงรับชื่อฟิลด์ที่เป็นไปได้หลายแบบ และไม่เดาค่าที่ไม่มี
# (ไม่มีข้อมูล = ไม่แสดงแถวนั้น ไม่ใช่โชว์ 0 ปลอมๆ) — รูปแบบที่แนะนำเขียนไว้ใน notes ของงานนี้
# ความปลอดภัย: ค่าของไฟล์คีย์/โทเค็นไม่เคยถูกแสดง (ใช้แค่ว่ามี/ไม่มี) และรายงานที่คัดลอกผ่าน b3Scrub อีกชั้น
# (hub ล้างด้วย secrets_util แล้ว — ชั้นนี้กันพลาด เช่น log ที่มี Bearer หรือคีย์ยาวๆ หลุดมา)
# --------------------------------------------------------------------------
_B3_JS = r"""/* ===== batch 3 (D4): ฟังก์ชันล้วนของแท็บ "การใช้งาน" + "ตรวจระบบ" — ดู _B3_JS ใน hub_i18n_parts.py ===== */
var B3_SLOTS = 5;
function b3Num(v) { v = typeof v === 'string' ? parseFloat(v) : +v; return isFinite(v) ? v : 0; }
function b3Obj(v) { return !!v && typeof v === 'object' && !Array.isArray(v); }
function b3Has(o, k) { return b3Obj(o) && Object.prototype.hasOwnProperty.call(o, k) && o[k] != null && o[k] !== ''; }
function b3Pick(o, keys) {
  for (var i = 0; i < keys.length; i++) if (b3Has(o, keys[i])) return o[keys[i]];
  return undefined;
}
/* แถวข้อมูล: รับทั้ง array ของออบเจกต์ และออบเจกต์ที่ใช้ชื่อเป็นคีย์ ({"2026-10-06": {...}} / {"router": {...}})
   คีย์ไปอยู่ใน _k  scalars=true: ค่าเดี่ยว ({"router": true}) กลายเป็น {value: true} (ใช้กับบริการ/ไฟล์คีย์) */
function b3List(v, scalars) {
  if (Array.isArray(v)) return v.filter(b3Obj);
  if (!b3Obj(v)) return [];
  return Object.keys(v).map(function (k) {
    var o = v[k], c = {};
    if (b3Obj(o)) { for (var j in o) if (Object.prototype.hasOwnProperty.call(o, j)) c[j] = o[j]; }
    else if (scalars && o != null && typeof o !== 'object') c.value = o;
    else return null;
    c._k = k;
    return c;
  }).filter(Boolean);
}
function b3Pad(n) { return (n < 10 ? '0' : '') + n; }
function b3Ymd(dt) { return dt.getFullYear() + '-' + b3Pad(dt.getMonth() + 1) + '-' + b3Pad(dt.getDate()); }
/* วันที่ → "YYYY-MM-DD" (ISO ที่มีเขตเวลาใช้วันที่ตามที่ hub เขียน = เวลาเครื่องนี้) · epoch วินาที/มิลลิวินาทีก็ได้ */
function b3Day(x) {
  if (x == null || x === '') return '';
  if (typeof x === 'number') { var dt = new Date(x < 1e12 ? x * 1000 : x); return isNaN(dt.getTime()) ? '' : b3Ymd(dt); }
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(x));
  return m ? m[0] : '';
}
function b3Time(ts) {
  if (typeof ts === 'number') return ts < 1e12 ? ts * 1000 : ts;
  var v = Date.parse(String(ts == null ? '' : ts));
  return isNaN(v) ? NaN : v;
}
/* n วันย้อนหลังจนถึง end (รวม end) นับตามปฏิทินท้องถิ่น — วันที่ไม่มีข้อมูลก็ต้องมีช่อง (แกนเวลาไม่กระโดด) */
function b3Days(n, end) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(end || ''), base = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(), out = [];
  for (var i = n - 1; i >= 0; i--) out.push(b3Ymd(new Date(base.getFullYear(), base.getMonth(), base.getDate() - i)));
  return out;
}
/* ชื่อไฟล์โมเดล → ชื่อรุ่นที่คนอ่าน (ตัดชนิด quantize ท้ายชื่อ — กติกาเดียวกับ model_display_name ใน hub.py) */
function b3Short(m) { m = String(m == null ? '' : m); return m.replace(/(-UD)?-(I?Q\d\w*|MXFP4\w*|F16|BF16|F32)$/i, '') || m; }

/* ---------------------------------------------------------------- การใช้งาน (/api/usage) */
var B3_ROW_KEYS = ['rows', 'per_day_model', 'per_day_project_model', 'by_day_model', 'per_day', 'by_day', 'daily', 'days',
  'buckets', 'aggregates'];
var B3_REC_KEYS = ['recent', 'sessions', 'recent_sessions', 'records', 'last'];
function b3Rec(o, ctx) {
  ctx = ctx || {};
  var e = b3Pick(o, ['errors', 'error_count', 'error']), c = b3Pick(o, ['compacted', 'compactions', 'compacted_count']);
  var r = {
    day: b3Day(b3Pick(o, ['day', 'date'])) || ctx.day || b3Day(b3Pick(o, ['ts', 'time', 'at'])),
    model: String(b3Pick(o, ['model', 'model_id']) || ctx.model || ''),
    project: String(b3Pick(o, ['project', 'project_slug', 'slug']) || ctx.project || ''),
    requests: b3Num(b3Pick(o, ['requests', 'count', 'calls', 'n'])),
    prompt: b3Num(b3Pick(o, ['prompt_tokens', 'prompt', 'tokens_in', 'input_tokens'])),
    cached: b3Num(b3Pick(o, ['cached_tokens', 'cached', 'cache_tokens'])),
    completion: b3Num(b3Pick(o, ['completion_tokens', 'completion', 'tokens_out', 'output_tokens'])),
    errors: typeof e === 'boolean' ? +e : b3Num(e),
    compacted: typeof c === 'boolean' ? +c : b3Num(c),
    wall: b3Num(b3Pick(o, ['wall_s', 'wall', 'seconds'])),
    gen: b3Num(b3Pick(o, ['gen_tps', 'avg_gen_tps', 'gen_tps_avg'])),
    ptps: b3Num(b3Pick(o, ['prompt_tps', 'avg_prompt_tps', 'prompt_tps_avg']))
  };
  /* บรรทัดดิบหนึ่งบรรทัด (มี ts) = คำขอเดียว: compacted อาจเป็นจำนวนรอบ — นับเป็น 1 ครั้ง ไม่ใช่ 12 */
  if (b3Has(o, 'ts')) { r.requests = r.requests || 1; r.compacted = r.compacted > 0 ? 1 : 0; r.errors = r.errors > 0 ? 1 : 0; }
  return r;
}
function b3Rows(d) {
  for (var i = 0; i < B3_ROW_KEYS.length; i++) {
    var v = d[B3_ROW_KEYS[i]];
    if (!v || typeof v !== 'object') continue;
    var out = [];
    b3List(v).forEach(function (o) {
      var day = b3Day(b3Pick(o, ['day', 'date', '_k'])), nest = b3Pick(o, ['models', 'by_model', 'per_model']);
      var subs = nest && typeof nest === 'object' ? b3List(nest) : [];
      if (subs.length) subs.forEach(function (m) { out.push(b3Rec(m, { day: day, model: m._k || '', project: String(b3Pick(o, ['project']) || '') })); });
      else out.push(b3Rec(o, { day: day }));
    });
    out = out.filter(function (r) { return r.day; });
    if (out.length) return out;
  }
  return null;
}
function b3Sess(o) {
  var r = b3Rec(o, {}), ts = b3Pick(o, ['ts', 'time', 'at', 'start']), tl = b3Pick(o, ['tools_used', 'tools']);
  var c = b3Pick(o, ['compacted', 'compactions']), ct = b3Pick(o, ['compacted_turns', 'turns_compacted']);
  var tools = Array.isArray(tl) ? tl : typeof tl === 'string' ? tl.split(/[\s,]+/) : [];
  r.t = b3Time(ts);
  r.name = typeof o.name === 'string' ? o.name.slice(0, 120) : '';
  if (!r.day) r.day = b3Day(ts);
  r.tools = tools.map(function (x) { return String(b3Obj(x) ? x.name || '' : x).slice(0, 60); }).filter(Boolean).slice(0, 12);
  r.turns = b3Num(ct) || (typeof c === 'number' && c > 1 ? c : 0);
  r.isCompacted = c === true || b3Num(c) > 0 || r.turns > 0;
  r.isError = r.errors > 0;
  return r;
}
/* d = คำตอบของ /api/usage · opt = {days, models: [id ตามลำดับของ /api/projects], today: "YYYY-MM-DD"}
   สีของโมเดล = ตำแหน่งในลำดับคงที่ (รายชื่อโมเดลของ router ก่อน แล้วชื่ออื่นเรียงตามตัวอักษร) — เปลี่ยนช่วง 7/30 วัน
   หรือโมเดลไหนไม่มีข้อมูล สีของตัวที่เหลือต้องไม่เปลี่ยน · เกิน 5 สี = รวมเป็น "อื่นๆ" (ไม่สร้างสีที่ 6) */
function b3Usage(d, opt) {
  d = b3Obj(d) ? d : {};
  opt = opt || {};
  var recent = [];
  for (var i = 0; i < B3_REC_KEYS.length; i++) {
    var rv = d[B3_REC_KEYS[i]];
    if (Array.isArray(rv)) { recent = rv.filter(b3Obj).map(b3Sess); break; }
  }
  recent.sort(function (a, b) { return (isNaN(b.t) ? 0 : b.t) - (isNaN(a.t) ? 0 : a.t); });
  var rows = b3Rows(d) || recent;
  var n = Math.max(1, Math.min(400, Math.round(b3Num(opt.days) || b3Num(d.days) || 7)));
  var days = b3Days(n, b3Day(b3Pick(d, ['to', 'until', 'end'])) || opt.today || ''), at = {};
  days.forEach(function (k, j) { at[k] = j; });
  function zero() { return days.map(function () { return 0; }); }
  var M = {}, P = {}, tot = { requests: 0, prompt: 0, cached: 0, completion: 0, errors: 0, compacted: 0, wall: 0 };
  rows.forEach(function (r) {
    if (!Object.prototype.hasOwnProperty.call(at, r.day)) return;
    var j = at[r.day], s = M[r.model];
    if (!s) s = M[r.model] = { tokens: zero(), gn: zero(), gt: zero(), gN: 0, gT: 0, pN: 0, pT: 0, prompt: 0, cached: 0, completion: 0, requests: 0 };
    s.tokens[j] += r.prompt + r.completion;
    s.prompt += r.prompt; s.cached += r.cached; s.completion += r.completion; s.requests += r.requests;
    /* ความเร็วเฉลี่ย = โทเค็นรวม ÷ เวลารวม (เวลา = โทเค็น ÷ tok/s ของแถวนั้น) — สูตรเดียวกับ hub_usage._done ค่าเฉลี่ยข้ามวัน
       จึงตรงกับ per_model ของ hub พอดี (เฉลี่ยเลข tok/s ตรงๆ คำตอบสั้นๆ 5 โทเค็นจะดึงค่าเพี้ยน)
       อ่านพรอมต์ถ่วงด้วยโทเค็นที่ต้องคำนวณจริง (prompt − cached) เหมือน hub */
    if (r.gen > 0) {
      var w = r.completion > 0 ? r.completion : Math.max(1, r.requests);
      s.gn[j] += w; s.gt[j] += w / r.gen; s.gN += w; s.gT += w / r.gen;
    }
    if (r.ptps > 0) {
      var w2 = r.prompt - r.cached > 0 ? r.prompt - r.cached : r.prompt > 0 ? r.prompt : Math.max(1, r.requests);
      s.pN += w2; s.pT += w2 / r.ptps;
    }
    if (r.project) {
      var p = P[r.project] || (P[r.project] = { project: r.project, tokens: 0, prompt: 0, completion: 0, requests: 0 });
      p.tokens += r.prompt + r.completion; p.prompt += r.prompt; p.completion += r.completion; p.requests += r.requests;
    }
    for (var k in tot) tot[k] += r[k] || 0;
  });
  var tt = b3Pick(d, ['totals', 'total', 'summary']);
  if (b3Obj(tt)) { var tr = b3Rec(tt, {}); for (var k2 in tot) if (!tot[k2] && tr[k2]) tot[k2] = tr[k2]; }
  var projects = Object.keys(P).map(function (k) { return P[k]; });
  if (!projects.length) {
    /* hub_usage.aggregate ส่ง per_project[] ที่มี name (ชื่อที่ผู้ใช้ตั้ง) มาด้วย — ใช้เมื่อโปรเจกต์ถูกลบไปแล้ว (ไม่อยู่ใน /api/projects) */
    projects = b3List(b3Pick(d, ['per_project', 'by_project', 'projects'])).map(function (o) {
      var r = b3Rec(o, { project: o._k || '' });
      return { project: r.project, name: typeof o.name === 'string' ? o.name.slice(0, 120) : '', tokens: r.prompt + r.completion,
        prompt: r.prompt, completion: r.completion, requests: r.requests };
    }).filter(function (p) { return p.project && (p.tokens || p.requests); });
  }
  projects.sort(function (a, b) { return b.tokens - a.tokens || b.requests - a.requests || (a.project < b.project ? -1 : 1); });
  var order = (opt.models || []).map(String).filter(Boolean);
  Object.keys(M).filter(function (x) { return x && order.indexOf(x) < 0; }).sort().forEach(function (x) { order.push(x); });
  if (M['']) order.push('');
  var series = [];
  order.forEach(function (m, slot) {
    var s = M[m];
    if (!s || !(s.prompt + s.completion + s.requests)) return;
    series.push({ model: m, slot: slot < B3_SLOTS ? slot : -1, tokens: s.tokens, total: s.prompt + s.completion,
      prompt: s.prompt, cached: s.cached, completion: s.completion, requests: s.requests,
      tps: s.gn.map(function (w, j) { return s.gt[j] > 0 ? w / s.gt[j] : null; }),
      avgTps: s.gT > 0 ? s.gN / s.gT : null, avgPtps: s.pT > 0 ? s.pN / s.pT : null });
  });
  var stack = series.filter(function (s) { return s.slot >= 0; }), rest = series.filter(function (s) { return s.slot < 0; });
  if (rest.length) {
    stack.push({ model: '*', other: true, slot: -1, names: rest.map(function (s) { return s.model; }),
      tokens: days.map(function (_, j) { return rest.reduce(function (a, s) { return a + s.tokens[j]; }, 0); }),
      total: rest.reduce(function (a, s) { return a + s.total; }, 0) });
  }
  return { days: days, series: series, stack: stack, projects: projects, totals: tot, recent: recent.slice(0, 50),
    empty: !(tot.requests || tot.prompt || tot.completion) && !recent.length };
}
/* เส้นแกนที่ปัดเป็นเลขกลมๆ (1/2/2.5/5 × 10^k) และตัวสุดท้าย ≥ ค่าสูงสุด */
function b3Ticks(max, count) {
  max = +max || 0;
  if (max <= 0) return [0, 1];
  var raw = max / (count || 4), p = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10)), f = raw / p;
  var step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p, out = [0];
  while (out[out.length - 1] < max - 1e-9 && out.length < 24) out.push(+(out.length * step).toPrecision(12));
  return out;
}
/* ตัวเลข: ≥ 10,000 ย่อ (12K, 1.2M) เว้นแต่ full — ตารางใช้เต็ม แกน/ป้ายใช้ย่อ */
function b3Fmt(n, lang, digits, full) {
  n = b3Num(n);
  /* ตัวเลขใช้ en-US ไม่ใช่ en-GB: Edge ย่อแบบ en-GB เป็นตัวเล็ก "2.6m" ซึ่งอ่านปนกับ "min" ของเวลา (วันที่ยังใช้ en-GB) */
  var loc = lang === 'th' ? 'th-TH' : 'en-US', a = Math.abs(n);
  try {
    if (!full && a >= 10000) return new Intl.NumberFormat(loc, { notation: 'compact', maximumFractionDigits: a >= 1e5 && a < 1e6 ? 0 : 1 }).format(n);
    return new Intl.NumberFormat(loc, { maximumFractionDigits: digits != null ? digits : a < 10 ? 1 : 0 }).format(n);
  } catch (e) { return String(Math.round(n)); }
}
/* วินาที → "850 ms" / "4.2 วิ" / "3 นาที" / "2 ชม. 5 นาที" (u = แม่แบบของหน้า: {ms, s, min, h} มี %s) */
function b3Dur(sec, u) {
  sec = b3Num(sec);
  if (sec <= 0) return '';
  if (sec < 1) return u.ms.replace('%s', String(Math.round(sec * 1000)));
  if (sec < 60) return u.s.replace('%s', String(sec < 10 ? Math.round(sec * 10) / 10 : Math.round(sec)));
  var m = Math.round(sec / 60);
  if (m < 60) return u.min.replace('%s', String(m));
  var h = Math.floor(m / 60), mm = m % 60;
  return u.h.replace('%s', String(h)) + (mm ? ' ' + u.min.replace('%s', String(mm)) : '');
}
function b3Bytes(b) {
  b = b3Num(b);
  if (b <= 0) return '0 GB';
  var gb = b / 1073741824, mb = b / 1048576;
  if (gb >= 100) return Math.round(gb) + ' GB';
  if (gb >= 1) return Math.round(gb * 10) / 10 + ' GB';
  return (mb >= 10 ? Math.round(mb) : Math.round(mb * 10) / 10) + ' MB';
}
/* ขนาดจากเซิร์ฟเวอร์ → ไบต์ ดูหน่วยจากชื่อฟิลด์ (free_gb, total_mb, used_bytes …) ไม่มีหน่วยในชื่อ = เดาจากขนาด
   (> 10^7 = ไบต์, > 4096 = MB เช่น VRAM 6141 จาก nvidia-smi, ไม่งั้น GB เช่น ดิสก์ 476) */
function b3SizeOf(o, base) {
  var units = [['_bytes', 1], ['_b', 1], ['_kb', 1024], ['_kib', 1024], ['_mb', 1048576], ['_mib', 1048576],
    ['_gb', 1073741824], ['_gib', 1073741824]];
  for (var i = 0; i < units.length; i++) if (b3Has(o, base + units[i][0])) return b3Num(o[base + units[i][0]]) * units[i][1];
  if (b3Has(o, base) && typeof o[base] !== 'object') {
    var v = b3Num(o[base]);
    return v > 1e7 ? v : v > 4096 ? v * 1048576 : v * 1073741824;
  }
  return null;
}
function b3SizeAny(o, bases) {
  for (var i = 0; i < bases.length; i++) { var v = b3SizeOf(o, bases[i]); if (v != null) return v; }
  return null;
}

/* ---------------------------------------------------------------- ตรวจระบบ (/api/doctor) */
var B3_SVC = [
  ['router', /^(router|llama|llama[-_]?(server|router)|upstream|model[-_]?server)$/i, 8099],
  ['mcp', /^(mcp|mcp[-_]?local|local[-_]?tools?)$/i, 8792],
  ['web', /^(web|websearch|web[-_]?search|mcp[-_]?web(search)?)$/i, 8791],
  ['embed', /^(embed|embedding|embeddings)$/i, 8093],
  ['stt', /^(stt|speech|voice|whisper|transcribe)$/i, 8795],
  ['sched', /^(sched|scheduler|tasks?)$/i, 0],
  ['gateway', /^(gateway|gw)$/i, 8780],
  ['hub', /^(hub|hub[-_]?ports?|ports|projects)$/i, 8100]
];
function b3SvcKind(id, port) {
  id = String(id == null ? '' : id);
  port = b3Num(port);
  for (var i = 0; i < B3_SVC.length; i++) if (B3_SVC[i][1].test(id)) return B3_SVC[i][0];
  for (var j = 0; j < B3_SVC.length; j++) if (port && B3_SVC[j][2] === port) return B3_SVC[j][0];
  return '';
}
/* สถานะ 4 ระดับ: ok | warn (ช้า/กำลังโหลด/ไม่ขยับ/ไม่มีไฟล์โมเดลเสริม) | bad (ไม่ทำงาน/โทเคนไม่ตรง/ตรวจไม่ทัน/ไม่มีของที่ต้องมี)
   | off (ปิดไว้โดยตั้งใจ — ไม่นับเป็นปัญหา) · จัดกลุ่มตาม hub_doctor._build (bad = down|auth|timeout|error|missing,
   warn = warn|stale|loading|absent) — คำเฉพาะ (auth, stale …) เก็บไว้ใน raw ให้หน้าเขียนคำที่ตรงกว่าได้ */
function b3State(s) {
  var v = b3Pick(s, ['state', 'status', 'health']);
  if (typeof v === 'boolean') return v ? 'ok' : 'bad';
  if (typeof v === 'string') {
    v = v.toLowerCase();
    if (/^(ok|up|ready|running|healthy|alive|pass(ed)?|good|online)$/.test(v)) return 'ok';
    if (/^(warn(ing)?|slow|degraded|loading|starting|stale|partial|busy|unknown|absent)$/.test(v)) return 'warn';
    if (/^(off|disabled|not[ _-]?installed|skipped|stopped|none|n\/a|unused|not[ _-]?configured)$/.test(v)) return 'off';
    return 'bad';
  }
  var ok = b3Pick(s, ['ok', 'up', 'alive', 'running', 'value']);
  if (typeof ok === 'boolean') return ok ? 'ok' : 'bad';
  return 'warn';
}
function b3Svc(o) {
  var id = String(b3Pick(o, ['id', 'key', 'service', 'name', '_k']) || '');
  var port = b3Num(b3Pick(o, ['port'])) || null;
  var lat = b3Pick(o, ['latency_ms', 'ms', 'rtt_ms', 'time_ms']);
  if (lat == null && b3Has(o, 'latency_s')) lat = b3Num(o.latency_s) * 1000;
  if (lat == null && b3Has(o, 'latency')) lat = o.latency;
  var ports = Array.isArray(o.ports) ? o.ports.map(function (p) {
    return b3Obj(p) ? { port: b3Num(p.port), state: b3State(p) } : { port: b3Num(p), state: 'ok' };
  }) : null;
  var state = b3State(o);
  if (ports && ports.length && !b3Has(o, 'state') && !b3Has(o, 'status') && !b3Has(o, 'ok')) {
    var good = ports.filter(function (p) { return p.state === 'ok'; }).length;
    state = good === ports.length ? 'ok' : good ? 'warn' : 'bad';
  }
  var loaded = b3Pick(o, ['models_loaded', 'loaded_models', 'loaded']);
  if (!Array.isArray(loaded)) {
    var ms = b3Pick(o, ['models']);
    loaded = Array.isArray(ms) ? ms.filter(function (m) {
      return !b3Obj(m) || !m.status || /loaded/i.test(typeof m.status === 'string' ? m.status : String(m.status.value || ''));
    }) : null;
  }
  var age = b3Pick(o, ['heartbeat_age_s', 'age_s', 'heartbeat_age', 'last_beat_s']), raw = b3Pick(o, ['state', 'status', 'health']);
  /* detail ที่เป็นคำของเครื่อง ("ready", "no_model") ไม่ใช่ประโยคสำหรับคน — ไม่แสดง (หน้าไทยจะมีคำอังกฤษโดดๆ) */
  var detail = String(b3Pick(o, ['detail', 'message', 'error', 'reason', 'note', 'heartbeat_message']) || '').slice(0, 300);
  if (/^[a-z_]{1,24}$/.test(detail)) detail = '';
  var mf = Array.isArray(o.modules_failed) ? o.modules_failed.map(String).slice(0, 10) : [];
  return {
    id: id, kind: b3SvcKind(id, port), name: String(b3Pick(o, ['label', 'title', 'name']) || id).slice(0, 80),
    port: port, state: state, raw: typeof raw === 'string' ? raw.toLowerCase().slice(0, 24) : '',
    latency: lat == null ? null : b3Num(lat), detail: detail,
    loaded: loaded ? loaded.map(function (m) { return b3Short(b3Obj(m) ? m.id || m.name || m.model || '' : m); }).filter(Boolean) : null,
    age: age == null ? null : b3Num(age), ports: ports, version: String(b3Pick(o, ['version', 'build']) || '').slice(0, 80),
    provider: typeof o.provider === 'string' && /^[\w .-]{1,24}$/.test(o.provider) ? o.provider : '',
    device: typeof o.device === 'string' && /^[a-z]{2,8}$/i.test(o.device) ? o.device.toUpperCase() : '',
    modulesFailed: mf, upstreamOk: typeof o.upstream_ok === 'boolean' ? o.upstream_ok : null,
    busy: typeof o.keep_awake === 'number' && o.keep_awake > 0 ? o.keep_awake : 0
  };
}
/* hub_doctor._fixes ส่ง {id, th, en} ไม่มีระดับความรุนแรง — จัดระดับจาก id เอง: บริการล่ม = bad,
   สิ่งที่รอผู้ใช้ทำเอง (วาง Brave key, ติดตั้ง Docker ใหม่) = info (ไม่นับเป็น "ปัญหา" ไม่งั้นหน้าขึ้นเหลืองตลอดกาล
   ทั้งที่ทุกบริการปกติ) · id อื่น/ใหม่ = warn */
var B3_FIX_LEVEL = { router: 'bad', router_auth: 'bad', mcp_local: 'bad', mcp_web: 'bad', mcp_auth: 'bad', embed: 'bad',
  stt: 'bad', scheduler: 'bad', gateway: 'bad', brave: 'info', docker: 'info' };
/* คำแนะนำ: array ของข้อความ หรือ {th, en, severity, service} หรือ {th: [...], en: [...]} — เลือกภาษาของหน้า ไม่มีก็ใช้อีกภาษา */
function b3Fixes(v, lang) {
  var other = lang === 'th' ? 'en' : 'th';
  if (b3Obj(v) && (Array.isArray(v[lang]) || Array.isArray(v[other]))) v = Array.isArray(v[lang]) ? v[lang] : v[other];
  var out = [];
  (Array.isArray(v) ? v : []).forEach(function (o) {
    var s = typeof o === 'string' ? o : b3Obj(o) ? String(b3Pick(o, [lang, 'text_' + lang, lang + '_text', 'text', 'message',
      'fix', 'hint', other, 'text_' + other]) || '') : '';
    s = s.trim();
    if (!s) return;
    var lv = String(b3Obj(o) && b3Pick(o, ['severity', 'level', 'kind']) || '').toLowerCase(), id = b3Obj(o) ? String(o.id || '') : '';
    if (!lv && Object.prototype.hasOwnProperty.call(B3_FIX_LEVEL, id)) lv = B3_FIX_LEVEL[id];
    out.push({ text: s.slice(0, 500), level: /crit|err|bad|high|danger|fail/.test(lv) ? 'bad' : /info|low|tip|hint/.test(lv) ? 'info' : 'warn',
      service: String(b3Obj(o) && b3Pick(o, ['service', 'target']) || ''), id: id.slice(0, 40) });
  });
  /* เรียงแบบคงลำดับเดิมภายในระดับ: ปัญหาจริงขึ้นก่อน คำแนะนำทั่วไป (info) ไปท้าย */
  var rank = { bad: 0, warn: 1, info: 2 };
  out.forEach(function (f, i) { f._i = i; });
  out.sort(function (a, b) { return rank[a.level] - rank[b.level] || a._i - b._i; });
  out.forEach(function (f) { delete f._i; });
  return out.slice(0, 30);
}
/* why = เหตุที่ตรวจ GPU ไม่ได้ (hub_doctor: gpu = null + _meta.gpu_error เช่น "timeout") — ไม่ใช่ "ไม่มี GPU" */
function b3Gpus(v, why) {
  var reason = '';
  if (b3Obj(v)) {
    if (v.available === false || v.ok === false) reason = String(b3Pick(v, ['reason', 'error', 'detail']) || '');
    if (Array.isArray(v.gpus)) v = v.gpus; else if (Array.isArray(v.devices)) v = v.devices;
  }
  if (v == null && why) reason = String(why);
  var list = Array.isArray(v) ? v.filter(b3Obj) : b3Obj(v) && b3Has(v, 'name') ? [v] : [];
  return { reason: reason.slice(0, 200), list: list.map(function (g) {
    var total = b3SizeAny(g, ['memory_total', 'mem_total', 'vram_total', 'total']);
    var used = b3SizeAny(g, ['memory_used', 'mem_used', 'vram_used', 'used']);
    var free = b3SizeAny(g, ['memory_free', 'mem_free', 'vram_free', 'free']);
    if (used == null && total != null && free != null) used = Math.max(0, total - free);
    var temp = b3Pick(g, ['temp_c', 'temperature_c', 'temperature', 'temp']), util = b3Pick(g, ['util_pct', 'utilization', 'util']);
    return { name: String(b3Pick(g, ['name', 'model', 'short']) || 'GPU').slice(0, 80),
      driver: String(b3Pick(g, ['driver', 'driver_version']) || '').slice(0, 40),
      total: total, used: used, temp: temp == null ? null : b3Num(temp), util: util == null ? null : b3Num(util) };
  }) };
}
/* แรม + commit: แบนราบ (ram_free_gb, commit_total_mb …) หรือซ้อน ({ram: {free_gb, total_gb}, commit: {...}}) */
function b3Mem(v) {
  var out = [];
  if (!b3Obj(v)) return out;
  [['ram', ['ram', 'phys', 'physical', 'memory', '']], ['commit', ['commit', 'pagefile', 'virtual']]].forEach(function (g) {
    for (var i = 0; i < g[1].length; i++) {
      var p = g[1][i], src = p && b3Obj(v[p]) ? v[p] : v, pre = p && !b3Obj(v[p]) ? p + '_' : '';
      if (!p && out.length) break;
      var total = b3SizeAny(src, [pre + 'total', pre + 'limit']), free = b3SizeAny(src, [pre + 'free', pre + 'available', pre + 'avail']);
      if (total != null || free != null) { out.push({ kind: g[0], total: total, free: free }); break; }
    }
  });
  return out;
}
function b3Disks(v) {
  return b3List(v).map(function (o) {
    var drive = String(b3Pick(o, ['drive', 'name', 'mount', 'path', '_k']) || '').replace(/[\\\/]+$/, '');
    if (/^[a-z]$/i.test(drive)) drive += ':';
    var gone = o.present === false || o.exists === false || o.ok === false;
    /* ระดับที่ hub ตัดสินมาเองต่อแถว (level/severity หรือ low: true) — ยังไม่มีใน hub_doctor ตอนนี้ แต่ถ้ามีจะชนะทุกอย่าง (b3MeterLv) */
    var hl = b3Lv(b3Pick(o, ['level', 'severity']));
    if (hl == null && typeof o.low === 'boolean') hl = o.low ? 'warn' : '';
    return { drive: drive.toUpperCase().slice(0, 40), total: b3SizeAny(o, ['total']), free: b3SizeAny(o, ['free', 'available']),
      missing: gone, note: String(b3Pick(o, ['error', 'reason', 'note']) || '').slice(0, 160), hubLevel: hl };
  }).filter(function (x) { return x.drive && (x.total != null || x.free != null || x.missing); });
}
/* คำระดับของ hub → '' | 'warn' | 'bad' · null = hub ไม่ได้บอก (คนละความหมายกับ '' ที่แปลว่า hub บอกว่าปกติ) */
function b3Lv(v) {
  if (typeof v !== 'string' || !v) return null;
  v = v.toLowerCase();
  return /crit|err|bad|high|danger|fail/.test(v) ? 'bad' : /warn|amber|medium/.test(v) ? 'warn' : /ok|info|none|normal|good/.test(v) ? '' : null;
}
/* สีของแถบดิสก์/หน่วยความจำ = คำตัดสินของ hub เท่านั้น
   ทำไม (integ b3 2026-10-06): หน้าเคยตัดสินเองจาก % ที่ว่าง (< 15% อำพัน, < 7% แดง) — C: ว่าง 26 GB (5.5%) กับ E: 11.5 GB
   ขึ้นแดง "เหลือน้อย" ทั้งที่ hub_doctor ใช้เกณฑ์ 10 GB ไม่มีคำแนะนำเรื่องดิสก์ และป้ายสรุปบอก "ทุกบริการทำงานปกติ" = สัญญาณขัดกัน
   ลำดับ: ระดับที่ hub ใส่มากับแถวเอง → คำแนะนำของ hub ที่พูดถึงแถวนั้น (id disk/commit หรือข้อความที่ไม่มี id) ใช้ระดับของคำแนะนำ
   → hub ไม่ได้ส่งรายการคำแนะนำมาเลย (hubJudged = false) จึงใช้เกณฑ์เดียวกับ hub_doctor (DISK_LOW_GB 10, COMMIT_LOW_GB 8) เป็นอำพัน
   หน้าไม่ตัดสินเป็นแดงเองเด็ดขาด · แรม: hub ไม่มีเกณฑ์ (โมเดลที่โหลดอยู่กินแรมเป็นเรื่องปกติ) → แถบสีกลางเสมอ */
var B3_DISK_LOW_GB = 10, B3_COMMIT_LOW_GB = 8;
/* ไดรฟ์ที่คำแนะนำพูดถึง = ไดรฟ์แรกในข้อความ ("ดิสก์ C: เหลือน้อย — ย้าย cache ไป D: หรือ E:" = C: เท่านั้น)
   ไม่นับ path ("C:\LLM\secrets\…" ในคำแนะนำเรื่อง Brave key) */
function b3FixDrive(text) {
  var m = /(?:^|[^A-Za-z0-9_])([A-Za-z]):(?![\\\/\w])/.exec(String(text || ''));
  return m ? m[1].toUpperCase() + ':' : '';
}
function b3MeterLv(n, hubJudged) {
  var GB = 1073741824;
  function fromFix(test) {
    var lv = null;
    n.fixes.forEach(function (f) {
      if (f.level === 'info' || !test(f)) return;
      lv = f.level === 'bad' || lv === 'bad' ? 'bad' : 'warn';
    });
    return lv;
  }
  n.disks.forEach(function (k) {
    var lv = k.hubLevel;
    if (lv == null) lv = fromFix(function (f) {
      return (f.id === 'disk' || (!f.id && /ดิสก์|disk|drive/i.test(f.text))) && b3FixDrive(f.text) === k.drive;
    });
    if (lv == null && !hubJudged && !k.missing && k.free != null && k.free < B3_DISK_LOW_GB * GB) lv = 'warn';
    k.level = lv || '';
    delete k.hubLevel;
  });
  n.mem.forEach(function (m) {
    var lv = m.kind === 'commit' ? fromFix(function (f) { return f.id === 'commit' || (!f.id && /commit/i.test(f.text)); }) : null;
    if (lv == null && !hubJudged && m.kind === 'commit' && m.free != null && m.free < B3_COMMIT_LOW_GB * GB) lv = 'warn';
    m.level = lv || '';
  });
}
/* ไฟล์คีย์/โทเค็น: ใช้แค่ "มี/ไม่มี" — ค่าที่ไม่ใช่ yes/true ไม่ถูกแสดงเด็ดขาด (เผื่อมีใครส่งค่าลับมาผิดช่อง) */
function b3Yes(p) { return p === true || p === 1 || /^(yes|true|present|ok|found)$/i.test(String(p == null ? '' : p)); }
/* ข้อความอื่นที่ไม่ใช่คำปฏิเสธ (เช่น ค่าลับที่หลุดมา) = มีไฟล์ — นับว่า "มี" แต่ตัวค่าไม่ถูกเก็บ/แสดงที่ไหนเลย */
function b3Present(p) {
  return b3Yes(p) || (typeof p === 'string' && p.length > 0 && !/^(no|false|missing|absent|none|0)$/i.test(p));
}
function b3Keys(v) {
  return b3List(v, true).map(function (o) {
    return { name: String(b3Pick(o, ['name', 'file', 'path', '_k']) || '').replace(/^.*[\\\/]/, '').slice(0, 80),
      present: b3Present(b3Pick(o, ['present', 'exists', 'ok', 'found', 'value'])) };
  }).filter(function (k) { return k.name; }).slice(0, 30);
}
function b3Models(v) {
  if (b3Obj(v)) v = Array.isArray(v.files) ? v.files : b3List(v, true).map(function (o) { return o.value != null ? { name: o._k, size: o.value } : o; });
  return (Array.isArray(v) ? v : []).map(function (m) {
    if (typeof m === 'string') return { name: m.replace(/^.*[\\\/]/, ''), size: null };
    if (!b3Obj(m)) return null;
    return { name: String(b3Pick(m, ['name', 'file', 'id', 'path', '_k']) || '').replace(/^.*[\\\/]/, '').slice(0, 120), size: b3SizeAny(m, ['size']) };
  }).filter(function (m) { return m && m.name; }).slice(0, 40);
}
function b3Errors(v) {
  var list = Array.isArray(v) ? v : b3Obj(v) && Array.isArray(v.lines) ? v.lines : [];
  return list.map(function (x) {
    if (typeof x === 'string') return { file: '', text: x };
    if (!b3Obj(x)) return null;
    return { file: String(b3Pick(x, ['file', 'log', 'source']) || '').replace(/^.*[\\\/]/, '').slice(0, 80),
      text: String(b3Pick(x, ['line', 'text', 'msg', 'message']) || '') };
  }).filter(function (e) { return e && e.text; }).slice(-20).map(function (e) { e.text = b3Scrub(e.text).slice(0, 600); return e; });
}
function b3Tests(v) {
  if (typeof v === 'string') return v.trim() ? { text: v.trim().slice(0, 200) } : null;
  if (!b3Obj(v)) return null;
  /* ลองทีละคีย์ — hub_doctor ส่ง failed เป็นรายชื่อเทสต์ (list) และจำนวนอยู่ที่ failures */
  function num(keys) {
    for (var i = 0; i < keys.length; i++) {
      var x = v[keys[i]];
      if (typeof x === 'number' || (typeof x === 'string' && /^\d+$/.test(x))) return b3Num(x);
    }
    return null;
  }
  var r = { passed: num(['passed', 'ok', 'pass', 'tests_ok']), skipped: num(['skipped', 'skip']), failed: num(['failures', 'failed', 'fail']),
    errors: num(['errors']), ts: b3Pick(v, ['ts', 'at', 'when', 'time', 'finished']), text: String(b3Pick(v, ['summary', 'text', 'result']) || '').slice(0, 200),
    names: Array.isArray(v.failed) ? v.failed.map(function (x) { return b3Scrub(String(x)).slice(0, 160); }).slice(0, 10) : [] };
  if (typeof v.ok === 'boolean') r.ok = v.ok;
  return r.passed == null && r.failed == null && !r.text && r.ok == null ? null : r;
}
var B3_DOC_KEYS = ['services', 'checks', 'service', 'fixes', 'suggestions', 'suggested_fixes', 'hints', 'gpu', 'gpus', 'memory',
  'ram', 'mem', 'disks', 'disk', 'drives', 'versions', 'models', 'model_files', 'secrets', 'keys', 'key_files', 'brave',
  'brave_key', 'brave_search', 'docker', 'errors', 'error_lines', 'log_errors', 'logs', 'tests', 'test_suite', 'test', 'ts',
  'checked_at', 'at', 'time', 'took_ms', 'elapsed_ms', 'ms', 'took_s', 'cached', 'age_s', 'ok', 'status', 'summary', 'lang',
  'python', 'llama_cpp', 'llamacpp', 'llama_build', 'platform', 'overall', 'text'];
function b3Secretish(k) { return /token|secret|passw|api[_-]?key|(^|[_-])keys?$|bearer|cookie|credential/i.test(String(k)); }
/* ค่าของคีย์ที่ไม่รู้จัก → ข้อความสั้น (คีย์ที่ชื่อเหมือนความลับ: ซ่อนค่า เหลือแค่ว่ามี/ไม่มี) */
function b3Brief(k, v) {
  if (b3Secretish(k)) return { yes: b3Obj(v) ? b3Present(b3Pick(v, ['present', 'exists', 'ok', 'value'])) : b3Present(v) };
  if (typeof v === 'boolean') return { yes: v };
  if (v == null) return { text: '—' };
  if (typeof v !== 'object') return { text: b3Scrub(String(v)).slice(0, 160) };
  var s = '';
  try {
    s = JSON.stringify(v, function (kk, vv) { return kk && b3Secretish(kk) && typeof vv !== 'boolean' ? (vv ? '***' : vv) : vv; });
  } catch (e) { s = ''; }
  return { text: b3Scrub(s || '').slice(0, 160) };
}
function b3Doctor(d, lang) {
  d = b3Obj(d) ? d : {};
  var used = {};
  B3_DOC_KEYS.forEach(function (k) { used[k] = 1; });
  var services = b3List(b3Pick(d, ['services', 'checks', 'service']), true).map(b3Svc);
  /* บริการที่วางไว้ระดับบนสุด ({"router": {"state": "ok"}, …}) ก็นับด้วย */
  Object.keys(d).forEach(function (k) {
    if (used[k] || !b3SvcKind(k) || !b3Obj(d[k])) return;
    if (!['state', 'status', 'ok', 'up', 'ports'].some(function (f) { return f in d[k]; })) return;
    var o = {}; for (var j in d[k]) o[j] = d[k][j];
    o._k = k; services.push(b3Svc(o)); used[k] = 1;
  });
  var rank = {}; B3_SVC.forEach(function (x, i) { rank[x[0]] = i; });
  services.sort(function (a, b) {
    var ra = a.kind in rank ? rank[a.kind] : 99, rb = b.kind in rank ? rank[b.kind] : 99;
    return ra - rb || (a.port || 0) - (b.port || 0) || (a.id < b.id ? -1 : 1);
  });
  var vv = b3Pick(d, ['versions']), versions = [];
  if (b3Obj(vv)) Object.keys(vv).forEach(function (k) {
    var x = vv[k];
    if (k === 'models') return;
    if (typeof x === 'string' || typeof x === 'number') versions.push([k, b3Scrub(String(x)).slice(0, 120)]);
    else if (b3Obj(x) && b3Pick(x, ['version', 'build'])) versions.push([k, b3Scrub(String(b3Pick(x, ['version', 'build']))).slice(0, 120)]);
  });
  [['llama_cpp', ['llama_cpp', 'llamacpp', 'llama_build']], ['python', ['python']], ['platform', ['platform']]].forEach(function (p) {
    var x = b3Pick(d, p[1]);
    if ((typeof x === 'string' || typeof x === 'number') && !versions.some(function (r) { return r[0] === p[0]; })) versions.push([p[0], String(x).slice(0, 120)]);
  });
  var g = b3Gpus(b3Pick(d, ['gpu', 'gpus']), b3Obj(d._meta) && d._meta.gpu_error ? String(d._meta.gpu_error).slice(0, 60) : '');
  var dk = b3Pick(d, ['docker']), docker = null;
  if (typeof dk === 'boolean') docker = { ok: dk, reason: '' };
  else if (b3Obj(dk)) {
    docker = { ok: b3Yes(b3Pick(dk, ['ok', 'usable', 'available', 'running'])),
      reason: b3Scrub(String(b3Pick(dk, ['reason', 'reason_' + lang, 'detail', 'error', 'message', 'reason_' + (lang === 'th' ? 'en' : 'th')]) || '')).slice(0, 200) };
  }
  var br = b3Pick(d, ['brave_key', 'brave', 'brave_search']);
  var took = b3Pick(d, ['took_ms', 'elapsed_ms', 'ms']);
  if (took == null && b3Has(d, 'took_s')) took = b3Num(d.took_s) * 1000;
  var extra = Object.keys(d).filter(function (k) { return !used[k] && k.charAt(0) !== '_'; }).slice(0, 20).map(function (k) { return [k, b3Brief(k, d[k])]; });
  var n = {
    ts: b3Time(b3Pick(d, ['ts', 'checked_at', 'at', 'time'])), took: took == null ? null : b3Num(took), cached: d.cached === true,
    services: services, fixes: b3Fixes(b3Pick(d, ['fixes', 'suggestions', 'suggested_fixes', 'hints']), lang),
    gpus: g.list, gpuReason: g.reason, mem: b3Mem(b3Pick(d, ['memory', 'ram', 'mem'])), disks: b3Disks(b3Pick(d, ['disks', 'disk', 'drives'])),
    versions: versions, models: b3Models(b3Pick(d, ['models', 'model_files']) || (b3Obj(vv) ? vv.models : null)),
    keys: b3Keys(b3Pick(d, ['secrets', 'keys', 'key_files'])),
    brave: br == null ? null : b3Obj(br) ? b3Yes(b3Pick(br, ['present', 'ok', 'value'])) : b3Yes(br), docker: docker,
    errors: b3Errors(b3Pick(d, ['errors', 'error_lines', 'log_errors', 'logs'])), tests: b3Tests(b3Pick(d, ['tests', 'test_suite', 'test'])),
    extra: extra
  };
  /* จำนวนปัญหา = ค่าที่มากกว่าระหว่าง "บริการที่ไม่ปกติ" กับ "คำแนะนำที่ไม่ใช่แค่ข้อมูล" — ดิสก์เหลือน้อยไม่ใช่บริการ
     แต่เป็นปัญหา, ส่วนบริการที่ล่มมักมีคำแนะนำคู่กันอยู่แล้ว (บวกกันจะนับซ้ำ) */
  var sick = services.filter(function (s) { return s.state === 'bad' || s.state === 'warn'; }).length;
  n.issues = Math.max(sick, n.fixes.filter(function (f) { return f.level !== 'info'; }).length);
  n.bad = services.some(function (s) { return s.state === 'bad'; }) || n.fixes.some(function (f) { return f.level === 'bad'; });
  n.tips = n.fixes.filter(function (f) { return f.level === 'info'; }).length;
  /* hub_doctor สรุปเองด้วย overall = ok | warn | error (error = router/hub ล่ม) — แต่ warn ของ hub นับคำแนะนำทุกข้อ
     (รวม Brave key/Docker ที่รอผู้ใช้) จึงใช้สีจากการนับของหน้าเอง และยกเป็นแดงเมื่อ hub บอก error เท่านั้น
     (จุดสีกับข้อความ "ทุกบริการทำงานปกติ" ต้องไม่ขัดกัน) */
  var ov = typeof d.overall === 'string' ? d.overall.toLowerCase() : '';
  n.overall = ov === 'error' || ov === 'bad' || n.bad ? 'bad' : n.issues ? 'warn' : 'ok';
  /* มีรายการคำแนะนำ (แม้ว่างเปล่า) = hub ตัดสินดิสก์/commit แล้ว — ไม่มีคำแนะนำเรื่องนั้นแปลว่าปกติ */
  b3MeterLv(n, b3Pick(d, ['fixes', 'suggestions', 'suggested_fixes', 'hints']) != null);
  return n;
}
/* ล้างความลับออกจากข้อความ (กันพลาดอีกชั้น): ค่าหลัง Bearer/Authorization, key=value ของ token/secret/password/api key,
   ?token= ใน URL, อีเมล, และสายอักขระสุ่มยาวๆ (มีท่อน ≥ 20 ตัวที่ปนตัวเลขกับตัวอักษร — ชื่อโมเดล/path ท่อนสั้นจึงไม่โดน) */
function b3Scrub(s) {
  return String(s == null ? '' : s)
    .replace(/\b(authorization|bearer)(\s*[:=]?\s*)(bearer\s+)?[^\s"',;]+/gi, '$1$2$3***')
    .replace(/\b([\w.-]*(?:token|secret|passw(?:or)?d?|api[_-]?key|apikey|access[_-]?key|private[_-]?key))(\s*["']?\s*[:=]\s*["']?)[^\s"',;&]+/gi, '$1$2***')
    .replace(/([?&](?:token|key|api_key|apikey|access_token|sig)=)[^&\s"']+/gi, '$1***')
    .replace(/[\w.+-]+@[\w-]+\.[\w.-]+/g, '***@***')
    .replace(/[A-Za-z0-9+\/_=-]{20,}/g, function (m) {
      return m.split(/[-_\/+=.]/).some(function (p) { return p.length >= 20 && /\d/.test(p) && /[A-Za-z]/.test(p); }) ? '***' : m;
    });
}
/* ชื่อแถวรุ่นซอฟต์แวร์ (คีย์ของ versions จาก hub → ชื่อที่คนอ่าน) — ใช้ทั้งบนหน้าและในรายงานที่คัดลอก */
function b3VerName(k, t) {
  return /llama/i.test(k) ? 'llama.cpp' : /^python/i.test(k) ? 'Python' : /^(platform|os|windows)$/i.test(k) ? t('b3_doc_os') : k;
}
function b3When(ms, lang) {
  if (!isFinite(ms)) return '';
  try {
    return new Date(ms).toLocaleString(lang === 'th' ? 'th-TH' : 'en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (e) { return new Date(ms).toISOString(); }
}
/* รายงานข้อความล้วนสำหรับปุ่ม "คัดลอกรายงาน" — t(key) ของหน้า (ไม่มี word joiner), u = หน่วยเวลา {ms, s, min, h}
   บรรทัดไฟล์คีย์ใช้ " — " ไม่ใช่ ":" (b3Scrub จะมองว่า "xxx.token: มี" เป็นค่าลับแล้วซ่อนคำว่า "มี") */
function b3Report(n, t, lang, u) {
  var L = [], st = { ok: t('b3_st_ok'), warn: t('b3_st_warn'), bad: t('b3_st_bad'), off: t('b3_st_off') };
  var yes = t('b3_doc_present'), no = t('b3_doc_missing');
  L.push(t('b3_doc_report_h'));
  if (isFinite(n.ts)) L.push(t('b3_doc_checked_at').replace('%s', b3When(n.ts, lang)) + (n.took != null ? ' · ' + b3Dur(n.took / 1000, u) : ''));
  L.push(n.issues ? t('b3_doc_issues').replace('%s', String(n.issues)) : n.tips ? t('b3_doc_ok_tips').replace('%s', String(n.tips)) : t('b3_doc_ok_all'));
  L.push('', '[' + t('b3_doc_svc') + ']');
  n.services.forEach(function (s) {
    var x = [s.word || st[s.state] || s.state];       // s.word = คำเดียวกับบนหน้า (หน้าเติมให้ก่อนเรียก)
    if (s.latency != null && !(s.kind === 'hub' && s.ports)) x.push(Math.round(s.latency) + ' ms');
    if (s.loaded && s.loaded.length) x.push(t('b3_loaded').replace('%s', s.loaded.join(', ')));
    if (s.age != null) x.push(t('b3_heartbeat').replace('%s', b3Dur(s.age, u) || '0'));
    if (s.ports && s.ports.length) {
      x.push(s.ports.map(function (p) { return p.port + (p.state === 'ok' ? '' : ' ' + (st[p.state] || p.state)); }).join(', '));
    }
    if (s.provider) x.push(s.provider);
    if (s.device) x.push(s.device);
    if (s.modulesFailed && s.modulesFailed.length) x.push(s.modulesFailed.join(', '));
    if (s.detail) x.push(s.detail);
    L.push('- ' + (s.label || s.name || s.id) + (s.port ? ' (' + s.port + ')' : '') + ' — ' + x.join(' · '));
  });
  if (n.fixes.length) { L.push('', '[' + t('b3_doc_fixes') + ']'); n.fixes.forEach(function (f) { L.push('- ' + f.text); }); }
  L.push('', '[' + t('b3_doc_machine') + ']');
  n.gpus.forEach(function (g) {
    L.push('- GPU ' + g.name + (g.driver ? ' · ' + t('b3_doc_driver').replace('%s', g.driver) : '') +
      (g.total != null && g.used != null ? ' · VRAM ' + b3Bytes(g.used) + ' / ' + b3Bytes(g.total) : '') + (g.temp != null ? ' · ' + Math.round(g.temp) + '°C' : ''));
  });
  if (!n.gpus.length) L.push('- ' + (n.gpuReason ? t('b3_doc_gpu_err').replace('%s', n.gpuReason) : t('b3_doc_nogpu')));
  /* "เหลือน้อย" ในรายงานตามระดับเดียวกับแถบบนหน้า (b3MeterLv = คำตัดสินของ hub) */
  var low = function (x) { return x.level ? ' · ' + t('b3_doc_low') : ''; };
  n.mem.forEach(function (m) {
    L.push('- ' + t(m.kind === 'ram' ? 'b3_doc_ram' : 'b3_doc_commit') + ' — ' + (m.free != null ? b3Bytes(m.free) : '?') + ' / ' + (m.total != null ? b3Bytes(m.total) : '?') + low(m));
  });
  n.disks.forEach(function (k) {
    L.push('- ' + t('b3_doc_disk').replace('%s', k.drive) + ' — ' + (k.missing ? t('b3_doc_disk_missing') : (k.free != null ? b3Bytes(k.free) : '?') + ' / ' + (k.total != null ? b3Bytes(k.total) : '?') + low(k)));
  });
  L.push('', '[' + t('b3_doc_soft') + ']');
  n.versions.forEach(function (v) { L.push('- ' + b3VerName(v[0], t) + ' — ' + v[1]); });
  n.models.forEach(function (m) { L.push('- ' + m.name + (m.size != null ? ' — ' + b3Bytes(m.size) : '')); });
  n.keys.forEach(function (k) { L.push('- ' + (k.label || k.name) + ' — ' + (k.present ? yes : no)); });
  if (n.brave != null && !n.keys.some(function (k) { return /brave/i.test(k.name); })) L.push('- ' + t('b3_doc_brave') + ' — ' + (n.brave ? yes : no));
  if (n.docker) L.push('- Docker — ' + (n.docker.ok ? t('b3_doc_usable') : t('b3_doc_unusable')) + (n.docker.reason ? ' (' + n.docker.reason + ')' : ''));
  if (n.tests) {
    var tx = n.tests.passed != null || n.tests.failed != null ? t('b3_doc_tests_v').replace('%1', String(n.tests.passed || 0))
      .replace('%2', String(n.tests.skipped || 0)).replace('%3', String((n.tests.failed || 0) + (n.tests.errors || 0))) : n.tests.text;
    L.push('- ' + t('b3_doc_tests') + ' — ' + tx + (isFinite(b3Time(n.tests.ts)) ? ' (' + b3When(b3Time(n.tests.ts), lang) + ')' : ''));
    (n.tests.names || []).forEach(function (nm) { L.push('  × ' + nm); });
  }
  if (n.errors.length) {
    L.push('', '[' + t('b3_doc_errors') + ']');
    n.errors.forEach(function (e) { L.push((e.file ? e.file + ' | ' : '') + e.text); });
  }
  if (n.extra.length) {
    L.push('', '[' + t('b3_doc_other') + ']');
    n.extra.forEach(function (x) { L.push('- ' + x[0] + ' — ' + (x[1].yes != null ? (x[1].yes ? yes : no) : x[1].text)); });
  }
  return b3Scrub(L.join('\n')).replace(/⁠/g, '');
}"""


def _inject_b3(tpl):
    # fill() ของ hub แทน __T_x__/__LANG__/__THEME__/__FONT__/__T_JSON__ ทั่วทั้งหน้า — ก้อน JS นี้ต้องไม่มีคำเหล่านี้
    assert tpl.count("__QW_B3__") == 1
    for bad in ('"""', "__T_", "__LANG__", "__THEME__", "__FONT__", "</script"):
        assert bad not in _B3_JS, bad
    return tpl.replace("__QW_B3__", _B3_JS)


PAGE = _inject_b3(PAGE)
