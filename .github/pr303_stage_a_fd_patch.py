from pathlib import Path

path = Path("src/alpha_cycle/research_package_assembler_v2_1.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f"expected fragment missing: {old[:120]!r}")
    text = text.replace(old, new, 1)


def replace_function(name: str, replacement: str) -> None:
    global text
    marker = f"def {name}("
    start = text.index(marker)
    next_start = text.find("\ndef ", start + len(marker))
    if next_start < 0:
        raise SystemExit(f"cannot find end of function {name}")
    text = text[:start] + replacement.rstrip() + "\n\n" + text[next_start + 1 :]


replace_once("import os\nimport tempfile\n", "import os\nimport secrets\nimport stat\nimport tempfile\n")

replace_once(
    """class _OwnedOpportunityPublication:\n    root: Path\n    directory: Path\n    directory_created: bool\n    root_created: bool\n    pointer: Path\n    pointer_before: bytes | None\n    pointer_after: bytes\n    pointer_inode: int\n    pointer_mtime_ns: int\n    pointer_size: int\n""",
    """class _OwnedOpportunityPublication:\n    root: Path\n    directory: Path\n    directory_created: bool\n    root_created: bool\n    pointer: Path\n    pointer_before: bytes | None\n    pointer_after: bytes\n    pointer_inode: int\n    pointer_mtime_ns: int\n    pointer_size: int\n    repository_fd: int | None = None\n""",
)
replace_once(
    """class _OwnedFilePublication:\n    path: Path\n    inode: int\n    mtime_ns: int\n    size: int\n    sha256: str\n""",
    """class _OwnedFilePublication:\n    path: Path\n    inode: int\n    mtime_ns: int\n    size: int\n    sha256: str\n    repository_fd: int | None = None\n    file_name: str | None = None\n""",
)

replace_once(
    """            publication = _persist_owned_opportunity_snapshot(\n                candidate,\n                output_root=publication_root.public_root,\n                repository_root=candidate_repository.io_path,\n            )\n""",
    """            publication = _persist_owned_opportunity_snapshot(\n                candidate,\n                output_root=publication_root.public_root,\n                repository_root=candidate_repository.io_path,\n                repository_fd=candidate_repository.fd,\n            )\n""",
)
replace_once(
    """            publication = _persist_owned_opportunity_snapshot(\n                artifacts.opportunity_set,\n                output_root=publication_root.public_root,\n                repository_root=set_repository.io_path,\n            )\n""",
    """            publication = _persist_owned_opportunity_snapshot(\n                artifacts.opportunity_set,\n                output_root=publication_root.public_root,\n                repository_root=set_repository.io_path,\n                repository_fd=set_repository.fd,\n            )\n""",
)
for repository_name, variable in (
    ("research_round_v2_1", "round_repository"),
    ("research_round_run_v2_1", "run_repository"),
    ("research_run_ledger_v2_1", "ledger_repository"),
):
    old = f'''            repository_root={variable}.io_path,\n            snapshot_id='''
    new = f'''            repository_root={variable}.io_path,\n            repository_fd={variable}.fd,\n            snapshot_id='''
    replace_once(old, new)

replace_once(
    """def _persist_owned_opportunity_snapshot(\n    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,\n    *,\n    output_root: Path,\n    repository_root: Path | None = None,\n) -> _OwnedOpportunityPublication:\n""",
    """def _persist_owned_opportunity_snapshot(\n    snapshot: OpportunityCandidateSnapshot | OpportunitySetSnapshot,\n    *,\n    output_root: Path,\n    repository_root: Path | None = None,\n    repository_fd: int | None = None,\n) -> _OwnedOpportunityPublication:\n""",
)

old_pointer_block = '''    pointer = root / f"latest_{object_name}.json"\n    pointer_before = _optional_bytes(pointer)\n    pointer_before_identity = (\n        _capture_file_identity(pointer) if pointer_before is not None else None\n    )\n    pointer_after = json.dumps(\n        {\n            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,\n            "object_type": object_name,\n            "snapshot_id": snapshot.snapshot_id,\n            "snapshot_path": str(public_directory),\n        },\n        ensure_ascii=False,\n        indent=2,\n        sort_keys=True,\n    ).encode("utf-8")\n    pointer_temp = _write_owned_pointer_temp(root, pointer.name, pointer_after)\n    pointer_temp_identity = _capture_file_identity(pointer_temp)\n    pointer_published_by_this_call = False\n    try:\n        if pointer_before is None:\n            try:\n                os.link(pointer_temp, pointer)\n                pointer_published_by_this_call = True\n            except FileExistsError:\n                pointer_published_by_this_call = False\n        elif pointer_before_identity is not None:\n            pointer_published_by_this_call = _replace_pointer_if_version_matches(\n                pointer_temp,\n                pointer,\n                expected_bytes=pointer_before,\n                expected_identity=pointer_before_identity,\n            )\n    finally:\n        pointer_temp.unlink(missing_ok=True)\n'''
new_pointer_block = '''    pointer_name = f"latest_{object_name}.json"\n    pointer = output_root / object_name / pointer_name\n    if repository_fd is not None:\n        before_version = _read_regular_file_at(repository_fd, pointer_name)\n        pointer_before = before_version[0] if before_version is not None else None\n        pointer_before_identity = before_version[1] if before_version is not None else None\n    else:\n        pointer_before = _optional_bytes(pointer)\n        pointer_before_identity = (\n            _capture_file_identity(pointer) if pointer_before is not None else None\n        )\n    pointer_after = json.dumps(\n        {\n            "schema_version": OPPORTUNITY_SET_SCHEMA_VERSION,\n            "object_type": object_name,\n            "snapshot_id": snapshot.snapshot_id,\n            "snapshot_path": str(public_directory),\n        },\n        ensure_ascii=False,\n        indent=2,\n        sort_keys=True,\n    ).encode("utf-8")\n    pointer_published_by_this_call = False\n    if repository_fd is not None:\n        pointer_temp_name, pointer_temp_identity = _write_owned_pointer_temp_at(\n            repository_fd, pointer_name, pointer_after\n        )\n        try:\n            if pointer_before is None:\n                try:\n                    os.link(\n                        pointer_temp_name,\n                        pointer_name,\n                        src_dir_fd=repository_fd,\n                        dst_dir_fd=repository_fd,\n                        follow_symlinks=False,\n                    )\n                    pointer_published_by_this_call = True\n                except FileExistsError:\n                    pointer_published_by_this_call = False\n            elif pointer_before_identity is not None:\n                pointer_published_by_this_call = _replace_pointer_if_version_matches_at(\n                    repository_fd,\n                    pointer_temp_name,\n                    pointer_name,\n                    expected_bytes=pointer_before,\n                    expected_identity=pointer_before_identity,\n                )\n        finally:\n            try:\n                os.unlink(pointer_temp_name, dir_fd=repository_fd)\n            except FileNotFoundError:\n                pass\n    else:\n        pointer_temp = _write_owned_pointer_temp(root, pointer.name, pointer_after)\n        pointer_temp_identity = _capture_file_identity(pointer_temp)\n        try:\n            if pointer_before is None:\n                try:\n                    os.link(pointer_temp, pointer)\n                    pointer_published_by_this_call = True\n                except FileExistsError:\n                    pointer_published_by_this_call = False\n            elif pointer_before_identity is not None:\n                pointer_published_by_this_call = _replace_pointer_if_version_matches(\n                    pointer_temp,\n                    pointer,\n                    expected_bytes=pointer_before,\n                    expected_identity=pointer_before_identity,\n                )\n        finally:\n            pointer_temp.unlink(missing_ok=True)\n'''
replace_once(old_pointer_block, new_pointer_block)
replace_once(
    """        pointer_size=size,\n    )\n\n\ndef _write_directory_relative_file""",
    """        pointer_size=size,\n        repository_fd=repository_fd,\n    )\n\n\ndef _write_directory_relative_file""",
)

helpers = r'''
def _read_regular_file_at(
    directory_fd: int,
    name: str,
) -> tuple[bytes, tuple[int, int, int]] | None:
    if not name or Path(name).name != name:
        raise ValueError("repository-relative file name must be one path component")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except FileNotFoundError:
        return None
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError(f"repository-relative file must be regular: {name}")
        with os.fdopen(fd, "rb") as handle:
            fd = -1
            content = handle.read()
        return content, (opened.st_ino, opened.st_mtime_ns, opened.st_size)
    finally:
        if fd >= 0:
            os.close(fd)


def _write_owned_pointer_temp_at(
    directory_fd: int,
    pointer_name: str,
    content: bytes,
) -> tuple[str, tuple[int, int, int]]:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(64):
        name = f".{pointer_name}.{secrets.token_hex(16)}.owned.tmp"
        try:
            fd = os.open(name, flags, 0o644, dir_fd=directory_fd)
        except FileExistsError:
            continue
        try:
            if os.name != "nt":
                os.fchmod(fd, 0o644)
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                opened = os.fstat(handle.fileno())
            return name, (opened.st_ino, opened.st_mtime_ns, opened.st_size)
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
    raise RuntimeError("could not allocate owned pointer temp file")


def _new_publication_quarantine_at(directory_fd: int, name: str) -> str:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    for _ in range(64):
        quarantine = f".{name}.{secrets.token_hex(16)}.quarantine"
        try:
            fd = os.open(quarantine, flags, 0o600, dir_fd=directory_fd)
        except FileExistsError:
            continue
        os.close(fd)
        return quarantine
    raise RuntimeError("could not allocate publication quarantine")


def _restore_quarantined_file_if_absent_at(
    directory_fd: int,
    quarantine: str,
    destination: str,
) -> bool:
    try:
        os.link(
            quarantine,
            destination,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
            follow_symlinks=False,
        )
        return True
    except FileExistsError:
        return False


def _replace_pointer_if_version_matches_at(
    directory_fd: int,
    replacement: str,
    pointer: str,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, int, int],
) -> bool:
    quarantine = _new_publication_quarantine_at(directory_fd, pointer)
    preserve_quarantine = False
    try:
        try:
            os.replace(
                pointer,
                quarantine,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return False
        observed = _read_regular_file_at(directory_fd, quarantine)
        matches = bool(
            observed is not None
            and observed[1] == expected_identity
            and observed[0] == expected_bytes
        )
        if not matches:
            _restore_quarantined_file_if_absent_at(
                directory_fd, quarantine, pointer
            )
            return False
        try:
            os.link(
                replacement,
                pointer,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except FileExistsError:
            return False
        except BaseException as publication_error:
            try:
                restored = _restore_quarantined_file_if_absent_at(
                    directory_fd, quarantine, pointer
                )
            except BaseException as restore_error:
                preserve_quarantine = (
                    _read_regular_file_at(directory_fd, pointer) is None
                )
                raise publication_error from restore_error
            if not restored and _read_regular_file_at(directory_fd, pointer) is None:
                preserve_quarantine = True
            raise
        return True
    finally:
        if not preserve_quarantine:
            try:
                os.unlink(quarantine, dir_fd=directory_fd)
            except FileNotFoundError:
                pass


def _unlink_pointer_if_version_matches_at(
    directory_fd: int,
    pointer: str,
    *,
    expected_bytes: bytes,
    expected_identity: tuple[int, int, int],
) -> bool:
    quarantine = _new_publication_quarantine_at(directory_fd, pointer)
    try:
        try:
            os.replace(
                pointer,
                quarantine,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        except FileNotFoundError:
            return False
        observed = _read_regular_file_at(directory_fd, quarantine)
        matches = bool(
            observed is not None
            and observed[1] == expected_identity
            and observed[0] == expected_bytes
        )
        if not matches:
            _restore_quarantined_file_if_absent_at(
                directory_fd, quarantine, pointer
            )
            return False
        return True
    finally:
        try:
            os.unlink(quarantine, dir_fd=directory_fd)
        except FileNotFoundError:
            pass


def _unlink_owned_file_at(
    publication: _OwnedFilePublication,
) -> bool:
    if publication.repository_fd is None or publication.file_name is None:
        return False
    quarantine = _new_publication_quarantine_at(
        publication.repository_fd, publication.file_name
    )
    try:
        try:
            os.replace(
                publication.file_name,
                quarantine,
                src_dir_fd=publication.repository_fd,
                dst_dir_fd=publication.repository_fd,
            )
        except FileNotFoundError:
            return False
        observed = _read_regular_file_at(publication.repository_fd, quarantine)
        if observed is None:
            return False
        content, identity = observed
        matches = bool(
            identity
            == (publication.inode, publication.mtime_ns, publication.size)
            and hashlib.sha256(content).hexdigest() == publication.sha256
        )
        if not matches:
            _restore_quarantined_file_if_absent_at(
                publication.repository_fd,
                quarantine,
                publication.file_name,
            )
            return False
        return True
    finally:
        try:
            os.unlink(quarantine, dir_fd=publication.repository_fd)
        except FileNotFoundError:
            pass
'''
marker = "def _write_directory_relative_file("
insert_at = text.index(marker)
text = text[:insert_at] + helpers + "\n\n" + text[insert_at:]

replace_function(
    "_pointer_version_is_current",
    r'''def _pointer_version_is_current(publication: _OwnedOpportunityPublication) -> bool:
    if publication.pointer_inode < 0:
        return False
    if publication.repository_fd is not None:
        try:
            observed = _read_regular_file_at(
                publication.repository_fd, publication.pointer.name
            )
            return bool(
                observed is not None
                and observed[1]
                == (
                    publication.pointer_inode,
                    publication.pointer_mtime_ns,
                    publication.pointer_size,
                )
                and observed[0] == publication.pointer_after
            )
        except OSError:
            return False
    if not publication.pointer.exists() or publication.pointer.is_symlink():
        return False
    try:
        stat_result = publication.pointer.stat()
        return bool(
            stat_result.st_ino == publication.pointer_inode
            and stat_result.st_mtime_ns == publication.pointer_mtime_ns
            and stat_result.st_size == publication.pointer_size
            and publication.pointer.read_bytes() == publication.pointer_after
        )
    except OSError:
        return False''',
)

replace_function(
    "_rollback_owned_opportunity_publication",
    r'''def _rollback_owned_opportunity_publication(
    publication: _OwnedOpportunityPublication,
    cleanup_errors: list[BaseException],
) -> None:
    expected_identity = (
        publication.pointer_inode,
        publication.pointer_mtime_ns,
        publication.pointer_size,
    )
    if publication.pointer_inode < 0:
        return
    if publication.repository_fd is not None:
        try:
            if publication.pointer_before is not None:
                previous_temp, _ = _write_owned_pointer_temp_at(
                    publication.repository_fd,
                    publication.pointer.name,
                    publication.pointer_before,
                )
                try:
                    _replace_pointer_if_version_matches_at(
                        publication.repository_fd,
                        previous_temp,
                        publication.pointer.name,
                        expected_bytes=publication.pointer_after,
                        expected_identity=expected_identity,
                    )
                finally:
                    try:
                        os.unlink(previous_temp, dir_fd=publication.repository_fd)
                    except FileNotFoundError:
                        pass
            else:
                _unlink_pointer_if_version_matches_at(
                    publication.repository_fd,
                    publication.pointer.name,
                    expected_bytes=publication.pointer_after,
                    expected_identity=expected_identity,
                )
        except BaseException as exc:
            cleanup_errors.append(exc)
        return
    if publication.pointer_before is not None:
        previous_temp = _write_owned_pointer_temp(
            publication.root,
            publication.pointer.name,
            publication.pointer_before,
        )
        try:
            _replace_pointer_if_version_matches(
                previous_temp,
                publication.pointer,
                expected_bytes=publication.pointer_after,
                expected_identity=expected_identity,
            )
        except BaseException as exc:
            cleanup_errors.append(exc)
        finally:
            previous_temp.unlink(missing_ok=True)
        return
    try:
        _unlink_pointer_if_version_matches(
            publication.pointer,
            expected_bytes=publication.pointer_after,
            expected_identity=expected_identity,
        )
    except BaseException as exc:
        cleanup_errors.append(exc)
    # Immutable content-addressed opportunity directories are intentionally preserved.''',
)

replace_function(
    "_persist_owned_content_addressed_json",
    r'''def _persist_owned_content_addressed_json(
    *,
    root: Path,
    repository_name: str,
    snapshot_id: str,
    payload_without_id: dict[str, object],
    repository_root: Path | None = None,
    repository_fd: int | None = None,
) -> tuple[Path, _OwnedFilePublication]:
    public_repository = root / repository_name
    repository = repository_root if repository_root is not None else public_repository
    if repository_root is None:
        repository.mkdir(parents=True, exist_ok=True)
    file_name = f"{snapshot_id}.json"
    public_path = public_repository / file_name
    io_path = repository / file_name
    payload = dict(payload_without_id)
    payload["snapshot_id"] = snapshot_id
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = -1
    owned_fd = -1
    created_inode: int | None = None
    publication: _OwnedFilePublication | None = None
    try:
        if repository_fd is not None:
            fd = os.open(file_name, flags, 0o644, dir_fd=repository_fd)
        else:
            fd = os.open(io_path, flags, 0o644)
        created = os.fstat(fd)
        created_inode = created.st_ino
        owned_fd = os.dup(fd)
        with os.fdopen(fd, "wb") as handle:
            fd = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
            completed = os.fstat(handle.fileno())
        publication = _OwnedFilePublication(
            path=public_path,
            inode=completed.st_ino,
            mtime_ns=completed.st_mtime_ns,
            size=completed.st_size,
            sha256=hashlib.sha256(encoded).hexdigest(),
            repository_fd=repository_fd,
            file_name=file_name if repository_fd is not None else None,
        )
        if not _owned_file_is_current(publication):
            raise RuntimeError(f"publication path changed during creation: {public_path}")
        return public_path, publication
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            if publication is not None:
                _unlink_owned_file_if_current(publication)
            elif repository_fd is None and created_inode is not None:
                _unlink_file_if_inode_matches(io_path, created_inode)
        except BaseException:
            pass
        raise
    finally:
        if owned_fd >= 0:
            os.close(owned_fd)''',
)

replace_function(
    "_owned_file_is_current",
    r'''def _owned_file_is_current(publication: _OwnedFilePublication) -> bool:
    if publication.repository_fd is not None and publication.file_name is not None:
        try:
            observed = _read_regular_file_at(
                publication.repository_fd, publication.file_name
            )
            if observed is None:
                return False
            content, identity = observed
            return bool(
                identity == (publication.inode, publication.mtime_ns, publication.size)
                and hashlib.sha256(content).hexdigest() == publication.sha256
            )
        except OSError:
            return False
    path = publication.path
    if path.is_symlink() or not path.is_file():
        return False
    try:
        inode, mtime_ns, size = _capture_file_identity(path)
        if (
            inode != publication.inode
            or mtime_ns != publication.mtime_ns
            or size != publication.size
        ):
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == publication.sha256
    except OSError:
        return False''',
)

replace_function(
    "_unlink_owned_file_if_current",
    r'''def _unlink_owned_file_if_current(publication: _OwnedFilePublication) -> bool:
    """Remove only the exact owned inode/version after atomically claiming its name."""
    if publication.repository_fd is not None and publication.file_name is not None:
        return _unlink_owned_file_at(publication)
    path = publication.path
    if path.is_symlink() or not path.exists():
        return False
    quarantine = _new_publication_quarantine(path)
    try:
        try:
            os.replace(path, quarantine)
        except FileNotFoundError:
            return False
        if quarantine.is_symlink() or not quarantine.is_file():
            return False
        try:
            inode, mtime_ns, size = _capture_file_identity(quarantine)
            digest = hashlib.sha256(quarantine.read_bytes()).hexdigest()
        except OSError:
            _restore_quarantined_file_if_absent(quarantine, path)
            return False
        matches = bool(
            inode == publication.inode
            and mtime_ns == publication.mtime_ns
            and size == publication.size
            and digest == publication.sha256
        )
        if not matches:
            _restore_quarantined_file_if_absent(quarantine, path)
            return False
        return True
    finally:
        quarantine.unlink(missing_ok=True)''',
)

replace_function(
    "_record_package_blockers",
    r'''def _record_package_blockers(
    *,
    request: AnalysisRequestSnapshot,
    run_id: str,
    processed_at: datetime,
    preflight_selected_at: datetime,
    blockers: tuple[ResearchRoundBlocker, ...],
    ledger: ResearchRunLedgerSnapshot,
    root: Path,
) -> tuple[ResearchRunLedgerSnapshot, Path | None, Path | None, bool]:
    prior = _matching_package_blocked_run(ledger, request.snapshot_id, blockers)
    latest_request_run = _latest_request_run(ledger, request.snapshot_id)
    if (
        prior is not None
        and latest_request_run == prior
        and prior.completed_at >= preflight_selected_at
    ):
        return ledger, None, None, False
    run = build_pre_orchestration_blocked_run(
        request,
        run_id=run_id,
        started_at=processed_at,
        completed_at=processed_at,
        blockers=blockers,
        flags=("typed_research_package_assembler_blocked",),
    )
    next_ledger = build_research_run_ledger(
        ledger.requests,
        (*ledger.runs, run),
        built_at=processed_at,
    )
    _require_safe_run_ledger_publication(root, run=run, ledger=next_ledger)
    publication_root = _open_pinned_publication_root(root)
    owned_run: _OwnedFilePublication | None = None
    owned_ledger: _OwnedFilePublication | None = None
    try:
        run_repository = _pin_publication_repository(
            publication_root, "research_round_run_v2_1"
        )
        ledger_repository = _pin_publication_repository(
            publication_root, "research_run_ledger_v2_1"
        )
        if not _publication_namespace_is_current(publication_root):
            raise RuntimeError("blocked-run publication namespace changed before creation")
        run_path, owned_run = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_round_run_v2_1",
            repository_root=run_repository.io_path,
            repository_fd=run_repository.fd,
            snapshot_id=run.snapshot_id,
            payload_without_id=run.payload_without_id(),
        )
        ledger_path, owned_ledger = _persist_owned_content_addressed_json(
            root=publication_root.public_root,
            repository_name="research_run_ledger_v2_1",
            repository_root=ledger_repository.io_path,
            repository_fd=ledger_repository.fd,
            snapshot_id=next_ledger.snapshot_id,
            payload_without_id=next_ledger.payload_without_id(),
        )
        if not _publication_namespace_is_current(publication_root):
            raise RuntimeError("blocked-run publication namespace changed before commit")
        return next_ledger, run_path, ledger_path, True
    except BaseException:
        for publication in (owned_ledger, owned_run):
            if publication is not None:
                try:
                    _unlink_owned_file_if_current(publication)
                except BaseException:
                    pass
        raise
    finally:
        _close_pinned_publication_root(publication_root)''',
)

# The generated publication spine passes the pinned descriptor explicitly.
for variable in ("round_repository", "run_repository", "ledger_repository"):
    needle = f"repository_root={variable}.io_path,\n            repository_fd={variable}.fd,"
    if needle not in text:
        raise SystemExit(f"missing descriptor-relative publication call for {variable}")

path.write_text(text, encoding="utf-8")

test_path = Path("tests/unit/test_research_package_final_review_round3_v2_1.py")
test_text = test_path.read_text(encoding="utf-8")
test_text = test_text.replace(
    "repository_root=repository.io_path,\n            snapshot_id=",
    "repository_root=repository.io_path,\n            repository_fd=repository.fd,\n            snapshot_id=",
    1,
)
test_text = test_text.replace(
    "repository_root=repository.io_path,\n        )\n        assert list(outside.iterdir()) == []",
    "repository_root=repository.io_path,\n            repository_fd=repository.fd,\n        )\n        assert list(outside.iterdir()) == []",
    1,
)
test_path.write_text(test_text, encoding="utf-8")
