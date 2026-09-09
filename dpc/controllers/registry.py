"""Self-declaration, so a new control law needs no UI changes.

A controller states what it is called and what knobs it has. The dashboard reads
that and builds the widgets. Without this the folder-drop promise would be
false: every new law would need dashboard code written for it.

This module lives with the controllers rather than with the UI on purpose.
Controllers declare their own parameters, so putting the declaration in the UI
package would make dpc/controllers -- the code destined for the MCU -- import
from host-only code.
"""

import importlib
import pkgutil
from dataclasses import dataclass


@dataclass(frozen=True)
class ParamSpec:
    """One tunable number, described well enough to build a widget from."""

    name: str
    """Constructor keyword this value is passed as."""

    label: str
    """Human wording for the widget."""

    unit: str
    """Shown beside the value. Empty string for dimensionless."""

    default: float
    lo: float
    hi: float
    step: float = 0.1
    """Increment for one click of a spin box."""


@dataclass(frozen=True)
class Entry:
    """A discovered controller, or a module that failed to import."""

    key: str
    label: str
    cls: type | None = None
    params: tuple[ParamSpec, ...] = ()
    error: str | None = None
    """Import failure message. When set, cls is None and the entry is shown
    disabled rather than silently dropped."""


_REGISTRY: dict[str, Entry] = {}


def register(label: str, key: str | None = None):
    """Class decorator.

    `key` defaults to the class name minus a trailing 'Controller', lowercased,
    so ConstantController becomes 'constant'.
    """
    def wrap(cls):
        k = key or cls.__name__.removesuffix("Controller").lower()
        _REGISTRY[k] = Entry(key=k, label=label, cls=cls,
                             params=tuple(getattr(cls, "PARAMS", ())))
        return cls
    return wrap


def discover() -> tuple[Entry, ...]:
    """Import every module in this package so the decorators fire.

    A module that raises on import becomes a disabled entry carrying its
    message. Losing one controller to a typo is acceptable; losing the whole
    dashboard to a half-written MPC is not.
    """
    import dpc.controllers as pkg

    failures: list[Entry] = []
    for info in pkgutil.iter_modules(pkg.__path__):
        if info.name == "registry":
            continue
        try:
            importlib.import_module(f"{pkg.__name__}.{info.name}")
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            failures.append(Entry(key=info.name,
                                  label=f"{info.name} (failed to load)",
                                  error=f"{type(exc).__name__}: {exc}"))

    entries = list(_REGISTRY.values()) + failures
    return tuple(sorted(entries, key=lambda e: e.label))


def build(entry: Entry, values: dict[str, float]):
    """Construct a controller, filling in declared defaults for anything the
    caller did not supply."""
    if entry.cls is None:
        raise ValueError(f"{entry.key} failed to load: {entry.error}")
    kwargs = {p.name: values.get(p.name, p.default) for p in entry.params}
    return entry.cls(**kwargs)
