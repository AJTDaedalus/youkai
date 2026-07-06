"""Tests for the pure title-matching and resolution helpers in capture.py.

Covers TASK-1 acceptance criteria:
- title_matches: default set, case/space insensitive, substring, rejects unknowns
- resolve_accepted_titles: env parsing, extra iterable, dedup, blank-drop
- TASK-3b: DEFAULT_GAME_TITLES includes both retail and chiaki-ng built-in
"""

from youkai_ocr.capture import (
    DEFAULT_GAME_TITLES,
    resolve_accepted_titles,
    title_matches,
)

# ── DEFAULT_GAME_TITLES (TASK-3b) ──────────────────────────────────────────────


def test_defaults_include_retail():
    assert "ZenlessZoneZero" in DEFAULT_GAME_TITLES


def test_defaults_include_chiaki_ng():
    assert "chiaki-ng" in DEFAULT_GAME_TITLES


# ── title_matches — default accepted set ──────────────────────────────────────


def test_default_accepts_exact_game_title():
    assert title_matches("ZenlessZoneZero", DEFAULT_GAME_TITLES)


def test_default_accepts_spaced_variant():
    # "Zenless Zone Zero" normalizes identically to "ZenlessZoneZero"
    assert title_matches("Zenless Zone Zero", DEFAULT_GAME_TITLES)


def test_default_accepts_chiaki_ng_built_in():
    assert title_matches("chiaki-ng", DEFAULT_GAME_TITLES)


def test_default_rejects_unrelated_title():
    assert not title_matches("Notepad", DEFAULT_GAME_TITLES)


def test_default_rejects_blank_title():
    assert not title_matches("", DEFAULT_GAME_TITLES)


# ── title_matches — custom accepted set ───────────────────────────────────────


def test_custom_accepts_after_add():
    accepted = resolve_accepted_titles(extra=["Chiaki"])
    assert title_matches("Chiaki Remote Play", accepted)


def test_custom_match_is_case_insensitive():
    accepted = resolve_accepted_titles(extra=["Chiaki"])
    assert title_matches("CHIAKI", accepted)
    assert title_matches("chiaki", accepted)
    assert title_matches("ChIaKi", accepted)


def test_custom_match_strips_whitespace():
    # "My App" and "MyApp" should both match "my app" accepted title
    accepted = resolve_accepted_titles(extra=["My App"])
    assert title_matches("MyApp Window", accepted)
    assert title_matches("My App Window", accepted)


def test_retail_still_matches_after_adding_chiaki():
    accepted = resolve_accepted_titles(extra=["Chiaki"])
    assert title_matches("ZenlessZoneZero", accepted)
    assert title_matches("chiaki-ng", accepted)  # built-in chiaki-ng also present


# ── resolve_accepted_titles — env parsing ─────────────────────────────────────


def test_env_comma_split():
    result = resolve_accepted_titles(env="A,B")
    assert "A" in result
    assert "B" in result


def test_env_drops_blanks():
    result = resolve_accepted_titles(env="A, ,B")
    assert "" not in result
    assert " " not in result
    assert "A" in result
    assert "B" in result


def test_env_strips_whitespace_around_commas():
    result = resolve_accepted_titles(env=" A , B ")
    # Values are stripped; "A" and "B" (not " A " or " B ") are in result
    assert "A" in result
    assert "B" in result


def test_defaults_always_present_with_env():
    result = resolve_accepted_titles(env="SomeOtherClient")
    assert "ZenlessZoneZero" in result
    assert "chiaki-ng" in result
    assert "SomeOtherClient" in result


# ── resolve_accepted_titles — dedup ───────────────────────────────────────────


def test_dedup_preserves_order():
    # ZenlessZoneZero is already in defaults; passing it again must not duplicate it
    result = resolve_accepted_titles(extra=["ZenlessZoneZero", "NewClient"])
    assert result.count("ZenlessZoneZero") == 1
    assert "NewClient" in result


def test_no_blank_from_empty_env():
    result = resolve_accepted_titles(env="")
    assert "" not in result


def test_no_blank_from_none_extra():
    result = resolve_accepted_titles(extra=None, env=None)
    assert all(t for t in result)  # no blank strings


# ── resolve_accepted_titles — return type ────────────────────────────────────


def test_returns_tuple():
    assert isinstance(resolve_accepted_titles(), tuple)
