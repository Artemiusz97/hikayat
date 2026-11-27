"""Shared lossless module proxy and callable-unwrapping utilities for decomposed package facades."""
from __future__ import annotations

import inspect
import sys
import types
from typing import Any, Callable


def install_submodule_proxy(
    module_name: str,
    submodules: tuple[types.ModuleType, ...],
    submodule_names: frozenset[str],
    *,
    cls_name: str = "_SubmoduleProxyModule",
) -> None:
    """Install a module subclass on `module_name` forwarding setattr/delattr losslessly.

    When an attribute not originally present on the facade module is added (for example
    via ``monkeypatch.setattr(facade, name, fake, raising=False)``), original submodule
    bindings are snapshotted before overwriting and restored on ``__delattr__`` rather
    than deleting symbols from child submodules permanently.
    """
    saved_for_added: dict[str, list[tuple[types.ModuleType, Any]]] = {}
    deleted_from_subs: dict[str, set[types.ModuleType]] = {}

    class _ProxyModule(types.ModuleType):
        def __setattr__(self, name: str, value: Any) -> None:
            if not name.startswith("__") and name not in submodule_names:
                existed = name in self.__dict__
                if not existed and name not in saved_for_added and name not in deleted_from_subs:
                    saved_for_added[name] = [
                        (sub, sub.__dict__[name]) for sub in submodules if name in sub.__dict__
                    ]
                super().__setattr__(name, value)
                restored_subs = deleted_from_subs.pop(name, None) or set()
                for sub in submodules:
                    if name in sub.__dict__ or sub in restored_subs:
                        setattr(sub, name, value)
            else:
                super().__setattr__(name, value)

        def __delattr__(self, name: str) -> None:
            super().__delattr__(name)
            if not name.startswith("__") and name not in submodule_names:
                if name in saved_for_added:
                    saved = saved_for_added.pop(name)
                    for sub, orig_val in saved:
                        setattr(sub, name, orig_val)
                else:
                    removed: set[types.ModuleType] = set()
                    for sub in submodules:
                        if name in sub.__dict__:
                            delattr(sub, name)
                            removed.add(sub)
                    if removed:
                        deleted_from_subs[name] = removed

    _ProxyModule.__name__ = cls_name
    _ProxyModule.__qualname__ = cls_name
    sys.modules[module_name].__class__ = _ProxyModule


def unwrap_callable_target(fn: Callable[..., Any] | Any, max_hops: int = 4) -> Any:
    """Resolve `side_effect` / `_mock_wraps` indirections to the underlying callable."""
    target = fn
    for _ in range(max_hops):
        se = getattr(target, "side_effect", None)
        if callable(se) and not (isinstance(se, type) and issubclass(se, BaseException)):
            target = se
            continue
        wraps = getattr(target, "_mock_wraps", None)
        if callable(wraps):
            target = wraps
            continue
        break
    return target


def callable_accepts_kwarg(fn: Any, kwarg: str) -> bool:
    """Return True when `fn` (or a mock wrapper around it) accepts `kwarg` or `**kwargs`."""
    target = unwrap_callable_target(fn)
    try:
        sig = inspect.signature(target)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.kind == inspect.Parameter.VAR_KEYWORD or (
            param.name == kwarg
            and param.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
        ):
            return True
    return False


def call_with_supported_kwargs(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Invoke `fn(*args, **supported_kwargs)` dropping keyword args omitted by legacy test mocks."""
    supported = {k: v for k, v in kwargs.items() if callable_accepts_kwarg(fn, k)}
    return fn(*args, **supported)
