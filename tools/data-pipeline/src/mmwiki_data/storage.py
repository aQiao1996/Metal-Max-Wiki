"""资料清单读取与原子化 JSON 写入。"""

import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import cast

import yaml
from pydantic import BaseModel, ValidationError

from mmwiki_data.models import Source, Target, VerificationStatus


class ManifestError(ValueError):
    """来源或目标清单不符合采集约束。"""


def _load_document(path: Path) -> Mapping[str, object]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ManifestError(f"cannot load manifest {path}: {error}") from error
    if not isinstance(value, dict):
        raise ManifestError(f"manifest must be a mapping: {path}")
    if value.get("schema_version") != 1:
        raise ManifestError(f"unsupported schema_version in {path}")
    return cast(Mapping[str, object], value)


def load_sources(path: Path) -> dict[str, Source]:
    """读取来源清单，并拒绝重复或空清单。"""
    document = _load_document(path)
    raw_sources = document.get("sources")
    if not isinstance(raw_sources, list):
        raise ManifestError(f"sources must be a list: {path}")

    result: dict[str, Source] = {}
    for raw_source in raw_sources:
        try:
            source = Source.model_validate(raw_source)
        except ValidationError as error:
            raise ManifestError(f"invalid source in {path}: {error}") from error
        if source.id in result:
            raise ManifestError(f"duplicate source id {source.id!r} in {path}")
        result[source.id] = source
    if not result:
        raise ManifestError(f"source manifest is empty: {path}")
    return result


def load_targets(path: Path, sources: Mapping[str, Source]) -> list[Target]:
    """读取采集目标，并验证来源和输出路径引用。"""
    document = _load_document(path)
    raw_targets = document.get("targets")
    if not isinstance(raw_targets, list):
        raise ManifestError(f"targets must be a list: {path}")

    result: list[Target] = []
    ids: set[str] = set()
    outputs: set[str] = set()
    for raw_target in raw_targets:
        try:
            target = Target.model_validate(raw_target)
        except ValidationError as error:
            raise ManifestError(f"invalid target in {path}: {error}") from error
        if target.id in ids:
            raise ManifestError(f"duplicate target id {target.id!r} in {path}")
        if target.output in outputs:
            raise ManifestError(f"duplicate target output {target.output!r} in {path}")
        if target.source_id not in sources:
            raise ManifestError(
                f"target {target.id!r} references unknown source {target.source_id!r}"
            )
        if target.verification_status is VerificationStatus.VERIFIED_0_99:
            raise ManifestError(f"target {target.id!r} cannot be verified_0_99")
        ids.add(target.id)
        outputs.add(target.output)
        result.append(target)
    if not result:
        raise ManifestError(f"target manifest is empty: {path}")
    return result


def model_content_hash(value: BaseModel) -> str:
    """按规范模型内容计算依赖哈希，排除文件排版差异。"""
    canonical = json.dumps(
        value.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def write_json_atomic(path: Path, value: BaseModel | Mapping[str, object]) -> None:
    """以 UTF-8 写入 JSON，并通过替换避免留下半个文件。"""
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            os.fchmod(temporary_file.fileno(), 0o644)
            temporary_file.write(encoded)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        replace_file(temporary_path, path)
        sync_directory(path.parent)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _serialize_json(value: BaseModel | Mapping[str, object]) -> bytes:
    """将受支持的数据值稳定序列化为 JSON 字节。"""
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def sync_file(file_descriptor: int) -> None:
    """将临时文件内容同步到磁盘。"""
    os.fsync(file_descriptor)


def replace_file(source: Path, target: Path) -> None:
    """替换目标路径，供批量写入统一处理失败。"""
    os.replace(source, target)


def sync_directory(path: Path) -> None:
    """同步目录项，确保替换操作已落盘。"""
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_temporary_json(path: Path, encoded: bytes) -> Path:
    """将 JSON 字节写入目标目录中的安全临时文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            os.fchmod(temporary_file.fileno(), 0o644)
            temporary_file.write(encoded)
            temporary_file.flush()
            sync_file(temporary_file.fileno())
        return temporary_path
    except OSError as error:
        cleanup_errors, _retry_errors, remaining_paths = _cleanup_paths_with_retry(
            [temporary_path] if temporary_path is not None else []
        )
        if cleanup_errors:
            residual = (
                f"; residual paths: {[str(path) for path in remaining_paths]}"
                if remaining_paths
                else ""
            )
            raise OSError(
                f"{error}; temporary JSON cleanup failures: "
                f"{_failure_details(cleanup_errors)}{residual}"
            ) from error
        raise


def _create_backup(path: Path) -> Path:
    """为已有目标创建同目录、已同步的内容备份。"""
    backup_path: Path | None = None
    try:
        with (
            path.open("rb") as source_file,
            tempfile.NamedTemporaryFile(
                mode="wb",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".bak",
                delete=False,
            ) as backup_file,
        ):
            backup_path = Path(backup_file.name)
            os.fchmod(backup_file.fileno(), 0o644)
            shutil.copyfileobj(source_file, backup_file)
            backup_file.flush()
            sync_file(backup_file.fileno())
        return backup_path
    except OSError as error:
        cleanup_errors, _retry_errors, remaining_paths = _cleanup_paths_with_retry(
            [backup_path] if backup_path is not None else []
        )
        if cleanup_errors:
            residual = (
                f"; residual paths: {[str(path) for path in remaining_paths]}"
                if remaining_paths
                else ""
            )
            raise OSError(
                f"{error}; backup cleanup failures: {_failure_details(cleanup_errors)}{residual}"
            ) from error
        raise


def _remove_paths(paths: list[Path]) -> list[OSError]:
    """尽力清理临时路径，并收集所有清理失败。"""
    errors: list[OSError] = []
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError as error:
            errors.append(error)
    return errors


def _sync_directories(paths: list[Path]) -> list[OSError]:
    """同步去重后的父目录，并收集所有失败。"""
    errors: list[OSError] = []
    for directory in sorted({path.parent for path in paths}):
        try:
            sync_directory(directory)
        except OSError as error:
            errors.append(error)
    return errors


def _rollback_replacements(
    replaced_paths: list[Path], backups: Mapping[Path, Path], target_paths: list[Path]
) -> list[OSError]:
    """恢复已替换目标，并同步其父目录。"""
    errors: list[OSError] = []
    for path in reversed(replaced_paths):
        try:
            backup_path = backups.get(path)
            if backup_path is None:
                path.unlink()
            else:
                replace_file(backup_path, path)
        except OSError as error:
            errors.append(error)
    errors.extend(_sync_directories(target_paths))
    return errors


def _cleanup_paths_with_retry(paths: list[Path]) -> tuple[list[OSError], list[OSError], list[Path]]:
    """清理临时路径；首次失败时重试并返回残留路径。"""
    first_errors: list[OSError] = []
    try:
        first_errors.extend(_remove_paths(paths))
    except OSError as error:
        first_errors.append(error)

    remaining_paths: list[Path] = []
    for path in paths:
        try:
            if path.exists():
                remaining_paths.append(path)
        except OSError as error:
            first_errors.append(error)
    retry_errors: list[OSError] = []
    if first_errors or remaining_paths:
        try:
            retry_errors.extend(_remove_paths(paths))
        except OSError as error:
            retry_errors.append(error)
        remaining_paths = []
        for path in paths:
            try:
                if path.exists():
                    remaining_paths.append(path)
            except OSError as error:
                retry_errors.append(error)
    return [*first_errors, *retry_errors], retry_errors, remaining_paths


def _failure_details(errors: list[OSError]) -> str:
    """压缩多个底层错误，保留其原始上下文。"""
    return "; ".join(str(error) for error in errors)


def write_json_batch_atomic(values: Mapping[Path, BaseModel | Mapping[str, object]]) -> None:
    """处理可恢复失败时回滚批量替换，不承诺多文件单步原子。"""
    serialized = [(path, _serialize_json(value)) for path, value in sorted(values.items())]
    temporary_paths: list[Path] = []
    backups: dict[Path, Path] = {}
    target_paths = [path for path, _ in serialized]
    replaced_paths: list[Path] = []
    primary_error: OSError | None = None
    rollback_errors: list[OSError] = []
    replacement_phase_started = False
    cleanup_errors: list[OSError] = []
    retry_cleanup_errors: list[OSError] = []
    remaining_paths: list[Path] = []
    recovery_backups: set[Path] = set()
    try:
        for path, encoded in serialized:
            temporary_paths.append(_write_temporary_json(path, encoded))
        for path in target_paths:
            if path.exists():
                backups[path] = _create_backup(path)

        replacement_phase_started = True
        for path, temporary_path in zip(target_paths, temporary_paths, strict=True):
            replace_file(temporary_path, path)
            replaced_paths.append(path)
        directory_errors = _sync_directories(target_paths)
        if directory_errors:
            raise directory_errors[0]
    except OSError as error:
        primary_error = error
        if replacement_phase_started:
            try:
                rollback_errors = _rollback_replacements(replaced_paths, backups, target_paths)
            except OSError as rollback_error:
                rollback_errors = [rollback_error]
            if rollback_errors:
                recovery_backups = {
                    backup
                    for path, backup in backups.items()
                    if path in replaced_paths and backup.exists()
                }
    finally:
        cleanup_errors, retry_cleanup_errors, remaining_paths = _cleanup_paths_with_retry(
            [
                *temporary_paths,
                *(backup for backup in backups.values() if backup not in recovery_backups),
            ]
        )

    if primary_error is not None:
        details: list[str] = []
        if rollback_errors:
            details.append(f"rollback failures: {_failure_details(rollback_errors)}")
        if recovery_backups:
            details.append(
                "recovery backups: " + ", ".join(str(path) for path in sorted(recovery_backups))
            )
        if cleanup_errors:
            details.append(f"cleanup failures: {_failure_details(cleanup_errors)}")
        if remaining_paths:
            details.append(f"residual paths: {[str(path) for path in remaining_paths]}")
        if details:
            message = f"batch write failed: {primary_error}; {'; '.join(details)}"
            raise OSError(message) from primary_error
        raise primary_error

    if retry_cleanup_errors or remaining_paths:
        details = (
            [f"cleanup failures: {_failure_details(cleanup_errors)}"] if cleanup_errors else []
        )
        if remaining_paths:
            details.append(f"residual paths: {[str(path) for path in remaining_paths]}")
        raise OSError(f"commit completed but cleanup failed: {'; '.join(details)}")
