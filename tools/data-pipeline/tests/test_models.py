from datetime import datetime

import pytest
from pydantic import ValidationError

from mmwiki_data.models import CandidateSnapshot, Source, Target, VerificationStatus


def test_candidate_cannot_claim_verified_0_99() -> None:
    with pytest.raises(ValidationError, match="candidate snapshot cannot be verified_0_99"):
        CandidateSnapshot.model_validate(
            {
                "source_id": "zzjb-mm2r",
                "target_id": "tank-parts",
                "source_url": "https://www.zzjb.com/wiki/mm2r/item/tank/part/start",
                "retrieved_at": datetime.fromisoformat("2026-09-21T12:00:00+08:00"),
                "content_hash": "sha256:" + "a" * 64,
                "license": "CC-BY-NC-SA-4.0",
                "verification_status": VerificationStatus.VERIFIED_0_99,
                "tables": [],
                "excerpts": [],
                "warnings": [],
            }
        )


def test_target_url_must_be_http() -> None:
    with pytest.raises(ValidationError):
        Target.model_validate(
            {
                "id": "bad",
                "source_id": "source",
                "category": "equipment",
                "url": "file:///tmp/page.html",
                "output": "bad.json",
            }
        )


def test_source_requires_explicit_license() -> None:
    with pytest.raises(ValidationError):
        Source.model_validate(
            {
                "id": "source",
                "title": "Source",
                "base_url": "https://example.com",
                "language": "ja",
                "license": "",
                "usage": "cross-check-only",
                "attribution": "Example",
            }
        )
