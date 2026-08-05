"""Unit tests for custom formula validation wizard."""

from __future__ import annotations

import pytest

from services.custom_formulas import (
    MODE_APP_FIRST,
    MODE_CALCULATOR_FIRST,
    answers_match,
    trial_mode_for_index,
)


class TestAnswersMatch:
    def test_exact_match(self):
        assert answers_match("30", 30.0)
        assert answers_match("30.0", 30.0)

    def test_rounded_match(self):
        assert answers_match("33.33", 33.333)

    def test_no_match(self):
        assert not answers_match("30", 31.0)

    def test_invalid_admin(self):
        assert not answers_match("", 10.0)
        assert not answers_match("abc", 10.0)


class TestTrialMode:
    def test_calculator_first_trials(self):
        for n in (1, 2, 3):
            assert trial_mode_for_index(n) == MODE_CALCULATOR_FIRST

    def test_app_first_trials(self):
        for n in (4, 5, 6):
            assert trial_mode_for_index(n) == MODE_APP_FIRST

    def test_invalid_trial(self):
        with pytest.raises(ValueError):
            trial_mode_for_index(0)
        with pytest.raises(ValueError):
            trial_mode_for_index(7)
