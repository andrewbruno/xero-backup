"""JSON and CSV export functions for Xero backup data."""

import csv
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def save_json(output_dir: Path, entity_name: str, records: list):
    """Save records as a pretty-printed JSON file."""
    filepath = output_dir / "json" / f"{entity_name}.json"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w") as f:
        json.dump(records, f, indent=2, default=str)

    logger.info("  Saved %d records to %s", len(records), filepath)


def save_csv(output_dir: Path, entity_name: str, records: list):
    """Save records as a flattened CSV file."""
    if not records:
        return

    filepath = output_dir / "csv" / f"{entity_name}.csv"
    filepath.parent.mkdir(parents=True, exist_ok=True)

    flat_records = [flatten_record(r) for r in records]

    # Collect all keys in insertion order across all records
    all_keys: list[str] = []
    seen: set[str] = set()
    for r in flat_records:
        for k in r:
            if k not in seen:
                all_keys.append(k)
                seen.add(k)

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=all_keys, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_records)

    logger.info("  Saved %d records to %s", len(records), filepath)


def flatten_record(record: dict, prefix: str = "") -> dict:
    """
    Recursively flatten a nested dict/list structure for CSV output.

    Examples:
        {"Contact": {"Name": "Bob"}} -> {"Contact_Name": "Bob"}
        {"LineItems": [{"Desc": "A"}]} -> {"LineItems_0_Desc": "A"}
        {"Tags": ["a", "b"]} -> {"Tags": "a; b"}
    """
    flat = {}

    for key, value in record.items():
        full_key = f"{prefix}_{key}" if prefix else key

        if isinstance(value, dict):
            flat.update(flatten_record(value, full_key))
        elif isinstance(value, list):
            if not value:
                flat[full_key] = ""
            elif isinstance(value[0], dict):
                for i, item in enumerate(value):
                    flat.update(flatten_record(item, f"{full_key}_{i}"))
            else:
                flat[full_key] = "; ".join(str(v) for v in value)
        else:
            flat[full_key] = value if value is not None else ""

    return flat


def save_report_csv(filepath: Path, report: dict):
    """
    Flatten a Xero report structure to CSV.

    Xero reports have: Rows -> [{RowType, Title, Cells: [{Value}]}]
    Sections contain nested Rows.
    """
    rows_out: list[list[str]] = []

    # Extract header row
    report_rows = report.get("Rows", [])
    for row in report_rows:
        row_type = row.get("RowType", "")

        if row_type == "Header":
            cells = row.get("Cells", [])
            header = [cell.get("Value", "") for cell in cells]
            rows_out.append(header)

        elif row_type == "Section":
            title = row.get("Title", "")
            section_rows = row.get("Rows", [])
            for section_row in section_rows:
                cells = section_row.get("Cells", [])
                values = [cell.get("Value", "") for cell in cells]
                if title and values:
                    # Prepend section title context if the first cell is empty
                    if not values[0]:
                        values[0] = title
                rows_out.append(values)
            # Add section summary row if present
            if title and not section_rows:
                rows_out.append([title])

        elif row_type == "Row":
            cells = row.get("Cells", [])
            values = [cell.get("Value", "") for cell in cells]
            rows_out.append(values)

        elif row_type == "SummaryRow":
            cells = row.get("Cells", [])
            values = [cell.get("Value", "") for cell in cells]
            rows_out.append(values)

    if not rows_out:
        return

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows_out)

    logger.info("  Saved report to %s", filepath)
