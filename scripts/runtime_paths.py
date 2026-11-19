"""The configured local home shared by packs, reading records and operation logs."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PackSettings:
    roots: tuple[Path, ...]
    state_file: Path
    cache_dir: Path
    managed_root: Path
    quarantine_root: Path
    default_enabled_packs: tuple[str, ...] = ()
    # Two different jobs. ``default_enabled_packs`` seeds a runtime that has no
    # state file yet; ``protected_pack_ids`` stands as a floor under explicit
    # user state and refuses to let those packs be disabled. Only the runtime
    # that uses the user's own state file carries the floor.
    protected_pack_ids: tuple[str, ...] = ()
    initialize_all_discovered: bool = False

def user_data_home() -> Path:
    """Return the configuration directory: CPB_HOME when it is set, ~/.character-prompt-builder otherwise.

    The pack state, the catalog cache, the managed packs, the home reading
    ledger and the operation logs live under it.
    """
    configured = os.environ.get("CPB_HOME", "").strip()
    return (Path(configured) if configured else Path.home() / ".character-prompt-builder").resolve()
