#!/usr/bin/env python3
"""Client for the Vispek Magic Pencil BLE protocol.

Protocol spec: PROTOCOL.md in the repo root (reverse-engineered
and verified against live hardware; method in README.md).

Usage:
    python3 vispek_client.py                    # info queries only
    python3 vispek_client.py --scan              # info + one scan (lamp!)
    python3 vispek_client.py --scan --scene 1    # scan with scene id
    python3 vispek_client.py --address AA:BB:... # known device address
    python3 vispek_client.py --name-prefix VSPK  # find by advertised name

Scans save to ./runs/run-<timestamp>/scan.csv (22 rows,
index,sample,reference), plus frames.txt with the raw exchange.
Feed that scan.csv to match.py identify or analyze.py. The runs/
directory is for local captures; captures/ holds the published
data.

Device rules that make sessions work (details in AGENTS.md):
- Do not scan while the device charges; connects get unstable.
- The device powers off about 2 minutes after a disconnect.
- Send the heartbeat every ~3 s for the whole session; idle links
  drop after tens of seconds.
- Connects fail at random: retry with a FRESH BleakClient object
  per attempt; re-scan when BlueZ reports "not found".
- Never send the 0x12 calibration, 0x24 PWM, or 0x23 temperature
  commands, and never touch the DFU service.
"""

import argparse
import asyncio
import csv
import time
from pathlib import Path

from bleak import BleakClient, BleakScanner

UART_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
UART_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # we write commands
UART_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # device notifies data

HEARTBEAT_S = 3.0
INFO_WAIT_S = 1.5
SCAN_COLLECT_S = 30.0


def crc8(data: bytes) -> int:
    """Poly 0x07, init 0x00, no reflection, no final xor."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def frame(cmd: int, params: bytes = b"") -> bytes:
    if len(params) > 17:
        raise ValueError("params too long")
    f = bytearray(20)
    f[0] = 0x3D
    f[1] = cmd
    f[2 : 2 + len(params)] = params
    f[19] = crc8(f[0:19])
    return bytes(f)


def heartbeat() -> bytes:
    """Same shape as the battery query, but byte 19 is forced to 0xAA
    — the vendor app's idle-link keep-alive (PROTOCOL.md, Quirks)."""
    f = bytearray(frame(0x01))
    f[19] = 0xAA
    return bytes(f)


def be(value: int, width: int) -> bytes:
    return value.to_bytes(width, "big")


class ResponseParser:
    """Mirrors the vendor app's response parser (PROTOCOL.md,
    Response frames).

    Human output goes through `self.say` (default: print), so other
    tools can route frames into a log file and keep stdout clean.
    Decoded values are stored on the instance too: `battery_pct`
    (last 5a01) and `info` (last value per info query).
    """

    def __init__(self, say=None):
        self.samples = []      # 5a11 stream: bytes 8-10
        self.reference = []   # 5a11 stream: bytes 5-7
        self.c_samples = []    # 5a34 stream
        self.c_reference = []
        self.scan_done = asyncio.Event()
        self.continuous_done = asyncio.Event()
        self.battery_pct = None
        self.info = {}
        self.say = say or print

    def feed(self, data: bytes):
        h = data.hex()
        self.say("  <- " + (h if len(h) <= 96 else h[:96] + "..."))
        if h.startswith("5a01"):
            self.battery_pct = data[2]
            self.say(f"  battery: {data[2]}%")
        elif h.startswith("5aff15"):
            self._store("sn", data)
            self.say(f"  serial number: {self.info['sn']}")
        elif h.startswith("5aff16"):
            self._store("hardware", data)
            self.say(f"  hardware version: {self.info['hardware']}")
        elif h.startswith("5aff17"):
            self._store("firmware", data)
            self.say(f"  firmware version: {self.info['firmware']}")
        elif h.startswith("5aff22"):
            self._store("model", data)
            self.say(f"  product model: {self.info['model']}")
        elif h.startswith("5aff23"):
            self.say(f"  temperature: {int.from_bytes(data[3:5], 'big') / 100} C")
        elif h.startswith("5aff1102"):
            if len(self.samples) == 1:
                self.say(f"  single scan value: {self.samples[0]}")
            else:
                self.say(
                    f"  scan stream end: {len(self.samples)} samples, "
                    f"{len(self.reference)} reference values"
                )
            self.scan_done.set()
        elif h.startswith("5aff1100"):
            self.say("  scan accepted, stream starting")
        elif h.startswith("5a11"):
            if data[2] == 1:
                self.samples.clear()
                self.reference.clear()
            if len(data) >= 11:
                self.samples.append(int.from_bytes(data[8:11], "big"))
            if len(data) >= 8:
                self.reference.append(int.from_bytes(data[5:8], "big"))
        elif h.startswith("5aff3401"):
            self.c_samples.clear()
            self.c_reference.clear()
        elif h.startswith("5aff3400"):
            self.say(
                f"  continuous stream end: {len(self.c_samples)} samples, "
                f"{len(self.c_reference)} reference values"
            )
            self.continuous_done.set()
        elif h.startswith("5a34"):
            n = data[4]
            mid = 5 + n * 3
            for i in range(n):
                self.c_samples.append(int.from_bytes(data[5 + i * 3 : 8 + i * 3], "big"))
            for i in range(n):
                base = mid + i * 3
                if base + 3 <= len(data) - 1:  # last byte is a checksum
                    self.c_reference.append(int.from_bytes(data[base : base + 3], "big"))
        elif h.startswith("5a33"):
            total = int.from_bytes(data[5:7], "big")
            index = int.from_bytes(data[7:9], "big")
            count = int.from_bytes(data[9:11], "big")
            if index == 1:
                self.samples.clear()
                self.reference.clear()
            body = data[11 : len(data) - 1]
            for i in range(0, len(body) - 2, 3):
                self.samples.append(int.from_bytes(body[i : i + 3], "big"))
            self.say(f"  periodic packet: index {index}/{count} of {total}, +{len(body)//3}")
            if total == count:
                self.scan_done.set()
        else:
            self.say("  (unparsed response)")

    def _store(self, key, data: bytes):
        length = data[3]
        self.info[key] = data[4 : 4 + length].decode("ascii", errors="replace")


def save_csv(path: Path, rows):
    # LF endings: the csv dialect defaults to CRLF, which makes git
    # warn on the first committed scans.
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["index", "sample", "reference"])
        for i, (s, r) in enumerate(rows):
            w.writerow([i, s, r])


async def find_device(address=None, name_prefix="VSPK", timeout=15.0):
    if address:
        print(f"scanning {timeout} s for {address} ...")
        hit = await BleakScanner.find_device_by_address(address, timeout=timeout)
    else:
        # advertised names start with VSPK (VSPK02... on newer units)
        print(f"scanning {timeout} s for a device named {name_prefix}* ...")
        hit = await BleakScanner.find_device_by_filter(
            lambda d, _: bool(d.name and d.name.startswith(name_prefix)),
            timeout=timeout,
        )
    if hit is None:
        raise SystemExit("pencil not found; is it on and awake?")
    return hit


async def send(client, label: str, payload: bytes):
    print(f"  -> {label}")
    await client.write_gatt_char(UART_RX, payload, response=True)


async def link_sessions(on_disconnect, address=None, name_prefix="VSPK",
                        max_links=3, connect_deadline_s=90):
    """Yield one connected BleakClient per successful link.

    Encodes the retry rules from AGENTS.md: links drop at random and a
    resume costs one reconnect; a fresh client per connect attempt, or
    the next connect on it breaks; when BlueZ evicts the device object
    (it does this once discovery stops), re-scan. Ends after max_links
    links, or when no link forms before the deadline. The caller
    disconnects each yielded client.
    """
    device = await find_device(address, name_prefix)
    for _ in range(max_links):
        client = None
        attempt = 0
        deadline = time.monotonic() + connect_deadline_s
        while client is None and time.monotonic() < deadline:
            attempt += 1
            if device is None:
                # BlueZ evicted the device object, or the device
                # stopped advertising; re-find before the next connect.
                print("  refreshing device via short scan ...")
                device = await find_device(address, name_prefix, timeout=6)
                if device is None:
                    print("  not advertising yet; waiting ...")
                    await asyncio.sleep(5)
                    continue
            c = BleakClient(device, disconnected_callback=on_disconnect, timeout=15)
            try:
                await c.connect()
                client = c
            except Exception as exc:
                print(f"connect attempt {attempt} failed: {type(exc).__name__}: {exc}")
                if "not found" in str(exc).lower():
                    device = None  # force a refresh next round
                await asyncio.sleep(5)
        if client is None:
            return
        print(f"connected to {device.address} (attempt {attempt})")
        yield client


async def run(args):
    # runs/, never captures/: the published tree stays clean
    run_dir = Path("runs") / f"run-{time.strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    # keep a local frame log beside the scan: it is what you diff
    # against the PROTOCOL.md example when something misparses
    frames_log = open(run_dir / "frames.txt", "w")

    def say(msg):
        frames_log.write(msg + "\n")
        frames_log.flush()
        print(msg)

    parser = ResponseParser(say=say)

    disconnected = asyncio.Event()
    # BlueZ fires the disconnect callback repeatedly during failed
    # connects; only report real connected-to-disconnected transitions.
    linked = {"on": False}

    def on_disc(_c):
        if linked["on"]:
            linked["on"] = False
            print("!! device disconnected")
        disconnected.set()

    ever_linked = False
    session_no = 0
    async for client in link_sessions(on_disc, args.address, args.name_prefix):
        ever_linked = True
        session_no += 1
        linked["on"] = True
        disconnected.clear()
        print(f"[session {session_no}]")
        try:
            done = await session(client, args, parser, disconnected, run_dir)
        finally:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception:
                pass
        if done:
            break
        print("session broke early; retrying on a fresh link")
    if not ever_linked:
        print("no connection; is the pencil on, charged, and nearby?")

    frames_log.close()
    print(f"scan and raw frame log: {run_dir}")


async def session(client, args, parser, disconnected, run_dir):
    """One connected session. True when the requested work completed."""
    await client.start_notify(UART_TX, lambda _c, data: parser.feed(bytes(data)))

    if not args.skip_info:
        # The 0x23 temperature query dropped the link in 2 of 2 runs;
        # keep it out of the default set. 5a11 scan data is the goal.
        for label, payload in [
            ("battery", frame(0x01)),
            ("serial number", frame(0x15)),
            ("hardware version", frame(0x16)),
            ("firmware version", frame(0x17)),
            ("product model", frame(0x22)),
        ]:
            try:
                await send(client, label, payload)
            except Exception as exc:
                print(f"  write failed during {label}: {exc}")
                return False
            await asyncio.sleep(INFO_WAIT_S)
        if disconnected.is_set():
            return False

    if not args.scan:
        return True
    if disconnected.is_set():
        return False

    params = bytes([23]) + be(1023, 2) + bytes([args.scene])
    print("\nLAMP WARNING: this fires the scan lamp. Starting in 2 s ...")
    await asyncio.sleep(2)
    try:
        parser.scan_done.clear()
        await send(client, f"scan (scene {args.scene})", frame(0x11, params))
    except Exception as exc:
        print(f"  write failed during scan: {exc}")
        return False
    hb_task = asyncio.create_task(heartbeat_loop(client, disconnected, parser))
    try:
        await asyncio.wait_for(parser.scan_done.wait(), timeout=SCAN_COLLECT_S)
    except asyncio.TimeoutError:
        print("  scan collection window closed without end marker")
        hb_task.cancel()
        # Partial data is worth keeping, but a complete scan is worth
        # one retry.
        rows = list(zip(parser.samples, parser.reference))
        save_csv(run_dir / "scan.csv", rows)
        print(f"saved {len(rows)} partial sample rows")
        return False
    hb_task.cancel()
    rows = list(zip(parser.samples, parser.reference))
    out = run_dir / "scan.csv"
    save_csv(out, rows)
    print(f"saved {len(rows)} sample rows to {out}")
    return True


async def heartbeat_loop(client, disconnected, parser):
    while not disconnected.is_set():
        await asyncio.sleep(HEARTBEAT_S)
        try:
            await client.write_gatt_char(UART_RX, heartbeat(), response=True)
            print("  -> heartbeat")
        except Exception as exc:
            print(f"  heartbeat failed: {exc}")


def main():
    p = argparse.ArgumentParser(description="Vispek Magic Pencil BLE client")
    p.add_argument("--scan", action="store_true", help="run one scan (fires the lamp)")
    p.add_argument("--scene", type=int, default=1, help="scene id byte for scan (default 1)")
    p.add_argument("--skip-info", action="store_true", help="skip info queries, scan immediately")
    p.add_argument("--address", help="device address; skips name matching")
    p.add_argument("--name-prefix", default="VSPK",
                   help="advertised-name prefix to find the device (default VSPK)")
    args = p.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
