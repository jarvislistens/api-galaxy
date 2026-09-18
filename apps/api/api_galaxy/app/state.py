"""Application state: the live registry of projects, providers and shared services.

Analysed projects are cached in memory because re-parsing an estate on every request
would make the graph view unusable, but the *source of truth* is always the files on
disk — a restart rehydrates everything, and nothing exists only in RAM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api_galaxy import __version__
from api_galaxy.app.jobs import JobManager
from api_galaxy.app.settings import Settings, get_settings
from api_galaxy.app.storage import Storage
from api_galaxy.contracts.analysis import AliasCluster, Ambiguity, Journey, Risk
from api_galaxy.contracts.graph import KnowledgeGraph
from api_galaxy.contracts.providers import ProviderKind
from api_galaxy.contracts.scenario import Scenario
from api_galaxy.parsing.normalize import NormalizedEstate
from api_galaxy.pipeline import AnalysedProject
from api_galaxy.providers import (
    ComparisonService,
    ConsentStore,
    DeterministicProvider,
    KimiProvider,
    OllamaProvider,
    PricingBook,
    ResultCache,
)
from api_galaxy.providers.comparison import ProviderPricing

DOCUMENTS = {
    "graph": "graph.json",
    "estate": "estate.json",
    "risks": "risks.json",
    "journeys": "journeys.json",
    "aliases": "aliases.json",
    "ambiguities": "ambiguities.json",
    "meta": "meta.json",
}


@dataclass
class LiveProject:
    """An analysed project plus the scenarios currently open against it."""

    analysed: AnalysedProject
    scenarios: dict[str, Scenario] = field(default_factory=dict)

    @property
    def graph(self) -> KnowledgeGraph:
        return self.analysed.graph


class AppState:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.storage = Storage(self.settings)
        self.jobs = JobManager()
        self.cache = ResultCache()
        self.consent = ConsentStore()
        self.pricing = PricingBook(self._load_pricing())
        self.comparison = ComparisonService(self.pricing)
        self._projects: dict[str, LiveProject] = {}

    # -- providers -----------------------------------------------------------------

    def provider_settings(self) -> dict[str, Any]:
        """Runtime overrides from the database win over environment defaults, so Settings
        changes apply without a restart."""
        stored = self.storage.get_setting("providers", {}) or {}
        return {
            "ollama_base_url": stored.get("ollama_base_url", self.settings.ollama_base_url),
            "ollama_model": stored.get("ollama_model", self.settings.ollama_model),
            "ollama_timeout": float(stored.get("ollama_timeout", self.settings.ollama_timeout)),
            "kimi_base_url": stored.get("kimi_base_url", self.settings.kimi_base_url),
            "kimi_model": stored.get("kimi_model", self.settings.kimi_model),
            "kimi_timeout": float(stored.get("kimi_timeout", self.settings.kimi_timeout)),
            "external_providers_enabled": bool(
                stored.get("external_providers_enabled", self.settings.external_providers_enabled)
            ),
        }

    def save_provider_settings(self, values: dict[str, Any]) -> dict[str, Any]:
        current = self.storage.get_setting("providers", {}) or {}
        # An API key is never written here — see `set_kimi_key`.
        current.update({k: v for k, v in values.items() if k != "kimi_api_key" and v is not None})
        self.storage.set_setting("providers", current)
        return self.provider_settings()

    # --- secrets ---------------------------------------------------------------
    #
    # The key is held in memory for the process lifetime and, when `keyring` is
    # available, in the OS keychain. It is never written to SQLite, never written to a
    # file, and never logged.
    _kimi_key_memory: str | None = None

    def set_kimi_key(self, key: str | None) -> dict[str, Any]:
        self._kimi_key_memory = key or None
        stored_in_keychain = False
        try:
            import keyring

            if key:
                keyring.set_password("api-galaxy", "kimi", key)
            else:
                try:
                    keyring.delete_password("api-galaxy", "kimi")
                except Exception:  # noqa: BLE001 - absent entry is not an error
                    pass
            stored_in_keychain = True
        except Exception:  # noqa: BLE001 - keyring is optional
            stored_in_keychain = False
        return {
            "configured": bool(key),
            "stored_in_keychain": stored_in_keychain,
            "note": (
                "Stored in your OS keychain."
                if stored_in_keychain
                else "Held in memory for this session only — `pip install keyring` to persist it "
                "securely."
            ),
        }

    def kimi_key(self) -> str:
        if self._kimi_key_memory:
            return self._kimi_key_memory
        try:
            import keyring

            value = keyring.get_password("api-galaxy", "kimi")
            if value:
                self._kimi_key_memory = value
                return value
        except Exception:  # noqa: BLE001 - keyring is optional
            pass
        return self.settings.kimi_api_key or ""

    def deterministic_provider(self, graph: KnowledgeGraph | None = None) -> DeterministicProvider:
        return DeterministicProvider(graph)

    def ollama_provider(self) -> OllamaProvider:
        values = self.provider_settings()
        return OllamaProvider(
            base_url=values["ollama_base_url"],
            model=values["ollama_model"],
            timeout=values["ollama_timeout"],
        )

    def kimi_provider(self) -> KimiProvider:
        values = self.provider_settings()
        return KimiProvider(
            api_key=self.kimi_key() or None,
            base_url=values["kimi_base_url"],
            model=values["kimi_model"],
            timeout=values["kimi_timeout"],
            enabled=values["external_providers_enabled"],
            consent=self.consent,
        )

    def provider(self, kind: ProviderKind, graph: KnowledgeGraph | None = None):
        if kind is ProviderKind.OLLAMA:
            return self.ollama_provider()
        if kind is ProviderKind.KIMI:
            return self.kimi_provider()
        return self.deterministic_provider(graph)

    # -- pricing -------------------------------------------------------------------

    def _load_pricing(self) -> dict[str, ProviderPricing] | None:
        stored = self.storage.get_setting("pricing")
        if not stored:
            return None
        try:
            return {
                name: ProviderPricing(
                    input_per_million=float(value["input_per_million"]),
                    output_per_million=float(value["output_per_million"]),
                    note=str(value.get("note", "")),
                    updated_by=str(value.get("updated_by", "local-user")),
                    updated_at=str(value.get("updated_at", "")),
                )
                for name, value in stored.items()
            }
        except (KeyError, TypeError, ValueError):
            return None

    def save_pricing(self) -> None:
        self.storage.set_setting("pricing", self.pricing.to_dict())

    # -- projects ------------------------------------------------------------------

    def register(self, project: AnalysedProject, *, is_demo: bool = False,
                 source_kind: str = "upload") -> LiveProject:
        live = LiveProject(analysed=project)
        self._projects[project.project_id] = live
        self.persist(project)
        self.storage.upsert_project(
            id=project.project_id,
            name=project.project_name,
            description=project.estate.description,
            source_kind=source_kind,
            spec_fingerprint=project.fingerprint,
            app_version=__version__,
            enrichment_label=project.enrichment_label,
            is_demo=is_demo,
            stats=project.graph.stats().model_dump(),
        )
        return live

    def persist(self, project: AnalysedProject) -> None:
        write = self.storage.write_document
        write(project.project_id, DOCUMENTS["graph"], project.graph.model_dump(mode="json"))
        write(project.project_id, DOCUMENTS["estate"], project.estate.model_dump(mode="json"))
        write(project.project_id, DOCUMENTS["risks"],
              [r.model_dump(mode="json") for r in project.risks])
        write(project.project_id, DOCUMENTS["journeys"],
              [j.model_dump(mode="json") for j in project.journeys])
        write(project.project_id, DOCUMENTS["aliases"],
              [a.model_dump(mode="json") for a in project.alias_clusters])
        write(project.project_id, DOCUMENTS["ambiguities"],
              [a.model_dump(mode="json") for a in project.ambiguities])
        write(
            project.project_id,
            DOCUMENTS["meta"],
            {
                "project_id": project.project_id,
                "project_name": project.project_name,
                "enrichment_label": project.enrichment_label,
                "enrichment_warnings": project.enrichment_warnings,
                "app_version": __version__,
            },
        )

    def get(self, project_id: str) -> LiveProject | None:
        live = self._projects.get(project_id)
        if live is not None:
            return live
        rehydrated = self._rehydrate(project_id)
        if rehydrated is not None:
            self._projects[project_id] = rehydrated
        return rehydrated

    def _rehydrate(self, project_id: str) -> LiveProject | None:
        directory = Path(self.storage.project_dir(project_id))
        graph_path = directory / DOCUMENTS["graph"]
        if not graph_path.is_file():
            return None
        try:
            graph = KnowledgeGraph.model_validate(json.loads(graph_path.read_text("utf-8")))
            estate = NormalizedEstate.model_validate(
                json.loads((directory / DOCUMENTS["estate"]).read_text("utf-8"))
            )
            risks = [
                Risk.model_validate(r)
                for r in json.loads((directory / DOCUMENTS["risks"]).read_text("utf-8"))
            ]
            journeys = [
                Journey.model_validate(j)
                for j in json.loads((directory / DOCUMENTS["journeys"]).read_text("utf-8"))
            ]
            aliases = [
                AliasCluster.model_validate(a)
                for a in json.loads((directory / DOCUMENTS["aliases"]).read_text("utf-8"))
            ]
            ambiguities = [
                Ambiguity.model_validate(a)
                for a in json.loads((directory / DOCUMENTS["ambiguities"]).read_text("utf-8"))
            ]
            meta = json.loads((directory / DOCUMENTS["meta"]).read_text("utf-8"))
        except (OSError, ValueError, KeyError):
            return None

        analysed = AnalysedProject(
            project_id=project_id,
            project_name=meta.get("project_name", project_id),
            estate=estate,
            graph=graph,
            risks=risks,
            journeys=journeys,
            alias_clusters=aliases,
            ambiguities=ambiguities,
            enrichment_label=meta.get("enrichment_label", "none"),
            enrichment_warnings=meta.get("enrichment_warnings", []),
        )
        live = LiveProject(analysed=analysed)
        for record in self.storage.list_scenarios(project_id):
            try:
                live.scenarios[record["id"]] = Scenario.model_validate(record["payload"])
            except ValueError:
                continue
        return live

    def forget(self, project_id: str) -> None:
        self._projects.pop(project_id, None)

    def project_count(self) -> int:
        return len(self.storage.list_projects())

    def save_scenario(self, project_id: str, scenario: Scenario) -> None:
        live = self.get(project_id)
        if live is None:
            return
        live.scenarios[scenario.id] = scenario
        self.storage.save_scenario(
            scenario.id,
            project_id,
            scenario.name,
            scenario.description,
            scenario.model_dump(mode="json"),
        )


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState()
    return _state


def reset_state() -> None:
    """Used by tests so each module gets a clean data directory."""
    global _state
    _state = None
