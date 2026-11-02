"""资料采集与审计命令行入口。"""

import argparse
import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from mmwiki_data.asset_pipeline import AssetPipelineError, audit_assets, fetch_assets
from mmwiki_data.c_units import collect_c_units, load_c_units
from mmwiki_data.engines import collect_engines, load_engines
from mmwiki_data.fetcher import FetchError, fetch
from mmwiki_data.guide_assets import publish_guide_assets, validate_guide_assets
from mmwiki_data.guide_normalization import (
    GuideRouteIndex,
    load_guide_references,
    validate_guide_sources,
)
from mmwiki_data.guides import collect_guides
from mmwiki_data.item_normalization import load_item_references, validate_item_sources
from mmwiki_data.items import collect_items
from mmwiki_data.job_normalization import load_job_references, validate_job_sources
from mmwiki_data.job_skills import collect_job_skills
from mmwiki_data.knowledge_models import build_knowledge_route_index
from mmwiki_data.models import (
    CandidateSnapshot,
    CollectedTarget,
    CollectionReport,
    FailedTarget,
)
from mmwiki_data.normalization import NormalizationError, normalize_snapshots
from mmwiki_data.normalization_models import NormalizedBundle
from mmwiki_data.parser import extract_page
from mmwiki_data.quest_normalization import load_quest_references, validate_quest_sources
from mmwiki_data.quests import collect_quests
from mmwiki_data.rom_names import validate_rom_names, verify_rom_names
from mmwiki_data.rom_parameters import validate_rom_parameters, verify_rom_parameters
from mmwiki_data.special_equipment import collect_special_equipment, load_special_equipment
from mmwiki_data.storage import (
    ManifestError,
    load_sources,
    load_targets,
    write_json_atomic,
    write_json_batch_atomic,
)
from mmwiki_data.sub_guns import collect_sub_guns, load_sub_guns
from mmwiki_data.vehicle_normalization import load_vehicle_references, validate_vehicle_sources
from mmwiki_data.vehicle_traits import collect_vehicle_traits
from mmwiki_data.vehicles import collect_vehicles
from mmwiki_data.wanted_drop_items import collect_wanted_drop_items
from mmwiki_data.wanted_monsters import collect_wanted_monsters
from mmwiki_data.wanted_normalization import load_wanted_monsters, validate_wanted_sources

USER_AGENT = "MetalMaxWikiResearch/0.1 (+https://mm.yangyunqiao.top)"

_NORMALIZED_FILENAMES = {
    "equipment": "equipment.json",
    "items": "items.json",
    "quests": "quests.json",
    "jobs": "jobs.json",
    "skills": "skills.json",
}


class NormalizationInputError(ValueError):
    """候选快照与清单契约不一致。"""


def _data_root(repo_root: Path) -> Path:
    return repo_root / "data" / "raw" / "mm2r" / "0.99"


def collect(
    repo_root: Path,
    *,
    client: httpx.Client | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> CollectionReport:
    """串行采集清单中的公开页面，并返回完整运行摘要。"""
    data_root = _data_root(repo_root)
    sources = load_sources(data_root / "sources.yaml")
    targets = load_targets(data_root / "targets.yaml", sources)
    collection_targets = [target for target in targets if target.collect]
    skipped = [target.id for target in targets if not target.collect]
    collected: list[CollectedTarget] = []
    failed: list[FailedTarget] = []
    own_client = client is None
    active_client = client or httpx.Client(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )

    try:
        for index, target in enumerate(collection_targets):
            source = sources[target.source_id]
            url = str(target.url)
            try:
                fetched = fetch(active_client, target.id, url)
                extraction = extract_page(fetched.body)
                row_count = sum(len(table.rows) for table in extraction.tables)
                if not extraction.tables or row_count == 0:
                    raise FetchError(f"{target.id}: page contains no non-empty data tables: {url}")
                snapshot = CandidateSnapshot(
                    source_id=source.id,
                    target_id=target.id,
                    source_url=target.url,
                    retrieved_at=datetime.now().astimezone(),
                    content_hash=fetched.content_hash,
                    license=source.license,
                    verification_status=target.verification_status,
                    tables=extraction.tables,
                    excerpts=extraction.excerpts if source.usage == "primary-data" else [],
                    warnings=extraction.warnings,
                )
                write_json_atomic(data_root / "candidates" / target.output, snapshot)
                collected.append(
                    CollectedTarget(
                        target_id=target.id,
                        output=target.output,
                        table_count=len(extraction.tables),
                        row_count=row_count,
                    )
                )
            except FetchError as error:
                failed.append(FailedTarget(target_id=target.id, url=target.url, error=str(error)))
            if index < len(collection_targets) - 1:
                sleep(1.5)
    finally:
        if own_client:
            active_client.close()

    report = CollectionReport(
        generated_at=datetime.now().astimezone(),
        collected=collected,
        skipped=skipped,
        failed=failed,
    )
    write_json_atomic(data_root / "reports" / "collection.json", report)
    return report


def audit(repo_root: Path) -> list[str]:
    """验证候选快照与清单之间的引用和版本边界。"""
    data_root = _data_root(repo_root)
    sources = load_sources(data_root / "sources.yaml")
    targets = load_targets(data_root / "targets.yaml", sources)
    expected = {target.output: target for target in targets if target.collect}
    candidate_root = data_root / "candidates"
    errors: list[str] = []

    for path in sorted(candidate_root.glob("*.json")):
        if path.name not in expected:
            errors.append(f"undeclared candidate file: {path}")

    for filename, target in expected.items():
        path = candidate_root / filename
        if not path.exists():
            errors.append(f"missing candidate for {target.id}: {path}")
            continue
        try:
            snapshot = CandidateSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            errors.append(f"invalid candidate {path}: {error}")
            continue
        source = sources[target.source_id]
        if snapshot.target_id != target.id:
            errors.append(f"{path}: target_id does not match {target.id}")
        if snapshot.source_id != target.source_id:
            errors.append(f"{path}: source_id does not match {target.source_id}")
        if str(snapshot.source_url) != str(target.url):
            errors.append(f"{path}: source_url does not match the target manifest")
        if snapshot.license != source.license:
            errors.append(f"{path}: license does not match source {source.id}")
        if not snapshot.tables or sum(len(table.rows) for table in snapshot.tables) == 0:
            errors.append(f"{path}: candidate contains no non-empty data tables")

    processed_root = repo_root / "data" / "processed" / "mm2r" / "0.99"
    for path in sorted(processed_root.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"invalid processed JSON {path}: {error}")
            continue
        records = value if isinstance(value, list) else [value]
        for index, record in enumerate(records):
            if not isinstance(record, dict) or record.get("verification_status") != "verified_0_99":
                errors.append(f"{path}: record {index} is not verified_0_99")

    try:
        load_special_equipment(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid S-E source: {error}")
    try:
        load_c_units(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid C-unit source: {error}")
    try:
        load_engines(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid engine source: {error}")
    try:
        load_sub_guns(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid sub-gun source: {error}")
    try:
        validate_wanted_sources(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid wanted-monster source: {error}")
    try:
        validate_vehicle_sources(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid vehicle source: {error}")
    try:
        validate_job_sources(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid job source: {error}")
    for label, validator in (("item", validate_item_sources), ("quest", validate_quest_sources)):
        try:
            validator(repo_root)
        except (OSError, ValueError) as error:
            errors.append(f"invalid {label} source: {error}")
    try:
        validate_guide_sources(repo_root)
        validate_guide_assets(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid guide source: {error}")
    try:
        validate_rom_names(repo_root)
        validate_rom_parameters(repo_root)
    except (OSError, ValueError) as error:
        errors.append(f"invalid ROM name verification: {error}")
    return errors


def _load_normalization_snapshots(repo_root: Path) -> list[CandidateSnapshot]:
    """读取并验证所有允许标准化的候选快照。"""
    data_root = _data_root(repo_root)
    sources = load_sources(data_root / "sources.yaml")
    targets = load_targets(data_root / "targets.yaml", sources)
    expected_outputs = {target.output for target in targets if target.collect}
    candidate_root = data_root / "candidates"
    actual_outputs = {path.name for path in candidate_root.glob("*.json")}
    missing_outputs = sorted(expected_outputs - actual_outputs)
    undeclared_outputs = sorted(actual_outputs - expected_outputs)
    if missing_outputs or undeclared_outputs:
        raise NormalizationInputError(
            f"missing candidate outputs={missing_outputs}; "
            f"undeclared candidate file={undeclared_outputs}"
        )
    snapshots: list[CandidateSnapshot] = []
    for target in (target for target in targets if target.collect):
        path = data_root / "candidates" / target.output
        if not path.is_file():
            raise NormalizationInputError(f"missing candidate for {target.id}: {path}")
        try:
            snapshot = CandidateSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise NormalizationInputError(f"invalid candidate {path}: {error}") from error
        source = sources[target.source_id]
        expected_values = (
            ("target_id", snapshot.target_id, target.id),
            ("source_id", snapshot.source_id, target.source_id),
            ("source_url", str(snapshot.source_url), str(target.url)),
            ("license", snapshot.license, source.license),
            ("verification_status", snapshot.verification_status, target.verification_status),
            ("game", snapshot.game, "mm2r"),
            ("target_version", snapshot.target_version, "0.99"),
            ("schema_version", snapshot.schema_version, 1),
        )
        for field, actual, expected in expected_values:
            if actual != expected:
                raise NormalizationInputError(
                    f"candidate {path}: {field} mismatch; actual={actual!r}; expected={expected!r}"
                )
        snapshots.append(snapshot)
    return snapshots


def normalize(repo_root: Path) -> dict[str, object]:
    """将完整候选集合写入确定性的 interim 数据包。"""
    result = normalize_snapshots(_load_normalization_snapshots(repo_root))
    for supplement in (
        load_special_equipment(repo_root),
        load_c_units(repo_root),
        load_engines(repo_root),
        load_sub_guns(repo_root),
    ):
        if supplement is None:
            continue
        equipment = result.bundles["equipment"]
        result.bundles["equipment"] = NormalizedBundle(
            domain="equipment",
            records=sorted([*equipment.records, *supplement.records], key=lambda r: r.id),
            source_hashes=[*equipment.source_hashes, *supplement.source_hashes],
        )
    output_root = repo_root / "data" / "interim" / "mm2r" / "0.99"
    output_values: dict[Path, BaseModel] = {
        output_root / _NORMALIZED_FILENAMES[domain]: bundle
        for domain, bundle in result.bundles.items()
    }
    output_values[output_root / "conflicts.json"] = result.conflicts
    wanted = load_wanted_monsters(
        repo_root,
        result.bundles["equipment"].records,
        rebuilt_bundles={
            f"data/interim/mm2r/0.99/{domain}.json": bundle
            for domain, bundle in result.bundles.items()
        },
    )
    if wanted is not None:
        output_values[output_root / "wanted-monsters.json"] = wanted
    vehicle = load_vehicle_references(repo_root)
    if vehicle is not None:
        output_values[output_root / "vehicles.json"] = vehicle
    jobs = load_job_references(
        repo_root,
        rebuilt_bundles={
            f"data/interim/mm2r/0.99/{domain}.json": result.bundles[domain]
            for domain in ("jobs", "skills")
        },
    )
    if jobs is not None:
        output_values[output_root / "job-entries.json"] = jobs
    items = load_item_references(repo_root, rebuilt_bundle=result.bundles["items"])
    quests = load_quest_references(repo_root, rebuilt_bundle=result.bundles["quests"])
    if items is not None:
        output_values[output_root / "item-entries.json"] = items
    if quests is not None:
        output_values[output_root / "quest-entries.json"] = quests
    knowledge_datasets = [
        dataset for dataset in (wanted, vehicle, jobs, items, quests) if dataset is not None
    ]
    if knowledge_datasets:
        output_values[output_root / "knowledge-routes.json"] = build_knowledge_route_index(
            knowledge_datasets
        )
    guides = load_guide_references(repo_root)
    if guides is not None:
        output_values[output_root / "guides.json"] = guides
        output_values[output_root / "guide-routes.json"] = GuideRouteIndex(
            slugs=[record.slug for record in guides.records]
        )
    write_json_batch_atomic(output_values)

    domain_counts = {domain: len(bundle.records) for domain, bundle in result.bundles.items()}
    source_ref_count = sum(
        len(record.source_refs) for bundle in result.bundles.values() for record in bundle.records
    )
    source_span_count = sum(
        len(record.source_spans) for bundle in result.bundles.values() for record in bundle.records
    )
    if wanted is not None:
        domain_counts[wanted.category] = len(wanted.records)
        source_ref_count += sum(len(record.source_refs) for record in wanted.records)
    if vehicle is not None:
        domain_counts[vehicle.category] = len(vehicle.records)
        source_ref_count += sum(len(record.source_refs) for record in vehicle.records)
    if jobs is not None:
        source_ref_count += sum(len(record.source_refs) for record in jobs.records)
    for dataset in (items, quests):
        if dataset is not None:
            domain_counts[dataset.category] = len(dataset.records)
            source_ref_count += sum(len(record.source_refs) for record in dataset.records)
    if guides is not None:
        domain_counts["guides"] = len(guides.records)
        source_ref_count += sum(len(record.source_refs) for record in guides.records)
    output_paths: Mapping[str, str] = {path.name: str(path) for path in sorted(output_values)}
    return {
        "domains": domain_counts,
        "total_records": sum(domain_counts.values()),
        "conflict_count": len(result.conflicts.conflicts),
        "source_ref_count": source_ref_count,
        "source_span_count": source_span_count,
        "output_paths": output_paths,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Metal Max Wiki data acquisition")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("verify-rom-names", "verify-rom-parameters"):
        rom_parser = subparsers.add_parser(command)
        rom_parser.add_argument("--repo-root", type=Path, required=True)
        rom_parser.add_argument("--rom", type=Path, required=True)
        rom_parser.add_argument("--check", action="store_true")
    for command in (
        "collect",
        "collect-special-equipment",
        "collect-c-units",
        "collect-engines",
        "collect-sub-guns",
        "collect-wanted-monsters",
        "collect-wanted-drop-items",
        "collect-vehicles",
        "collect-vehicle-traits",
        "collect-job-skills",
        "collect-items",
        "collect-quests",
        "collect-guides",
        "audit",
        "normalize",
        "asset-audit",
        "asset-fetch",
        "asset-publish-guides",
    ):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--repo-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行采集或审计命令。"""
    arguments = _build_parser().parse_args(argv)
    command_labels = {
        "normalize": "normalization",
        "asset-audit": "asset audit",
        "asset-fetch": "asset fetch",
        "asset-publish-guides": "guide asset publish",
    }
    command_label = command_labels.get(arguments.command, arguments.command)
    try:
        if arguments.command == "verify-rom-parameters":
            parameter_summary = verify_rom_parameters(
                arguments.repo_root.resolve(), arguments.rom.resolve(), check=arguments.check
            )
            print(json.dumps(parameter_summary, ensure_ascii=False))
            return 0
        if arguments.command == "verify-rom-names":
            rom_summary = verify_rom_names(
                arguments.repo_root.resolve(), arguments.rom.resolve(), check=arguments.check
            )
            print(json.dumps(rom_summary, ensure_ascii=False))
            return 0
        if arguments.command == "asset-publish-guides":
            count = publish_guide_assets(arguments.repo_root.resolve())
            print(json.dumps({"published": count}, ensure_ascii=False))
            return 0
        if arguments.command == "collect-guides":
            guide_summary = collect_guides(arguments.repo_root.resolve())
            print(json.dumps(guide_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-items":
            item_summary = collect_items(arguments.repo_root.resolve())
            print(json.dumps(item_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-quests":
            quest_summary = collect_quests(arguments.repo_root.resolve())
            print(json.dumps(quest_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-job-skills":
            job_summary = collect_job_skills(arguments.repo_root.resolve())
            print(json.dumps(job_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-vehicles":
            vehicle_summary = collect_vehicles(arguments.repo_root.resolve())
            print(json.dumps(vehicle_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-vehicle-traits":
            vehicle_trait_summary = collect_vehicle_traits(arguments.repo_root.resolve())
            print(json.dumps(vehicle_trait_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-wanted-monsters":
            wanted_summary = collect_wanted_monsters(arguments.repo_root.resolve())
            print(json.dumps(wanted_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-wanted-drop-items":
            drop_summary = collect_wanted_drop_items(arguments.repo_root.resolve())
            print(json.dumps(drop_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-sub-guns":
            sub_gun_summary = collect_sub_guns(arguments.repo_root.resolve())
            print(json.dumps(sub_gun_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-engines":
            engine_summary = collect_engines(arguments.repo_root.resolve())
            print(json.dumps(engine_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-c-units":
            c_unit_summary = collect_c_units(arguments.repo_root.resolve())
            print(json.dumps(c_unit_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect-special-equipment":
            se_summary = collect_special_equipment(arguments.repo_root.resolve())
            print(json.dumps(se_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "collect":
            report = collect(arguments.repo_root.resolve())
            print(report.model_dump_json(indent=2))
            return 1 if report.failed else 0
        if arguments.command == "normalize":
            summary = normalize(arguments.repo_root.resolve())
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "asset-fetch":
            fetch_summary = fetch_assets(arguments.repo_root.resolve())
            print(json.dumps(fetch_summary, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "asset-audit":
            asset_errors = audit_assets(arguments.repo_root.resolve())
            if asset_errors:
                for asset_error in asset_errors:
                    print(f"asset audit error: {asset_error}")
                return 1
            print("asset audit passed")
            return 0
        errors = audit(arguments.repo_root.resolve())
    except ManifestError as error:
        print(f"{command_label} error: {error}")
        return 1
    except NormalizationInputError as error:
        print(f"normalization error: {error}")
        return 1
    except AssetPipelineError as error:
        print(f"{command_label} error: {error}")
        return 1
    except (NormalizationError, OSError, ValueError, httpx.HTTPError) as error:
        print(f"{command_label} error: {error}")
        return 1

    if errors:
        for audit_error in errors:
            print(audit_error)
        return 1
    print("data audit passed")
    return 0
