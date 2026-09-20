"""Write-back: turn a Break Lab scenario into a diff against the original documents.

Until this existed, a scenario produced a decision and a checklist but nothing you could
apply. You knew a rename broke two journeys; you still had to go and make the edit by
hand. This closes that gap — the same change, expressed as a patch you can review.

Why the edits are textual, not structural
-----------------------------------------
The obvious implementation is: parse the YAML, mutate the dict, dump it back. That
produces a correct document and a *useless* diff — the dumper reorders keys, drops every
comment, normalises quoting, and rewrites block scalars, so a one-word rename shows up as
"±400 lines". Nobody reviews that.

So we edit the original text in place instead. ``yaml.compose`` gives a node tree where
every key and value carries its exact line and column, which is enough to find the one
token a change refers to and replace only that. Comments, ordering and formatting survive,
and the diff is the size of the change.

JSON inputs fall back to a structural rewrite, because ``json`` exposes no marks. JSON has
no comments to lose, but key order and indentation are normalised — the diff is honest,
just larger. That is reported rather than hidden.
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from api_galaxy.contracts.graph import KnowledgeGraph
from api_galaxy.contracts.scenario import Change, ChangeKind, RepairStatus, Scenario
from api_galaxy.parsing.normalize import NormalizedEstate, NormalizedService

# Change kinds that correspond to an edit in a specification document. The rest — a
# simulated outage, added latency, moving an entity between domains — are statements
# about the model, not about the file, and are reported as such rather than faked.
DOCUMENT_CHANGES = frozenset(
    {
        ChangeKind.RENAME_FIELD,
        ChangeKind.REMOVE_FIELD,
        ChangeKind.CHANGE_FIELD_TYPE,
        ChangeKind.SET_FIELD_REQUIRED,
        ChangeKind.REMOVE_ENDPOINT,
        ChangeKind.DEPRECATE_ENDPOINT,
    }
)

# An applied repair of this kind cancels the change it was proposed for, so the diff
# should come out empty rather than showing a change the user has already undone.
REVERTING_REPAIRS = frozenset(
    {"restore_field_name", "restore_type", "restore_field", "restore_endpoint"}
)


class WriteBackError(RuntimeError):
    pass


@dataclass
class Span:
    """Where something sits in the original text."""

    start_line: int  # 0-based, inclusive
    end_line: int  # 0-based, inclusive
    key_line: int | None = None
    key_column: int | None = None
    indent: int = 0


@dataclass
class FileDiff:
    filename: str
    original: str
    modified: str
    applied: list[str] = field(default_factory=list)
    valid: bool = True
    validation_errors: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original != self.modified

    def unified(self, *, context: int = 3) -> str:
        if not self.changed:
            return ""
        return "".join(
            difflib.unified_diff(
                self.original.splitlines(keepends=True),
                self.modified.splitlines(keepends=True),
                fromfile=f"a/{self.filename}",
                tofile=f"b/{self.filename}",
                n=context,
            )
        )


@dataclass
class WriteBackResult:
    files: list[FileDiff] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reformatted: list[str] = field(default_factory=list)

    @property
    def changed_files(self) -> list[FileDiff]:
        return [f for f in self.files if f.changed]

    def patch(self, *, context: int = 3) -> str:
        return "".join(f.unified(context=context) for f in self.changed_files)

    def summary(self) -> str:
        if not self.changed_files:
            if self.skipped:
                return (
                    "No document changes. "
                    + "; ".join(self.skipped[:3])
                    + ("…" if len(self.skipped) > 3 else "")
                )
            return "No document changes."
        added = sum(
            1
            for f in self.changed_files
            for line in f.unified().splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        removed = sum(
            1
            for f in self.changed_files
            for line in f.unified().splitlines()
            if line.startswith("-") and not line.startswith("---")
        )
        return (
            f"{len(self.changed_files)} file(s) changed, "
            f"{added} insertion(s), {removed} deletion(s)"
        )


# --------------------------------------------------------------------------------------
# Locating a JSON Pointer in the original YAML text
# --------------------------------------------------------------------------------------


def _escape(segment: str) -> str:
    return segment.replace("~", "~0").replace("/", "~1")


def index_spans(text: str) -> dict[str, Span]:
    """Map every JSON Pointer in a YAML document to its line span in the source text.

    ``yaml.compose`` keeps the marks that ``yaml.safe_load`` throws away. We record both
    the value span and the *key token* position, because a rename has to rewrite the key
    and nothing else on that line.
    """
    try:
        root = yaml.compose(text)
    except yaml.YAMLError as exc:  # pragma: no cover - the parser rejects these earlier
        raise WriteBackError(f"Could not re-read the document to locate edits: {exc}") from exc
    if root is None:
        return {}

    lines = text.splitlines()
    spans: dict[str, Span] = {}

    def line_indent(index: int) -> int:
        if 0 <= index < len(lines):
            stripped = lines[index].lstrip()
            return len(lines[index]) - len(stripped)
        return 0

    def walk(node: yaml.Node, pointer: str, fallback_end: int) -> None:
        start = node.start_mark.line
        end = min(node.end_mark.line, len(lines) - 1)
        # PyYAML's end_mark for a block collection points at the first line *after* it,
        # so trailing blank lines and the next sibling get swallowed without this.
        while end > start and not lines[end].strip():
            end -= 1
        spans.setdefault(pointer, Span(start, max(start, end), indent=line_indent(start)))

        if isinstance(node, yaml.MappingNode):
            children = node.value
            for position, (key_node, value_node) in enumerate(children):
                key = str(key_node.value)
                child_pointer = f"{pointer}/{_escape(key)}"
                # An entry runs from its key line to just before the next sibling's key.
                if position + 1 < len(children):
                    entry_end = children[position + 1][0].start_mark.line - 1
                else:
                    entry_end = fallback_end
                while entry_end > key_node.start_mark.line and not lines[entry_end].strip():
                    entry_end -= 1
                spans[child_pointer] = Span(
                    start_line=key_node.start_mark.line,
                    end_line=max(key_node.start_mark.line, entry_end),
                    key_line=key_node.start_mark.line,
                    key_column=key_node.start_mark.column,
                    indent=line_indent(key_node.start_mark.line),
                )
                walk(value_node, child_pointer, entry_end)
        elif isinstance(node, yaml.SequenceNode):
            children = node.value
            for position, item in enumerate(children):
                if position + 1 < len(children):
                    entry_end = children[position + 1].start_mark.line - 1
                else:
                    entry_end = fallback_end
                child_pointer = f"{pointer}/{position}"
                spans[child_pointer] = Span(
                    start_line=item.start_mark.line,
                    end_line=max(item.start_mark.line, entry_end),
                    indent=line_indent(item.start_mark.line),
                )
                walk(item, child_pointer, entry_end)

    walk(root, "", len(lines) - 1)
    return spans


# --------------------------------------------------------------------------------------
# Per-service editing
# --------------------------------------------------------------------------------------


class SpecEditor:
    """Applies changes to one document's text, keeping everything else byte-identical."""

    def __init__(self, service: NormalizedService) -> None:
        if not service.source_text:
            raise WriteBackError(
                f"{service.source_file} was imported before write-back existed, so its "
                "original text was not kept. Re-import the project to enable the patch."
            )
        self.service = service
        self.original = service.source_text
        self.lines = self.original.splitlines()
        self.is_json = self.original.lstrip().startswith(("{", "["))
        self.spans = {} if self.is_json else index_spans(self.original)
        self.applied: list[str] = []
        self.warnings: list[str] = []
        # Deleting lines shifts everything below, so edits are collected and applied in
        # one pass from the bottom of the file upwards.
        self._deletions: list[Span] = []
        self._replacements: dict[int, str] = {}
        self._insertions: dict[int, list[str]] = {}

    # -- edit primitives -----------------------------------------------------------

    def _replace_on_line(self, index: int, old: str, new: str) -> bool:
        current = self._replacements.get(index, self.lines[index])
        if old not in current:
            return False
        self._replacements[index] = current.replace(old, new, 1)
        return True

    def _delete(self, span: Span) -> None:
        self._deletions.append(span)

    def _insert_after(self, index: int, text: str) -> None:
        self._insertions.setdefault(index, []).append(text)

    def render(self) -> str:
        out = list(self.lines)
        for index, replacement in self._replacements.items():
            out[index] = replacement
        for index, additions in sorted(self._insertions.items(), reverse=True):
            for addition in reversed(additions):
                out.insert(index + 1, addition)
        for span in sorted(self._deletions, key=lambda s: s.start_line, reverse=True):
            del out[span.start_line : span.end_line + 1]
        trailing = "\n" if self.original.endswith("\n") else ""
        return "\n".join(out) + trailing

    # -- change kinds --------------------------------------------------------------

    def rename_field(self, pointer: str, old: str, new: str, schema_pointer: str) -> bool:
        span = self.spans.get(pointer)
        if span is None or span.key_line is None:
            self.warnings.append(f"Could not locate '{old}' at {pointer}.")
            return False
        if not self._replace_on_line(span.key_line, f"{old}:", f"{new}:"):
            self.warnings.append(f"'{old}' was not on the line its pointer claims.")
            return False
        self.applied.append(f"renamed {old} → {new}")
        self._rewrite_required_entry(schema_pointer, old, new)
        return True

    def remove_field(self, pointer: str, name: str, schema_pointer: str) -> bool:
        span = self.spans.get(pointer)
        if span is None:
            self.warnings.append(f"Could not locate '{name}' at {pointer}.")
            return False
        self._delete(span)
        self.applied.append(f"removed {name}")
        self._rewrite_required_entry(schema_pointer, name, None)
        return True

    def change_field_type(self, pointer: str, name: str, new_type: str) -> bool:
        type_span = self.spans.get(f"{pointer}/type")
        if type_span is None or type_span.key_line is None:
            self.warnings.append(f"'{name}' has no inline 'type:' to change.")
            return False
        line = self.lines[type_span.key_line]
        indent = " " * type_span.indent
        self._replacements[type_span.key_line] = f"{indent}type: {new_type}"
        if line.strip() != f"type: {new_type}":
            self.applied.append(f"{name}: type → {new_type}")
        return True

    def set_deprecated(self, pointer: str, label: str) -> bool:
        span = self.spans.get(pointer)
        if span is None:
            self.warnings.append(f"Could not locate {label} at {pointer}.")
            return False
        if self.spans.get(f"{pointer}/deprecated") is not None:
            existing = self.spans[f"{pointer}/deprecated"]
            if existing.key_line is not None:
                indent = " " * existing.indent
                self._replacements[existing.key_line] = f"{indent}deprecated: true"
                self.applied.append(f"{label}: deprecated → true")
                return True
        # Insert immediately under the operation key, at the indent of its first child.
        child_indent = span.indent + 2
        for index in range(span.start_line + 1, min(span.end_line + 1, len(self.lines))):
            if self.lines[index].strip():
                child_indent = len(self.lines[index]) - len(self.lines[index].lstrip())
                break
        self._insert_after(span.start_line, f"{' ' * child_indent}deprecated: true")
        self.applied.append(f"{label}: marked deprecated")
        return True

    def remove_operation(self, pointer: str, label: str) -> bool:
        span = self.spans.get(pointer)
        if span is None:
            self.warnings.append(f"Could not locate {label} at {pointer}.")
            return False
        self._delete(span)
        self.applied.append(f"removed {label}")
        return True

    def set_required(self, schema_pointer: str, name: str, required: bool) -> bool:
        required_span = self.spans.get(f"{schema_pointer}/required")
        if required:
            if self._find_required_entry(schema_pointer, name) is not None:
                return False
            if required_span is None:
                self.warnings.append(
                    f"'{name}' cannot be made required: the schema declares no 'required:' list."
                )
                return False
            if self._is_flow_sequence(schema_pointer):
                line_index = required_span.start_line
                current = self._replacements.get(line_index, self.lines[line_index])
                self._replacements[line_index] = current.replace("]", f", {name}]", 1)
                self.applied.append(f"{name}: now required")
                return True
            indent = " " * (required_span.indent + 2)
            self._insert_after(required_span.start_line, f"{indent}- {name}")
            self.applied.append(f"{name}: now required")
            return True
        if self._is_flow_sequence(schema_pointer):
            self._rewrite_required_entry(schema_pointer, name, None)
            return True
        entry = self._find_required_entry(schema_pointer, name)
        if entry is None:
            return False
        self._delete(entry)
        self.applied.append(f"{name}: no longer required")
        return True

    # -- helpers -------------------------------------------------------------------

    def _is_flow_sequence(self, schema_pointer: str) -> bool:
        """True for `required: [a, b, c]` rather than a block list of `- a` lines.

        Both are legal YAML and both appear in real specifications. A flow sequence puts
        every item on one line, so its entries cannot be deleted or rewritten by line —
        they have to be edited as tokens within that line.
        """
        span = self.spans.get(f"{schema_pointer}/required")
        if span is None:
            return False
        return "[" in self.lines[span.start_line]

    def _find_required_entry(self, schema_pointer: str, name: str) -> Span | None:
        index = 0
        while True:
            span = self.spans.get(f"{schema_pointer}/required/{index}")
            if span is None:
                return None
            text = self.lines[span.start_line].strip().lstrip("-").strip().strip("'\",")
            if text == name:
                return span
            index += 1

    def _rewrite_required_entry(self, schema_pointer: str, old: str, new: str | None) -> None:
        """Keep the schema's ``required:`` list consistent with a rename or a removal.

        Skipping this emits a patch that renames a property while leaving `required:`
        pointing at a name that no longer exists — a document that no longer validates.
        """
        required_span = self.spans.get(f"{schema_pointer}/required")
        if required_span is None:
            return

        if self._is_flow_sequence(schema_pointer):
            line_index = required_span.start_line
            current = self._replacements.get(line_index, self.lines[line_index])
            if not re.search(rf"(?<![\w-]){re.escape(old)}(?![\w-])", current):
                return
            if new is None:
                # Drop the item and exactly one adjacent separator, so the list stays valid.
                updated = re.sub(
                    rf"(?<![\w-]){re.escape(old)}(?![\w-])\s*,\s*|,\s*(?<![\w-]){re.escape(old)}(?![\w-])",
                    "",
                    current,
                    count=1,
                )
                self.applied.append(f"removed {old} from required")
            else:
                updated = re.sub(
                    rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, current, count=1
                )
                self.applied.append(f"required: {old} → {new}")
            self._replacements[line_index] = updated
            return

        entry = self._find_required_entry(schema_pointer, old)
        if entry is None:
            return
        if new is None:
            self._delete(entry)
            self.applied.append(f"removed {old} from required")
        else:
            self._replace_on_line(entry.start_line, old, new)
            self.applied.append(f"required: {old} → {new}")


# --------------------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------------------


def _effective_changes(scenario: Scenario) -> tuple[list[Change], list[str]]:
    """Drop changes an applied repair has already undone."""
    reverted: set[str] = set()
    notes: list[str] = []
    for repair in scenario.repairs:
        if repair.status is not RepairStatus.APPLIED or repair.kind not in REVERTING_REPAIRS:
            continue
        for target in repair.target_ids:
            reverted.add(target)
        notes.append(f"'{repair.title}' was applied, so its change is not in this patch.")
    remaining = [c for c in scenario.changes if c.target_id not in reverted]
    return remaining, notes


def generate_writeback(
    estate: NormalizedEstate,
    graph: KnowledgeGraph,
    scenario: Scenario,
) -> WriteBackResult:
    """Produce the modified documents and the diff for a scenario."""
    result = WriteBackResult()
    changes, notes = _effective_changes(scenario)
    result.warnings.extend(notes)

    index = graph.node_index()
    by_service: dict[str, list[tuple[Change, Any]]] = {}

    for change in changes:
        node = index.get(change.target_id)
        if change.kind not in DOCUMENT_CHANGES:
            result.skipped.append(
                f"{change.describe()} — simulated behaviour, not a document edit"
            )
            continue
        if node is None or not node.provenance.source_file:
            result.skipped.append(f"{change.describe()} — no source location recorded")
            continue
        by_service.setdefault(node.provenance.source_file, []).append((change, node))

    for service in estate.services:
        pending = by_service.get(service.source_file)
        if not pending:
            continue
        try:
            editor = SpecEditor(service)
        except WriteBackError as exc:
            result.warnings.append(str(exc))
            continue

        if editor.is_json:
            modified = _apply_structurally(service, pending)
            result.reformatted.append(service.source_file)
            result.warnings.append(
                f"{service.source_file} is JSON, which carries no source marks, so it was "
                "rewritten structurally. The change is correct; the diff is larger than "
                "it needs to be because key order and indentation are normalised."
            )
        else:
            for change, node in pending:
                _apply_one(editor, change, node)
            modified = editor.render()
            result.warnings.extend(editor.warnings)

        valid, errors = _validate(service.source_file, modified)
        if not valid:
            result.warnings.append(
                f"{service.source_file}: the edit did not produce a valid document, so it "
                "is reported rather than offered as a patch. " + "; ".join(errors[:2])
            )
        result.files.append(
            FileDiff(
                filename=service.source_file,
                original=service.source_text,
                modified=modified,
                applied=list(editor.applied),
                valid=valid,
                validation_errors=errors,
            )
        )

    return result


def _validate(filename: str, text: str) -> tuple[bool, list[str]]:
    """Re-parse the edited document. A patch that does not parse is worse than none.

    This is the gate that makes write-back safe to hand to someone: the same parser that
    read the original has to accept the result, and every name in a `required:` list has
    to still exist as a property.
    """
    from api_galaxy.parsing.loader import SpecLoadError, load_spec_text
    from api_galaxy.parsing.normalize import DiagnosticLevel
    from api_galaxy.parsing.openapi import OpenAPIParser

    errors: list[str] = []
    try:
        document = load_spec_text(text, source_file=filename)
    except SpecLoadError as exc:
        return False, [f"no longer parses: {exc.message}"]

    service = OpenAPIParser(document, service_name=filename).parse()
    errors.extend(
        f"{d.code}: {d.message}"
        for d in service.diagnostics
        if d.level is DiagnosticLevel.ERROR
    )

    for schema in service.schemas:
        declared = {f.name for f in schema.fields if "." not in f.dotted_path}
        for name in schema.required:
            if name not in declared:
                errors.append(
                    f"{schema.name}: 'required' lists '{name}', which is not a property"
                )

    return not errors, errors


def _apply_one(editor: SpecEditor, change: Change, node: Any) -> None:
    pointer = node.provenance.source_pointer or ""
    attrs = node.attrs or {}

    if change.kind is ChangeKind.RENAME_FIELD:
        old = str(attrs.get("name") or node.label.split(".")[-1])
        new = str(change.params.get("new_name") or f"{old}_v2")
        editor.rename_field(pointer, old, new, _schema_pointer(pointer))

    elif change.kind is ChangeKind.REMOVE_FIELD:
        name = str(attrs.get("name") or node.label.split(".")[-1])
        editor.remove_field(pointer, name, _schema_pointer(pointer))

    elif change.kind is ChangeKind.CHANGE_FIELD_TYPE:
        name = str(attrs.get("name") or node.label)
        editor.change_field_type(pointer, name, str(change.params.get("new_type", "string")))

    elif change.kind is ChangeKind.SET_FIELD_REQUIRED:
        name = str(attrs.get("name") or node.label.split(".")[-1])
        editor.set_required(
            _schema_pointer(pointer), name, bool(change.params.get("required", True))
        )

    elif change.kind is ChangeKind.DEPRECATE_ENDPOINT:
        editor.set_deprecated(pointer, node.label)

    elif change.kind is ChangeKind.REMOVE_ENDPOINT:
        editor.remove_operation(pointer, node.label)


def _schema_pointer(field_pointer: str) -> str:
    """'/components/schemas/Customer/properties/customer_id' → the schema's pointer."""
    marker = "/properties/"
    position = field_pointer.rfind(marker)
    return field_pointer[:position] if position != -1 else field_pointer


def _apply_structurally(service: NormalizedService, pending: list[tuple[Change, Any]]) -> str:
    """JSON fallback: mutate the parsed document and re-serialise."""
    document = json.loads(service.source_text)

    for change, node in pending:
        pointer = (node.provenance.source_pointer or "").strip("/")
        if not pointer:
            continue
        parts = [p.replace("~1", "/").replace("~0", "~") for p in pointer.split("/")]
        parent: Any = document
        for part in parts[:-1]:
            if isinstance(parent, list):
                parent = parent[int(part)]
            else:
                parent = parent.get(part, {})
        leaf = parts[-1]
        if not isinstance(parent, dict) or leaf not in parent:
            continue

        if change.kind is ChangeKind.RENAME_FIELD:
            new = str(change.params.get("new_name") or f"{leaf}_v2")
            parent[new] = parent.pop(leaf)
        elif change.kind is ChangeKind.REMOVE_FIELD:
            parent.pop(leaf, None)
        elif change.kind is ChangeKind.CHANGE_FIELD_TYPE:
            if isinstance(parent[leaf], dict):
                parent[leaf]["type"] = change.params.get("new_type", "string")
        elif change.kind is ChangeKind.DEPRECATE_ENDPOINT:
            if isinstance(parent[leaf], dict):
                parent[leaf]["deprecated"] = True
        elif change.kind is ChangeKind.REMOVE_ENDPOINT:
            parent.pop(leaf, None)

    return json.dumps(document, indent=2) + ("\n" if service.source_text.endswith("\n") else "")
