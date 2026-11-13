"""mt health — 统一健康检查与自愈（v1）。

覆盖对象与口径（设计说明见 README.md）：
- FreeLLMAPI（:3001）：带 unified key 鉴权测活 + start.sh 自愈 + 复验。
  * key 只在运行时从 sqlite 读入内存，永不打印、永不写日志。
  * 测活走直连（等价 curl --noproxy '*'），避免本机出站代理把 localhost
    流量拐走造成假超时（2026-10-20 误重启教训）。
  * 判活标准：HTTP 200 且响应含 "data"。401≠挂掉：进程有响应但无 "data"
    时只报 DEGRADED、不重启（重启解决不了鉴权/应用层问题）。
  * 连接拒绝/超时（无任何响应）才判 DOWN 并自愈：bash start.sh（幂等），
    等 5 秒后同口径复验。
- PerkRadar（:38471）：探活 /api/health，200 为活。本轮只探不愈——
  其拉起由 services-keepalive cron 在管，避免双路同时拉起打架；
  mt 接管其自愈是后续切换事项（见 README 路线图）。
- n8n（:5678）：探活 / ，200/401 为活。同样只探不愈（同上）。

退出码：0 = 全部健康（含自愈成功）；1 = 有对象仍异常。
"""

import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

FREELLM_DIR = os.path.expanduser(
    os.environ.get("MT_FREELLMAPI_HOME", "~/freellmapi")
)
FREELLM_DB = os.path.join(FREELLM_DIR, "server/data/freeapi.db")
FREELLM_URL = os.environ.get("MT_FREELLMAPI_URL", "http://localhost:3001/v1/models")
FREELLM_START = os.path.join(FREELLM_DIR, "start.sh")
FREELLM_LOG = os.path.join(FREELLM_DIR, "server/data/server.log")

PERKRADAR_URL = os.environ.get("MT_PERKRADAR_URL", "http://127.0.0.1:38471/api/health")
N8N_URL = os.environ.get("MT_N8N_URL", "http://127.0.0.1:5678/")

PROBE_TIMEOUT = 5

# localhost 直连 opener：空 ProxyHandler 等价于 curl --noproxy '*'
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def probe(url, headers=None, timeout=PROBE_TIMEOUT):
    """返回 (http_status 或 None, body_text, error_text)。None = 无任何响应。"""
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body, ""
    except Exception as e:  # 连接拒绝 / 超时 / DNS 等：无响应
        return None, "", f"{type(e).__name__}: {e}"


def _freellm_key():
    """运行时从 sqlite 读 unified key（只进内存，永不输出）。"""
    con = sqlite3.connect(f"file:{FREELLM_DB}?mode=ro", uri=True)
    try:
        row = con.execute(
            "SELECT value FROM settings WHERE key='unified_api_key'"
        ).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def _freellm_state(key):
    """返回 (state, detail)：state ∈ ok / degraded / down。"""
    status, body, err = probe(
        FREELLM_URL, headers={"Authorization": f"Bearer {key}"}
    )
    if status == 200 and '"data"' in body:
        return "ok", 'HTTP 200, "data" present'
    if status is not None:
        return "degraded", f"HTTP {status} but no \"data\" in response"
    return "down", err or "no response"


def _log_tail(path, n=10):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        return lines[-n:]
    except OSError:
        return []


def check_freellmapi(heal=True):
    """返回 (final_state, lines)：final_state ∈ ok / degraded / down。"""
    lines = []
    try:
        key = _freellm_key()
    except Exception as e:
        return "down", [f"[FAIL]   freellmapi  cannot read unified key from sqlite ({e})"]
    if not key:
        return "down", ["[FAIL]   freellmapi  unified key missing in sqlite settings"]

    state, detail = _freellm_state(key)
    if state == "ok":
        return "ok", [f"[OK]     freellmapi  {FREELLM_URL}  authenticated, {detail}"]
    if state == "degraded":
        lines.append(
            f"[DEGRADED] freellmapi  {FREELLM_URL}  responding but unhealthy ({detail}); "
            "not restarting (401/no-data is not a dead process)"
        )
        return "degraded", lines

    # down：无任何响应 → 自愈
    lines.append(f"[DOWN]   freellmapi  {FREELLM_URL}  no response ({detail})")
    if not heal:
        lines.append("[SKIP]   freellmapi  --no-heal given, restart skipped")
        return "down", lines
    lines.append("[HEAL]   freellmapi  running start.sh ...")
    try:
        proc = subprocess.run(
            ["bash", FREELLM_START],
            capture_output=True, text=True, timeout=90,
        )
        out = (proc.stdout or "").strip().replace("\n", " ")[:200]
        if out:
            lines.append(f"         start.sh: {out}")
        if proc.returncode != 0:
            err = (proc.stderr or "").strip().replace("\n", " ")[:200]
            lines.append(f"[FAIL]   freellmapi  start.sh exit {proc.returncode} {err}")
            return "down", lines
    except Exception as e:
        lines.append(f"[FAIL]   freellmapi  start.sh failed to run ({e})")
        return "down", lines

    time.sleep(5)
    state2, detail2 = _freellm_state(key)
    if state2 == "ok":
        lines.append(f"[HEALED] freellmapi  restarted, re-check passed ({detail2})")
        return "ok", lines
    lines.append(f"[FAIL]   freellmapi  still unhealthy after restart ({detail2})")
    for ln in _log_tail(FREELLM_LOG, 10):
        lines.append(f"         server.log: {ln}")
    return "down", lines


def check_probe_only(name, url, ok_statuses, note):
    status, _body, err = probe(url)
    if status in ok_statuses:
        return "ok", [f"[OK]     {name:<10} {url}  HTTP {status}"]
    if status is not None:
        return "degraded", [
            f"[DEGRADED] {name:<10} {url}  HTTP {status} (probe-only in mt v1; {note})"
        ]
    return "down", [
        f"[DOWN]   {name:<10} {url}  no response ({err}; probe-only in mt v1; {note})"
    ]


def run(argv):
    heal = "--no-heal" not in argv
    print(f"mt health — {_now()} (heal={'on' if heal else 'off'})")
    results = []

    state, lines = check_freellmapi(heal=heal)
    results.append(state)
    for ln in lines:
        print(ln)

    for name, url, ok_statuses in (
        ("perkradar", PERKRADAR_URL, (200,)),
        ("n8n", N8N_URL, (200, 401)),
    ):
        state, lines = check_probe_only(
            name, url, ok_statuses,
            note="restart owned by services-keepalive cron",
        )
        results.append(state)
        for ln in lines:
            print(ln)

    healthy = sum(1 for s in results if s == "ok")
    print(f"summary: {healthy}/{len(results)} healthy")
    return 0 if healthy == len(results) else 1


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
