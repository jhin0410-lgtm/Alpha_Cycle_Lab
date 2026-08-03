"""Safe local readiness check for Kiwoom REST credentials and OAuth."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from alpha_cycle.providers.kiwoom_rest import (
    KiwoomRestAuthClient,
    KiwoomRestCredentials,
)

DEFAULT_OUTPUT_PATH = Path(
    "data/private/live-research/kiwoom_rest_readiness.json"
)


@dataclass(frozen=True)
class KiwoomReadinessReport:
    status: str
    mode: str
    credential_source: str | None
    credentials_valid: bool
    authentication_attempted: bool
    authentication_valid: bool
    token_type: str | None
    expires_at: str | None
    account_api_enabled: bool
    order_api_enabled: bool
    failure: str | None


def check_readiness(
    *,
    mock: bool = False,
    offline: bool = False,
) -> KiwoomReadinessReport:
    mode = "mock" if mock else "live"
    try:
        credentials = KiwoomRestCredentials.from_env()
    except (ValueError, OSError) as exc:
        return KiwoomReadinessReport(
            status="failed",
            mode=mode,
            credential_source=None,
            credentials_valid=False,
            authentication_attempted=False,
            authentication_valid=False,
            token_type=None,
            expires_at=None,
            account_api_enabled=False,
            order_api_enabled=False,
            failure=str(exc),
        )

    if offline:
        return KiwoomReadinessReport(
            status="passed",
            mode=mode,
            credential_source=credentials.source,
            credentials_valid=True,
            authentication_attempted=False,
            authentication_valid=False,
            token_type=None,
            expires_at=None,
            account_api_enabled=False,
            order_api_enabled=False,
            failure=None,
        )

    try:
        token = KiwoomRestAuthClient(credentials, mock=mock).authenticate()
    except (ValueError, OSError, TypeError) as exc:
        return KiwoomReadinessReport(
            status="failed",
            mode=mode,
            credential_source=credentials.source,
            credentials_valid=True,
            authentication_attempted=True,
            authentication_valid=False,
            token_type=None,
            expires_at=None,
            account_api_enabled=False,
            order_api_enabled=False,
            failure=str(exc),
        )

    return KiwoomReadinessReport(
        status="passed",
        mode=mode,
        credential_source=credentials.source,
        credentials_valid=True,
        authentication_attempted=True,
        authentication_valid=True,
        token_type=token.token_type,
        expires_at=token.expires_at.isoformat(),
        account_api_enabled=False,
        order_api_enabled=False,
        failure=None,
    )


def _write_report(report: KiwoomReadinessReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="alpha-cycle-kiwoom-ready",
        description="Validate local Kiwoom REST files and optionally request an OAuth token",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="use the official Kiwoom mock REST host",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="validate credential files without a network request",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = check_readiness(mock=args.mock, offline=args.offline)
    _write_report(report, args.output)

    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    elif report.status == "passed":
        print("KIWOOM REST READINESS: PASS")
        print(f"mode: {report.mode}")
        print(f"credential source: {report.credential_source}")
        if report.authentication_attempted:
            print(f"token type: {report.token_type}")
            print(f"expires at: {report.expires_at}")
        else:
            print("authentication: skipped (offline validation)")
        print("account API: disabled")
        print("order API: disabled")
        print(f"readiness artifact: {args.output}")
    else:
        print("KIWOOM REST READINESS: FAIL", file=sys.stderr)
        print(f"- {report.failure}", file=sys.stderr)
        print(f"readiness artifact: {args.output}", file=sys.stderr)
    return 0 if report.status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
