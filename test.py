import serial
import time
from serial.tools import list_ports

# ─────────────────────────────────────────────
#  CONFIG — adjust these to match your setup
# ─────────────────────────────────────────────
BAUDRATE        = 9600          # change if your STM uses a different baud
BOARD_SERIAL_SN = "YOUR_SN"    # partial/full serial-number suffix of your STM board
                                # e.g. "A6008" — leave "" to auto-pick first port
TIMEOUT_OPEN    = 10            # seconds to wait for "Lx op" after sending open cmd
TIMEOUT_CLOSE   = 45            # seconds to wait for "Lx cl" after locker opened
FAST_OPEN_SEC   = 2.0           # if op+cl arrive within this window → treat as "didn't open"
POLL            = 0.3           # read poll interval (seconds)

LOCKER_PRIMARY  = 3
LOCKER_FALLBACK = 4
# ─────────────────────────────────────────────


def banner(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)


def find_port() -> str | None:
    """Return the serial device path for the STM board."""
    ports = list_ports.comports()
    if not ports:
        print("❌  No serial ports detected on this machine.")
        return None

    print("\n📋  Available serial ports:")
    for p in ports:
        sn = p.serial_number or "—"
        print(f"     {p.device:20s}  SN={sn:20s}  desc={p.description}")

    # if a serial-number filter is configured, use it
    if BOARD_SERIAL_SN:
        for p in ports:
            sn = p.serial_number or ""
            if sn.endswith(BOARD_SERIAL_SN):
                print(f"\n🎯  Matched STM board → {p.device}  (SN ends with '{BOARD_SERIAL_SN}')")
                return p.device
        print(f"\n⚠️   No port whose SN ends with '{BOARD_SERIAL_SN}' found.")
        return None

    # fallback: just take the first port and warn
    print(f"\n⚠️   BOARD_SERIAL_SN not set — using first port: {ports[0].device}")
    return ports[0].device


def open_serial(device: str) -> serial.Serial | None:
    """Open and return a Serial object, or None on failure."""
    try:
        ser = serial.Serial(port=device, baudrate=BAUDRATE, timeout=1)
        time.sleep(2)               # let STM boot after DTR toggle
        ser.reset_input_buffer()
        print(f"✅  Serial opened → {device}  @ {BAUDRATE} baud")
        return ser
    except serial.SerialException as e:
        print(f"❌  Could not open {device}: {e}")
        return None


def send(ser: serial.Serial, cmd: str):
    """Send a command string followed by newline."""
    full = cmd + '\n'
    ser.reset_input_buffer()
    ser.write(full.encode())
    ser.flush()
    print(f"  ➤  SENT : {cmd!r}")
    time.sleep(0.15)


def read_line(ser: serial.Serial) -> str:
    """Read one line (non-blocking).  Returns '' if nothing waiting."""
    if ser.in_waiting > 0:
        raw = ser.readline()
        line = raw.decode(errors='ignore').strip()
        if line:
            print(f"  ◀  RECV : {line!r}")
        return line
    return ''


def drain_for(ser: serial.Serial, seconds: float):
    """Print everything arriving for `seconds` seconds (for debug)."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        line = read_line(ser)
        if not line:
            time.sleep(POLL)


def wait_for_open(ser: serial.Serial, locker: int) -> bool:
    """
    Wait up to TIMEOUT_OPEN seconds for 'Lx op'.
    Returns True if seen, False on timeout or 'System Busy!'.
    """
    print(f"\n⏳  Waiting for L{locker} open confirmation ({TIMEOUT_OPEN}s max)…")
    deadline = time.time() + TIMEOUT_OPEN
    while time.time() < deadline:
        line = read_line(ser)
        if not line:
            time.sleep(POLL)
            continue
        ll = line.lower()
        if f"l{locker} op" in ll:
            print(f"  🔓  Locker {locker} is OPEN.")
            return True
        if "system busy" in ll:
            print("  ⚠️   System Busy — another locker may already be open.")
            return False
        if "unknown command" in ll:
            print("  ⚠️   Unknown Command response — check locker number.")
            return False
    print(f"  ⏰  Timeout waiting for L{locker} op.")
    return False


def wait_for_close_check_fast(ser: serial.Serial, locker: int) -> str:
    """
    After seeing 'op', monitor for 'cl'.
    Returns:
      'closed'     — normal close, user interacted
      'fast_close' — op+cl within FAST_OPEN_SEC (locker didn't really open)
      'timeout'    — never closed within TIMEOUT_CLOSE
    """
    print(f"\n⏳  Waiting for L{locker} close (timeout={TIMEOUT_CLOSE}s)…")
    open_time  = time.time()
    deadline   = open_time + TIMEOUT_CLOSE

    while time.time() < deadline:
        line = read_line(ser)
        if not line:
            time.sleep(POLL)
            continue
        ll = line.lower()
        if f"l{locker} cl" in ll:
            elapsed = time.time() - open_time
            print(f"  🔒  L{locker} closed after {elapsed:.2f}s.")
            if elapsed <= FAST_OPEN_SEC:
                print(f"  ⚡  Closed within {FAST_OPEN_SEC}s → locker did NOT physically open.")
                return 'fast_close'
            return 'closed'

    print(f"  ⏰  Timeout — L{locker} never closed.")
    return 'timeout'


def do_quit(ser: serial.Serial):
    """Send Quit and wait for 'OK'."""
    print("\n  🔄  Sending 'Quit' to reset locker flags…")
    send(ser, "Quit")
    deadline = time.time() + 5
    while time.time() < deadline:
        line = read_line(ser)
        if line.strip().upper() == "OK":
            print("  ✅  STM acknowledged Quit (OK).")
            return
        time.sleep(POLL)
    print("  ⚠️   No 'OK' received after Quit.")


def do_reset(ser: serial.Serial):
    """Send reset and wait for 'System Ready'."""
    print("\n  🔄  Sending 'reset'…")
    send(ser, "reset")
    deadline = time.time() + 5
    while time.time() < deadline:
        line = read_line(ser)
        if "system ready" in line.lower():
            print(f"  ✅  STM reset OK: {line!r}")
            return
        time.sleep(POLL)
    print("  ⚠️   No 'System Ready' after reset.")


def operate_locker(ser: serial.Serial, locker: int) -> str:
    """
    Full open→close flow for one locker.
    Returns: 'success' | 'fast_close' | 'timeout' | 'no_open'
    """
    banner(f"Opening Locker {locker}")

    # reset before each command to clear stale state
    do_reset(ser)
    time.sleep(0.3)

    send(ser, str(locker))

    opened = wait_for_open(ser, locker)
    if not opened:
        return 'no_open'

    result = wait_for_close_check_fast(ser, locker)
    return result


# ─────────────────────────────────────────────
#  MAIN FLOW
# ─────────────────────────────────────────────
def main():
    banner("Locker Control — Terminal Test")

    # 1. Find & open serial port
    device = find_port()
    if not device:
        print("\n❌  Aborting — no suitable port found.")
        return

    ser = open_serial(device)
    if not ser:
        print("\n❌  Aborting — could not open serial port.")
        return

    try:
        # ── STEP 1: ping to verify comms ──────────────────────────
        print("\n🏓  Pinging STM (PING → ACK)…")
        send(ser, "PING")
        deadline = time.time() + 5
        ack = False
        while time.time() < deadline:
            line = read_line(ser)
            if "ack" in line.lower():
                print(f"  ✅  Got ACK: {line!r}")
                ack = True
                break
            time.sleep(POLL)
        if not ack:
            print("  ⚠️   No ACK — continuing anyway (STM may not support PING).")

        # ── STEP 2: try primary locker ────────────────────────────
        result = operate_locker(ser, LOCKER_PRIMARY)

        if result == 'success':
            # ── happy path ────────────────────────────────────────
            banner(f"✅  Locker {LOCKER_PRIMARY} opened & closed successfully!")

        elif result == 'fast_close':
            # op + cl within 2 s → locker didn't physically open
            banner(f"⚡  Locker {LOCKER_PRIMARY} did NOT open (fast op→cl detected)")
            print(f"  ➜  Sending 'Quit' and switching to Locker {LOCKER_FALLBACK}…")
            do_quit(ser)
            time.sleep(0.5)

            result2 = operate_locker(ser, LOCKER_FALLBACK)
            if result2 == 'success':
                banner(f"✅  Fallback Locker {LOCKER_FALLBACK} opened & closed successfully!")
            elif result2 == 'fast_close':
                banner(f"❌  Locker {LOCKER_FALLBACK} also fast-closed — hardware issue?")
                do_quit(ser)
            elif result2 == 'timeout':
                banner(f"⏰  Locker {LOCKER_FALLBACK} opened but never closed — manual intervention needed.")
            else:
                banner(f"❌  Could not open Locker {LOCKER_FALLBACK} either.")

        elif result == 'timeout':
            banner(f"⏰  Locker {LOCKER_PRIMARY} opened but never closed (timeout).")
            print("  ➜  Sending 'Quit' to reset system.")
            do_quit(ser)

        else:  # 'no_open'
            banner(f"❌  Locker {LOCKER_PRIMARY} did not respond / system busy.")
            print("  ➜  No fallback attempted (locker never confirmed open).")

    finally:
        if ser and ser.is_open:
            ser.close()
            print("\n🔌  Serial port closed. Goodbye.")


if __name__ == "__main__":
    main()