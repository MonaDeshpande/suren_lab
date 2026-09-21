"""Unit tests for namespaced customer picker session keys."""

from __future__ import annotations

from ui.components import customer_picker_keys


def test_default_prefix():
    keys = customer_picker_keys()
    assert keys["search_q"] == "ctr_customer_search_q"
    assert keys["select"] == "ctr_customer_select"


def test_distinct_prefixes_do_not_collide():
    intake = customer_picker_keys("intake_")
    master = customer_picker_keys("cust_master_")
    edit = customer_picker_keys("ctr_edit_")
    all_search = {intake["search_q"], master["search_q"], edit["search_q"]}
    assert len(all_search) == 3
    assert intake["results"] != master["results"]
