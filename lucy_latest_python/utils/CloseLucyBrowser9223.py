# WINDOWS ONLY


import argparse
import subprocess

def kill_cdp_browser(port: int = 9223):
    cmd = (
        f"$con = Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue; "
        f"if ($con) {{ $con | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}; "
        f'Write-Host "CDP browser on port {port} has been closed." -ForegroundColor Green }} '
        f'else {{ Write-Host "No active browser session found on port {port}." -ForegroundColor Red }}'
    )
    subprocess.run(["powershell", "-Command", cmd])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Close CDP browser by port.")
    parser.add_argument("-p", "--port", type=int, default=9223, help="Port number")
    kill_cdp_browser()
    