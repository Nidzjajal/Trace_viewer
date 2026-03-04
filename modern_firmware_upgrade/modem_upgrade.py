#!/usr/bin/env python3
"""
Modem Firmware Upgrade Script
Self-contained script for upgrading modem firmware via serial connection
"""

import serial
import serial.tools.list_ports
import time
import re
import os
import getpass

# ============================================================================
# CONFIGURATION
# ============================================================================

BAUD_RATE = 115200
TIMEOUT = 5

# Login credentials (try in order)
CREDENTIALS = [
    {"username": "root", "password": "root"},
    # Add more credentials if needed:
    # {"username": "root", "password": "letmeinside!"},
]

# Firmware version configuration
FIRMWARE_VERSION = "03.04.10.01"
CONFIG_VERSION = "040.024_000"
CARRIER = "GENERIC"
FIRMWARE_PATH = "/storage/3_04_10"
FIRMWARE_CWE = "SWIX65C_03.04.10.01.cwe"
FIRMWARE_NVU = "SWIX65C_03.04.10.01_GENERIC_040.024_000.nvu"

# ============================================================================
# SERIAL COMMUNICATION FUNCTIONS
# ============================================================================

def read_serial_output(ser, wait=1):
    """Read all available data from serial port using raw read"""
    time.sleep(wait)
    data = b""
    while ser.in_waiting:
        data += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return data.decode(errors="ignore")


def run_command(ser, command, wait=3):
    """Send a command and capture all output"""
    # Clear any leftover data in the buffer
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.2)
    
    # Read and discard any pending data
    if ser.in_waiting:
        ser.read(ser.in_waiting)
    
    # Send the command
    ser.write((command + "\r\n").encode())
    ser.flush()
    
    # Wait for command to execute and output to arrive
    output = ""
    max_wait = wait + 10  # Total max seconds to wait
    start = time.time()
    no_data_count = 0
    
    # Initial wait for command to start producing output
    time.sleep(wait)
    
    while (time.time() - start) < max_wait:
        # Read all available bytes
        if ser.in_waiting:
            data = ser.read(ser.in_waiting)
            if data:
                chunk = data.decode(errors="ignore")
                output += chunk
                no_data_count = 0
                
                # Check for prompts that need auto-response
                response = _check_for_prompt(chunk)
                if response:
                    ser.write(response.encode())
                    ser.flush()
                    time.sleep(0.5)
                    continue
        else:
            no_data_count += 1
            if no_data_count >= 10:  # ~1 second of no data
                break
            time.sleep(0.1)
    
    # Final read — grab anything left
    time.sleep(0.3)
    if ser.in_waiting:
        final = ser.read(ser.in_waiting)
        if final:
            output += final.decode(errors="ignore")
    
    return output


def _check_for_prompt(text):
    """Check if text contains a prompt that needs auto-response"""
    lines = text.split('\n')
    last_lines = lines[-5:] if len(lines) > 5 else lines
    
    for line in last_lines:
        line_stripped = line.strip()
        line_lower = line_stripped.lower()
        
        if '[yn]' in line_lower:
            return "y\n"
        elif any(p in line_stripped for p in ["Y/N", "[Y/N]", "(Y/N)", "Y or N"]):
            return "Y\n"
        elif any(p in line_lower for p in ["y/n", "[y/n]", "(y/n)", "y or n"]):
            return "y\n"
        elif any(p in line_stripped for p in ["YES/NO", "[YES/NO]", "(YES/NO)", "YES or NO"]):
            return "YES\n"
        elif any(p in line_lower for p in ["yes/no", "[yes/no]", "(yes/no)", "yes or no"]):
            return "yes\n"
        elif 'continue' in line_lower and '?' in line_stripped:
            return "y\n"
        elif any(p in line_lower for p in ["proceed?", "are you sure", "confirm"]):
            return "yes\n"
    
    return None


# ============================================================================
# CONNECTION FUNCTIONS
# ============================================================================

def detect_usb_ports():
    """Detect available USB serial ports"""
    ports = [
        (p.device, p.description)
        for p in serial.tools.list_ports.comports()
        if p.device.startswith("/dev/ttyUSB")
    ]
    return ports


def open_serial_connection(ports):
    """Open serial connection to device"""
    if not ports:
        print("No USB devices found")
        return None
    
    # If single port, use it directly
    if len(ports) == 1:
        port_device = ports[0][0]
        try:
            ser = serial.Serial(port_device, BAUD_RATE, timeout=TIMEOUT)
            time.sleep(2)
            print(f"Connected to {port_device}")
            return ser
        except serial.SerialException as e:
            error_msg = str(e)
            print(f"Failed to open {port_device}: {e}")
            if "Permission denied" in error_msg or "Errno 13" in error_msg:
                print_permission_help(port_device)
            return None
        except PermissionError as e:
            print(f"Permission denied: {e}")
            print_permission_help(port_device)
            return None
    
    # Multiple ports - let user choose
    print("\nAvailable USB ports:")
    for i, (device, desc) in enumerate(ports):
        print(f"  [{i}] {device} - {desc}")
    
    while True:
        choice = input("\nSelect port number (or 'q' to quit): ").strip()
        
        if choice.lower() == 'q':
            return None
        
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(ports):
                port_device = ports[idx][0]
                try:
                    ser = serial.Serial(port_device, BAUD_RATE, timeout=TIMEOUT)
                    time.sleep(2)
                    print(f"Connected to {port_device}")
                    return ser
                except serial.SerialException as e:
                    error_msg = str(e)
                    print(f"Failed to open {port_device}: {e}")
                    if "Permission denied" in error_msg or "Errno 13" in error_msg:
                        print_permission_help(port_device)
                        retry = input("\nTry again after fixing permissions? (y/n/q): ").lower()
                        if retry == 'q':
                            return None
                        elif retry != 'y':
                            continue
                    else:
                        retry = input("Try another port? (y/n/q): ").lower()
                        if retry == 'q':
                            return None
                        elif retry != 'y':
                            return None
                except PermissionError as e:
                    print(f"Permission denied: {e}")
                    print_permission_help(port_device)
                    retry = input("\nTry again after fixing permissions? (y/n/q): ").lower()
                    if retry == 'q':
                        return None
                    elif retry != 'y':
                        continue
            else:
                print("Invalid index. Try again.")
        else:
            print("Invalid input. Enter a number or 'q'.")


def print_permission_help(port_device):
    """Print helpful instructions for fixing permission issues"""
    current_user = getpass.getuser()
    
    print("\n" + "=" * 60)
    print("PERMISSION DENIED - Fix Instructions")
    print("=" * 60)
    print(f"\nDevice: {port_device}")
    print(f"Current user: {current_user}")
    print("\nTo fix this issue, run one of the following commands:")
    print("\nOption 1: Add user to dialout group (recommended, permanent fix):")
    print(f"  sudo usermod -a -G dialout {current_user}")
    print("  Then log out and log back in, or run: newgrp dialout")
    print("\nOption 2: Change device permissions temporarily (until reboot):")
    print(f"  sudo chmod 666 {port_device}")
    print("\nOption 3: Use sudo to run this script (quick fix):")
    print("  sudo python3 modem_upgrade.py")
    print("\nNote: If you see 'sudo: unable to resolve host' warning,")
    print("      it's harmless and doesn't prevent sudo from working.")
    print("      You can ignore it or fix it later by editing /etc/hosts")
    print("\n" + "=" * 60)


def login(ser):
    """Login to the device"""
    read_serial_output(ser, 0.5)
    
    for cred in CREDENTIALS:
        # Wake up device
        ser.write(b"\n")
        ser.flush()
        time.sleep(1)
        
        # Send username
        ser.write((cred["username"] + "\n").encode())
        ser.flush()
        read_serial_output(ser, 0.5)
        
        # Send password
        ser.write((cred["password"] + "\n").encode())
        ser.flush()
        time.sleep(1)
        output = read_serial_output(ser, 1)
        
        if "login incorrect" in output.lower() or "failed" in output.lower():
            print(f"Login failed with {cred['username']}")
        else:
            print(f"Login successful as {cred['username']}")
            ser.write(b"\n")
            ser.flush()
            read_serial_output(ser, 0.5)
            return True
    
    return False


def close_connection(ser):
    """Close serial connection gracefully"""
    try:
        ser.write(b"exit\n")
        ser.flush()
        time.sleep(1)
    except Exception:
        pass
    finally:
        ser.close()
        print("Connection closed")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def extract_pid_from_output(output):
    """Extract PID from ps -ef output"""
    if not output or not output.strip():
        return None
    
    # Clean up output - remove command echo and prompts
    lines = output.strip().split('\n')
    for line in lines:
        line = line.strip()
        
        # Skip empty lines
        if not line:
            continue
        
        # Skip command echo (line that contains the command itself)
        if 'ps -ef' in line and 'grep' in line:
            continue
        
        # Skip grep process line
        if 'grep' in line and '/usr/libexec/mbim-proxy' in line:
            continue
        
        # Skip shell prompts
        if any(pattern in line for pattern in ['root@', '$', '#', 'bash', 'sh-']):
            continue
        
        # Look for mbim-proxy process line
        if '/usr/libexec/mbim-proxy' in line:
            parts = line.split()
            # ps -ef format: UID PID PPID C STIME TTY TIME CMD
            # So PID is at index 1 (second column)
            if len(parts) >= 2:
                pid = parts[1].strip()
                # Remove any non-digit characters
                pid = ''.join(filter(str.isdigit, pid))
                if pid and pid.isdigit():
                    return pid
    
    return None


def find_cdc_wdm_number(ser, max_attempts=10):
    """Find cdc-wdm device number from dmesg (loop until found)"""
    print("  Searching for cdc-wdm device number...")
    
    for attempt in range(1, max_attempts + 1):
        output = run_command(ser, "dmesg | grep cdc-wdm", wait=2)
        print(f"  Attempt {attempt}: {output.strip()}")
        
        # Look for pattern like "cdc-wdm0", "cdc-wdm1", etc.
        match = re.search(r'cdc-wdm(\d+)', output)
        if match:
            number = match.group(1)
            print(f"  ✓ Found cdc-wdm device: cdc-wdm{number}")
            return number
        
        time.sleep(1)
    
    print("  ⚠ Could not find cdc-wdm device number, using default 0")
    return "0"


def extract_dmesg_pattern(ser):
    """Extract dmesg pattern (e.g., 3-1.3) for firmware upgrade"""
    # Use same command as multiple_device.py: dmesg | tail -1 | grep -oE
    output = run_command(ser, "dmesg | tail -1 | grep -oE '[0-9]+-[0-9]+\\.[0-9]+'", wait=2)
    
    # Extract pattern from output
    var = None
    lines = output.split('\n')
    for line in lines:
        match = re.search(r'[0-9]+-[0-9]+\.[0-9]+', line)
        if match:
            var = match.group(0)
            print(f"  ✓ Extracted pattern: {var}")
            return var
    
    print("  ⚠ Could not extract dmesg pattern")
    return None


# ============================================================================
# MAIN UPGRADE PROCESS
# ============================================================================

def main():
    """Main firmware upgrade process"""
    print("=" * 60)
    print("Modem Firmware Upgrade Script")
    print("=" * 60)
    
    # Step 0: Connect to device
    print("\n[Step 0] Connecting to device...")
    ports = detect_usb_ports()
    ser = open_serial_connection(ports)
    if not ser:
        print("Failed to connect. Exiting.")
        return
    
    # Login
    if not login(ser):
        print("Login failed. Exiting.")
        close_connection(ser)
        return
    
    print("\n" + "=" * 60)
    print("Starting Firmware Upgrade Process")
    print("=" * 60)
    start_time = time.time()
    
    try:
        # Step 1: Stop liveu service
        print("\n[Step 1] Stopping liveu service...")
        output = run_command(ser, "/etc/init.d/liveu stop", wait=5)
        print(f"Output: {output.strip()}")
        time.sleep(2)
        
        # Step 2: Find mbim-proxy process
        print("\n[Step 2] Finding mbim-proxy process...")
        output = run_command(ser, "ps -ef | grep /usr/libexec/mbim-proxy", wait=5)
        print(f"Raw output (repr): {repr(output)}")
        print(f"Output: {output}")
        
        # Step 3: Kill mbim-proxy process
        print("\n[Step 3] Killing mbim-proxy process...")
        pid = extract_pid_from_output(output)
        print(f"Extracted PID: {pid}")
        
        if pid:
            print(f"  Found PID: {pid}")
            kill_output = run_command(ser, f"kill -9 {pid}", wait=3)
            print(f"  Kill output: {kill_output}")
            time.sleep(1)
            
            # Verify process was killed
            verify_output = run_command(ser, "ps -ef | grep /usr/libexec/mbim-proxy", wait=3)
            if pid not in verify_output or '/usr/libexec/mbim-proxy' not in verify_output:
                print(f"  ✓ Process {pid} successfully killed")
            else:
                print(f"  ⚠ Warning: Process {pid} may still be running")
        else:
            print("  No mbim-proxy process found (may already be stopped)")
            print(f"  Debug: Output length = {len(output)}, Output content = {repr(output[:200])}")
        
        # Step 4: Use cdc-wdm0 device (hardcoded)
        print("\n[Step 4] Using cdc-wdm0 device...")
        cdc_wdm_device = "/dev/cdc-wdm0"
        print(f"  Using device: {cdc_wdm_device}")
        
        # Step 5: Set firmware preference
        print("\n[Step 5] Setting firmware preference...")
        firmware_cmd = (
            f'qmicli -d {cdc_wdm_device} --dms-set-firmware-preference='
            f'"firmware-version={FIRMWARE_VERSION},'
            f'config-version={CONFIG_VERSION},carrier={CARRIER}"'
        )
        output = run_command(ser, firmware_cmd, wait=3)
        print(f"Output: {output.strip()}")
        
        # Step 6: Set operating mode to offline
        print("\n[Step 6] Setting operating mode to offline...")
        output = run_command(ser, f"qmicli -d {cdc_wdm_device} --dms-set-operating-mode=offline", wait=3)
        print(f"Output: {output.strip()}")
        
        # Step 7: Set operating mode to reset
        print("\n[Step 7] Setting operating mode to reset...")
        output = run_command(ser, f"qmicli -d {cdc_wdm_device} --dms-set-operating-mode=reset", wait=3)
        print(f"Output: {output.strip()}")
        time.sleep(2)
        
        # Step 8: Get dmesg pattern for mapping
        print("\n[Step 8] Getting dmesg pattern for mapping...")
        dmesg_pattern = extract_dmesg_pattern(ser)
        if not dmesg_pattern:
            print("  ⚠ Warning: Could not extract dmesg pattern. Using empty value.")
            dmesg_pattern = ""  # Empty fallback (matching multiple_device.py behavior)
        
        # Step 9: Firmware upgrade
        print("\n[Step 9] Running firmware upgrade...")
        upgrade_cmd = (
            f"/opt/liveu/hw_tests/sierra_firmware_upgrade "
            f"-f {FIRMWARE_PATH} "
            f"-m 4 -c MBIM "
            f"-P {dmesg_pattern} "
            f"-t 3 "
            f"-w {FIRMWARE_CWE} "
            f"-n {FIRMWARE_NVU}"
        )
        print(f"Command: {upgrade_cmd}")
        output = run_command(ser, upgrade_cmd, wait=10)
        print(f"Output: {output.strip()}")
        
        # Check for specific messages
        if "Application version: 1.0.2402.1" in output and "Unable to locate the device" in output:
            print("\n*** Modem is already in version 6. ***")
        
        # Restart liveu service
        print("\n[Step 10] Starting liveu service...")
        output = run_command(ser, "/etc/init.d/liveu start", wait=10)
        print(f"Output: {output.strip()}")
        
        # Summary
        end_time = time.time()
        total_time = end_time - start_time
        print("\n" + "=" * 60)
        print("Firmware Upgrade Process Completed")
        print(f"Total time: {total_time:.2f} seconds")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error during upgrade: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        close_connection(ser)


if __name__ == "__main__":
    main()
