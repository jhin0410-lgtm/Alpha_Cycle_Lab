"""Safe read-only evidence reader for OpenDART original disclosure documents."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from html.parser import HTMLParser
from pathlib import PurePosixPath
from xml.etree import ElementTree

from alpha_cycle.providers.opendart import OpenDartReadOnlyClient, _node_text

MAX_DOCUMENT_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_DOCUMENT_MEMBER_COUNT = 128
MAX_DOCUMENT_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_DOCUMENT_TEXT_CHARS = 1_000_000
_TEXT_SUFFIXES = frozenset({".xml", ".html", ".htm", ".xhtml", ".txt"})
_DECLARED_ENCODING = re.compile(
    rb"encoding\s*=\s*['\"]\s*([A-Za-z0-9._-]+)\s*['\"]",
    re.IGNORECASE,
)
_ALLOWED_ENCODINGS = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "euc-kr": "euc-kr",
    "euckr": "euc-kr",
    "ks_c_5601-1987": "cp949",
    "ks_c_5601": "cp949",
    "cp949": "cp949",
}


@dataclass(frozen=True)
class DisclosureDocumentMemberEvidence:
    name: str
    sha256: str
    compressed_bytes: int
    uncompressed_bytes: int
    encoding: str
    text_chars: int


@dataclass(frozen=True)
class DisclosureDocumentEvidence:
    rcept_no: str
    retrieved_at: datetime
    archive_sha256: str
    archive_bytes: int
    member_count: int
    text_member_count: int
    uncompressed_bytes: int
    text_sha256: str
    text_chars: int
    text_truncated: bool
    text: str
    members: tuple[DisclosureDocumentMemberEvidence, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["retrieved_at"] = self.retrieved_at.isoformat()
        payload["members"] = [asdict(member) for member in self.members]
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class DisclosureDocumentArchive:
    """Parsed document evidence plus the exact official ZIP bytes that produced it."""

    evidence: DisclosureDocumentEvidence
    archive_bytes: bytes

    def __post_init__(self) -> None:
        if hashlib.sha256(self.archive_bytes).hexdigest() != self.evidence.archive_sha256:
            raise ValueError("OpenDART archived bytes do not reproduce archive_sha256")
        if len(self.archive_bytes) != self.evidence.archive_bytes:
            raise ValueError("OpenDART archived bytes do not reproduce archive byte count")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)

    def value(self) -> str:
        return "\n".join(self.parts)


def _validate_receipt_no(value: object) -> str:
    text = str(value).strip()
    if len(text) != 14 or not text.isdigit():
        raise ValueError("OpenDART receipt number must be 14 digits")
    return text


def _safe_member_name(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"OpenDART document archive has unsafe member path: {value!r}")
    return path.as_posix()


def _decode_text(body: bytes) -> tuple[str, str]:
    candidates: list[str] = []
    declared = _DECLARED_ENCODING.search(body[:512])
    if declared is not None:
        raw = declared.group(1).decode("ascii", errors="ignore").casefold()
        mapped = _ALLOWED_ENCODINGS.get(raw)
        if mapped is not None:
            candidates.append(mapped)
    candidates.extend(("utf-8-sig", "utf-8", "cp949", "euc-kr"))
    for encoding in dict.fromkeys(candidates):
        try:
            return body.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("OpenDART document text member uses an unsupported encoding")


def _plain_text(value: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
    except Exception as exc:  # HTMLParser can surface malformed entity edge cases.
        raise ValueError("OpenDART document markup could not be parsed") from exc
    text = parser.value()
    if text:
        return text
    return "\n".join(line.strip() for line in value.splitlines() if line.strip())


def _provider_error(body: bytes) -> ValueError:
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        return ValueError("OpenDART /api/document.xml returned a non-ZIP response")
    status = _node_text(root, "status")
    message = _node_text(root, "message") or "request failed"
    return ValueError(
        "OpenDART /api/document.xml failed: "
        f"status={status or 'unknown'} message={message}"
    )


def _parse_document_archive(
    body: bytes,
    *,
    receipt: str,
    retrieved_at: datetime,
) -> DisclosureDocumentEvidence:
    if len(body) > MAX_DOCUMENT_ARCHIVE_BYTES:
        raise ValueError("OpenDART document archive exceeds the compressed-size limit")
    try:
        archive = zipfile.ZipFile(io.BytesIO(body))
    except zipfile.BadZipFile as exc:
        raise _provider_error(body) from exc

    warnings: list[str] = []
    member_evidence: list[DisclosureDocumentMemberEvidence] = []
    text_parts: list[str] = []
    total_uncompressed = 0
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if not infos:
            raise ValueError("OpenDART document archive contains no files")
        if len(infos) > MAX_DOCUMENT_MEMBER_COUNT:
            raise ValueError("OpenDART document archive contains too many members")
        for info in infos:
            safe_name = _safe_member_name(info.filename)
            if info.flag_bits & 0x1:
                raise ValueError("OpenDART document archive contains an encrypted member")
            if info.file_size < 0 or info.compress_size < 0:
                raise ValueError("OpenDART document archive has invalid member sizes")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_DOCUMENT_UNCOMPRESSED_BYTES:
                raise ValueError("OpenDART document archive exceeds the uncompressed-size limit")
            if PurePosixPath(safe_name).suffix.casefold() not in _TEXT_SUFFIXES:
                warnings.append(f"non_text_member_skipped:{safe_name}")
                continue
            raw = archive.read(info)
            if len(raw) != info.file_size:
                raise ValueError("OpenDART document member size changed while reading")
            decoded, encoding = _decode_text(raw)
            text = _plain_text(decoded)
            if not text:
                warnings.append(f"empty_text_member:{safe_name}")
                continue
            member_evidence.append(
                DisclosureDocumentMemberEvidence(
                    name=safe_name,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    compressed_bytes=info.compress_size,
                    uncompressed_bytes=info.file_size,
                    encoding=encoding,
                    text_chars=len(text),
                )
            )
            text_parts.append(text)

    if not member_evidence:
        raise ValueError("OpenDART document archive contains no readable text members")
    combined = "\n\n".join(text_parts)
    truncated = len(combined) > MAX_DOCUMENT_TEXT_CHARS
    if truncated:
        combined = combined[:MAX_DOCUMENT_TEXT_CHARS]
        warnings.append("document_text_truncated")
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise ValueError("OpenDART client clock must be timezone-aware")
    return DisclosureDocumentEvidence(
        rcept_no=receipt,
        retrieved_at=retrieved_at,
        archive_sha256=hashlib.sha256(body).hexdigest(),
        archive_bytes=len(body),
        member_count=len(infos),
        text_member_count=len(member_evidence),
        uncompressed_bytes=total_uncompressed,
        text_sha256=hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        text_chars=len(combined),
        text_truncated=truncated,
        text=combined,
        members=tuple(member_evidence),
        warnings=tuple(dict.fromkeys(warnings)),
    )


class OpenDartDisclosureDocumentClient:
    """Download and normalize immutable OpenDART original-document evidence."""

    def __init__(self, client: OpenDartReadOnlyClient) -> None:
        self.client = client

    def _download(self, receipt: str) -> bytes:
        response = self.client._get(  # noqa: SLF001 - provider extension shares boundary.
            self.client._url(  # noqa: SLF001
                "/api/document.xml",
                {"rcept_no": receipt},
            )
        )
        if response.status != 200:
            raise ValueError(f"OpenDART HTTP {response.status}: endpoint=/api/document.xml")
        return response.body

    def document_with_archive(self, rcept_no: object) -> DisclosureDocumentArchive:
        """Fetch once and retain the exact official ZIP bytes with parsed evidence."""

        receipt = _validate_receipt_no(rcept_no)
        body = self._download(receipt)
        evidence = _parse_document_archive(
            body,
            receipt=receipt,
            retrieved_at=self.client.now(),
        )
        return DisclosureDocumentArchive(evidence=evidence, archive_bytes=body)

    def document(self, rcept_no: object) -> DisclosureDocumentEvidence:
        """Backward-compatible parsed evidence API."""

        return self.document_with_archive(rcept_no).evidence


__all__ = [
    "DisclosureDocumentArchive",
    "DisclosureDocumentEvidence",
    "DisclosureDocumentMemberEvidence",
    "OpenDartDisclosureDocumentClient",
]