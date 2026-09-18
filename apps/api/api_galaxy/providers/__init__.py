"""Semantic providers: deterministic, Ollama (default), Kimi (optional, consented)."""

from api_galaxy.providers.base import (
    ProviderError,
    SchemaViolation,
    SemanticProvider,
    StructuredCall,
    extract_json,
    filter_references,
    validate_against,
)
from api_galaxy.providers.cache import CacheKey, ResultCache, context_fingerprint
from api_galaxy.providers.comparison import (
    DEFAULT_PRICING,
    ArenaRun,
    ComparisonService,
    PricingBook,
    ProviderPricing,
)
from api_galaxy.providers.context import (
    build_context,
    chunk_by_domain,
    context_for_question,
)
from api_galaxy.providers.deterministic import DeterministicProvider
from api_galaxy.providers.kimi import ConsentRequired, ConsentStore, KimiProvider
from api_galaxy.providers.ollama import OllamaProvider
from api_galaxy.providers.sanitizer import (
    ExternalRequestPreview,
    SanitizationReport,
    build_preview,
    payload_fingerprint,
    sanitize,
    sanitize_text,
)

__all__ = [
    "DEFAULT_PRICING",
    "ArenaRun",
    "CacheKey",
    "ComparisonService",
    "ConsentRequired",
    "ConsentStore",
    "DeterministicProvider",
    "ExternalRequestPreview",
    "KimiProvider",
    "OllamaProvider",
    "PricingBook",
    "ProviderError",
    "ProviderPricing",
    "ResultCache",
    "SanitizationReport",
    "SchemaViolation",
    "SemanticProvider",
    "StructuredCall",
    "build_context",
    "build_preview",
    "chunk_by_domain",
    "context_fingerprint",
    "context_for_question",
    "extract_json",
    "filter_references",
    "payload_fingerprint",
    "sanitize",
    "sanitize_text",
    "validate_against",
]
