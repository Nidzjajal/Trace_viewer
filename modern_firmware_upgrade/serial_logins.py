import serial
import time
import os
import getpass
import serial.tools.list_ports


BAUD = 115200
TIMEOUT = 5

CREDENTIALS = [
    #{"username": "root", "password": "letmeinside!"},
    #{"username": "root", "password": "Nothinglikeanlu8!"},
    {"username": "root", "password": "root"},
]


def detect_usb_ports():
    return [
        (p.device, p.description)
        for p in serial.tools.list_ports.comports()
        if p.device.startswith("/dev/ttyUSB")
    ]
    

def list_serial_ports():
    ports = [p.device for p in serial.tools.list_ports.comports()]
    return ports


def print_permission_help(port):
    """Print helpful instructions when permission is denied."""
    user = getpass.getuser()
    print(f"\n{'='*60}")
    print("PERMISSION DENIED - Fix Instructions")
    print(f"{'='*60}")
    print(f"\nDevice: {port}")
    print(f"Current user: {user}")
    print(f"\nTo fix this issue, run one of the following commands:\n")
    print(f"Option 1: Add user to dialout group (recommended, permanent fix):")
    print(f"  sudo usermod -a -G dialout {user}")
    print(f"  Then log out and log back in, or run: newgrp dialout\n")
    print(f"Option 2: Change device permissions temporarily (until reboot):")
    print(f"  sudo chmod 666 {port}\n")
    print(f"Option 3: Use sudo to run this script (quick fix):")
    print(f"  sudo python3 multiple_device.py")
    print(f"\n{'='*60}\n")


def open_serial_interactive(ports):
    if isinstance(ports, tuple):
        port_device = ports[0]
        try:
            ser = serial.Serial(port_device, BAUD, timeout=TIMEOUT)
            time.sleep(2)
            return ser
        except (serial.SerialException, PermissionError) as e:
            print(f"Failed to open {port_device}: {e}")
            if "Permission denied" in str(e):
                print_permission_help(port_device)
            return None
    elif isinstance(ports, str):
        try:
            ser = serial.Serial(ports, BAUD, timeout=TIMEOUT)
            time.sleep(2)
            return ser
        except (serial.SerialException, PermissionError) as e:
            print(f"Failed to open {ports}: {e}")
            if "Permission denied" in str(e):
                print_permission_help(ports)
            return None

    if not ports:
        print("No serial ports detected.")
        return None

    print("\nAvailable serial ports:")
    for i, port in enumerate(ports):
        if isinstance(port, tuple):
            print(f"  [{i}] {port[0]} - {port[1]}")
        else:
            print(f"[{i}] {port}")

    print("\nOptions:")
    print("  - Enter port number (0,1,2...)")
    print("  - Enter full port name (/dev/ttyUSB0)")
    print("  - Enter 'q' to quit")

    while True:
        choice = input("\nSelect serial port: ").strip()

        if choice.lower() == "q":
            print("Exiting.")
            return None

        # If user entered index
        if choice.isdigit():
            idx = int(choice)
            if 0 <= idx < len(ports):
                port = ports[idx]
                # Extract device if it's a tuple
                if isinstance(port, tuple):
                    port = port[0]
            else:
                print("Invalid index. Try again.")
                continue
        else:
            port = choice

        try:
            ser = serial.Serial(port, BAUD, timeout=TIMEOUT)
            time.sleep(2)
            return ser
        except (serial.SerialException, PermissionError) as e:
            print(f"Failed to open {port}: {e}")
            if "Permission denied" in str(e):
                print_permission_help(port)
            retry = input("Try another port? (y/n/q): ").lower()
            if retry == "q":
                print("Exiting.")
                return None
            if retry != "y":
                return None

            
def read_output(ser, wait=1):
    """Read all available data from serial port using raw read.
    
    Continuously reads for 'wait' seconds, collecting all data.
    """
    data = b""
    start = time.time()
    while (time.time() - start) < wait:
        if ser.in_waiting:
            data += ser.read(ser.in_waiting)
        time.sleep(0.05)
    # Final drain
    while ser.in_waiting:
        data += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return data.decode(errors="ignore")


def login(ser):
    # Read any initial data
    read_output(ser, 0.5)
    
    for cred in CREDENTIALS:
        # Send carriage return to wake up
        ser.write(b"\r\n")
        ser.flush()
        time.sleep(1)
        read_output(ser, 0.5)
        
        # Send username
        ser.write((cred["username"] + "\r\n").encode())
        ser.flush()
        time.sleep(0.5)
        read_output(ser, 0.5)
        
        # Send password
        ser.write((cred["password"] + "\r\n").encode())
        ser.flush()
        time.sleep(1)
        output = read_output(ser, 1)
        
        if "login incorrect" in output.lower() or "failed" in output.lower():
            print(f" Login failed : [{ser.port}]")
        else:
            print(f"Login successful : [{ser.port}] ")
            # Wait for shell prompt and clear any remaining output
            ser.write(b"\r\n")
            ser.flush()
            read_output(ser, 0.5)
            return True
    return False
