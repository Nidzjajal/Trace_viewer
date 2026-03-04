import time


def read_output(ser, wait=1):
    """Read all available data from serial port using raw read (not readline)"""
    time.sleep(wait)
    data = b""
    # Read whatever is in the buffer
    while ser.in_waiting:
        data += ser.read(ser.in_waiting)
        time.sleep(0.05)
    return data.decode(errors="ignore")


def run_command(ser, command, wait=3, auto_yes=True, email="abc@liveu.tv"):
    """Send a command and capture all output.
    
    Reads data continuously while waiting, so nothing is lost from the buffer.
    """
    # Clear any leftover data in the buffer
    ser.reset_input_buffer()
    ser.reset_output_buffer()
    time.sleep(0.1)

    # Discard any pending data
    if ser.in_waiting:
        ser.read(ser.in_waiting)

    # Send the command
    ser.write((command + "\r\n").encode())
    ser.flush()

    # Continuously read output while waiting
    output = b""
    start = time.time()
    last_data_time = start
    min_wait = wait          # minimum seconds to keep reading
    idle_timeout = 2.0       # stop after this many seconds of no new data (after min_wait)

    while True:
        elapsed = time.time() - start
        idle = time.time() - last_data_time

        # Read whatever is available
        if ser.in_waiting:
            chunk = ser.read(ser.in_waiting)
            if chunk:
                output += chunk
                last_data_time = time.time()

                # Check for prompts that need auto-response
                if auto_yes:
                    decoded_chunk = chunk.decode(errors="ignore")
                    response = _check_for_prompt(decoded_chunk)
                    if response:
                        ser.write(response.encode())
                        ser.flush()
                        time.sleep(0.3)
                        continue
        else:
            time.sleep(0.1)

        # Exit conditions:
        # 1. We've waited at least min_wait AND no data for idle_timeout
        if elapsed >= min_wait and idle >= idle_timeout:
            break
        # 2. Hard cap to prevent infinite loops
        if elapsed >= (wait + 30):
            break

    # Final drain — grab anything still in the buffer
    time.sleep(0.3)
    while ser.in_waiting:
        output += ser.read(ser.in_waiting)
        time.sleep(0.05)

    decoded = output.decode(errors="ignore")

    # Strip the command echo from the beginning if present
    lines = decoded.split('\n')
    cleaned_lines = []
    command_stripped = command.strip()
    for line in lines:
        # Skip lines that are just the echoed command
        if command_stripped and line.strip() == command_stripped:
            continue
        cleaned_lines.append(line)
    decoded = '\n'.join(cleaned_lines)

    return decoded


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
