# WINDOWS ONLY

import argparse
import subprocess

def kill_cdp_browser(port: int = 9223):
    cmd = (
        f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"
    )
    subprocess.run(["powershell", "-Command", cmd])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Close CDP browser by port.")
    parser.add_argument("-p", "--port", type=int, default=9223, help="Port number")
    kill_cdp_browser()
    