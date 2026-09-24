import json
import stat
from pathlib import Path

import pytest
from pydantic import BaseModel

from mmwiki_data import storage
from mmwiki_data.storage import (
    ManifestError,
    load_sources,
    load_targets,
    write_json_atomic,
    write_json_batch_atomic,
)


class JsonPayload(BaseModel):
    """批量写入测试的最小 Pydantic 数据。"""

    name: str


def test_load_sources_rejects_duplicate_ids(tmp_path: Path) -> None:
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(
        """schema_version: 1
sources:
  - &source
    id: same
    title: Source
    base_url: https://example.com/
    language: ja
    license: NOASSERTION
    usage: cross-check-only
    attribution: Example
  - <<: *source
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="duplicate source id"):
        load_sources(manifest)


def test_load_targets_rejects_unknown_source(tmp_path: Path) -> None:
    manifest = tmp_path / "targets.yaml"
    manifest.write_text(
        """schema_version: 1
targets:
  - id: target
    source_id: missing
    category: equipment
    url: https://example.com/page
    output: target.json
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="unknown source"):
        load_targets(manifest, {})


def test_load_targets_rejects_verified_candidate(tmp_path: Path) -> None:
    sources_manifest = tmp_path / "sources.yaml"
    sources_manifest.write_text(
        """schema_version: 1
sources:
  - id: source
    title: Source
    base_url: https://example.com/
    language: ja
    license: NOASSERTION
    usage: cross-check-only
    attribution: Example
""",
        encoding="utf-8",
    )
    targets_manifest = tmp_path / "targets.yaml"
    targets_manifest.write_text(
        """schema_version: 1
targets:
  - id: target
    source_id: source
    category: equipment
    url: https://example.com/page
    output: target.json
    verification_status: verified_0_99
""",
        encoding="utf-8",
    )

    with pytest.raises(ManifestError, match="cannot be verified_0_99"):
        load_targets(targets_manifest, load_sources(sources_manifest))


def test_write_json_atomic_preserves_chinese(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "output.json"

    write_json_atomic(output, {"name": "生锈大炮"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"name": "生锈大炮"}
    assert "生锈大炮" in output.read_text(encoding="utf-8")
    assert list(output.parent.glob(".*.tmp")) == []


def test_write_json_batch_atomic_cleans_temps_and_preserves_old_files_on_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_text('{"old": 1}\n', encoding="utf-8")
    second.write_text('{"old": 2}\n', encoding="utf-8")
    calls = 0
    original_sync_file = storage.sync_file

    def fail_second_sync(file_descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated fsync failure")
        original_sync_file(file_descriptor)

    monkeypatch.setattr(storage, "sync_file", fail_second_sync)

    with pytest.raises(OSError, match="simulated fsync failure"):
        write_json_batch_atomic({first: JsonPayload(name="新一"), second: JsonPayload(name="新二")})

    assert first.read_text(encoding="utf-8") == '{"old": 1}\n'
    assert second.read_text(encoding="utf-8") == '{"old": 2}\n'
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_json_batch_atomic_keeps_write_and_temp_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.json"
    original_unlink = Path.unlink
    failed_unlink = False

    def fail_sync(_file_descriptor: int) -> None:
        raise OSError("FILE SYNC FAILURE")

    def fail_first_unlink(path: Path, missing_ok: bool = False) -> None:
        nonlocal failed_unlink
        if path.suffix == ".tmp" and not failed_unlink:
            failed_unlink = True
            raise OSError("TEMP CLEANUP FAILURE")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(storage, "sync_file", fail_sync)
    monkeypatch.setattr(Path, "unlink", fail_first_unlink)

    with pytest.raises(OSError) as captured:
        write_json_batch_atomic({output: JsonPayload(name="new")})

    message = str(captured.value)
    assert "FILE SYNC FAILURE" in message
    assert "TEMP CLEANUP FAILURE" in message
    assert list(tmp_path.glob(".*.tmp")) == []


def test_write_json_batch_atomic_rolls_back_all_outputs_when_second_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = [tmp_path / f"output-{index}.json" for index in range(6)]
    old_values = {path: f'{{"old": {index}}}\n'.encode() for index, path in enumerate(outputs)}
    for path, value in old_values.items():
        path.write_bytes(value)
    calls = 0
    original_replace = storage.replace_file

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second replace failure")
        original_replace(source, target)

    monkeypatch.setattr(storage, "replace_file", fail_second_replace)

    with pytest.raises(OSError, match="simulated second replace failure"):
        write_json_batch_atomic(
            {path: JsonPayload(name=f"new-{index}") for index, path in enumerate(outputs)}
        )

    assert {path: path.read_bytes() for path in outputs} == old_values
    assert list(tmp_path.glob(".*.tmp")) == []
    assert list(tmp_path.glob(".*.bak")) == []


def test_write_json_batch_atomic_keeps_backup_when_rollback_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    first.write_bytes(b'{"old": 1}\n')
    second.write_bytes(b'{"old": 2}\n')
    calls = 0
    original_replace = storage.replace_file

    def fail_commit_and_rollback(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("PRIMARY REPLACE FAILURE")
        if calls == 3:
            raise OSError("ROLLBACK REPLACE FAILURE")
        original_replace(source, target)

    monkeypatch.setattr(storage, "replace_file", fail_commit_and_rollback)

    with pytest.raises(OSError) as captured:
        write_json_batch_atomic(
            {first: JsonPayload(name="new-first"), second: JsonPayload(name="new-second")}
        )

    message = str(captured.value)
    assert "PRIMARY REPLACE FAILURE" in message
    assert "ROLLBACK REPLACE FAILURE" in message
    assert json.loads(first.read_text(encoding="utf-8")) == {"name": "new-first"}
    assert second.read_bytes() == b'{"old": 2}\n'
    backups = list(tmp_path.glob(".*.bak"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b'{"old": 1}\n'
    assert str(backups[0]) in message
    assert list(tmp_path.glob(".*.tmp")) == []


def test_json_writers_create_world_readable_files(tmp_path: Path) -> None:
    single_output = tmp_path / "single.json"
    batch_output = tmp_path / "batch.json"

    write_json_atomic(single_output, {"name": "单文件"})
    write_json_batch_atomic({batch_output: JsonPayload(name="批量文件")})

    assert stat.S_IMODE(single_output.stat().st_mode) == 0o644
    assert stat.S_IMODE(batch_output.stat().st_mode) == 0o644


def test_write_json_batch_atomic_rolls_back_when_commit_directory_sync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = [tmp_path / f"output-{index}.json" for index in range(6)]
    old_values = {path: f'{{"old": {index}}}\n'.encode() for index, path in enumerate(outputs)}
    for path, value in old_values.items():
        path.write_bytes(value)
    calls = 0
    original_sync_directory = storage.sync_directory

    def fail_first_sync(directory: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated commit directory sync failure")
        original_sync_directory(directory)

    monkeypatch.setattr(storage, "sync_directory", fail_first_sync)

    with pytest.raises(OSError, match="simulated commit directory sync failure"):
        write_json_batch_atomic(
            {path: JsonPayload(name=f"new-{index}") for index, path in enumerate(outputs)}
        )

    assert {path: path.read_bytes() for path in outputs} == old_values
    assert list(tmp_path.glob(".*.tmp")) == []
    assert list(tmp_path.glob(".*.bak")) == []


def test_write_json_batch_atomic_does_not_fail_after_committed_backup_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.json"
    output.write_text('{"old": true}\n', encoding="utf-8")
    calls = 0
    original_sync_directory = storage.sync_directory

    def fail_unexpected_second_sync(directory: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated cleanup directory sync failure")
        original_sync_directory(directory)

    monkeypatch.setattr(storage, "sync_directory", fail_unexpected_second_sync)

    write_json_batch_atomic({output: JsonPayload(name="new")})

    assert calls == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {"name": "new"}
    assert list(tmp_path.glob(".*.tmp")) == []
    assert list(tmp_path.glob(".*.bak")) == []


def test_write_json_batch_atomic_keeps_root_rollback_and_cleanup_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.json"
    output.write_text('{"old": true}\n', encoding="utf-8")
    original_remove_paths = storage._remove_paths

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("ROOT REPLACE FAILURE")

    def fail_rollback(
        replaced_paths: list[Path], backups: dict[Path, Path], target_paths: list[Path]
    ) -> list[OSError]:
        return [OSError("ROLLBACK FAILURE")]

    cleanup_calls = 0

    def add_cleanup_failure(paths: list[Path]) -> list[OSError]:
        nonlocal cleanup_calls
        cleanup_calls += 1
        errors = original_remove_paths(paths)
        errors.append(OSError(f"CLEANUP FAILURE {cleanup_calls}"))
        return errors

    monkeypatch.setattr(storage, "replace_file", fail_replace)
    monkeypatch.setattr(storage, "_rollback_replacements", fail_rollback)
    monkeypatch.setattr(storage, "_remove_paths", add_cleanup_failure)

    with pytest.raises(OSError) as error:
        write_json_batch_atomic({output: JsonPayload(name="new")})

    message = str(error.value)
    assert "ROOT REPLACE FAILURE" in message
    assert "ROLLBACK FAILURE" in message
    assert "CLEANUP FAILURE 1" in message
    assert "CLEANUP FAILURE 2" in message


def test_write_json_batch_atomic_retries_transient_backup_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.json"
    output.write_text('{"old": true}\n', encoding="utf-8")
    original_remove_paths = storage._remove_paths
    cleanup_calls = 0

    def fail_first_cleanup(paths: list[Path]) -> list[OSError]:
        nonlocal cleanup_calls
        cleanup_calls += 1
        if cleanup_calls == 1:
            return [OSError("TRANSIENT BACKUP UNLINK FAILURE")]
        return original_remove_paths(paths)

    monkeypatch.setattr(storage, "_remove_paths", fail_first_cleanup)

    write_json_batch_atomic({output: JsonPayload(name="new")})

    assert json.loads(output.read_text(encoding="utf-8")) == {"name": "new"}
    assert list(tmp_path.glob(".*.tmp")) == []
    assert list(tmp_path.glob(".*.bak")) == []


def test_write_json_batch_atomic_reports_persistent_cleanup_after_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "output.json"
    output.write_text('{"old": true}\n', encoding="utf-8")

    def fail_cleanup(paths: list[Path]) -> list[OSError]:
        return [OSError("PERSISTENT BACKUP UNLINK FAILURE")]

    monkeypatch.setattr(storage, "_remove_paths", fail_cleanup)

    with pytest.raises(OSError, match="commit completed but cleanup failed") as error:
        write_json_batch_atomic({output: JsonPayload(name="new")})

    residual_paths = [*tmp_path.glob(".*.tmp"), *tmp_path.glob(".*.bak")]
    assert residual_paths
    assert all(str(path) in str(error.value) for path in residual_paths)
    assert json.loads(output.read_text(encoding="utf-8")) == {"name": "new"}
