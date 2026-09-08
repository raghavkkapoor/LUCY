import os
import sqlite3
import psutil
import wmi

# Set DB path to the same directory as this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(SCRIPT_DIR, "pc_specs.db")


def init_db():
    """Creates the specs table if it doesn't already exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pc_specs (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_specs_to_sqlite():
    """Gathers system specs and inserts/updates them in the SQLite DB."""
    w = wmi.WMI()

    # Hardware Specs
    cpu_obj = w.Win32_Processor()[0]
    gpu_obj = w.Win32_VideoController()[0]
    os_obj = w.Win32_OperatingSystem()[0]

    cpu = cpu_obj.Name.strip()
    gpu = gpu_obj.Name

    vram_gb = round(int(gpu_obj.AdapterRAM or 0) / (1024**3), 1)
    ram_gb = round(psutil.virtual_memory().total / (1024**3))

    # Storage Specs
    drives = [
        p for p in psutil.disk_partitions(all=False) if "cdrom" not in p.opts
    ]
    drive_count = len(drives)

    total_storage_bytes = 0
    drive_free_list = []

    for drive in drives:
        try:
            usage = psutil.disk_usage(drive.mountpoint)
            total_storage_bytes += usage.total
            free_gb = round(usage.free / (1024**3))
            drive_letter = drive.device.rstrip(":\\").rstrip("\\")
            drive_free_list.append(f"{drive_letter}: {free_gb} GB free")
        except PermissionError:
            continue

    total_storage_gb = round(total_storage_bytes / (1024**3))

    # OS Spec
    os_name = os_obj.Caption.strip()

    # Formatted String Values
    specs_data = {
        "cpu": f"CPU         {cpu}",
        "gpu": f"GPU         {gpu}",
        "vram": f"VRAM        {vram_gb} GB",
        "ram": f"RAM         {ram_gb} GB",
        "storage_summary": f"Storage     {total_storage_gb} GB total | {drive_count} drive(s)",
        "os": f"OS          {os_name}",
    }

    # Add drive details as individual keys
    for idx, drive_str in enumerate(drive_free_list, start=1):
        specs_data[f"drive_{idx}"] = f"            {drive_str}"

    # Display Specs
    displays = [
        d
        for d in w.Win32_VideoController()
        if d.CurrentHorizontalResolution and d.CurrentVerticalResolution
    ]

    for idx, display in enumerate(displays, start=1):
        specs_data[f"display_{idx}"] = (
            f"Display {idx} : {display.CurrentHorizontalResolution} x "
            f"{display.CurrentVerticalResolution} @ {display.CurrentRefreshRate} Hz"
        )

    # Save to SQLite
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Insert or replace values into the key-value table
    for key, value in specs_data.items():
        cursor.execute(
            """
            INSERT INTO pc_specs (key, value) 
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
            (key, value),
        )

    conn.commit()
    conn.close()
    print(f"Saved PC specs to database at: {DB_PATH}")


if __name__ == "__main__":
    save_specs_to_sqlite()