from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterator

SCHEMA_VERSION = "APEX_COURT_TEMPORAL_AUDIT_V1"
CHUNK_SIZE = 1024 * 1024

COURT_NON_DESTRUCTIVE_INVARIANT = (
    "Every independently acquired court record remains a distinct acquisition object; "
    "no acquisition may be deleted, overwritten, or collapsed because of filename, "
    "visual similarity, extracted text, page count, or apparent equivalence."
)


class TemporalAuditError(RuntimeError):
    """Raised when a temporal comparison cannot preserve evidentiary provenance."""


@dataclass(frozen=True)
class FileFingerprint:
    byte_size: int
    sha256: str
    sha512: str


@dataclass(frozen=True)
class Acquisition:
    acquisition_id: str
    document_id: str
    source: str
    acquired_at: str
    original_path: str
    original_name: str
    fingerprint: FileFingerprint


@dataclass(frozen=True)
class TemporalComparison:
    left_acquisition_id: str
    right_acquisition_id: str
    classification: str
    byte_identical: bool
    sha256_equal: bool
    sha512_equal: bool
    size_equal: bool
    first_difference_offset: int | None
    left_size: int
    right_size: int
    conclusion: str


def _iter_chunks(stream: BinaryIO, chunk_size: int = CHUNK_SIZE) -> Iterator[bytes]:
    while True:
        chunk = stream.read(chunk_size)
        if not chunk:
            return
        yield chunk


def fingerprint_file(path: str | Path) -> FileFingerprint:
    source = Path(path)
    sha256 = hashlib.sha256()
    sha512 = hashlib.sha512()
    size = 0
    with source.open("rb") as stream:
        for chunk in _iter_chunks(stream):
            size += len(chunk)
            sha256.update(chunk)
            sha512.update(chunk)
    return FileFingerprint(byte_size=size, sha256=sha256.hexdigest(), sha512=sha512.hexdigest())


def first_difference_offset(left: str | Path, right: str | Path) -> int | None:
    """Return the first differing byte offset, or None when both byte streams are identical."""
    left_path, right_path = Path(left), Path(right)
    offset = 0
    with left_path.open("rb") as lhs, right_path.open("rb") as rhs:
        while True:
            left_chunk = lhs.read(CHUNK_SIZE)
            right_chunk = rhs.read(CHUNK_SIZE)
            if left_chunk == right_chunk:
                if not left_chunk:
                    return None
                offset += len(left_chunk)
                continue
            limit = min(len(left_chunk), len(right_chunk))
            for index in range(limit):
                if left_chunk[index] != right_chunk[index]:
                    return offset + index
            return offset + limit


def compare_files(
    left_path: str | Path,
    right_path: str | Path,
    *,
    left_acquisition_id: str,
    right_acquisition_id: str,
) -> TemporalComparison:
    left_fp = fingerprint_file(left_path)
    right_fp = fingerprint_file(right_path)
    size_equal = left_fp.byte_size == right_fp.byte_size
    sha256_equal = left_fp.sha256 == right_fp.sha256
    sha512_equal = left_fp.sha512 == right_fp.sha512

    # Cryptographic agreement is checked, but direct byte comparison remains mandatory.
    difference = first_difference_offset(left_path, right_path)
    byte_identical = difference is None

    if byte_identical and not (size_equal and sha256_equal and sha512_equal):
        raise TemporalAuditError(
            "direct byte comparison reported identity while fingerprint fields disagreed"
        )

    if byte_identical:
        classification = "BYTE_IDENTICAL"
        conclusion = (
            "The two acquisition objects contain exactly identical bytes. Their acquisition "
            "events remain distinct provenance records and MUST NOT be collapsed."
        )
    else:
        classification = "BINARY_DIFFERENT_REQUIRES_FORENSIC_DELTA"
        conclusion = (
            "The purported copies are physically different. Preserve both independently and "
            "escalate to PDF/document structural, visual, textual, metadata, signature, "
            "annotation, attachment, and procedural-timeline comparison before disposition."
        )

    return TemporalComparison(
        left_acquisition_id=left_acquisition_id,
        right_acquisition_id=right_acquisition_id,
        classification=classification,
        byte_identical=byte_identical,
        sha256_equal=sha256_equal,
        sha512_equal=sha512_equal,
        size_equal=size_equal,
        first_difference_offset=difference,
        left_size=left_fp.byte_size,
        right_size=right_fp.byte_size,
        conclusion=conclusion,
    )


def build_acquisition(
    path: str | Path,
    *,
    acquisition_id: str,
    document_id: str,
    source: str,
    acquired_at: str,
) -> Acquisition:
    source_path = Path(path)
    return Acquisition(
        acquisition_id=acquisition_id,
        document_id=document_id,
        source=source,
        acquired_at=acquired_at,
        original_path=str(source_path),
        original_name=source_path.name,
        fingerprint=fingerprint_file(source_path),
    )


def audit_pair(
    left_path: str | Path,
    right_path: str | Path,
    *,
    document_id: str,
    left_acquisition_id: str,
    right_acquisition_id: str,
    left_source: str,
    right_source: str,
    left_acquired_at: str,
    right_acquired_at: str,
) -> dict[str, object]:
    left = build_acquisition(
        left_path,
        acquisition_id=left_acquisition_id,
        document_id=document_id,
        source=left_source,
        acquired_at=left_acquired_at,
    )
    right = build_acquisition(
        right_path,
        acquisition_id=right_acquisition_id,
        document_id=document_id,
        source=right_source,
        acquired_at=right_acquired_at,
    )
    comparison = compare_files(
        left_path,
        right_path,
        left_acquisition_id=left_acquisition_id,
        right_acquisition_id=right_acquisition_id,
    )
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "court_record_preservation_invariant": COURT_NON_DESTRUCTIVE_INVARIANT,
        "acquisitions": [asdict(left), asdict(right)],
        "comparison": asdict(comparison),
        "destructive_deduplication_allowed": False,
        "next_action": (
            "PRESERVE_ACQUISITION_PROVENANCE"
            if comparison.byte_identical
            else "RUN_FULL_FORENSIC_DOCUMENT_DELTA"
        ),
    }


def _write_json(payload: dict[str, object], output: str | Path | None) -> None:
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if output is None:
        print(encoded, end="")
        return
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    temp.write_text(encoded, encoding="utf-8")
    os.replace(temp, target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare independently acquired court-record copies without destructive deduplication."
        )
    )
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--left-acquisition-id", required=True)
    parser.add_argument("--right-acquisition-id", required=True)
    parser.add_argument("--left-source", required=True)
    parser.add_argument("--right-source", required=True)
    parser.add_argument("--left-acquired-at", required=True)
    parser.add_argument("--right-acquired-at", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    payload = audit_pair(
        args.left,
        args.right,
        document_id=args.document_id,
        left_acquisition_id=args.left_acquisition_id,
        right_acquisition_id=args.right_acquisition_id,
        left_source=args.left_source,
        right_source=args.right_source,
        left_acquired_at=args.left_acquired_at,
        right_acquired_at=args.right_acquired_at,
    )
    _write_json(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
