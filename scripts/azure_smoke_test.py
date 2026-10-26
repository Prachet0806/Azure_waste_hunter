"""Opt-in, non-destructive Azure smoke check for staging environments."""

from __future__ import annotations

import os
from uuid import uuid4

from scanner.resource_graph import query


def main() -> None:
    if os.getenv("AZURE_SMOKE_DELIVERY") == "1" and os.getenv("AZURE_SMOKE_ARCHIVE") != "1":
        raise ValueError("AZURE_SMOKE_DELIVERY=1 requires AZURE_SMOKE_ARCHIVE=1")
    rows = query("Resources | project id | take 1")
    if any(not isinstance(row.get("id"), str) or not row["id"] for row in rows):
        raise RuntimeError("Resource Graph smoke query returned an invalid resource shape")
    print(f"Resource Graph read-only query: OK ({len(rows)} sample rows)")

    run_id = f"smoke-{uuid4()}"
    report = f"Azure Waste Hunter staging smoke check: {run_id}"
    if os.getenv("AZURE_SMOKE_ARCHIVE") == "1":
        from delivery.blob import archive_report
        print(f"Smoke report archived: {archive_report(run_id, report)}")
    if os.getenv("AZURE_SMOKE_DELIVERY") == "1":
        from delivery.lgapp_sender import send_report
        outcome = send_report(report, run_id)
        print(f"Smoke notification: {outcome['status']}")


if __name__ == "__main__":
    main()
