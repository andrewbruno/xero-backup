"""Fetch and export Xero financial reports."""

import json
import logging
from pathlib import Path

from xero.exporters import save_report_csv

logger = logging.getLogger(__name__)

REPORTS = [
    {"name": "trial_balance", "endpoint": "Reports/TrialBalance"},
    {"name": "balance_sheet", "endpoint": "Reports/BalanceSheet"},
    {"name": "profit_and_loss", "endpoint": "Reports/ProfitAndLoss"},
    {"name": "aged_receivables", "endpoint": "Reports/AgedReceivablesByContact"},
    {"name": "aged_payables", "endpoint": "Reports/AgedPayablesByContact"},
    {"name": "bank_summary", "endpoint": "Reports/BankSummary"},
]


def fetch_all_reports(client, output_dir: Path):
    """Fetch all financial reports and save as JSON and CSV."""
    reports_dir = output_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for report_def in REPORTS:
        name = report_def["name"]
        print(f"  Fetching report: {name}...")

        try:
            data = client.get(report_def["endpoint"])
            reports = data.get("Reports", [])

            if not reports:
                logger.warning("  No data returned for report: %s", name)
                continue

            # Save raw JSON
            json_path = reports_dir / f"{name}.json"
            with open(json_path, "w") as f:
                json.dump(reports, f, indent=2, default=str)
            logger.info("  Saved report JSON: %s", json_path)

            # Flatten to CSV
            csv_path = reports_dir / f"{name}.csv"
            save_report_csv(csv_path, reports[0])

        except Exception as e:
            logger.error("  Failed to fetch report %s: %s", name, e)
