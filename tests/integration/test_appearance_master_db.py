"""Integration tests for appearance_master CRUD."""

from __future__ import annotations

import uuid

import pytest

from services.appearance_master import get_or_create_appearance, list_appearances


@pytest.mark.integration
def test_list_and_create_custom_appearance(require_db, appearance_test_cleanup):
    label = f"Creamy white {uuid.uuid4().hex[:6]}"
    created = get_or_create_appearance(label)
    appearance_test_cleanup.append(created.id)
    assert created.appearance_text == label

    texts = {o.appearance_text for o in list_appearances()}
    assert label in texts

    again = get_or_create_appearance(label.upper())
    assert again.id == created.id
    assert again.appearance_text == label
