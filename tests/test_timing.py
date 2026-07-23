"""Tests de la logique pure de durée (aucune I/O)."""

import pytest

from lectio.core.timing import (
    count_words,
    duration_to_words,
    deviation,
    format_duration,
    parse_duration,
    words_to_duration,
)


def test_duration_to_words_uses_rate():
    assert duration_to_words(60, 2.0) == 120
    assert duration_to_words(90, 2.3) == 207


def test_words_to_duration_is_inverse():
    assert words_to_duration(120, 2.0) == pytest.approx(60.0)


def test_deviation():
    assert deviation(110, 100) == pytest.approx(0.10)
    assert deviation(90, 100) == pytest.approx(0.10)


def test_rate_must_be_positive():
    with pytest.raises(ValueError):
        duration_to_words(60, 0)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("90", 90.0),
        ("90s", 90.0),
        ("2m", 120.0),
        ("1m30s", 90.0),
        ("1.5m", 90.0),
    ],
)
def test_parse_duration(text, expected):
    assert parse_duration(text) == expected


def test_parse_duration_invalid():
    with pytest.raises(ValueError):
        parse_duration("abc")


def test_format_duration():
    assert format_duration(None) == "—"
    assert format_duration(45) == "45s"
    assert format_duration(95) == "1m35s"


def test_count_words():
    assert count_words("le professeur explique le concept") == 5
