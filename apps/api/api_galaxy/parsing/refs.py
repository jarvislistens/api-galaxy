"""``$ref`` resolution with cycle protection and SSRF-safe remote handling.

Design notes
------------
* Internal refs (``#/components/schemas/Foo``) are resolved against the document root.
* Recursive schemas are *expected* — a ``Category`` with a ``parent: Category`` is normal.
  We never inline a ref we are already inside; instead we return a marker that records
  the cycle so the graph gets a ``REFERENCES`` edge and the parser stops descending.
* Remote refs (``https://…#/…``) are **off by default**. Enabling them requires explicit
  approval and still refuses private/loopback/link-local hosts.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

MAX_REF_DEPTH = 24


class RefResolutionError(ValueError):
    def __init__(self, ref: str, reason: str) -> None:
        super().__init__(f"Cannot resolve '{ref}': {reason}")
        self.ref = ref
        self.reason = reason


@dataclass
class ResolvedRef:
    ref: str
    pointer: str
    value: Any
    component_kind: str | None = None  # "schemas" | "parameters" | "responses" | …
    component_name: str | None = None
    cyclic: bool = False


def unescape_pointer_segment(segment: str) -> str:
    return segment.replace("~1", "/").replace("~0", "~")


def escape_pointer_segment(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def resolve_pointer(root: Any, pointer: str) -> Any:
    """RFC 6901 pointer resolution. Raises KeyError/IndexError on a bad path."""
    if pointer in ("", "#"):
        return root
    if pointer.startswith("#"):
        pointer = pointer[1:]
    if not pointer.startswith("/"):
        raise RefResolutionError(pointer, "JSON Pointer must start with '/'")
    current = root
    for raw in pointer.split("/")[1:]:
        segment = unescape_pointer_segment(raw)
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError) as exc:
                raise RefResolutionError(pointer, f"no array index '{segment}'") from exc
        elif isinstance(current, dict):
            if segment not in current:
                raise RefResolutionError(pointer, f"no key '{segment}'")
            current = current[segment]
        else:
            raise RefResolutionError(pointer, f"cannot descend into {type(current).__name__}")
    return current


class RefResolver:
    """Resolves refs against one document root, tracking the active resolution stack."""

    def __init__(
        self,
        root: dict[str, Any],
        *,
        source_file: str = "spec.yaml",
        allow_remote: bool = False,
    ) -> None:
        self.root = root
        self.source_file = source_file
        self.allow_remote = allow_remote
        self.broken: list[dict[str, str]] = []
        self._stack: list[str] = []

    # -- public API ---------------------------------------------------------------

    def is_ref(self, node: Any) -> bool:
        return isinstance(node, dict) and isinstance(node.get("$ref"), str)

    def component_name(self, ref: str) -> tuple[str | None, str | None]:
        """('schemas', 'Customer') for '#/components/schemas/Customer'."""
        return _component_of(ref)

    def resolve(self, ref: str, *, pointer_hint: str = "") -> ResolvedRef:
        if ref.startswith("#"):
            kind, name = _component_of(ref)
            if ref in self._stack:
                return ResolvedRef(ref=ref, pointer=ref, value=None, component_kind=kind,
                                   component_name=name, cyclic=True)
            if len(self._stack) >= MAX_REF_DEPTH:
                raise RefResolutionError(ref, f"exceeded max $ref depth of {MAX_REF_DEPTH}")
            try:
                value = resolve_pointer(self.root, ref)
            except RefResolutionError as exc:
                self.broken.append(
                    {"ref": ref, "reason": exc.reason, "at": pointer_hint, "file": self.source_file}
                )
                raise
            return ResolvedRef(ref=ref, pointer=ref, value=value, component_kind=kind,
                               component_name=name)

        # Remote / relative refs
        if not self.allow_remote:
            self.broken.append(
                {
                    "ref": ref,
                    "reason": "remote references are disabled",
                    "at": pointer_hint,
                    "file": self.source_file,
                }
            )
            raise RefResolutionError(ref, "remote references are disabled for this import")
        assert_url_is_safe(ref.split("#", 1)[0])
        raise RefResolutionError(ref, "remote reference fetching is not implemented")

    def enter(self, ref: str) -> None:
        self._stack.append(ref)

    def leave(self) -> None:
        if self._stack:
            self._stack.pop()

    def in_progress(self, ref: str) -> bool:
        return ref in self._stack

    def deref(self, node: Any, *, pointer_hint: str = "") -> tuple[Any, ResolvedRef | None]:
        """Return (value, resolved) — ``resolved`` is None when ``node`` was not a ref."""
        if not self.is_ref(node):
            return node, None
        ref = node["$ref"]
        try:
            resolved = self.resolve(ref, pointer_hint=pointer_hint)
        except RefResolutionError:
            return None, None
        if resolved.cyclic:
            return None, resolved
        return resolved.value, resolved


def _component_of(ref: str) -> tuple[str | None, str | None]:
    """'#/components/schemas/Customer' → ('schemas', 'Customer').

    Note the segment count: splitting on '/' yields ['#', 'components', <kind>, <name>],
    i.e. exactly four parts for a well-formed component reference.
    """
    if not ref.startswith("#/components/"):
        return None, None
    parts = [unescape_pointer_segment(p) for p in ref.split("/")]
    if len(parts) < 4:
        return None, None
    return parts[2], parts[3]


# --------------------------------------------------------------------------------------
# SSRF protection for the (optional) "import from URL" path
# --------------------------------------------------------------------------------------

BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".localdomain")


@dataclass
class UrlPolicy:
    allow_private_networks: bool = False
    allowed_schemes: tuple[str, ...] = ("https",)
    blocked_ports: frozenset[int] = field(default_factory=lambda: frozenset({22, 23, 25, 3306,
                                                                             5432, 6379, 9200,
                                                                             11434, 27017}))


class UnsafeUrlError(ValueError):
    pass


def assert_url_is_safe(url: str, policy: UrlPolicy | None = None) -> str:
    """Reject URLs that could be used to reach the machine's own network.

    Checks scheme, host shape, port, and — crucially — every IP the host resolves to,
    so ``http://evil.example`` pointing at ``127.0.0.1`` is still refused.
    """
    policy = policy or UrlPolicy()
    parts = urlsplit(url)
    if parts.scheme not in policy.allowed_schemes:
        raise UnsafeUrlError(
            f"Only {'/'.join(policy.allowed_schemes)} URLs are allowed (got '{parts.scheme}')."
        )
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("URL has no host.")
    if parts.port and parts.port in policy.blocked_ports:
        raise UnsafeUrlError(f"Port {parts.port} is not allowed.")
    lowered = host.lower()
    if lowered in ("localhost", "0.0.0.0", "::1") or lowered.endswith(BLOCKED_HOST_SUFFIXES):
        if not policy.allow_private_networks:
            raise UnsafeUrlError(f"Host '{host}' is a local address; local access is disabled.")

    addresses: list[str] = []
    try:
        infos = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80))
        addresses = sorted({info[4][0] for info in infos})
    except OSError as exc:
        raise UnsafeUrlError(f"Could not resolve host '{host}': {exc}") from exc

    if not addresses:
        raise UnsafeUrlError(f"Host '{host}' resolved to no addresses.")

    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:  # pragma: no cover - getaddrinfo always yields valid IPs
            raise UnsafeUrlError(f"Host '{host}' resolved to an unparseable address.") from None
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ) and not policy.allow_private_networks:
            raise UnsafeUrlError(
                f"Host '{host}' resolves to the private address {address}; "
                "local-network access is disabled by default."
            )
    return url
