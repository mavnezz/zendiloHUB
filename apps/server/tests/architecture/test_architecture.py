"""
Enforces the module and layer boundaries, like deptrac in the Laravel projects:
modules/<module>/{domain,application,infrastructure,ui} + <module>_module.py.
"""

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import zendilohub

SRC = Path(zendilohub.__file__).parent

type Layer = Literal['domain', 'application', 'infrastructure', 'ui', 'module']
type Area = Literal['core-domain', 'core', 'bootstrap'] | Layer

LAYERS: tuple[Layer, ...] = ('domain', 'application', 'infrastructure', 'ui')


@dataclass(frozen=True)
class Location:
    area: str
    """`core`, `app` (bootstrap) or the module's name."""
    layer: Area
    path: str
    """Dotted module path below `zendilohub`, e.g. `modules.identity.domain.models.user`."""


@dataclass(frozen=True)
class Rules:
    own: tuple[Layer, ...]
    core: tuple[Literal['core-domain', 'core'], ...]
    packages: bool
    """Third-party packages; the standard library is always allowed."""


ALLOWED: dict[Layer, Rules] = {
    'domain': Rules(own=('domain',), core=('core-domain',), packages=False),
    'application': Rules(own=('domain', 'application'), core=('core-domain',), packages=False),
    'infrastructure': Rules(
        own=('domain', 'application', 'infrastructure'), core=('core-domain', 'core'), packages=True
    ),
    'ui': Rules(own=('domain', 'application', 'ui'), core=('core-domain', 'core'), packages=True),
    'module': Rules(own=(*LAYERS, 'module'), core=('core-domain', 'core'), packages=True),
}

# Pure, in-process parts of the core the application layer may use.
APPLICATION_CORE = ('core.bus', 'core.events')


def source_files() -> list[Path]:
    return sorted(SRC.rglob('*.py'))


def module_path(file: Path) -> str:
    parts = list(file.relative_to(SRC).with_suffix('').parts)
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def imports_of(file: Path) -> list[str]:
    """Absolute dotted names of everything a file imports (`zendilohub.…` for our own code)."""
    tree = ast.parse(file.read_text('utf-8'))
    dotted = module_path(file).split('.') if file.is_relative_to(SRC) else []
    package = dotted if file.name == '__init__.py' else dotted[:-1]
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                names.append(node.module or '')
                continue
            base = package[: len(package) - (node.level - 1)] if node.level > 1 else package
            target = '.'.join(['zendilohub', *base, *([node.module] if node.module else [])])
            names.append(target)
    return names


def locate(path: str) -> Location:
    parts = path.split('.')
    if parts[0] == 'core':
        return Location('core', 'core-domain' if len(parts) > 1 and parts[1] == 'domain' else 'core', path)
    if parts[0] == 'modules' and len(parts) > 1:
        layer: Area = 'module' if len(parts) == 2 or parts[2] not in LAYERS else parts[2]
        return Location(parts[1], layer, path)
    return Location('app', 'bootstrap', path)


def target(specifier: str) -> Location | None:
    """Resolves an import to a source location, or None for the standard library and packages."""
    if specifier == 'zendilohub' or specifier.startswith('zendilohub.'):
        return locate(specifier.removeprefix('zendilohub').removeprefix('.'))
    return None


def is_stdlib(specifier: str) -> bool:
    return specifier.split('.')[0] in sys.stdlib_module_names


def violations() -> list[str]:
    problems: list[str] = []
    for file in source_files():
        origin = locate(module_path(file))
        for specifier in imports_of(file):
            to = target(specifier)
            where = f'{file.relative_to(SRC)} imports {specifier}'

            if origin.layer == 'core-domain':
                if (to is None and not is_stdlib(specifier)) or (to is not None and to.layer != 'core-domain'):
                    problems.append(f'{where}: the core domain must stay free of other code and packages')
                continue
            if origin.area == 'core':
                if to is not None and to.area != 'core':
                    problems.append(f'{where}: the core must not depend on modules')
                continue
            if origin.layer == 'bootstrap':
                continue

            rules = ALLOWED[origin.layer]  # type: ignore[index]
            if to is None:
                if not rules.packages and not is_stdlib(specifier):
                    problems.append(f'{where}: the {origin.layer} layer must not use packages')
                continue
            if to.area == 'core':
                allowed = to.layer in rules.core or (
                    origin.layer == 'application' and to.path.startswith(APPLICATION_CORE)
                )
                if not allowed:
                    problems.append(f'{where}: the {origin.layer} layer must not use {to.path}')
                continue
            if to.area != origin.area:
                problems.append(f'{where}: modules must not depend on other modules')
                continue
            if to.layer not in rules.own:
                problems.append(f'{where}: the {origin.layer} layer must not use the {to.layer} layer')
    return problems


def test_respects_module_and_layer_boundaries() -> None:
    assert violations() == []


def test_gives_every_module_the_same_structure() -> None:
    for module in sorted(path for path in (SRC / 'modules').iterdir() if path.is_dir() and path.name != '__pycache__'):
        entries = {entry.name for entry in module.iterdir() if entry.name != '__pycache__'}
        assert f'{module.name}_module.py' in entries, module.name
        assert {'domain', 'application'} <= entries, module.name
        assert entries <= {*LAYERS, f'{module.name}_module.py', '__init__.py'}, module.name


def test_detects_violations() -> None:
    # Guard against a checker that silently passes everything.
    assert locate('modules.identity.domain.models.user') == Location(
        'identity', 'domain', 'modules.identity.domain.models.user'
    )
    assert locate('modules.identity.identity_module').layer == 'module'
    assert locate('core.domain.clock').layer == 'core-domain'
    assert locate('core.http.access').layer == 'core'
    assert locate('main').layer == 'bootstrap'
    assert target('fastapi') is None
    assert target('zendilohub.modules.billing.domain.plan') == Location(
        'billing', 'domain', 'modules.billing.domain.plan'
    )
    assert is_stdlib('dataclasses')
    assert not is_stdlib('fastapi')
    assert 'pathlib' in imports_of(Path(__file__))
    assert 'zendilohub.core.domain.app_domain_error' in imports_of(SRC / 'core' / 'http' / 'access.py')
    assert 'zendilohub.core.http.http_kernel' in imports_of(SRC / 'core' / 'application.py')
