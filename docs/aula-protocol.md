# AULA WIN60 / WIN68 / WIN75 HE (Standard) – USB protocol notes

Device: `2e3c:c365` "WIN 68 HE", USB high-speed, 3 interfaces. Config channel = interface 2,
usage page **0xFF1B**, usage **0x91**, report ID **1**, 63-byte output/input reports.
Official web driver: `hed.aulacn.com` (not reachable from our network – 403 / HTTPS fails).

Based on the reverse engineering in **[AulaControl](https://github.com/sgtflixy/AulaControl)** (Apache-2.0,
WIN60 HE capture of the official driver), verified and extended on a WIN68 HE:

| Item | Value (WIN68 HE of the user's son) |
|---|---|
| `0d` info | `W669,34,KB,SI,SI2828HEARGB,V3.14.29`, build `Jul  2 2025,14:52:56` (two replies) |
| Official firmware download | "WIN68 HE Firmware" → `WIN68HE_标准版GD278CKB_W669KBSI_SI2828HEARGB_V30821.exe` = V3.08.21 (**older** than installed) |

## Frame
Payload (after report ID 1): `[CMD] [SUB] [00] [IDX] [LEN] [data…]`. Multi-packet replies: IDX = packet number,
LEN = data bytes in this packet (0x3a = 58 max).

## Commands seen in the official driver's connect sequence (all reads)
`0d` info · `01` status/heartbeat · `0e` fixed block · `19 80..89` 10 tables × 5 packets · `22 80` 40 packets ·
`24 02`, `24 01` · `18 80/82` 10 packets each · `0a`, `02` · `07 01` lighting · `08 01` second lighting block ·
`09 20/80/81` RGB tables (8 packets) · `21 … 18 04 00` · **`21 00 00 00 18 05 ROW COL`** per-key block (row 1–6,
col 0–15) · `21 … 01 09` · `25 00/02` · `26 00`.
Tool: `tools/aula_backup.py` replays all of them and stores request/replies as JSON (read-only).

## Lighting – `07` (verified on WIN68 HE with webcam)
- Read: `07 01` → `07 00 00 00 0c [EFFECT] [BRIGHT] [SPEED] [R G B] [R2 G2 B2] [?] 00 00`
- Write: `07 00 00 00 0c [same 12 data bytes]` – no reply. Read-back returns exactly what was written.
- `EFFECT 00` = static colour (R G B). Son's original: `0f 04 02 bb 79 79 ff d2 ca 06 00 00`
  (effect 0x0f = presumably per-key/custom colours from the `09` tables – shown as white/blue, ignores R G B).
- Restore verified: writing the original 12 bytes back returns the keyboard to its original look.

## Per-key block – `21 00 00 00 18 05 ROW COL`
Reply `21 00 00 00 0c 05 [6 bytes] … ROW COL`; on the son's board e.g. `aa aa 01 01` – per-key travel values
(AulaControl: trigger/reset travel in 0.01 mm). Write format per AulaControl: `21 00 00 00 18 ROW COL 00 08 …` –
**not yet verified on WIN68**.
