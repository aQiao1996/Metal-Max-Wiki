"""离线发布攻略原创图，并审计来源、人工清单、锁文件与公开副本。"""

import os
import stat
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.parse import urldefrag

from pydantic import HttpUrl

from mmwiki_data.asset_models import AssetEntry, RightsStatus
from mmwiki_data.asset_pipeline import (
    MAX_ASSET_BYTES,
    AssetPipelineError,
    _asset_process_lock,
    _audit_assets_locked,
    _cleanup_with_retry,
    _commit_files,
    _load_asset_lock,
    _reject_symlink,
    _temporary_file,
    load_asset_manifest,
)
from mmwiki_data.guide_normalization import (
    GuideDataset,
    GuideReferenceDiagram,
    load_guide_references,
)

_RAW_ROOT = Path("data/raw/mm2r/0.99/guides")
_ASSET_ROOT = Path("data/raw/mm2r/0.99/assets")
_DATASET_PATH = Path("data/interim/mm2r/0.99/guides.json")
_PUBLIC_ROOT = Path("apps/frontend/client/public/wiki/mm2r/0.99/guides")
_PUBLIC_URL = "/wiki/mm2r/0.99/guides/"
_ASSET_PREFIX = "mm2r-guide-"


@dataclass(frozen=True, slots=True)
class _Publication:
    diagram: GuideReferenceDiagram
    target: Path
    data: bytes


def _regular_bytes(path: Path, repo_root: Path, *, mode: int | None = None) -> bytes:
    _reject_symlink(path, repo_root)
    try:
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            raise AssetPipelineError(f"攻略资产必须是普通文件：{path}")
        if not 0 < metadata.st_size <= MAX_ASSET_BYTES:
            raise AssetPipelineError(f"攻略资产为空或超过 10 MiB：{path}")
        if mode is not None and stat.S_IMODE(metadata.st_mode) != mode:
            raise AssetPipelineError(f"攻略公开资产权限必须为 {mode:04o}：{path}")
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as file:
            opened = os.fstat(file.fileno())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise AssetPipelineError(f"攻略资产在校验期间被替换：{path}")
            data = file.read(MAX_ASSET_BYTES + 1)
        _reject_symlink(path, repo_root)
    except OSError as error:
        raise AssetPipelineError(f"无法读取攻略资产 {path}：{error}") from error
    if len(data) != metadata.st_size:
        raise AssetPipelineError(f"攻略资产在读取期间变化：{path}")
    return data


def _flat_files(path: Path, repo_root: Path, *, required: bool) -> set[Path]:
    _reject_symlink(path, repo_root)
    if not path.exists():
        if required:
            raise AssetPipelineError(f"攻略资产目录缺失：{path}")
        return set()
    if not path.is_dir():
        raise AssetPipelineError(f"攻略资产目录不是普通目录：{path}")
    try:
        files = set(path.iterdir())
        for file in files:
            _reject_symlink(file, repo_root)
            if not stat.S_ISREG(file.lstat().st_mode):
                raise AssetPipelineError(f"攻略资产目录不允许子目录或特殊文件：{file}")
        return files
    except OSError as error:
        raise AssetPipelineError(f"无法枚举攻略资产目录 {path}：{error}") from error


def _source_dataset(repo_root: Path) -> GuideDataset | None:
    names_path = repo_root / _RAW_ROOT / "names.yaml"
    facts_path = repo_root / _RAW_ROOT / "facts.json"
    dataset_path = repo_root / _DATASET_PATH
    public_root = repo_root / _PUBLIC_ROOT
    diagrams_root = repo_root / _RAW_ROOT / "diagrams"
    for path in (
        names_path,
        facts_path,
        dataset_path,
        public_root,
        diagrams_root,
        repo_root / _ASSET_ROOT / "lock.json",
    ):
        _reject_symlink(path, repo_root)
    if not names_path.exists() and not facts_path.exists():
        if dataset_path.exists() or public_root.exists() or diagrams_root.exists():
            raise AssetPipelineError("攻略原始来源缺失，但仍有结构化资料或图片，不能跳过审计")
        manifest_path = repo_root / _ASSET_ROOT / "manifest.yaml"
        _reject_symlink(manifest_path, repo_root)
        if manifest_path.exists() and any(
            entry.id.startswith(_ASSET_PREFIX) for entry in load_asset_manifest(repo_root).assets
        ):
            raise AssetPipelineError("攻略原始来源缺失，但人工清单仍登记了攻略原创图")
        return None
    _regular_bytes(names_path, repo_root)
    _regular_bytes(facts_path, repo_root)
    raw_files = _flat_files(repo_root / _RAW_ROOT / "diagrams", repo_root, required=True)
    rebuilt = load_guide_references(repo_root)
    if rebuilt is None:
        raise AssetPipelineError("攻略原始来源不完整，无法核对原创图")
    stored = GuideDataset.model_validate_json(_regular_bytes(dataset_path, repo_root))
    if stored != rebuilt:
        raise AssetPipelineError("攻略结构化资料与当前原始来源不一致，请先重建资料再审核资产清单")
    expected_raw = {repo_root / diagram.repo_relative_path for diagram in stored.diagrams}
    if raw_files != expected_raw:
        raise AssetPipelineError("攻略原始图目录与快照不一致，存在缺失图或未登记文件")
    return stored


def _expected_entry(dataset: GuideDataset, diagram: GuideReferenceDiagram) -> AssetEntry:
    filename = f"{diagram.id}-{diagram.content_hash.removeprefix('sha256:')[:12]}.svg"
    if (
        diagram.repo_relative_path != (_RAW_ROOT / "diagrams" / filename).as_posix()
        or diagram.public_path != _PUBLIC_URL + filename
    ):
        raise AssetPipelineError(f"{diagram.id}: 攻略图不是确定的内容寻址路径")
    return AssetEntry(
        id=_ASSET_PREFIX + diagram.id,
        kind="guide",
        title=diagram.title_zh,
        source_page_url=HttpUrl(urldefrag(str(diagram.source_refs[0].source_url))[0]),
        source_image_url=None,
        author=diagram.author,
        license=diagram.license,
        rights_status=RightsStatus.ORIGINAL_DIAGRAM,
        version_scope=[dataset.version_scope, "mm2r-099-unverified"],
        entity_refs=[],
        local_path="files/original-diagrams/" + filename,
        allowed_redirect_hosts=[],
        alt=diagram.alt_zh,
        notes=(
            "项目原创流程示意，非游戏截图、非实机地图；依据 MM2R 日版公开事实整理，"
            "中文参考，0.99 未验证。对应章节："
            + "、".join(diagram.chapter_ids)
            + "。完整事实出处与逐条证据保留在攻略章节中。"
        ),
    )


def _public_files(
    repo_root: Path, publications: list[_Publication], *, required: bool
) -> set[Path]:
    public_files = _flat_files(repo_root / _PUBLIC_ROOT, repo_root, required=required)
    targets = {publication.target for publication in publications}
    extra = public_files - targets
    if extra:
        raise AssetPipelineError(
            "攻略公开图存在人工清单未登记的旧图或额外文件，请明确处理后重新发布："
            + "、".join(str(path.relative_to(repo_root)) for path in sorted(extra))
        )
    return public_files


def _locked_publications(repo_root: Path, dataset: GuideDataset) -> list[_Publication]:
    manifest = load_asset_manifest(repo_root)
    lock = _load_asset_lock(repo_root, required=True)
    if lock is None:
        raise AssetPipelineError("攻略图片锁文件缺失")
    manifest_by_id = {entry.id: entry for entry in manifest.assets}
    locked_by_id = {entry.asset_id: entry for entry in lock.assets}
    expected_ids = {_ASSET_PREFIX + diagram.id for diagram in dataset.diagrams}
    guide_ids = {entry.id for entry in manifest.assets if entry.id.startswith(_ASSET_PREFIX)}
    if guide_ids != expected_ids:
        raise AssetPipelineError("攻略原创图人工清单不完整或仍保留旧条目，请先审核清单")
    publications: list[_Publication] = []
    for diagram in dataset.diagrams:
        expected = _expected_entry(dataset, diagram)
        entry = manifest_by_id[expected.id]
        if entry != expected:
            raise AssetPipelineError(
                f"{expected.id}: 清单路径、版权属性或版本说明已漂移，请先审核清单"
            )
        locked = locked_by_id.get(entry.id)
        if locked is None or (
            locked.local_path != expected.local_path
            or locked.sha256 != diagram.content_hash
            or locked.final_url is not None
            or locked.media_type != "image/svg+xml"
            or locked.width != diagram.width
            or locked.height != diagram.height
        ):
            raise AssetPipelineError(
                f"{entry.id}: 攻略锁定信息与当前快照不一致，请审核后重建锁文件"
            )
        if expected.local_path is None:
            raise AssetPipelineError(f"{entry.id}: 原创图缺少本地路径")
        source = repo_root / _ASSET_ROOT / expected.local_path
        data = _regular_bytes(source, repo_root, mode=0o644)
        original = _regular_bytes(repo_root / diagram.repo_relative_path, repo_root)
        if (
            "sha256:" + sha256(data).hexdigest() != diagram.content_hash
            or data != original
            or len(data) != locked.byte_size
        ):
            raise AssetPipelineError(f"{entry.id}: 本地资产与攻略原图或内容哈希不一致")
        publications.append(
            _Publication(diagram, repo_root / _PUBLIC_ROOT / Path(source).name, data)
        )
    errors = _audit_assets_locked(repo_root)
    if errors:
        raise AssetPipelineError("攻略图发布前的完整资产审计失败：" + "; ".join(errors))
    return publications


def _validate_public(repo_root: Path, publications: list[_Publication]) -> None:
    public_files = _public_files(repo_root, publications, required=True)
    for publication in publications:
        if publication.target not in public_files:
            raise AssetPipelineError(f"攻略公开图缺失，请明确执行图片发布：{publication.target}")
        data = _regular_bytes(publication.target, repo_root, mode=0o644)
        if data != publication.data or "sha256:" + sha256(data).hexdigest() != (
            publication.diagram.content_hash
        ):
            raise AssetPipelineError(
                f"攻略公开图内容漂移，请审核来源后重新发布：{publication.target}"
            )


def publish_guide_assets(repo_root: Path) -> int:
    """原子发布三张已核验的原创图，返回有效发布数；来源未采集时返回零。"""
    root = Path(os.path.abspath(repo_root))
    dataset = _source_dataset(root)
    if dataset is None:
        return 0
    with _asset_process_lock(root):
        publications = _locked_publications(root, dataset)
        public_files = _public_files(root, publications, required=False)
        replacements: list[tuple[Path, Path]] = []
        try:
            for publication in publications:
                if publication.target in public_files:
                    existing = _regular_bytes(publication.target, root)
                    if (
                        existing == publication.data
                        and stat.S_IMODE(publication.target.lstat().st_mode) == 0o644
                    ):
                        continue
                temporary, handle = _temporary_file(
                    publication.target.parent, prefix=".guide-publish-", boundary=root
                )
                replacements.append((temporary, publication.target))
                with handle:
                    handle.write(publication.data)
                    handle.flush()
                    os.fsync(handle.fileno())
            _commit_files(replacements, asset_root=root, replace=os.replace)
            replacements.clear()
        except Exception as error:
            cleanup_errors = _cleanup_with_retry(path for path, _target in replacements)
            if cleanup_errors:
                raise AssetPipelineError(
                    f"{error}; 攻略公开图临时文件清理失败："
                    + "; ".join(str(item) for item in cleanup_errors)
                ) from error
            raise
        _validate_public(root, publications)
        return len(publications)


def validate_guide_assets(repo_root: Path) -> bool:
    """离线审计三张原创图的全部副本、路径、版权与锁定信息，漂移时明确失败。"""
    root = Path(os.path.abspath(repo_root))
    dataset = _source_dataset(root)
    if dataset is None:
        return False
    with _asset_process_lock(root, shared=True, blocking=True):
        publications = _locked_publications(root, dataset)
        _validate_public(root, publications)
    return True
