"""Sample app process-tree socket tables; explicitly not a complete egress audit."""
import json
import ipaddress
import subprocess
import sys
import time
from pathlib import Path

import psutil


def main():
    output = Path("reports/runtime/network-observation")
    output.mkdir(parents=True, exist_ok=True)
    observed, inaccessible = {}, set()
    process = subprocess.Popen([sys.executable, "scripts/verify_ocr.py"],
        stdout=(output / "synthetic-run.txt").open("w"), stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW)
    samples = 0
    while process.poll() is None:
        samples += 1
        try:
            processes = [psutil.Process(process.pid)] + psutil.Process(process.pid).children(recursive=True)
        except psutil.Error:
            processes = []
        for child in processes:
            try:
                key = f"{child.pid}:{child.create_time()}"
                row = observed.setdefault(key, {"process": child.name(), "loopback_entry_observations": 0,
                    "nonloopback_remote_entry_observations": 0, "nonloopback_bound_entry_observations": 0})
                # Only counts are retained; unrelated processes and endpoints are not recorded.
                for connection in child.net_connections(kind="inet"):
                    if connection.raddr and not ipaddress.ip_address(connection.raddr.ip).is_loopback:
                        row["nonloopback_remote_entry_observations"] += 1
                    elif connection.laddr and not ipaddress.ip_address(connection.laddr.ip).is_loopback:
                        row["nonloopback_bound_entry_observations"] += 1
                    else:
                        row["loopback_entry_observations"] += 1
            except psutil.AccessDenied:
                inaccessible.add(key)
            except psutil.NoSuchProcess:
                pass
        time.sleep(.01)
    report = {"synthetic_run_exit_code": process.returncode, "sample_count": samples,
              "processes_observed": list(observed.values()), "inaccessible_process_count": len(inaccessible),
              "complete_egress_audit": False,
              "limits": ["Socket-table sampling can miss short-lived connections and attempts",
                         "Entry counts can count the same socket repeatedly; they are not connection-attempt counts",
                         "Native OCR system services outside the descendant tree are not attributed",
                         "No OS-level network blocking or security policy change was performed"]}
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    assert process.returncode == 0


if __name__ == "__main__":
    main()
