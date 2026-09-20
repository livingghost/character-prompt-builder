#!/usr/bin/env python3
"""Public single-image visual-evidence extraction API.

The implementation uses the compact perceptual three-layer pipeline. Layer A
keeps native canvas dimensions and applies one uniform full-frame profile;
Layers B and C provide audit artifacts and disposable runtime recipes.
"""
from __future__ import annotations

from compact_perceptual_visual_evidence import (
    PROFILES,
    QUALITY_THRESHOLDS,
    main as batch_main,
    process_source,
)

__all__ = [
    "PROFILES",
    "QUALITY_THRESHOLDS",
    "batch_main",
    "process_source",
]

if __name__ == "__main__":
    raise SystemExit(batch_main())
