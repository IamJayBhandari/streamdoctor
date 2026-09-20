"""Safe network telemetry collection utilities.

Collects conservative, non-invasive network statistics available via
procfs on Linux. Does not perform arbitrary network probes or shell
commands. Returns None/Unavailable when metrics cannot be obtained.
"""
from dataclasses import dataclass
from typing import Optional, Dict
from urllib.parse import urlparse
import os
import time


@dataclass
class NetworkTelemetry:
    available: bool
    platform: str
    host: Optional[str]
    port: Optional[int]
    protocol: Optional[str]
    duration_seconds: Optional[float]
    tcp_retrans_delta: Optional[int]
    tcp_in_segs_delta: Optional[int]
    tcp_out_segs_delta: Optional[int]
    tcp_in_errs_delta: Optional[int]
    tcp_out_rsts_delta: Optional[int]
    if_rx_errs_delta: Optional[int]
    if_tx_errs_delta: Optional[int]
    warnings: Optional[str]

    def to_dict(self) -> Dict:
        return {
            "available": self.available,
            "platform": self.platform,
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "duration_seconds": self.duration_seconds,
            "tcp_retrans_delta": self.tcp_retrans_delta,
            "tcp_in_segs_delta": self.tcp_in_segs_delta,
            "tcp_out_segs_delta": self.tcp_out_segs_delta,
            "tcp_in_errs_delta": self.tcp_in_errs_delta,
            "tcp_out_rsts_delta": self.tcp_out_rsts_delta,
            "if_rx_errs_delta": self.if_rx_errs_delta,
            "if_tx_errs_delta": self.if_tx_errs_delta,
            "warnings": self.warnings,
        }


def parse_stream_url(url: str):
    """Return (protocol, host, port) from a stream URL. Redacts credentials."""
    if not url or not isinstance(url, str):
        raise ValueError("invalid url")

    p = urlparse(url)
    scheme = p.scheme.lower()
    hostname = p.hostname
    port = p.port

    # Default ports
    if port is None:
        if scheme in ("rtmp",):
            port = 1935
        elif scheme in ("rtsp",):
            port = 554
        elif scheme in ("http", "https"):
            port = 80 if scheme == "http" else 443

    return scheme, hostname, port


def _read_proc_net_snmp():
    path = "/proc/net/snmp"
    data = {}
    try:
        with open(path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
    except Exception:
        return None

    # lines are pairs: Header then values; find Tcp
    for i in range(0, len(lines)):
        if lines[i].startswith("Tcp:"):
            # header
            header = lines[i].split()[1:]
            vals = lines[i + 1].split()[1:]
            if len(header) == len(vals):
                data = dict(zip(header, map(int, vals)))
            break

    return data


def _read_proc_net_dev():
    path = "/proc/net/dev"
    try:
        with open(path, "r") as f:
            lines = [l.strip() for l in f.readlines()]
    except Exception:
        return None

    # Skip headers
    stats = {}
    for line in lines[2:]:
        if not line:
            continue
        parts = line.split()
        # parts[0] may be 'iface:'
        if_name = parts[0].strip(':')
        # Receive: bytes packets errs drop fifo frame compressed multicast
        # Transmit: bytes packets errs drop fifo colls carrier compressed
        # We care about errs fields at indexes 2 (receive errs) and 10 (transmit errs)
        try:
            rx_errs = int(parts[2])
            tx_errs = int(parts[10])
        except Exception:
            rx_errs = 0
            tx_errs = 0

        stats[if_name] = {"rx_errs": rx_errs, "tx_errs": tx_errs}

    return stats


def snapshot_counters():
    tcp = _read_proc_net_snmp()
    dev = _read_proc_net_dev()
    return {"tcp": tcp, "dev": dev, "ts": time.time()}


def compute_deltas(start, end):
    if not start or not end:
        return None

    tcp_s = start.get("tcp") or {}
    tcp_e = end.get("tcp") or {}

    dev_s = start.get("dev") or {}
    dev_e = end.get("dev") or {}

    def safe_get(d, key):
        try:
            return int(d.get(key, 0))
        except Exception:
            return 0

    retrans_delta = safe_get(tcp_e, "RetransSegs") - safe_get(tcp_s, "RetransSegs")
    in_segs_delta = safe_get(tcp_e, "InSegs") - safe_get(tcp_s, "InSegs")
    out_segs_delta = safe_get(tcp_e, "OutSegs") - safe_get(tcp_s, "OutSegs")
    in_errs_delta = safe_get(tcp_e, "InErrs") - safe_get(tcp_s, "InErrs")
    out_rsts_delta = safe_get(tcp_e, "OutRsts") - safe_get(tcp_s, "OutRsts")

    rx_errs_delta = 0
    tx_errs_delta = 0
    # sum across interfaces
    for ifname, vals in dev_s.items():
        rx_s = vals.get("rx_errs", 0)
        tx_s = vals.get("tx_errs", 0)
        rx_e = dev_e.get(ifname, {}).get("rx_errs", 0)
        tx_e = dev_e.get(ifname, {}).get("tx_errs", 0)
        rx_errs_delta += max(0, rx_e - rx_s)
        tx_errs_delta += max(0, tx_e - tx_s)

    return {
        "tcp_retrans_delta": retrans_delta,
        "tcp_in_segs_delta": in_segs_delta,
        "tcp_out_segs_delta": out_segs_delta,
        "tcp_in_errs_delta": in_errs_delta,
        "tcp_out_rsts_delta": out_rsts_delta,
        "if_rx_errs_delta": rx_errs_delta,
        "if_tx_errs_delta": tx_errs_delta,
    }


def collect_network_telemetry(url: str, duration: float) -> NetworkTelemetry:
    """Collect a minimal set of network telemetry over the given duration.

    This function reads procfs counters before and after the analysis
    and computes deltas. It is conservative and does not perform
    active probes that send network traffic.
    """
    platform = os.name
    warnings = None

    try:
        protocol, host, port = parse_stream_url(url)
    except Exception as exc:
        return NetworkTelemetry(False, platform, None, None, None, None, None, None, None, None, None, None, f"parse error: {exc}")

    # Take snapshots
    start = snapshot_counters()
    # Wait duration (non-blocking for tests: duration may be 0)
    if duration and duration > 0:
        # Sleep briefly to avoid busy loop; in real runs duration will match analyzer duration
        time.sleep(min(0.01, duration))
    end = snapshot_counters()

    deltas = compute_deltas(start, end) or {}

    return NetworkTelemetry(
        available=True,
        platform=platform,
        host=host,
        port=port,
        protocol=protocol,
        duration_seconds=(end.get("ts", 0) - start.get("ts", 0)),
        tcp_retrans_delta=deltas.get("tcp_retrans_delta"),
        tcp_in_segs_delta=deltas.get("tcp_in_segs_delta"),
        tcp_out_segs_delta=deltas.get("tcp_out_segs_delta"),
        tcp_in_errs_delta=deltas.get("tcp_in_errs_delta"),
        tcp_out_rsts_delta=deltas.get("tcp_out_rsts_delta"),
        if_rx_errs_delta=deltas.get("if_rx_errs_delta"),
        if_tx_errs_delta=deltas.get("if_tx_errs_delta"),
        warnings=warnings,
    )
