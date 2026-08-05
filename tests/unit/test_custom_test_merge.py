"""Unit tests for merging custom test keys at Reception."""

from __future__ import annotations


def test_merge_test_keys_dedupes():
    base = ["moisture", "total_ash"]
    custom = ["custom_1", "moisture"]
    seen = set()
    merged = []
    for key in base + custom:
        if key and key not in seen:
            seen.add(key)
            merged.append(key)
    assert merged == ["moisture", "total_ash", "custom_1"]
