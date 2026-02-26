"""Download file attachments from Xero entities."""

import json
import logging
from pathlib import Path

from xero.endpoints import ATTACHMENT_ENTITIES

logger = logging.getLogger(__name__)


def download_all(client, output_dir: Path) -> dict:
    """
    Download attachments for all supported entity types.

    Reads the already-exported JSON files to find records with attachments,
    then downloads each attachment file.

    Returns a summary dict with total_files and total_bytes.
    """
    attachments_dir = output_dir / "attachments"
    total_files = 0
    total_bytes = 0

    for entity in ATTACHMENT_ENTITIES:
        json_path = output_dir / "json" / f"{entity.name}.json"
        if not json_path.exists():
            continue

        records = json.loads(json_path.read_text())
        if not records:
            continue

        # Only check records that have attachments
        records_with_attachments = [
            r for r in records if r.get("HasAttachments", False)
        ]

        if not records_with_attachments:
            continue

        print(f"  Downloading attachments for {entity.name} "
              f"({len(records_with_attachments)} records with attachments)...")

        for record in records_with_attachments:
            record_id = record.get(entity.id_field, "")
            if not record_id:
                continue

            try:
                att_data = client.get(
                    f"{entity.endpoint}/{record_id}/Attachments"
                )
                attachments = att_data.get("Attachments", [])

                for att in attachments:
                    result = _download_attachment(
                        client, entity, str(record_id), att, attachments_dir
                    )
                    if result:
                        total_files += 1
                        total_bytes += result

            except Exception as e:
                logger.error(
                    "  Failed to get attachments for %s/%s: %s",
                    entity.name, record_id, e,
                )

    return {"total_files": total_files, "total_bytes": total_bytes}


def _download_attachment(client, entity, record_id: str,
                         attachment_info: dict, attachments_dir: Path) -> int:
    """
    Download a single attachment file.

    Returns the file size in bytes, or 0 if skipped.
    """
    filename = attachment_info.get("FileName", "unknown")
    entity_dir = attachments_dir / entity.name / record_id
    entity_dir.mkdir(parents=True, exist_ok=True)

    filepath = entity_dir / filename

    # Skip if already downloaded (idempotent)
    if filepath.exists():
        logger.debug("  Skipping existing: %s", filepath)
        return 0

    try:
        content = client.get_binary(
            f"{entity.endpoint}/{record_id}/Attachments/{filename}"
        )
        filepath.write_bytes(content)
        logger.info("  Downloaded: %s (%d bytes)", filepath, len(content))
        return len(content)

    except Exception as e:
        logger.error("  Failed to download %s: %s", filepath, e)
        return 0
