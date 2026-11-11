#!/usr/bin/env python3
"""BLE recon tool for the Vispek Magic Pencil (NT-BL-G1).

The pencil is a miniature spectroscopic analyzer with no published
protocol. This tool maps the GATT table, records notifications, and
sends test payloads to writable characteristics -- the generic recon
step that found the Nordic UART transport (see PROTOCOL.md). It
works on any BLE device, not just this one.

Setup (Linux, verified against bleak 2.0):
    pip install bleak
    bluetoothctl power on              # if the scan finds nothing
    sudo rfkill unblock bluetooth      # if the adapter is soft-blocked

Typical runs:
    python3 ble_recon.py                          # full interactive session
    python3 ble_recon.py --list-only              # GATT map only, then exit
    python3 ble_recon.py --address AA:BB:CC:DD:EE:FF --auto-subscribe

If the device refuses a connection, pair it once with bluetoothctl.
Legacy PIN devices need the agent prompt for the PIN:

    bluetoothctl
    [bluetoothctl] power on
    [bluetoothctl] agent on
    [bluetoothctl] default-agent
    [bluetoothctl] scan on
    [bluetoothctl] pair AA:BB:CC:DD:EE:FF
    [bluetoothctl] trust AA:BB:CC:DD:EE:FF

Then connect with --address AA:BB:CC:DD:EE:FF.

Outputs, under <out>/run-<timestamp>/:
    gatt_dump.json     service and characteristic map
    notify_log.csv      one row per notification: time, char, length, hex
    notify_<uuid>.bin   raw payloads, appended, per characteristic

Safety: the pencil has a lamp (200-1700 nm). A write can start a
measurement. The stimulus phase asks before each write.
"""

import argparse
import asyncio
import csv
import json
import re
import sys
import time
from collections import namedtuple
from datetime import datetime, timezone
from pathlib import Path

from bleak import BleakClient, BleakScanner

# Name fragments that identify the pencil in a scan. "VSPK" is the
# advertised short form of Vispek; names on newer units start with
# VSPK02.
NAME_HINTS = ("magic pencil", "vispek", "vspk", "nt-bl", "nt1000", "spectro")

GATT_BASE = re.compile(r"^0000([0-9a-f]{4})-0000-1000-8000-00805f9b34fb$", re.I)

# First-poke payloads for stimulus mode. Vendor protocols usually answer
# to at least one of these.
CANDIDATE_PAYLOADS = (
    ("0x01", "01"),
    ("0x00", "00"),
    ("0xAA", "AA"),
    ("0xFF", "FF"),
    ("'S'", "53"),
    ("'R'", "52"),
    ("'G'", "47"),
    ("'s'", "73"),
    ("0x01 0x00", "0100"),
    ("'AT' + CRLF", "41540D0A"),
)

CharInfo = namedtuple("CharInfo", "obj uuid props")


def is_standard_char(uuid):
    """True for Bluetooth SIG assigned UUIDs (0x2xxx chars, 0x18xx services).

    The 16-bit base form also covers vendor ranges like 0xffe1. The filter
    must block only the assigned space, or stimulus mode could not reach
    common vendor characteristics.
    """
    m = GATT_BASE.match(uuid)
    if not m:
        return False
    short = m.group(1).lower()
    return short.startswith("2") or short.startswith("18")


def parse_hex_input(text):
    """Turn loose hex input ('a1 02') into bytes. None if not valid hex."""
    cleaned = re.sub(r"[^0-9a-fA-F]", "", text)
    if not cleaned or len(cleaned) % 2:
        return None
    return bytes.fromhex(cleaned)


def render(value):
    """Hex plus printable-ASCII rendering of a read value."""
    text = "".join(chr(b) if 32 <= b < 127 else "." for b in value)
    return f"{value.hex()} |{text}|"


async def ainput(prompt):
    """input() that does not block the event loop, so notifications keep
    flowing while a prompt waits."""
    return await asyncio.to_thread(input, prompt)


class FrameLogger:
    """Records notification frames to CSV and per-characteristic .bin files."""

    def __init__(self, run_dir):
        self.run_dir = run_dir
        self.counts = {}     # uuid -> total frames
        self.bin_files = {}  # uuid -> open file
        self.csv_file = None
        self.csv_writer = None

    def open(self):
        self.csv_file = open(self.run_dir / "notify_log.csv", "a", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        if self.csv_file.tell() == 0:
            self.csv_writer.writerow(
                ["unix_time", "iso_time", "char_uuid", "char_handle", "length", "hex"]
            )

    def log(self, char, data):
        """Notify callback: (BleakGATTCharacteristic, bytearray)."""
        now = time.time()
        iso = datetime.now().astimezone().isoformat(timespec="milliseconds")
        uuid = char.uuid.lower()
        self.counts[uuid] = self.counts.get(uuid, 0) + 1
        self.csv_writer.writerow(
            [f"{now:.6f}", iso, uuid, getattr(char, "handle", ""), len(data), bytes(data).hex()]
        )
        self.csv_file.flush()  # survive Ctrl+C mid-stream
        if uuid not in self.bin_files:
            self.bin_files[uuid] = open(self.run_dir / f"notify_{uuid}.bin", "ab")
        self.bin_files[uuid].write(bytes(data))
        hexline = bytes(data).hex()
        if len(hexline) > 96:
            hexline = hexline[:96] + "..."
        print(f"  <- {uuid} #{self.counts[uuid]} [{len(data)}B] {hexline}")

    def close(self):
        if self.csv_file:
            self.csv_file.close()
        for f in self.bin_files.values():
            f.close()


async def scan(args):
    print(f"Scanning for {args.timeout} s ...")
    try:
        found = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
    except Exception as exc:
        sys.exit(f"Scan failed: {exc}\nTry: bluetoothctl power on")
    if not found:
        sys.exit("No BLE devices found. Try: bluetoothctl power on")
    devices = sorted(
        found.values(),
        key=lambda pair: pair[1].rssi if pair[1].rssi is not None else -127,
        reverse=True,
    )
    shown = devices[:40]
    if len(devices) > 40:
        print(f"\n{len(devices)} device(s) found, first 40 shown:")
    else:
        print(f"\n{len(devices)} device(s) found:")
    for i, (dev, adv) in enumerate(shown):
        name = adv.local_name or dev.name or "<no name>"
        print(f"  [{i}] {name}  {dev.address}")
        details = f"      RSSI {adv.rssi}"
        if adv.service_uuids:
            details += f"  services {','.join(adv.service_uuids)}"
        print(details)
        for cid, blob in adv.manufacturer_data.items():
            print(f"      manufacturer 0x{cid:04x}: {bytes(blob).hex()}")
    return devices


async def pick_device(devices, args):
    if args.address:
        wanted = args.address.lower()
        for dev, _ in devices:
            if dev.address.lower() == wanted:
                print(f"\nUsing {dev.address} (seen in scan).")
                return dev.address
        print(f"\n{args.address} was not in the scan. Trying a direct connection.")
        return args.address
    matches = []
    needle = args.name.lower() if args.name else None
    for i, (dev, adv) in enumerate(devices):
        name = (adv.local_name or dev.name or "").lower()
        hit = needle in name if needle else any(h in name for h in NAME_HINTS)
        if hit:
            matches.append(i)
    if needle and not matches:
        sys.exit(f"No device name contains '{args.name}'.")
    if len(matches) == 1:
        i = matches[0]
        dev, adv = devices[i]
        name = adv.local_name or dev.name or "<no name>"
        reply = (await ainput(f"\nConnect to [{i}] {name} {dev.address}? [Y/n] ")).strip().lower()
        if reply != "n":
            return dev.address
    reply = (await ainput("Device index to connect to: ")).strip()
    if not reply.isdigit() or int(reply) >= len(devices):
        sys.exit("Bad index.")
    return devices[int(reply)][0].address


async def enumerate_gatt(client, run_dir, read_all):
    dump = {"captured_at": datetime.now(timezone.utc).isoformat(), "services": []}
    chars = []
    print("\nGATT map:")
    for service in client.services:
        print(f"  service {service.uuid}")
        svc = {"uuid": service.uuid, "characteristics": []}
        for c in service.characteristics:
            props = sorted({str(p).lower() for p in c.properties})
            entry = {
                "uuid": c.uuid,
                "handle": getattr(c, "handle", None),
                "properties": props,
                "descriptors": [d.uuid for d in c.descriptors],
            }
            if read_all and "read" in props:
                try:
                    value = bytes(await client.read_gatt_char(c))
                except Exception as exc:
                    entry["read_error"] = str(exc) or repr(exc)
                else:
                    entry["value_hex"] = value.hex()
            svc["characteristics"].append(entry)
            print(f"    char {c.uuid}  [{','.join(props)}]")
            if entry.get("value_hex"):
                print(f"      value {render(value)}")
            if entry.get("read_error"):
                print(f"      read error: {entry['read_error']}")
            chars.append(CharInfo(c, c.uuid, props))
        dump["services"].append(svc)
    path = run_dir / "gatt_dump.json"
    path.write_text(json.dumps(dump, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved {path}")
    return chars


async def subscribe_phase(client, chars, logger, auto_all):
    notify_chars = [c for c in chars if "notify" in c.props or "indicate" in c.props]
    if not notify_chars:
        print("\nNo notify/indicate characteristic. Nothing to subscribe to.")
        return []
    print("\nNotification characteristics:")
    for i, c in enumerate(notify_chars):
        print(f"  [{i}] {c.uuid}  [{','.join(c.props)}]")
    subscribed = []
    auto = auto_all
    for i, c in enumerate(notify_chars):
        if not auto:
            reply = (await ainput(f"Subscribe to [{i}] {c.uuid}? [y/N/a(ll)/q(uit)] ")).strip().lower()
            if reply == "q":
                break
            if reply == "a":
                auto = True
            if not auto and reply != "y":
                print(f"  skipped {c.uuid}")
                continue
        try:
            await client.start_notify(c.obj, logger.log)
        except Exception as exc:
            print(f"  !! subscribe failed on {c.uuid}: {exc}")
            continue
        subscribed.append(c)
        print(f"  subscribed {c.uuid}")
    return subscribed


async def stimulus_phase(client, chars, logger):
    writable = [
        c
        for c in chars
        if ("write" in c.props or "write-without-response" in c.props)
        and not is_standard_char(c.uuid)
    ]
    if not writable:
        print("\nNo writable non-standard characteristic found.")
        return
    print("\nWritable characteristics (standard GATT excluded):")
    for i, c in enumerate(writable):
        print(f"  [{i}] {c.uuid}  [{','.join(c.props)}]")
    reply = (await ainput("Index to poke, 'a' for all, Enter to skip: ")).strip().lower()
    if reply in ("", "q"):
        return
    if reply == "a":
        chosen = writable
    elif reply.isdigit() and int(reply) < len(writable):
        chosen = [writable[int(reply)]]
    else:
        print("No valid selection.")
        return
    print("\nNote: a write can start a lamp cycle. Confirm each payload.")
    for c in chosen:
        print(f"\nTarget {c.uuid}")
        baseline = dict(logger.counts)
        for label, hexstr in CANDIDATE_PAYLOADS:
            reply = (
                await ainput(f"Send {label} ({hexstr})? [y/N/s(kip rest)/q] or type hex bytes: ")
            ).strip().lower()
            if reply == "q":
                return
            if reply == "s":
                break
            if reply == "y":
                payload = bytes.fromhex(hexstr)
            else:
                payload = parse_hex_input(reply)
            if payload is None:
                continue
            # 'write' means with-response; a char that only supports
            # write-without-response must be sent with response=False.
            use_response = "write" in c.props
            try:
                await client.write_gatt_char(c.obj, payload, response=use_response)
                print(f"  -> sent {payload.hex()}")
            except Exception as exc:
                print(f"  !! write failed: {exc}")
                continue
            await asyncio.sleep(2.0)
            deltas = {u: n - baseline.get(u, 0) for u, n in logger.counts.items()}
            deltas = {u: d for u, d in deltas.items() if d > 0}
            if deltas:
                for u, d in sorted(deltas.items()):
                    print(f"  response: +{d} frame(s) on {u}")
            else:
                print("  no notification within 2 s")
            baseline = dict(logger.counts)


async def listen_forever(disconnected):
    print("\nListening for notifications. Ctrl+C stops and exits.")
    try:
        await disconnected.wait()
    except KeyboardInterrupt:
        pass


def print_summary(run_dir, logger):
    print(f"\nDone. Files in {run_dir}:")
    if (run_dir / "gatt_dump.json").exists():
        print("  gatt_dump.json")
    total = sum(logger.counts.values())
    print(f"  notify_log.csv ({total} frame(s))")
    for uuid in sorted(logger.bin_files):
        print(f"  notify_{uuid}.bin  ({logger.counts.get(uuid, 0)} frame(s))")
    if not total:
        print("  (no notifications captured)")


async def run(args):
    devices = await scan(args)
    address = await pick_device(devices, args)
    run_dir = Path(args.out) / f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nOutput directory: {run_dir}")
    logger = FrameLogger(run_dir)
    logger.open()

    disconnected = asyncio.Event()

    def on_disconnect(_client):
        print("\n!! Device disconnected.")
        disconnected.set()

    try:
        try:
            async with BleakClient(
                address, disconnected_callback=on_disconnect, timeout=args.connect_timeout
            ) as client:
                print(f"\nConnected to {address}")
                mtu = getattr(client, "mtu_size", None)
                if mtu:
                    print(f"Negotiated MTU: {mtu} bytes")
                if args.pair:
                    try:
                        await client.pair()
                        print("Paired.")
                    except Exception as exc:
                        print(f"Pairing failed (continuing): {exc}")
                chars = await enumerate_gatt(client, run_dir, args.read_all)
                if args.list_only:
                    return
                subscribed = await subscribe_phase(client, chars, logger, args.auto_subscribe)
                if subscribed:
                    print(f"\nSubscribed to {len(subscribed)} characteristic(s).")
                if not args.no_stimulus:
                    reply = (await ainput("\nStart stimulus testing? [y/N] ")).strip().lower()
                    while reply == "y":
                        await stimulus_phase(client, chars, logger)
                        reply = (await ainput("Run another stimulus round? [y/N] ")).strip().lower()
                if subscribed and not disconnected.is_set():
                    await listen_forever(disconnected)
        except Exception as exc:
            print(f"\nSession ended early: {exc}")
            if not (run_dir / "gatt_dump.json").exists():
                print(
                    "If the device refused the connection, pair it once first.\n"
                    "See the bluetoothctl steps in the header of this script."
                )
    finally:
        print_summary(run_dir, logger)
        logger.close()


def parse_args():
    p = argparse.ArgumentParser(
        description="BLE recon: GATT map, notification capture, stimulus writes."
    )
    p.add_argument("-a", "--address", help="MAC address; skips device picking")
    p.add_argument("-n", "--name", help="connect to a device whose name contains this text")
    p.add_argument("--timeout", type=float, default=10.0, help="scan seconds (default 10)")
    p.add_argument(
        "--connect-timeout", type=float, default=15.0, help="connect timeout seconds (default 15)"
    )
    p.add_argument("--out", default="runs", help="output directory (default runs)")
    p.add_argument("--pair", action="store_true", help="pair after connecting (BlueZ)")
    p.add_argument(
        "--auto-subscribe",
        action="store_true",
        help="subscribe to all notify/indicate chars without asking",
    )
    p.add_argument(
        "--read-all",
        action="store_true",
        help="read every readable characteristic during enumeration",
    )
    p.add_argument("--list-only", action="store_true", help="enumerate GATT, save dump, exit")
    p.add_argument("--no-stimulus", action="store_true", help="never offer stimulus writes")
    return p.parse_args()


def main():
    args = parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
