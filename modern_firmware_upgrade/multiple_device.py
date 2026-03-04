from serial_logins import detect_usb_ports, open_serial_interactive, login
from serial_commands import run_command
from serial_exit import graceful_exit

import re
import time

# ============================================================
# CONFIGURATION — Change these values as needed
# ============================================================
CDC_WDM_DEVICE = "/dev/cdc-wdm2"          # <-- change to wdm0 or wdm1
FIRMWARE_VERSION = "03.04.06.00"
CONFIG_VERSION = "040.018_000"
CARRIER = "GENERIC"
FIRMWARE_DIR = "/storage/3_04_06"
CWE_FILE = "SWIX65C_03.04.06.00.cwe"
NVU_FILE = "SWIX65C_03.04.06.00_GENERIC_040.018_000.nvu"

# Step 1: Stop liveu service
COMMAND_STOP_LIVEU = "/etc/init.d/liveu stop"

# Step 2: Find mbim-proxy process
COMMAND_FIND_MBIM = "ps -ef | grep /usr/libexec/mbim-proxy"

# Step 4: Set firmware preference
COMMAND_SET_FIRMWARE = f'qmicli -d {CDC_WDM_DEVICE} --dms-set-firmware-preference="firmware-version={FIRMWARE_VERSION},config-version={CONFIG_VERSION},carrier={CARRIER}"'

# Step 5: Set operating mode to offline
COMMAND_SET_OFFLINE = f"qmicli -d {CDC_WDM_DEVICE} --dms-set-operating-mode=offline"

# Step 6: Set operating mode to reset
COMMAND_SET_RESET = f"qmicli -d {CDC_WDM_DEVICE} --dms-set-operating-mode=reset"

# Step 7: Get dmesg pattern
COMMAND_GET_DMESG = "dmesg | tail -1 | grep -oE '[0-9]+-[0-9]+\\.[0-9]+'"

# Step 8: Firmware upgrade command (will use var from step 7)
COMMAND_FIRMWARE_UPGRADE = f"/opt/liveu/hw_tests/sierra_firmware_upgrade -f {FIRMWARE_DIR} -m 4 -c MBIM -P {{var}} -t 3 -w {CWE_FILE} -n {NVU_FILE}"

liveu_start_command = "/etc/init.d/liveu start"


# ============================================================
# Helper: run a qmicli command with retry on timeout/closed
# ============================================================
def run_qmicli_with_retry(ser, command, step_name, max_retries=3, wait=5):
    """Run a qmicli command. If it fails with 'timed out' or 'device is closed',
    wait a few seconds and retry up to max_retries times."""
    for attempt in range(1, max_retries + 1):
        output = run_command(ser, command, wait=wait)
        print(f"Output: {output}")

        # Check for known transient errors
        if output and ("timed out" in output.lower() or "device is closed" in output.lower()):
            print(f"  ⚠ QmiDevice error detected (attempt {attempt}/{max_retries}). Retrying in 5s...")
            time.sleep(5)
            continue

        # Check for "couldn't open" errors
        if output and "couldn't open" in output.lower():
            print(f"  ⚠ Could not open device (attempt {attempt}/{max_retries}). Retrying in 5s...")
            time.sleep(5)
            continue

        # Success or unrecognised output — return as-is
        return output

    print(f"  ✗ {step_name} failed after {max_retries} attempts.")
    return output


# ============================================================
# MAIN FLOW
# ============================================================

# Detect and display available USB ports
ports = detect_usb_ports()
if not ports:
    print("No USB devices found")
    exit(1)

print("\n=== Available USB Devices ===")
for device, desc in ports:
    print(f"  {device} - {desc}")

# Open serial connection
results = {}
ser = open_serial_interactive(ports)
if not ser:
    print("No port selected or connection failed")
    exit(1)

device_name = ser.port
print(f"\n=== Connected to: {device_name} ===\n")

# Login to device
if not login(ser):
    print(f"Login failed on {device_name}")
    ser.close()
    exit(1)

print("\n=== Starting Firmware Upgrade Process ===\n")
start_time = time.time()

# ----------------------------------------------------------
# Step 1: Stop liveu service
# ----------------------------------------------------------
print("Step 1: Stopping liveu service...")
output = run_command(ser, COMMAND_STOP_LIVEU, wait=10)
print(f"Output: {output}")
time.sleep(3)

# ----------------------------------------------------------
# Step 2: Find mbim-proxy process
# ----------------------------------------------------------
print("\nStep 2: Finding mbim-proxy process...")
output = run_command(ser, COMMAND_FIND_MBIM, wait=5)
print(f"Output: {output}")

# ----------------------------------------------------------
# Step 3: Extract PID and kill the process
# ----------------------------------------------------------
pid = None
if output and output.strip():
    lines = output.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip the grep process itself and command echo
        if 'grep' in line:
            continue
        # Look for the actual mbim-proxy process line
        if '/usr/libexec/mbim-proxy' in line:
            parts = line.split()
            # ps -ef format: PID USER ... CMD (on busybox/embedded)
            # Find the first numeric token — that's the PID
            for part in parts:
                part = part.strip()
                if part.isdigit():
                    pid = part
                    break
            if pid:
                break

if pid:
    print(f"\nStep 3: Killing mbim-proxy process with PID: {pid}")
    kill_output = run_command(ser, f"kill -9 {pid}", wait=3)
    print(f"Kill output: {kill_output}")
    time.sleep(2)
    # Verify it's gone
    verify = run_command(ser, COMMAND_FIND_MBIM, wait=3)
    still_running = False
    if verify:
        for vline in verify.strip().split('\n'):
            if '/usr/libexec/mbim-proxy' in vline and 'grep' not in vline:
                still_running = True
    if still_running:
        print("  ⚠ mbim-proxy may still be running — check manually")
    else:
        print("  ✓ mbim-proxy killed successfully")
else:
    print("Step 3: No mbim-proxy process found to kill (may already be stopped)")

# Give the system time to release the device after killing mbim-proxy
time.sleep(3)

# ----------------------------------------------------------
# Step 4: Set firmware preference (with retry)
# ----------------------------------------------------------
print(f"\nStep 4: Setting firmware preference on {CDC_WDM_DEVICE}...")
output = run_qmicli_with_retry(ser, COMMAND_SET_FIRMWARE, "Set firmware preference", wait=10)

# ----------------------------------------------------------
# Step 5: Set operating mode to offline (with retry)
# ----------------------------------------------------------
print(f"\nStep 5: Setting operating mode to offline on {CDC_WDM_DEVICE}...")
output = run_qmicli_with_retry(ser, COMMAND_SET_OFFLINE, "Set offline mode", wait=5)

# ----------------------------------------------------------
# Step 6: Set operating mode to reset (with retry)
# ----------------------------------------------------------
print(f"\nStep 6: Setting operating mode to reset on {CDC_WDM_DEVICE}...")
output = run_qmicli_with_retry(ser, COMMAND_SET_RESET, "Set reset mode", wait=5)
time.sleep(5)  # give modem time to reset

# ----------------------------------------------------------
# Step 7: Get dmesg pattern
# ----------------------------------------------------------
print("\nStep 7: Getting dmesg pattern...")
# Try multiple times — the modem may take a moment to re-enumerate after reset
var = None
for dmesg_attempt in range(1, 4):
    output = run_command(ser, COMMAND_GET_DMESG, wait=3)
    print(f"Output: {output}")

    # Extract the pattern from output
    if output:
        for line in output.split('\n'):
            match = re.search(r'[0-9]+-[0-9]+\.[0-9]+', line)
            if match:
                var = match.group(0)
                print(f"  ✓ Extracted pattern: {var}")
                break
    if var:
        break
    print(f"  ⚠ Attempt {dmesg_attempt}/3 — no pattern found, retrying in 3s...")
    time.sleep(3)

if not var:
    print("  ✗ Warning: Could not extract dmesg pattern. Using empty value.")
    var = ""

# ----------------------------------------------------------
# Step 8: Firmware upgrade
# ----------------------------------------------------------
print(f"\nStep 8: Running firmware upgrade with pattern: {var}")
upgrade_command = COMMAND_FIRMWARE_UPGRADE.format(var=var)
print(f"  Command: {upgrade_command}")
output = run_command(ser, upgrade_command, wait=30)  # firmware upgrade takes long
print(f"Output: {output}")

# Check for the specific message
if output and "Application version: 1.0.2402.1" in output and "Unable to locate the device or determine device mode." in output:
    print("\n*** Modem is already in version 6. ***")

results[device_name] = output

# ----------------------------------------------------------
# Step 9: Start liveu service
# ----------------------------------------------------------
print("\nStep 9: Starting liveu service...")
output = run_command(ser, liveu_start_command, wait=15)
print(f"Output: {output}")

# ----------------------------------------------------------
# Done
# ----------------------------------------------------------
end_time = time.time()
total_time = end_time - start_time
print(f"\n=== Firmware Upgrade Process Completed ===")
print(f"Total time taken: {total_time:.2f} seconds")

graceful_exit(ser)

print("\n=== OUTPUT ===")
for port, out in results.items():
    print(f"\n{out}")
