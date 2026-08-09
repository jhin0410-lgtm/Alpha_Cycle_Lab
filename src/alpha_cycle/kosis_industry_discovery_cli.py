"""Discover and pin the official KOSIS mining/manufacturing industry table identity."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from alpha_cycle.providers.kosis import (
    DEFAULT_INDUSTRY_SEARCH,
    DEFAULT_KOSIS_ORG_ID,
    KosisReadOnlyClient,
    KosisTableCandidate,
)

DEFAULT_OUTPUT_ROOT = Path("data/private/live-research/kosis-industry-discovery")
LATEST_POINTER_NAME = "latest_kosis_industry_discovery.json"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)


def _candidate_dict(candidate: KosisTableCandidate) -> dict[str, str]:
    return cast(dict[str, str], asdict(candidate))


def discover(
    *,
    client: KosisReadOnlyClient,
    search_name: str,
    org_id: str,
    output_root: Path,
    now: datetime,
) -> dict[str, object]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("KOSIS discovery clock must be timezone-aware")
    candidates, raw_search = client.search_tables(search_name, org_id=org_id)
    exact = tuple(candidate for candidate in candidates if candidate.table_name == search_name)

    selected: KosisTableCandidate | None = exact[0] if len(exact) == 1 else None
    raw_meta: object | None = None
    metadata_title_verified = False
    if selected is not None:
        metadata_title, raw_meta = client.table_title(selected.org_id, selected.table_id)
        metadata_title_verified = metadata_title == selected.table_name

    if len(exact) == 0:
        status = "no_exact_table_match"
    elif len(exact) > 1:
        status = "ambiguous_exact_table_match"
    elif not metadata_title_verified:
        status = "table_metadata_mismatch"
    else:
        status = "table_identity_verified"

    captured_at = now.astimezone(UTC)
    normalized_candidates = [_candidate_dict(candidate) for candidate in candidates]
    selected_payload = _candidate_dict(selected) if selected is not None else None
    identity_material = {
        "schema_version": 1,
        "source": "kosis_openapi",
        "source_scope": "mining_manufacturing_industry_table_discovery",
        "captured_at": captured_at.isoformat(),
        "search_name": search_name,
        "org_id": org_id,
        "status": status,
        "exact_match_count": len(exact),
        "selected_table": selected_payload,
        "metadata_title_verified": metadata_title_verified,
        "candidate_count": len(candidates),
        "raw_search_sha256": hashlib.sha256(_canonical_bytes(raw_search)).hexdigest(),
        "raw_table_meta_sha256": (
            hashlib.sha256(_canonical_bytes(raw_meta)).hexdigest()
            if raw_meta is not None
            else None
        ),
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    artifact_id = hashlib.sha256(_canonical_bytes(identity_material)).hexdigest()
    directory = output_root / (
        captured_at.strftime("%Y%m%dT%H%M%S%fZ") + f"__{artifact_id[:12]}"
    )
    directory.mkdir(parents=True, exist_ok=False)

    _write_json(directory / "raw_search.json", raw_search)
    if raw_meta is not None:
        _write_json(directory / "raw_table_meta.json", raw_meta)
    _write_json(directory / "candidates.json", normalized_candidates)
    manifest = {**identity_material, "artifact_id": artifact_id}
    _write_json(directory / "manifest.json", manifest)

    pointer = {
        "artifact_id": artifact_id,
        "artifact_directory": str(directory.resolve()),
        "manifest_path": str((directory / "manifest.json").resolve()),
        "status": status,
        "selected_table_id": selected.table_id if selected is not None else None,
        "selected_org_id": selected.org_id if selected is not None else None,
        "industry_cycle_certified": False,
        "decision_score_enabled": False,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    _write_json(output_root / LATEST_POINTER_NAME, pointer)
    return pointer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kosis-discovery",
        description=(
            "Discover the official KOSIS mining/manufacturing product table without "
            "enabling industry-cycle scoring"
        ),
    )
    parser.add_argument("--search-name", default=DEFAULT_INDUSTRY_SEARCH)
    parser.add_argument("--org-id", default=DEFAULT_KOSIS_ORG_ID)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-retries", type=int, default=3)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.timeout_seconds <= 0:
            raise ValueError("--timeout-seconds must be positive")
        if args.max_retries < 0:
            raise ValueError("--max-retries cannot be negative")
        search_name = str(args.search_name).strip()
        org_id = str(args.org_id).strip()
        if not search_name or not org_id:
            raise ValueError("--search-name and --org-id cannot be blank")
        client = KosisReadOnlyClient.from_env()
        client.timeout_seconds = args.timeout_seconds
        client.max_retries = args.max_retries
        pointer = discover(
            client=client,
            search_name=search_name,
            org_id=org_id,
            output_root=args.output,
            now=datetime.now(UTC),
        )
        print(json.dumps(pointer, ensure_ascii=False, sort_keys=True))
        return 0 if pointer["status"] == "table_identity_verified" else 3
    except (ValueError, OSError, TypeError) as exc:
        error_payload = json.dumps(
            {"status": "failed", "error": str(exc)},
            ensure_ascii=False,
        )
        print(error_payload, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
