#!/usr/bin/env python3
"""Xero Business Account Backup Tool.

Backs up all data from a Xero organisation before account closure.
Exports entities as JSON + CSV, downloads reports and file attachments.

Usage:
    python backup.py
    python backup.py --skip-attachments --skip-reports
    python backup.py --entities invoices,contacts
    python backup.py --output-dir ./my-backups --verbose
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from xero import attachments, auth, reports
from xero.api import RateLimiter, XeroClient
from xero.endpoints import ENTITY_REGISTRY
from xero.exporters import save_csv, save_json

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Back up a Xero business account to JSON, CSV, and attachment files.",
    )
    parser.add_argument(
        "--output-dir",
        default="./backups",
        help="Base directory for backups (default: ./backups)",
    )
    parser.add_argument(
        "--skip-attachments",
        action="store_true",
        help="Skip downloading file attachments",
    )
    parser.add_argument(
        "--skip-reports",
        action="store_true",
        help="Skip fetching financial reports",
    )
    parser.add_argument(
        "--entities",
        help="Comma-separated list of entity names to back up (e.g., invoices,contacts)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def setup_logging(verbose: bool, log_file: Path | None = None):
    level = logging.DEBUG if verbose else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )


def create_output_dir(base_dir: str) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    output_dir = Path(base_dir) / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def main():
    args = parse_args()
    load_dotenv()

    # Create output directory early so we can set up log file
    output_dir = create_output_dir(args.output_dir)
    setup_logging(args.verbose, log_file=output_dir / "backup.log")

    print(f"\n{'=' * 60}")
    print("  Xero Business Account Backup")
    print(f"{'=' * 60}")
    print(f"  Output: {output_dir}\n")

    # Authenticate
    print("[1/4] Authenticating with Xero...")
    session, tokens = auth.get_authenticated_session()
    tenant_id = auth.get_tenant_id(session)
    print(f"  Connected to tenant: {tenant_id}\n")

    # Set up API client
    rate_limiter = RateLimiter()
    client = XeroClient(session, tenant_id, rate_limiter, tokens)

    # Determine which entities to back up
    entity_filter = None
    if args.entities:
        entity_filter = set(args.entities.split(","))

    entities_to_backup = [
        e for e in ENTITY_REGISTRY
        if entity_filter is None or e.name in entity_filter
    ]

    start_time = time.time()
    entity_results = {}
    errors = []

    # Back up entities
    print(f"[2/4] Backing up {len(entities_to_backup)} entity types...")
    for i, entity in enumerate(entities_to_backup, 1):
        label = f"  [{i}/{len(entities_to_backup)}] {entity.name}"
        print(f"{label}...", end=" ", flush=True)

        try:
            records = client.fetch_all_pages(
                entity.endpoint, entity.response_key, entity.paginated
            )
            save_json(output_dir, entity.name, records)
            save_csv(output_dir, entity.name, records)
            entity_results[entity.name] = {"count": len(records), "status": "success"}
            print(f"{len(records)} records")
        except Exception as e:
            logger.error("FAILED to backup %s: %s", entity.name, e)
            entity_results[entity.name] = {"count": 0, "status": "failed", "error": str(e)}
            errors.append({"entity": entity.name, "error": str(e)})
            print(f"FAILED: {e}")

    # Fetch reports
    report_names = []
    if not args.skip_reports:
        print("\n[3/4] Fetching financial reports...")
        try:
            reports.fetch_all_reports(client, output_dir)
            report_names = [r["name"] for r in reports.REPORTS]
        except Exception as e:
            logger.error("Failed to fetch reports: %s", e)
            errors.append({"entity": "reports", "error": str(e)})
            print(f"  FAILED: {e}")
    else:
        print("\n[3/4] Skipping reports (--skip-reports)")

    # Download attachments
    attachment_summary = {"total_files": 0, "total_bytes": 0}
    if not args.skip_attachments:
        print("\n[4/4] Downloading attachments...")
        try:
            attachment_summary = attachments.download_all(client, output_dir)
            print(f"  Downloaded {attachment_summary['total_files']} files "
                  f"({attachment_summary['total_bytes'] / 1024 / 1024:.1f} MB)")
        except Exception as e:
            logger.error("Failed to download attachments: %s", e)
            errors.append({"entity": "attachments", "error": str(e)})
            print(f"  FAILED: {e}")
    else:
        print("\n[4/4] Skipping attachments (--skip-attachments)")

    duration = time.time() - start_time

    # Write backup manifest
    manifest = {
        "timestamp": datetime.now().isoformat(),
        "tenant_id": tenant_id,
        "entities": entity_results,
        "reports": report_names,
        "attachments": attachment_summary,
        "errors": errors,
        "api_calls_used": client.total_api_calls,
        "duration_seconds": round(duration, 1),
    }

    manifest_path = output_dir / "backup_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Print summary
    total_records = sum(r["count"] for r in entity_results.values())
    successful = sum(1 for r in entity_results.values() if r["status"] == "success")
    failed = sum(1 for r in entity_results.values() if r["status"] == "failed")

    print(f"\n{'=' * 60}")
    print("  Backup Complete!")
    print(f"{'=' * 60}")
    print(f"  Entities: {successful} successful, {failed} failed")
    print(f"  Records:  {total_records} total")
    print(f"  Reports:  {len(report_names)}")
    print(f"  Files:    {attachment_summary['total_files']} attachments")
    print(f"  API calls: {client.total_api_calls}")
    print(f"  Duration: {duration:.0f}s")
    print(f"  Output:   {output_dir}")
    print(f"  Manifest: {manifest_path}")

    if errors:
        print(f"\n  Errors ({len(errors)}):")
        for err in errors:
            print(f"    - {err['entity']}: {err['error']}")

    print()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
