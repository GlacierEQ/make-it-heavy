from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from data_lake_temporal_audit import fingerprint_file

SCHEMA_VERSION = "APEX_DATA_LAKE_INVENTORY_V1"
CASE_RE = re.compile(r"(?i)(?<![A-Z0-9])(\dFDV-\d{2}-\d{7})(?![A-Z0-9])")
DKT_RE = re.compile(r"(?i)\b(?:DKT|DOCKET)[\s._-]*(\d{1,4})\b")
BARE_DKT_RE = re.compile(r"^(\d{1,4})(?:\s*\(\d+\))?$", re.IGNORECASE)
DATE_RE = re.compile(r"\b(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)\b")


@dataclass(frozen=True)
class InventoryRecord:
    acquisition_id: str
    content_id: str
    source: str
    source_object_id: str | None
    original_path: str
    original_name: str
    extension: str
    mime_type: str | None
    byte_size: int
    sha256: str
    sha512: str
    discovered_at: str
    source_modified_at: str | None
    case_id: str | None
    docket_number: int | None
    document_family_id: str | None
    proposed_name: str | None
    rename_state: str
    destructive_deduplication_allowed: bool


def _utc_iso_from_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _slug_source(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value.strip()).strip("-").upper()
    return cleaned or "UNKNOWN"


def _stable_acquisition_id(source: str, original_path: str, source_object_id: str | None) -> str:
    locator = source_object_id or original_path
    digest = hashlib.sha256(f"{source}\0{locator}".encode("utf-8", errors="surrogatepass")).hexdigest()[:20]
    return f"ACQ-{_slug_source(source)}-{digest.upper()}"


def identify_case_and_docket(path: str | Path) -> tuple[str | None, int | None]:
    value = str(path)
    case_match = CASE_RE.search(value)
    case_id = case_match.group(1).upper() if case_match else None

    docket_match = DKT_RE.search(value)
    docket_number = int(docket_match.group(1)) if docket_match else None
    if docket_number is None and case_id:
        stem = Path(path).stem.strip()
        bare = BARE_DKT_RE.fullmatch(stem)
        if bare:
            docket_number = int(bare.group(1))
    return case_id, docket_number


def _date_hint(path: str | Path) -> str | None:
    match = DATE_RE.search(str(path))
    if not match:
        return None
    year, month, day = match.groups()
    return f"{year}-{month}-{day}"


def propose_name(path: str | Path, case_id: str | None, docket_number: int | None) -> str | None:
    if not case_id or docket_number is None:
        return None
    source = Path(path)
    date = _date_hint(source)
    parts = [case_id]
    if date:
        parts.append(date)
    parts.append(f"DKT-{docket_number:03d}")
    parts.append(f"SOURCE-{source.stem}")
    suffix = source.suffix.lower()
    return "__".join(parts) + suffix


def inventory_file(
    path: str | Path,
    *,
    source: str,
    source_object_id: str | None = None,
    discovered_at: str | None = None,
) -> InventoryRecord:
    source_path = Path(path)
    stat = source_path.stat()
    fp = fingerprint_file(source_path)
    case_id, docket_number = identify_case_and_docket(source_path)
    family_id = f"{case_id}:DKT-{docket_number}" if case_id and docket_number is not None else None
    content_id = f"SHA256-{fp.sha256.upper()}"
    proposed = propose_name(source_path, case_id, docket_number)
    discovered = discovered_at or datetime.now(timezone.utc).isoformat()
    mime, _ = mimetypes.guess_type(source_path.name)
    is_court = family_id is not None

    return InventoryRecord(
        acquisition_id=_stable_acquisition_id(source, str(source_path), source_object_id),
        content_id=content_id,
        source=source,
        source_object_id=source_object_id,
        original_path=str(source_path),
        original_name=source_path.name,
        extension=source_path.suffix.lower(),
        mime_type=mime,
        byte_size=fp.byte_size,
        sha256=fp.sha256,
        sha512=fp.sha512,
        discovered_at=discovered,
        source_modified_at=_utc_iso_from_timestamp(stat.st_mtime),
        case_id=case_id,
        docket_number=docket_number,
        document_family_id=family_id,
        proposed_name=proposed,
        rename_state="PROPOSED" if proposed and proposed != source_path.name else "UNCHANGED",
        destructive_deduplication_allowed=False if is_court else False,
    )


def scan_root(root: str | Path, *, source: str) -> list[InventoryRecord]:
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    paths = [root_path] if root_path.is_file() else sorted(
        path for path in root_path.rglob("*") if path.is_file() and not path.is_symlink()
    )
    discovered = datetime.now(timezone.utc).isoformat()
    return [inventory_file(path, source=source, discovered_at=discovered) for path in paths]


def build_manifest(records: Iterable[InventoryRecord]) -> dict[str, object]:
    rows = list(records)
    by_content: dict[str, list[str]] = {}
    by_family: dict[str, list[str]] = {}
    rename_proposals: list[dict[str, str]] = []

    for row in rows:
        by_content.setdefault(row.content_id, []).append(row.acquisition_id)
        if row.document_family_id:
            by_family.setdefault(row.document_family_id, []).append(row.acquisition_id)
        if row.rename_state == "PROPOSED" and row.proposed_name:
            rename_proposals.append(
                {
                    "acquisition_id": row.acquisition_id,
                    "from": row.original_name,
                    "to": row.proposed_name,
                    "state": "PROPOSED_NOT_APPLIED",
                }
            )

    exact_content_groups = {
        content_id: ids for content_id, ids in by_content.items() if len(ids) > 1
    }
    temporal_queue = {
        family: ids for family, ids in by_family.items() if len(ids) > 1
    }

    return {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_count": len(rows),
        "total_bytes": sum(row.byte_size for row in rows),
        "acquisitions": [asdict(row) for row in rows],
        "exact_content_groups": exact_content_groups,
        "court_temporal_comparison_queue": temporal_queue,
        "rename_proposals": rename_proposals,
        "mutations_applied": 0,
        "court_deduplication_policy": "NO_DESTRUCTIVE_DEDUPLICATION",
    }


def write_manifest(payload: dict[str, object], output: str | Path) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temp.write_text(encoded, encoding="utf-8")
    os.replace(temp, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inventory and classify data-lake objects without mutating source files."
    )
    parser.add_argument("root")
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    manifest = build_manifest(scan_root(args.root, source=args.source))
    write_manifest(manifest, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
