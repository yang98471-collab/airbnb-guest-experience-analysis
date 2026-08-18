"""Deterministic partitioning, global budget tracking, and final merging."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import pandas as pd


PARTITION_VERSION = "airbnb_final_50000_five_equal_parts_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    temporary_path.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary_path, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {path}: {error}"
                ) from error
            if not isinstance(record, dict):
                raise ValueError(
                    f"Line {line_number} of {path} is not a JSON object."
                )
            records.append(record)
    return records


def prepare_final_partitions(
    master_df: pd.DataFrame,
    master_input_file: Path,
    parts_dir: Path,
    *,
    total_parts: int,
    rows_per_part: int,
    id_column: str = "id",
) -> dict[str, Any]:
    """Create five immutable equal CSV parts, or validate existing ones."""
    expected_total_rows = total_parts * rows_per_part
    if len(master_df) != expected_total_rows:
        raise ValueError(
            f"Expected {expected_total_rows:,} master rows, "
            f"but found {len(master_df):,}."
        )
    if id_column not in master_df.columns:
        raise ValueError(f"Master input is missing {id_column!r}.")
    if master_df[id_column].isna().any():
        raise ValueError("Master input contains missing comment IDs.")
    if master_df[id_column].astype(str).duplicated().any():
        raise ValueError("Master input contains duplicate comment IDs.")

    expected_source_rows = pd.Series(
        range(1, expected_total_rows + 1),
        dtype="int64",
    )
    if "source_row" not in master_df.columns:
        master_df = master_df.copy()
        master_df["source_row"] = expected_source_rows
    else:
        actual_source_rows = pd.to_numeric(
            master_df["source_row"],
            errors="raise",
        ).astype("int64")
        if not actual_source_rows.reset_index(drop=True).equals(
            expected_source_rows
        ):
            raise ValueError(
                "Master source_row must be the consecutive sequence 1..50,000."
            )
        master_df = master_df.copy()
        master_df["source_row"] = actual_source_rows

    parts_dir.mkdir(parents=True, exist_ok=True)
    part_entries: list[dict[str, Any]] = []

    for part_number in range(1, total_parts + 1):
        start_index = (part_number - 1) * rows_per_part
        end_index = part_number * rows_per_part
        part_df = master_df.iloc[start_index:end_index].copy()
        expected_csv = part_df.to_csv(index=False, lineterminator="\n")
        expected_sha256 = sha256_text(expected_csv)
        part_file = parts_dir / f"reviews_part_{part_number:02d}.csv"

        if part_file.exists():
            existing_csv = part_file.read_text(encoding="utf-8")
            existing_csv = existing_csv.replace("\r\n", "\n").replace(
                "\r", "\n"
            )
            if sha256_text(existing_csv) != expected_sha256:
                raise RuntimeError(
                    f"Existing partition does not match the frozen master input: "
                    f"{part_file}"
                )
        else:
            atomic_write_text(part_file, expected_csv)

        source_row_start = start_index + 1
        source_row_end = end_index
        part_entries.append(
            {
                "part_number": part_number,
                "file": part_file.name,
                "rows": len(part_df),
                "source_row_start": source_row_start,
                "source_row_end": source_row_end,
                "first_comment_id": str(part_df.iloc[0][id_column]),
                "last_comment_id": str(part_df.iloc[-1][id_column]),
                "sha256": expected_sha256,
            }
        )

    manifest = {
        "partition_version": PARTITION_VERSION,
        "master_file": master_input_file.name,
        "master_sha256": sha256_file(master_input_file),
        "total_rows": expected_total_rows,
        "total_parts": total_parts,
        "rows_per_part": rows_per_part,
        "parts": part_entries,
    }
    manifest_file = parts_dir / "partition_manifest.json"
    manifest_text = json.dumps(
        manifest,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    ) + "\n"

    if manifest_file.exists():
        try:
            saved_manifest = json.loads(
                manifest_file.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError as error:
            raise RuntimeError(
                f"Partition manifest is invalid JSON: {manifest_file}"
            ) from error
        if saved_manifest != manifest:
            raise RuntimeError(
                "Existing partition manifest does not match the frozen master input."
            )
    else:
        atomic_write_text(manifest_file, manifest_text)

    return manifest


def load_global_usage(
    output_root: Path,
    *,
    expected_total_parts: int,
) -> tuple[list[dict[str, Any]], float]:
    """Load and validate usage records across every part."""
    part_pattern = re.compile(r"part_(\d{2})$")
    records: list[dict[str, Any]] = []
    seen_keys: set[tuple[int, str]] = set()

    for part_dir in sorted(output_root.glob("part_[0-9][0-9]")):
        match = part_pattern.fullmatch(part_dir.name)
        if match is None:
            continue
        part_number = int(match.group(1))
        if not 1 <= part_number <= expected_total_parts:
            raise RuntimeError(f"Unexpected output part folder: {part_dir}")

        usage_file = part_dir / f"part_{part_number:02d}_usage.jsonl"
        for record in read_jsonl(usage_file):
            record_part_number = record.get("part_number")
            if record_part_number != part_number:
                raise RuntimeError(
                    f"Usage record in {usage_file} has part_number "
                    f"{record_part_number!r}; expected {part_number}."
                )

            batch_id = record.get("batch_id")
            if not isinstance(batch_id, str) or not batch_id:
                raise RuntimeError(
                    f"Usage record in {usage_file} has no valid batch_id."
                )
            key = (part_number, batch_id)
            if key in seen_keys:
                raise RuntimeError(
                    f"Duplicate global usage record for part {part_number}, "
                    f"batch {batch_id}."
                )
            seen_keys.add(key)

            usage = record.get("usage")
            if not isinstance(usage, dict):
                raise RuntimeError(
                    f"Usage record {key} has no valid usage object."
                )
            estimated_cost = usage.get("estimated_cost_usd")
            if (
                not isinstance(estimated_cost, (int, float))
                or isinstance(estimated_cost, bool)
                or estimated_cost < 0
            ):
                raise RuntimeError(
                    f"Usage record {key} has invalid estimated cost."
                )
            records.append(record)

    total_cost = sum(
        float(record["usage"]["estimated_cost_usd"])
        for record in records
    )
    return records, total_cost


def estimate_wave_cost_reserve(
    request_count: int,
    usage_records: list[dict[str, Any]],
    *,
    minimum_per_request_usd: float,
    observed_cost_multiplier: float,
) -> dict[str, float]:
    """Reserve a conservative amount before a wave is submitted."""
    if request_count < 0:
        raise ValueError("request_count cannot be negative.")
    observed_costs = [
        float(record["usage"]["estimated_cost_usd"])
        for record in usage_records
    ]
    observed_high = max(observed_costs, default=0.0)
    reserve_per_request = max(
        minimum_per_request_usd,
        observed_high * observed_cost_multiplier,
    )
    return {
        "observed_high_cost_per_request_usd": observed_high,
        "reserve_per_request_usd": reserve_per_request,
        "wave_reserve_usd": reserve_per_request * request_count,
    }


def _finding_category(aspect_score: int) -> str:
    if aspect_score > 0:
        return "Strength"
    if aspect_score < 0:
        return "Problem"
    return "Neutral"


def merge_final_parts(
    master_df: pd.DataFrame,
    output_root: Path,
    merged_dir: Path,
    *,
    total_parts: int,
    rows_per_part: int,
    comment_model: Any,
    method_version: str,
    max_total_cost_usd: float,
) -> dict[str, Any]:
    """Merge only after every part has passed its independent audit."""
    ready_parts: list[int] = []
    waiting_parts: list[int] = []
    part_audits: dict[int, dict[str, Any]] = {}

    for part_number in range(1, total_parts + 1):
        part_dir = output_root / f"part_{part_number:02d}"
        audit_file = part_dir / f"part_{part_number:02d}_audit.json"
        if not audit_file.exists():
            waiting_parts.append(part_number)
            continue
        try:
            audit = json.loads(audit_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid part audit: {audit_file}") from error
        if audit.get("completion_status") not in {
            "completed",
            "completed_with_audit_warnings",
        }:
            waiting_parts.append(part_number)
            continue
        if audit.get("part_number") != part_number:
            raise RuntimeError(
                f"Part audit number mismatch in {audit_file}."
            )
        if audit.get("expected_comments") != rows_per_part:
            raise RuntimeError(
                f"Part audit row-count mismatch in {audit_file}."
            )
        ready_parts.append(part_number)
        part_audits[part_number] = audit

    usage_records, global_cost = load_global_usage(
        output_root,
        expected_total_parts=total_parts,
    )
    if waiting_parts:
        return {
            "method_version": method_version,
            "completion_status": "waiting_for_parts",
            "is_complete": False,
            "ready_parts": ready_parts,
            "parts_remaining": waiting_parts,
            "global_successful_usage_records": len(usage_records),
            "global_estimated_cost_usd": round(global_cost, 4),
            "max_total_cost_usd": max_total_cost_usd,
        }

    expected_by_id = {
        str(row["id"]): row
        for row in master_df.to_dict("records")
    }
    expected_ids = set(expected_by_id)
    result_by_id: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    unexpected_ids: list[str] = []
    part_assignment_errors: list[dict[str, Any]] = []
    schema_errors: list[dict[str, Any]] = []
    evidence_errors: list[dict[str, Any]] = []
    finding_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []

    for part_number in range(1, total_parts + 1):
        part_dir = output_root / f"part_{part_number:02d}"
        results_file = part_dir / f"part_{part_number:02d}_extractions.jsonl"
        part_results = read_jsonl(results_file)
        if len(part_results) != rows_per_part:
            raise RuntimeError(
                f"Part {part_number} has {len(part_results):,} result lines; "
                f"expected {rows_per_part:,}."
            )

        expected_start = (part_number - 1) * rows_per_part + 1
        expected_end = part_number * rows_per_part
        for record in part_results:
            comment_id = str(record.get("comment_id"))
            if comment_id in result_by_id:
                duplicate_ids.append(comment_id)
                continue
            if comment_id not in expected_ids:
                unexpected_ids.append(comment_id)
                continue

            source_row = int(record.get("source_row", -1))
            if (
                record.get("part_number") != part_number
                or not expected_start <= source_row <= expected_end
                or source_row != int(expected_by_id[comment_id]["source_row"])
            ):
                part_assignment_errors.append(
                    {
                        "comment_id": comment_id,
                        "saved_part_number": record.get("part_number"),
                        "source_row": source_row,
                        "expected_part_number": part_number,
                    }
                )
            result_by_id[comment_id] = record

    missing_ids = sorted(expected_ids - set(result_by_id))
    ordered_results = sorted(
        result_by_id.values(),
        key=lambda record: int(record["source_row"]),
    )

    for record in ordered_results:
        comment_id = str(record["comment_id"])
        try:
            validated = comment_model.model_validate(record.get("extraction"))
        except Exception as error:
            schema_errors.append(
                {"comment_id": comment_id, "error": str(error)}
            )
            continue

        review_rows.append(
            {
                "source_row": record["source_row"],
                "part_number": record["part_number"],
                "listing_id": record["listing_id"],
                "comment_id": comment_id,
                "date": record["date"],
                "year": record["year"],
                "listing_comment_count": record["listing_comment_count"],
                "listing_activity": record["listing_activity"],
                "comments_original": record["comments_original"],
                "comments_clean": record["comments_clean"],
                "finding_count": len(validated.findings),
                "batch_id": record["batch_id"],
                "attempt": record["attempt"],
            }
        )

        for finding_number, finding in enumerate(
            validated.findings,
            start=1,
        ):
            quote_is_exact = finding.evidence_quote in record["comments_clean"]
            if not quote_is_exact:
                evidence_errors.append(
                    {
                        "comment_id": comment_id,
                        "finding_number": finding_number,
                        "evidence_quote": finding.evidence_quote,
                    }
                )
            finding_rows.append(
                {
                    "source_row": record["source_row"],
                    "part_number": record["part_number"],
                    "listing_id": record["listing_id"],
                    "comment_id": comment_id,
                    "date": record["date"],
                    "year": record["year"],
                    "listing_comment_count": record["listing_comment_count"],
                    "listing_activity": record["listing_activity"],
                    "finding_number": finding_number,
                    "aspect": finding.aspect,
                    "object": finding.object,
                    "observation": finding.observation,
                    "aspect_score": finding.aspect_score,
                    "severity_score": finding.severity_score,
                    "evidence_quote": finding.evidence_quote,
                    "evidence_quote_exact": quote_is_exact,
                    "finding_category": _finding_category(
                        finding.aspect_score
                    ),
                    "manual_review": finding.aspect == "Other",
                    "comments_clean": record["comments_clean"],
                }
            )

    budget_exceeded = global_cost > max_total_cost_usd
    coverage_and_schema_complete = (
        len(result_by_id) == len(master_df)
        and not missing_ids
        and not unexpected_ids
        and not duplicate_ids
        and not part_assignment_errors
        and not schema_errors
    )
    part_audit_warnings = any(
        audit["completion_status"] == "completed_with_audit_warnings"
        for audit in part_audits.values()
    )
    if coverage_and_schema_complete and not (
        evidence_errors or part_audit_warnings or budget_exceeded
    ):
        completion_status = "completed"
    elif coverage_and_schema_complete:
        completion_status = "completed_with_audit_warnings"
    else:
        completion_status = "merge_validation_failed"

    audit = {
        "method_version": method_version,
        "completion_status": completion_status,
        "is_complete": completion_status == "completed",
        "coverage_complete": coverage_and_schema_complete,
        "ready_parts": ready_parts,
        "expected_comments": len(master_df),
        "returned_comments": len(result_by_id),
        "missing_comment_count": len(missing_ids),
        "unexpected_comment_count": len(unexpected_ids),
        "duplicate_comment_count": len(duplicate_ids),
        "part_assignment_error_count": len(part_assignment_errors),
        "schema_error_count": len(schema_errors),
        "finding_count": len(finding_rows),
        "evidence_quote_error_count": len(evidence_errors),
        "global_successful_usage_records": len(usage_records),
        "global_estimated_cost_usd": round(global_cost, 4),
        "max_total_cost_usd": max_total_cost_usd,
        "budget_exceeded": budget_exceeded,
        "missing_comment_ids": missing_ids[:100],
        "unexpected_comment_ids": unexpected_ids[:100],
        "duplicate_comment_ids": duplicate_ids[:100],
        "part_assignment_errors": part_assignment_errors[:100],
        "schema_errors": schema_errors[:100],
        "evidence_errors": evidence_errors[:100],
    }

    merged_dir.mkdir(parents=True, exist_ok=True)
    audit_file = merged_dir / "reviews_50000_global_audit.json"
    atomic_write_text(
        audit_file,
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n",
    )

    if coverage_and_schema_complete:
        results_text = "".join(
            json.dumps(record, ensure_ascii=False) + "\n"
            for record in ordered_results
        )
        atomic_write_text(
            merged_dir / "reviews_50000_extractions.jsonl",
            results_text,
        )
        findings_df = pd.DataFrame(finding_rows)
        review_summary_df = pd.DataFrame(review_rows)
        atomic_write_text(
            merged_dir / "reviews_50000_findings.csv",
            findings_df.to_csv(index=False, lineterminator="\n"),
        )
        atomic_write_text(
            merged_dir / "reviews_50000_review_summary.csv",
            review_summary_df.to_csv(index=False, lineterminator="\n"),
        )

    return audit
