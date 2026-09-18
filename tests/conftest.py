"""Shared fixtures.

The NovaCart estate is parsed once per session: it is seven specifications, and the
pipeline is deterministic, so re-running it per test would only cost seconds and prove
nothing that ``test_pipeline`` does not already prove.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api_galaxy.exports.bundle import ReportBundle, build_bundle
from api_galaxy.pipeline import AnalysedProject, analyse_manifest

REPO_ROOT = Path(__file__).resolve().parents[1]
NOVACART_MANIFEST = REPO_ROOT / "samples" / "novacart" / "novacart-manifest.yaml"


@pytest.fixture(scope="session")
def novacart() -> AnalysedProject:
    return analyse_manifest(NOVACART_MANIFEST, project_id="test-novacart")


@pytest.fixture(scope="session")
def novacart_bundle(novacart: AnalysedProject) -> ReportBundle:
    return build_bundle(novacart)
