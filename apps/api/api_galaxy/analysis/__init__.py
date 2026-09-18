"""Deterministic analysis: risks, aliases, journeys and change impact."""

from api_galaxy.analysis.aliases import detect_alias_clusters, looks_like_identifier
from api_galaxy.analysis.impact import (
    ASSUMPTIONS,
    LIMITATIONS,
    apply_changes,
    attach_impact_to_graph,
    compute_impact,
    propose_deterministic_repairs,
)
from api_galaxy.analysis.journeys import (
    attach_journeys_to_graph,
    derive_journeys,
    validate_all,
    validate_journey,
)
from api_galaxy.analysis.pii import DEFAULT_DICTIONARY, PiiDictionary
from api_galaxy.analysis.rules import RULE_CATALOG, attach_risks_to_graph, run_rules

__all__ = [
    "ASSUMPTIONS",
    "DEFAULT_DICTIONARY",
    "LIMITATIONS",
    "PiiDictionary",
    "RULE_CATALOG",
    "apply_changes",
    "attach_impact_to_graph",
    "attach_journeys_to_graph",
    "attach_risks_to_graph",
    "compute_impact",
    "derive_journeys",
    "detect_alias_clusters",
    "looks_like_identifier",
    "propose_deterministic_repairs",
    "run_rules",
    "validate_all",
    "validate_journey",
]
