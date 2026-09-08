import os
import sys
import time
import base64
import socket
import threading
import traceback
import subprocess
import importlib.util
from pathlib import Path
from datetime import datetime
from email.message import EmailMessage

ROOT = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython")
MAIN = ROOT / "main.py"
ABILITY = ROOT / "LUCY_ABILITIES" / "lucy-watchdog"
LOG_DIR = ABILITY / "logs"
STATE = ABILITY / "watchdog-state.txt"
HANDLER = ROOT / "Services[IGNORE]" / "Emailing" / "Gmailhandler.py"
RECIPIENT = "raghavkkapoor7@gmail.com"

LOG_DIR.mkdir(parents=True, exist_ok=True)

RESTART_DELAY_SECONDS = 0.10
CRASH_LOOP_WINDOW = 60
CRASH_LOOP_LIMIT = 5
CRASH_LOOP_BACKOFF = 5

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def write_state(**values):
    try:
        text = "\n".join(f"{k}={v}" for k, v in values.items()) + "\n"
        STATE.write_text(text, encoding="utf-8")
    except Exception:
        pass

def send_email(log_path, exit_code, old_pid, new_pid):
    try:
        spec = importlib.util.spec_from_file_location("lucy_gmailhandler", str(HANDLER))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        service = mod.setup_gmail()
        if service is None:
            raise RuntimeError("Gmail authentication failed")

        sender = service.users().getProfile(userId="me").execute()["emailAddress"]

        msg = EmailMessage()
        msg["To"] = RECIPIENT
        msg["From"] = sender
        msg["Subject"] = f"Lucy crashed and restarted - {timestamp()}"

        msg.set_content(
            "Lucy crashed or exited unexpectedly and the watchdog restarted it.\n\n"
            f"Detected: {timestamp()}\n"
            f"Computer: {socket.gethostname()}\n"
            f"Exit code: {exit_code}\n"
            f"Old Lucy PID: {old_pid}\n"
            f"Restarted Lucy PID: {new_pid}\n\n"
            "The captured console/error log from the failed instance is attached."
        )

        with open(log_path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype="text",
                subtype="plain",
                filename=Path(log_path).name
            )

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

        result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        with open(log_path, "a", encoding="utf-8", errors="replace") as f:
            f.write("\nEMAIL_SENT=True\n")
            f.write("EMAIL_MESSAGE_ID=" + str(result.get("id", "")) + "\n")

    except Exception:
        try:
            with open(log_path, "a", encoding="utf-8", errors="replace") as f:
                f.write("\n=== EMAIL FAILURE ===\n")
                f.write(traceback.format_exc())
        except Exception:
            pass

def pump_output(proc, logfile):
    """
    Relay stdout immediately, including prompts that do not end in '\n'.

    readline() caused prompts such as:
        Enter a task/goal to achieve:
    to remain invisible until later output produced a newline.

    read(1) forwards each available character immediately.
    """
    try:
        while True:
            chunk = proc.stdout.read(1)

            if chunk == "":
                if proc.poll() is not None:
                    break

                time.sleep(0.005)
                continue

            try:
                sys.stdout.write(chunk)
                sys.stdout.flush()
            except Exception:
                pass

            try:
                logfile.write(chunk)
                logfile.flush()
            except Exception:
                pass

    except Exception:
        try:
            logfile.write("\n=== OUTPUT CAPTURE FAILURE ===\n")
            logfile.write(traceback.format_exc())
            logfile.flush()
        except Exception:
            pass

def launch_lucy():
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_path = LOG_DIR / f"lucy_{run_id}.log"

    logfile = open(
        log_path,
        "w",
        encoding="utf-8",
        errors="replace",
        buffering=1
    )

    logfile.write("=== LUCY WATCHDOG SESSION ===\n")
    logfile.write(f"Started: {timestamp()}\n")
    logfile.write(f"Python: {sys.executable}\n")
    logfile.write(f"main.py: {MAIN}\n\n")
    logfile.flush()

    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    proc = subprocess.Popen(
        [sys.executable, "-u", str(MAIN)],
        cwd=str(ROOT),

        # Keep Lucy interactive.
        stdin=None,

        # Capture both streams while teeing them to this console.
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,

        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,

        creationflags=creationflags
    )

    thread = threading.Thread(
        target=pump_output,
        args=(proc, logfile),
        daemon=True
    )
    thread.start()

    write_state(
        WATCHDOG_PID=os.getpid(),
        LUCY_PID=proc.pid,
        STATUS="RUNNING",
        STARTED=timestamp(),
        LOG=log_path
    )

    return proc, thread, logfile, log_path

print("LUCY_WATCHDOG_STARTED=True")
print(f"WATCHDOG_PID={os.getpid()}")
sys.stdout.flush()

crashes = []

while True:
    proc = None
    thread = None
    logfile = None

    try:
        proc, thread, logfile, log_path = launch_lucy()
        old_pid = proc.pid

        exit_code = proc.wait()

        try:
            thread.join(timeout=2)
        except Exception:
            pass

        runtime_end = time.time()

        try:
            logfile.write("\n=== PROCESS EXIT ===\n")
            logfile.write(f"Detected: {timestamp()}\n")
            logfile.write(f"PID: {old_pid}\n")
            logfile.write(f"Exit code: {exit_code}\n")
            logfile.flush()
        except Exception:
            pass

        # Exit code 0 means Lucy intentionally completed/stopped.
        if exit_code == 0:
            write_state(
                WATCHDOG_PID=os.getpid(),
                LUCY_PID="",
                STATUS="CLEAN_EXIT",
                EXIT_CODE=exit_code,
                TIME=timestamp(),
                LOG=log_path
            )

            try:
                logfile.close()
            except Exception:
                pass

            print("LUCY_CLEAN_EXIT=True")
            sys.stdout.flush()
            break

        # -------------------------------------------------------------
        # CRASH PATH
        # -------------------------------------------------------------
        now = time.time()
        crashes = [x for x in crashes if now - x < CRASH_LOOP_WINDOW]
        crashes.append(now)

        try:
            logfile.write("CRASH_DETECTED=True\n")
            logfile.write("WATCHDOG_ACTION=RESTART_IMMEDIATELY\n")
            logfile.flush()
            logfile.close()
        except Exception:
            pass

        write_state(
            WATCHDOG_PID=os.getpid(),
            LUCY_PID="",
            STATUS="CRASH_DETECTED",
            EXIT_CODE=exit_code,
            TIME=timestamp(),
            LOG=log_path
        )

        print(f"LUCY_CRASH_DETECTED=True|PID={old_pid}|EXIT_CODE={exit_code}")
        sys.stdout.flush()

        # Tiny delay only to let Windows release handles.
        time.sleep(RESTART_DELAY_SECONDS)

        # Restart FIRST to minimize downtime.
        new_proc, new_thread, new_logfile, new_log_path = launch_lucy()
        new_pid = new_proc.pid

        print(f"LUCY_RESTARTED=True|NEW_PID={new_pid}")
        sys.stdout.flush()

        # Send notification independently so Gmail/network latency cannot delay restart.
        threading.Thread(
            target=send_email,
            args=(str(log_path), exit_code, old_pid, new_pid),
            daemon=True
        ).start()

        # We already launched the replacement, so monitor this exact process here.
        proc = new_proc
        thread = new_thread
        logfile = new_logfile
        log_path = new_log_path

        while True:
            exit_code = proc.poll()

            if exit_code is not None:
                try:
                    thread.join(timeout=2)
                except Exception:
                    pass

                try:
                    logfile.write("\n=== PROCESS EXIT ===\n")
                    logfile.write(f"Detected: {timestamp()}\n")
                    logfile.write(f"PID: {proc.pid}\n")
                    logfile.write(f"Exit code: {exit_code}\n")
                    logfile.flush()
                except Exception:
                    pass

                if exit_code == 0:
                    try:
                        logfile.close()
                    except Exception:
                        pass

                    write_state(
                        WATCHDOG_PID=os.getpid(),
                        LUCY_PID="",
                        STATUS="CLEAN_EXIT",
                        EXIT_CODE=exit_code,
                        TIME=timestamp(),
                        LOG=log_path
                    )

                    sys.exit(0)

                # Close this log and let outer loop restart it again.
                try:
                    logfile.write("CRASH_DETECTED=True\n")
                    logfile.flush()
                    logfile.close()
                except Exception:
                    pass

                # email current crash after next restart
                previous_log = str(log_path)
                previous_code = exit_code
                previous_pid = proc.pid

                now = time.time()
                crashes = [x for x in crashes if now - x < CRASH_LOOP_WINDOW]
                crashes.append(now)

                if len(crashes) >= CRASH_LOOP_LIMIT:
                    time.sleep(CRASH_LOOP_BACKOFF)
                else:
                    time.sleep(RESTART_DELAY_SECONDS)

                next_proc, next_thread, next_logfile, next_log_path = launch_lucy()

                threading.Thread(
                    target=send_email,
                    args=(
                        previous_log,
                        previous_code,
                        previous_pid,
                        next_proc.pid
                    ),
                    daemon=True
                ).start()

                proc = next_proc
                thread = next_thread
                logfile = next_logfile
                log_path = next_log_path
                continue

            time.sleep(0.10)

    except KeyboardInterrupt:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

        write_state(
            WATCHDOG_PID=os.getpid(),
            LUCY_PID="",
            STATUS="WATCHDOG_STOPPED",
            TIME=timestamp()
        )
        break

    except Exception:
        watchdog_error = LOG_DIR / (
            "watchdog_error_" +
            datetime.now().strftime("%Y%m%d_%H%M%S_%f") +
            ".log"
        )

        try:
            watchdog_error.write_text(
                traceback.format_exc(),
                encoding="utf-8"
            )
        except Exception:
            pass

        # Protect the watchdog itself from transient internal errors.
        time.sleep(1)

