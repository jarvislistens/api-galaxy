"""Parser, `$ref` resolution, recursion and diagnostics."""

from __future__ import annotations

import pytest
from api_galaxy.parsing import SpecLoadError, load_spec_text, parse_service
from api_galaxy.parsing.loader import postman_to_openapi
from api_galaxy.parsing.normalize import DiagnosticLevel
from api_galaxy.parsing.refs import UnsafeUrlError, assert_url_is_safe, resolve_pointer

MINIMAL = """
openapi: 3.0.3
info: {title: Tiny, version: "1.0"}
paths:
  /things:
    get:
      operationId: listThings
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema: {type: array, items: {$ref: "#/components/schemas/Thing"}}
              example: []
components:
  schemas:
    Thing:
      type: object
      required: [id]
      properties:
        id: {type: string}
        parent: {$ref: "#/components/schemas/Thing"}
        children: {type: array, items: {$ref: "#/components/schemas/Thing"}}
        nested:
          type: object
          properties:
            tag: {type: string}
"""


def test_parses_a_minimal_document():
    service = parse_service(MINIMAL, source_file="tiny.yaml", service_name="tiny-api")
    assert service.openapi_version == "3.0.3"
    assert [op.operation_id for op in service.operations] == ["listThings"]
    assert service.operations[0].responses[0].schema_ref == "Thing"
    assert service.operations[0].responses[0].is_array is True


def test_recursive_schema_terminates_and_is_flagged():
    """A self-referencing schema must produce one field, not an exponential blow-up."""
    service = parse_service(MINIMAL, service_name="tiny-api")
    thing = service.schema_by_name("Thing")
    assert thing is not None
    assert thing.recursive is True
    paths = [f.dotted_path for f in thing.fields]
    # `parent` is a $ref, so it is an edge, not an inlined subtree.
    assert paths == ["id", "parent", "children", "nested", "nested.tag"]
    assert thing.field_by_path("parent").ref_target == "Thing"
    assert thing.field_by_path("children").array_item_type == "Thing"


def test_inline_objects_are_flattened_with_dotted_paths():
    service = parse_service(MINIMAL, service_name="tiny-api")
    nested = service.schema_by_name("Thing").field_by_path("nested.tag")
    assert nested is not None and nested.type == "string"


def test_required_flag_comes_from_the_schema():
    service = parse_service(MINIMAL, service_name="tiny-api")
    thing = service.schema_by_name("Thing")
    assert thing.field_by_path("id").required is True
    assert thing.field_by_path("parent").required is False


def test_broken_ref_becomes_a_diagnostic_not_an_exception():
    spec = MINIMAL.replace('#/components/schemas/Thing"}\n        children', '#/components/schemas/Missing"}\n        children')
    service = parse_service(spec, service_name="tiny-api")
    codes = {d.code for d in service.diagnostics}
    assert "broken-ref" in codes
    assert any(d.level is DiagnosticLevel.ERROR for d in service.diagnostics)


def test_duplicate_operation_ids_are_reported():
    spec = """
openapi: 3.0.3
info: {title: Dup, version: "1"}
paths:
  /a:
    get: {operationId: same, responses: {"200": {description: ok}}}
  /b:
    get: {operationId: same, responses: {"200": {description: ok}}}
"""
    service = parse_service(spec, service_name="dup-api")
    assert any(d.code == "duplicate-operation-id" for d in service.diagnostics)


def test_security_opt_out_is_distinguished_from_inheritance():
    spec = """
openapi: 3.0.3
info: {title: Sec, version: "1"}
security: [{bearerAuth: []}]
paths:
  /open:
    get: {operationId: open, security: [], responses: {"200": {description: ok}}}
  /closed:
    get: {operationId: closed, responses: {"200": {description: ok}}}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
"""
    service = parse_service(spec, service_name="sec-api")
    opened = service.operation_by_id("open")
    closed = service.operation_by_id("closed")
    assert opened.security == [] and opened.security_declared is True
    assert closed.security == ["bearerAuth"] and closed.security_declared is False
    assert opened.is_public and not closed.is_public


def test_openapi_31_nullable_type_arrays():
    spec = """
openapi: 3.1.0
info: {title: Modern, version: "1"}
paths: {}
components:
  schemas:
    X:
      type: object
      properties:
        maybe: {type: [string, "null"]}
"""
    service = parse_service(spec, service_name="modern-api")
    field = service.schema_by_name("X").field_by_path("maybe")
    assert field.type == "string" and field.nullable is True


def test_webhooks_are_parsed_in_31():
    spec = """
openapi: 3.1.0
info: {title: Hooks, version: "1"}
webhooks:
  orderPlaced:
    post:
      operationId: onOrderPlaced
      responses: {"200": {description: ok}}
"""
    service = parse_service(spec, service_name="hooks-api")
    assert [op.kind for op in service.operations] == ["webhook"]


def test_swagger_2_is_rejected_with_an_actionable_message():
    service = parse_service('{"swagger": "2.0", "info": {}}', source_file="old.json",
                            service_name="old-api")
    error = next(d for d in service.diagnostics if d.code == "unsupported-version")
    assert "swagger2openapi" in error.hint.lower()


def test_pagination_style_detection():
    service = parse_service(
        """
openapi: 3.0.3
info: {title: P, version: "1"}
paths:
  /a: {get: {operationId: a, parameters: [{name: page, in: query, schema: {type: integer}},
        {name: size, in: query, schema: {type: integer}}], responses: {"200": {description: ok}}}}
  /b: {get: {operationId: b, parameters: [{name: limit, in: query, schema: {type: integer}},
        {name: offset, in: query, schema: {type: integer}}], responses: {"200": {description: ok}}}}
  /c: {get: {operationId: c, parameters: [{name: cursor, in: query, schema: {type: string}}],
        responses: {"200": {description: ok}}}}
""",
        service_name="p-api",
    )
    styles = {op.operation_id: op.pagination_style for op in service.operations}
    assert styles == {"a": "page-size", "b": "limit-offset", "c": "cursor"}


# --------------------------------------------------------------------------------------
# Loader
# --------------------------------------------------------------------------------------


def test_yaml_error_carries_a_line_number():
    with pytest.raises(SpecLoadError) as caught:
        load_spec_text("openapi: 3.0.0\npaths: [", source_file="bad.yaml")
    assert caught.value.line is not None
    assert "YAML" in caught.value.message


def test_json_error_carries_a_line_and_column():
    with pytest.raises(SpecLoadError) as caught:
        load_spec_text('{"openapi": "3.0.0",}', source_file="bad.json")
    assert caught.value.line == 1
    assert caught.value.column is not None


def test_empty_document_is_rejected_kindly():
    with pytest.raises(SpecLoadError) as caught:
        load_spec_text("   ", source_file="empty.yaml")
    assert "empty" in caught.value.message.lower()


def test_postman_conversion_recovers_paths_and_methods():
    collection = {
        "info": {"name": "Demo", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/"},
        "item": [
            {
                "name": "Orders",
                "item": [
                    {
                        "name": "Get order",
                        "request": {
                            "method": "GET",
                            "url": {"raw": "{{baseUrl}}/orders/:orderId",
                                    "path": ["orders", ":orderId"], "host": ["api", "example"]},
                        },
                    }
                ],
            }
        ],
    }
    document = postman_to_openapi(collection)
    assert document["openapi"] == "3.0.3"
    assert "/orders/{orderId}" in document["paths"]
    operation = document["paths"]["/orders/{orderId}"]["get"]
    assert operation["tags"] == ["Orders"]
    assert operation["parameters"][0]["name"] == "orderId"


# --------------------------------------------------------------------------------------
# Pointers and SSRF
# --------------------------------------------------------------------------------------


def test_json_pointer_escaping_round_trips():
    document = {"paths": {"/a~b/c": {"get": 1}}}
    assert resolve_pointer(document, "#/paths/~1a~0b~1c/get") == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/spec.yaml",       # http is not allowed
        "https://localhost/spec.yaml",        # loopback by name
        "https://127.0.0.1/spec.yaml",        # loopback by address
        "https://192.168.1.10/spec.yaml",     # private range
        "https://internal.local/spec.yaml",   # blocked suffix
    ],
)
def test_ssrf_guard_refuses_dangerous_urls(url):
    with pytest.raises(UnsafeUrlError):
        assert_url_is_safe(url)
