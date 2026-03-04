import time

def graceful_exit(ser):
    try:
        ser.write(b"exit\n")
        ser.flush()
        time.sleep(1)
    except Exception:
        pass
    finally:
        ser.close()
