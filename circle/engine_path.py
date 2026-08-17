"""Locate the `engine/` submodule and put it on the import path.

`engine/` is a git submodule (`4KInc/agent-authorization-gateway`) supplying
the `gateway` package: canonicalization, Merkle roots, policy, receipts, and
token issuance. A plain `git clone` records only a gitlink — the directory is
created empty and the code is absent until `git submodule update --init`.

The obvious guard is wrong:

    if os.path.isdir(ENGINE_PATH):        # an EMPTY engine/ is still a dir
        sys.path.insert(0, ENGINE_PATH)
    from gateway.canonical import ...     # ModuleNotFoundError, five frames deep

An uninitialised submodule passes `isdir`, so the path is added and the import
fails later with a message that names `gateway` — a package nobody can grep for,
because it does not exist in this repository. Worse, it fails at *container
start* rather than at build or test time, which means the first place it shows
up is a Cloud Run health-check timeout during a deploy.

This module checks for the `gateway` package itself and fails with an
actionable message naming the one command that fixes it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ENGINE_PATH = Path(__file__).resolve().parent.parent / "engine"
GATEWAY_PATH = ENGINE_PATH / "gateway"

_FIX = "git submodule update --init --recursive"


def engine_available() -> bool:
    """True when the `gateway` package is actually present on disk.

    Checks for the package, not the directory that should contain it, so an
    uninitialised submodule reads as unavailable rather than as present.
    """
    return (GATEWAY_PATH / "__init__.py").is_file()


def diagnose() -> str:
    """Explain what is wrong with the engine checkout, and how to fix it."""
    if engine_available():
        return f"engine/ present: {GATEWAY_PATH}"
    if not ENGINE_PATH.exists():
        return (
            f"engine/ is missing entirely (expected at {ENGINE_PATH}). "
            f"The submodule is not registered in this checkout. Run: {_FIX}"
        )
    if not any(ENGINE_PATH.iterdir()):
        return (
            f"engine/ exists but is EMPTY ({ENGINE_PATH}). This is an "
            f"uninitialised git submodule — the repository records a gitlink, "
            f"not the code. Run: {_FIX}"
        )
    return (
        f"engine/ has content but no gateway package at {GATEWAY_PATH}. "
        f"The submodule may be checked out at an unexpected commit. "
        f"Verify with `git submodule status`, then: {_FIX}"
    )


def ensure_on_path(*, required: bool = True) -> bool:
    """Add `engine/` to `sys.path` when the gateway package is present.

    Args:
        required: When True (the default, and correct for anything that will
            import `gateway`), raise immediately with a diagnostic instead of
            allowing a bare ModuleNotFoundError further down the import chain.
            When False, return a boolean so optional callers can degrade.

    Returns:
        True when the engine is on the path, False when absent and optional.

    Raises:
        ModuleNotFoundError: engine unavailable and `required` is True.
    """
    if not engine_available():
        if required:
            raise ModuleNotFoundError(
                f"Verigate requires the `gateway` package from the engine "
                f"submodule, which is not available.\n\n  {diagnose()}\n"
            )
        return False

    engine_str = str(ENGINE_PATH)
    if engine_str not in sys.path:
        sys.path.insert(0, engine_str)
    return True
