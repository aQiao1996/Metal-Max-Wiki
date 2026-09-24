import json
from pathlib import Path

import httpx
import pytest

from mmwiki_data.cli import audit, collect, main
from mmwiki_data.models import CandidateSnapshot

INTERIM_FILENAMES = (
    "equipment.json",
    "items.json",
    "quests.json",
    "jobs.json",
    "skills.json",
    "conflicts.json",
)


def write_normalize_fixture(repo_root: Path) -> Path:
    """以每个目标的一行有效数据构造最小标准化仓库。"""
    fixture_root = Path(__file__).parents[3] / "data" / "raw" / "mm2r" / "0.99"
    data_root = repo_root / "data" / "raw" / "mm2r" / "0.99"
    candidate_root = data_root / "candidates"
    candidate_root.mkdir(parents=True)
    for manifest_name in ("sources.yaml", "targets.yaml"):
        (data_root / manifest_name).write_text(
            (fixture_root / manifest_name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    for path in sorted((fixture_root / "candidates").glob("*.json")):
        snapshot = CandidateSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        minimal_snapshot = snapshot.model_copy(
            update={
                "tables": [
                    table.model_copy(
                        update={
                            "rows": table.rows[:1],
                            "merged_cells": [
                                cell for cell in table.merged_cells if cell.row_index == 2
                            ],
                        }
                    )
                    for table in snapshot.tables
                ]
            }
        )
        (candidate_root / path.name).write_text(
            minimal_snapshot.model_dump_json(indent=2), encoding="utf-8"
        )
    return data_root


def write_old_interim_files(repo_root: Path) -> dict[str, bytes]:
    """预置文件用于验证失败运行不会覆盖已有输出。"""
    interim_root = repo_root / "data" / "interim" / "mm2r" / "0.99"
    interim_root.mkdir(parents=True)
    old_files: dict[str, bytes] = {}
    for filename in INTERIM_FILENAMES:
        content = f'{{"old": "{filename}"}}\n'.encode()
        (interim_root / filename).write_bytes(content)
        old_files[filename] = content
    return old_files


def assert_interim_files_unchanged(repo_root: Path, old_files: dict[str, bytes]) -> None:
    """断言预置 interim 输出未被失败运行部分替换。"""
    interim_root = repo_root / "data" / "interim" / "mm2r" / "0.99"
    assert {path.name: path.read_bytes() for path in interim_root.glob("*.json")} == old_files


def write_manifests(repo_root: Path) -> None:
    data_root = repo_root / "data" / "raw" / "mm2r" / "0.99"
    data_root.mkdir(parents=True)
    (data_root / "sources.yaml").write_text(
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
    (data_root / "targets.yaml").write_text(
        """schema_version: 1
targets:
  - id: target
    source_id: source
    category: equipment
    url: https://example.com/page
    output: target.json
  - id: reference
    source_id: source
    category: reference
    url: https://example.com/reference
    output: reference.json
    collect: false
""",
        encoding="utf-8",
    )


def test_collect_writes_candidate_and_report(tmp_path: Path) -> None:
    write_manifests(tmp_path)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/html"},
            content=(
                b"<h1>Items</h1><h2>Weapons</h2><table>"
                b"<tr><th>Name</th></tr><tr><td>Cannon</td></tr></table>"
            ),
            request=request,
        )
    )

    with httpx.Client(transport=transport) as client:
        report = collect(tmp_path, client=client, sleep=lambda _: None)

    candidate = tmp_path / "data/raw/mm2r/0.99/candidates/target.json"
    assert candidate.exists()
    assert report.collected[0].row_count == 1
    assert report.skipped == ["reference"]
    assert report.failed == []
    assert json.loads(candidate.read_text(encoding="utf-8"))["target_id"] == "target"
    assert audit(tmp_path) == []


def test_collect_reports_failure_without_empty_candidate(tmp_path: Path) -> None:
    write_manifests(tmp_path)
    transport = httpx.MockTransport(lambda request: httpx.Response(404, request=request))

    with httpx.Client(transport=transport) as client:
        report = collect(tmp_path, client=client, sleep=lambda _: None)

    candidate = tmp_path / "data/raw/mm2r/0.99/candidates/target.json"
    report_path = tmp_path / "data/raw/mm2r/0.99/reports/collection.json"
    assert not candidate.exists()
    assert report.collected == []
    assert len(report.failed) == 1
    assert report_path.exists()


def test_normalize_writes_all_domain_bundles_and_deterministic_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_normalize_fixture(tmp_path)

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 0
    first_summary = json.loads(capsys.readouterr().out)
    interim_root = tmp_path / "data" / "interim" / "mm2r" / "0.99"
    first_bytes = {
        filename: (interim_root / filename).read_bytes() for filename in INTERIM_FILENAMES
    }

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 0
    second_summary = json.loads(capsys.readouterr().out)
    assert {
        filename: (interim_root / filename).read_bytes() for filename in INTERIM_FILENAMES
    } == first_bytes
    assert set(first_summary["domains"]) == {"equipment", "items", "quests", "jobs", "skills"}
    assert first_summary == second_summary
    assert first_summary["conflict_count"] == 0
    assert set(first_summary["output_paths"]) == set(INTERIM_FILENAMES)


def test_normalize_missing_candidate_preserves_existing_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_root = write_normalize_fixture(tmp_path)
    old_files = write_old_interim_files(tmp_path)
    (data_root / "candidates" / "tank-parts.json").unlink()

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 1
    assert "normalization error: missing candidate" in capsys.readouterr().out
    assert_interim_files_unchanged(tmp_path, old_files)


def test_normalize_undeclared_candidate_preserves_existing_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_root = write_normalize_fixture(tmp_path)
    old_files = write_old_interim_files(tmp_path)
    (data_root / "candidates" / "undeclared.json").write_text("{}\n", encoding="utf-8")

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 1
    assert "undeclared candidate file" in capsys.readouterr().out
    assert_interim_files_unchanged(tmp_path, old_files)


@pytest.mark.parametrize("invalid_content", ["{", None])
def test_normalize_invalid_candidate_preserves_existing_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], invalid_content: str | None
) -> None:
    data_root = write_normalize_fixture(tmp_path)
    old_files = write_old_interim_files(tmp_path)
    candidate_path = data_root / "candidates" / "tank-parts.json"
    if invalid_content is None:
        snapshot = json.loads(candidate_path.read_text(encoding="utf-8"))
        snapshot["tables"][0]["headers"].append("未知列")
        candidate_path.write_text(json.dumps(snapshot), encoding="utf-8")
    else:
        candidate_path.write_text(invalid_content, encoding="utf-8")

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "invalid candidate" in output or "normalization error" in output
    assert_interim_files_unchanged(tmp_path, old_files)


def test_normalize_candidate_contract_mismatch_has_actual_and_expected_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_root = write_normalize_fixture(tmp_path)
    old_files = write_old_interim_files(tmp_path)
    candidate_path = data_root / "candidates" / "tank-parts.json"
    snapshot = json.loads(candidate_path.read_text(encoding="utf-8"))
    snapshot["target_id"] = "tank-tools"
    candidate_path.write_text(json.dumps(snapshot), encoding="utf-8")

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "target_id" in output
    assert "actual='tank-tools'" in output
    assert "expected='tank-parts'" in output
    assert_interim_files_unchanged(tmp_path, old_files)


def test_normalize_invalid_candidate_uses_normalization_error_prefix(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_root = write_normalize_fixture(tmp_path)
    (data_root / "candidates" / "tank-parts.json").write_text("{", encoding="utf-8")

    assert main(["normalize", "--repo-root", str(tmp_path)]) == 1
    assert capsys.readouterr().out.startswith("normalization error: invalid candidate")
