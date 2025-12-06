import os
import json
import time
import subprocess
import platform
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_INTERVAL = 60


def load_agent_config() -> Dict[str, Any]:
    cfg_path = Path(__file__).parent / "agent.json"
    cfg: Dict[str, Any] = {}
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            cfg = {}
    # Env overrides
    site = os.getenv("AGENT_SITE", cfg.get("site", "default"))
    server = os.getenv("AGENT_SERVER", cfg.get("server", "http://92.113.38.123:9999"))
    token = os.getenv("AGENT_TOKEN", cfg.get("token"))
    interval_sec = int(os.getenv("AGENT_INTERVAL_SEC", str(cfg.get("interval_sec", DEFAULT_INTERVAL))))
    loop = os.getenv("AGENT_LOOP", str(cfg.get("loop", "false"))).lower() in ("1", "true", "yes")
    cameras = cfg.get("cameras") if isinstance(cfg.get("cameras"), list) else []
    # Speedtest options (optional)
    speed_enabled = os.getenv("AGENT_SPEEDTEST", str(cfg.get("speedtest", "1"))).lower() in ("1", "true", "yes")
    try:
        speed_dl = int(os.getenv("AGENT_SPEEDTEST_DOWNLOAD_BYTES", str(cfg.get("speed_download_bytes", 1024 * 1024))))
    except Exception:
        speed_dl = 1024 * 1024
    try:
        speed_ul = int(os.getenv("AGENT_SPEEDTEST_UPLOAD_BYTES", str(cfg.get("speed_upload_bytes", 512 * 1024))))
    except Exception:
        speed_ul = 512 * 1024
    return {
        "site": site,
        "server": server.rstrip("/"),
        "token": token,
        "interval_sec": interval_sec,
        "loop": loop,
        "cameras": cameras,
        "speedtest": speed_enabled,
        "speed_download_bytes": speed_dl,
        "speed_upload_bytes": speed_ul,
    }


def ping_ip(ip: str, count: int = 2, timeout_ms: int = 800) -> Tuple[bool, Optional[float], Optional[float], str]:
    """
    Retorna: (reachable, avg_latency_ms, packet_loss_percent, raw_output_tail)
    """
    is_windows = platform.system().lower().startswith("win")
    if is_windows:
        cmd = ["ping", "-n", str(count), "-w", str(timeout_ms), ip]
    else:
        # -W 1 (segundos no Linux), -c count
        cmd = ["ping", "-c", str(count), "-W", "1", ip]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=max(3, count * 2))
        output = (proc.stdout or "") + (proc.stderr or "")
        reachable = proc.returncode == 0
        avg_ms: Optional[float] = None
        loss_pct: Optional[float] = None
        if is_windows:
            # Ex.: Média = 4ms
            for line in output.splitlines():
                line = line.strip()
                if "Média" in line or "Average" in line:
                    # pegar último número antes de 'ms'
                    import re as _re
                    m = _re.search(r"(\d+)ms", line)
                    if m:
                        avg_ms = float(m.group(1))
            # Perda: Lost = X (Y% loss)
            for line in output.splitlines():
                if "perdidos" in line.lower() or "lost" in line.lower():
                    import re as _re
                    m = _re.search(r"\((\d+)%", line)
                    if m:
                        loss_pct = float(m.group(1))
        else:
            # Linux/mac output: rtt min/avg/max/mdev = 0.345/0.456/...
            for line in output.splitlines():
                if "rtt min/avg/max" in line or "round-trip min/avg/max" in line:
                    try:
                        part = line.split("=")[-1].strip().split("/")
                        avg_ms = float(part[1])
                    except Exception:
                        pass
            for line in output.splitlines():
                if "% packet loss" in line:
                    try:
                        loss_pct = float(line.split("% packet loss")[0].split(" ")[-1])
                    except Exception:
                        pass
        return reachable, avg_ms, loss_pct, output[-500:]
    except Exception as e:
        return False, None, None, f"ping error: {e}"


def test_network() -> Dict[str, Any]:
    net: Dict[str, Any] = {}
    reachable_1, avg1, _, _ = ping_ip("1.1.1.1", count=2)
    reachable_8, avg8, _, _ = ping_ip("8.8.8.8", count=2)
    net["ping_1_1_1_1_ms"] = avg1 if reachable_1 else None
    net["ping_8_8_8_8_ms"] = avg8 if reachable_8 else None
    # DNS
    try:
        socket.gethostbyname("google.com")
        net["dns_ok"] = True
    except Exception:
        net["dns_ok"] = False
    # HTTP
    try:
        requests.get("https://www.google.com", timeout=5)
        net["http_ok"] = True
    except Exception:
        net["http_ok"] = False
    return net


def bytes_to_mbps(byte_count: int, seconds: float) -> Optional[float]:
    try:
        if seconds <= 0:
            return None
        # Mbps = (bytes * 8) / (seconds * 1e6)
        return round((byte_count * 8) / (seconds * 1_000_000), 2)
    except Exception:
        return None


def speedtest(server: str, download_bytes: int, upload_bytes: int, token: Optional[str]) -> Dict[str, Any]:
    """Measure download/upload throughput using API endpoints provided by the server.
    Returns: { download_mbps, upload_mbps }
    """
    out: Dict[str, Any] = {"download_mbps": None, "upload_mbps": None}
    headers = {"X-Agent-Token": token} if token else {}

    # Download test
    try:
        url_dl = f"{server}/api/speedtest/download?size_bytes={max(1, int(download_bytes))}"
        t0 = time.monotonic()
        r = requests.get(url_dl, headers=headers, stream=True, timeout=15)
        r.raise_for_status()
        total = 0
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
        dt = time.monotonic() - t0
        out["download_mbps"] = bytes_to_mbps(total, dt)
    except Exception:
        pass

    # Upload test
    try:
        url_ul = f"{server}/api/speedtest/upload"
        payload = b"\x00" * max(1, int(upload_bytes))
        t0 = time.monotonic()
        r = requests.post(url_ul, headers=headers, data=payload, timeout=15)
        r.raise_for_status()
        # Prefer server-acknowledged bytes if available
        acknowledged = None
        try:
            js = r.json()
            acknowledged = int(js.get("received_bytes")) if isinstance(js, dict) else None
        except Exception:
            acknowledged = None
        sent = acknowledged if acknowledged is not None else len(payload)
        dt = time.monotonic() - t0
        out["upload_mbps"] = bytes_to_mbps(sent, dt)
    except Exception:
        pass

    return out


def get_host_name() -> str:
    return platform.node() or os.getenv("COMPUTERNAME", "unknown-host")


def fetch_server_config(server: str, site: str, token: Optional[str]) -> Optional[Dict[str, Any]]:
    url = f"{server}/api/agents/{site}/config"
    headers = {"X-Agent-Token": token} if token else {}
    try:
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            return r.json()
        else:
            print(f"[agent] config HTTP {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        print(f"[agent] config error: {e}")
        return None


def post_report(server: str, site: str, token: Optional[str], payload: Dict[str, Any]) -> bool:
    url = f"{server}/api/agents/{site}/report"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Agent-Token"] = token
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"[agent] report ok: {r.json()}")
            return True
        else:
            print(f"[agent] report HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"[agent] report error: {e}")
        return False


def run_once(cfg: Dict[str, Any]) -> None:
    site: str = cfg["site"]
    server: str = cfg["server"]
    token: Optional[str] = cfg.get("token")

    # 1) Obter lista de câmeras do servidor (ou fallback para config local)
    conf = fetch_server_config(server, site, token)
    cameras: List[Dict[str, Any]] = []
    if conf and isinstance(conf.get("cameras"), list):
        for c in conf["cameras"]:
            if isinstance(c, dict) and c.get("ip"):
                cameras.append({"name": c.get("name"), "ip": c.get("ip")})
    else:
        # fallback local
        for c in cfg.get("cameras", []):
            if isinstance(c, dict) and c.get("ip"):
                cameras.append({"name": c.get("name"), "ip": c.get("ip")})

    # 2) Testes de rede
    net = test_network()
    # 2.1) Speedtest (opcional)
    if cfg.get("speedtest"):
        st = speedtest(server, cfg.get("speed_download_bytes", 1024 * 1024), cfg.get("speed_upload_bytes", 512 * 1024), token)
        net.update(st)

    # 3) Pingar cameras
    cam_reports: List[Dict[str, Any]] = []
    for c in cameras:
        ip = c.get("ip")
        name = c.get("name")
        reachable, avg_ms, loss, _out = ping_ip(ip, count=2)
        cam_reports.append({
            "name": name,
            "ip": ip,
            "status": "up" if reachable else "down",
            "latency_ms": avg_ms,
            "packet_loss": loss
        })

    # 4) Montar payload
    payload = {
        "site": site,
        "host": get_host_name(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "network": net,
        "cameras": cam_reports,
        "agent": {"version": "1.0.0", "interval_sec": cfg.get("interval_sec", DEFAULT_INTERVAL)}
    }

    # 5) Enviar
    post_report(server, site, token, payload)


if __name__ == "__main__":
    config = load_agent_config()
    if config.get("loop"):
        interval = int(config.get("interval_sec", DEFAULT_INTERVAL))
        while True:
            try:
                run_once(config)
            except Exception as e:
                print(f"[agent] error: {e}")
            time.sleep(interval)
    else:
        run_once(config)
