"""
The public API reference: what other systems may call with an organization's API key, and nothing else. The full
schema (`/api/openapi.json`, for the web app) also has the account and the platform routes.
"""

from collections.abc import Callable, Iterable
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute

PUBLIC_PREFIXES = ('/api/v1/tenants/{tenant_id}',)

DESCRIPTION = """
The API of a zendiloHUB organization: its team, audit log and, as they arrive, its queues and tickets.

**Authentication.** Create an API key on the page *API keys* and send it as `Authorization: Bearer zhk_…`.
A key has the permissions it was given (a request beyond them gets `403 permission_denied`), in its organization
only, at most 600 requests a minute. Every path starts with `/api/v1/tenants/{tenant_id}`; the organization's id is
in the address of the web app, and `GET` on that path shows what the key may do.
""".strip()


def _uses(dependant: Dependant, policy: Callable[..., Any]) -> bool:
    return dependant.call is policy or any(_uses(each, policy) for each in dependant.dependencies)


def public_operations(routes: Iterable[Any], prefix: str, people_only: Callable[..., Any]) -> set[tuple[str, str]]:
    """(path, method) of the routes an API key can use, among a router's routes mounted below `prefix`."""
    operations: set[tuple[str, str]] = set()
    for route in routes:
        if not isinstance(route, APIRoute) or not route.include_in_schema:
            continue
        path = prefix + route.path
        if not path.startswith(PUBLIC_PREFIXES) or _uses(route.dependant, people_only):
            continue
        operations.update((path, method.lower()) for method in route.methods or ())
    return operations


def _references(value: Any) -> set[str]:
    if isinstance(value, dict):
        found = {value['$ref'].rsplit('/', 1)[-1]} if isinstance(value.get('$ref'), str) else set()
        return found.union(*(_references(each) for each in value.values()))
    if isinstance(value, list):
        return set().union(*(_references(each) for each in value))
    return set()


def public_schema(full: dict[str, Any], operations: set[tuple[str, str]]) -> dict[str, Any]:
    """The full OpenAPI schema with only the public operations and the schemas they use."""
    paths: dict[str, Any] = {}
    for path, item in full.get('paths', {}).items():
        kept = {method: operation for method, operation in item.items() if (path, method) in operations}
        if kept:
            paths[path] = kept
    components = full.get('components', {})
    schemas = components.get('schemas', {})
    needed: set[str] = set()
    pending = _references(paths)
    while pending:
        name = pending.pop()
        if name in needed or name not in schemas:
            continue
        needed.add(name)
        pending |= _references(schemas[name])
    return {
        **full,
        'info': {**full.get('info', {}), 'title': 'zendiloHUB API', 'description': DESCRIPTION},
        'paths': paths,
        'components': {
            **components,
            'schemas': {name: schema for name, schema in schemas.items() if name in needed},
        },
    }
