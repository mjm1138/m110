"""Tests for catalog ordering (mirrors the site's _catalog_sort_key)."""
from m110.catalog import catalog_sort_key, season_sort_key


def test_messier_numeric_not_lexical():
    ids = ["M10", "M1", "M100", "M2", "M9"]
    assert sorted(ids, key=catalog_sort_key) == ["M1", "M2", "M9", "M10", "M100"]


def test_messier_then_ngc_then_other():
    ids = ["NGC 3628", "M81", "Markarian's Chain"]
    assert sorted(ids, key=catalog_sort_key) == ["M81", "NGC 3628", "Markarian's Chain"]


def test_ngc_numeric():
    assert sorted(["NGC 3628", "NGC 891", "NGC 2903"], key=catalog_sort_key) == [
        "NGC 891", "NGC 2903", "NGC 3628"]


def test_markarians_not_parsed_as_messier():
    # starts with M but must NOT sort as a Messier number
    assert catalog_sort_key("Markarian's Chain")[0] == 2
    assert catalog_sort_key("M81")[0] == 0


def test_season_sort_by_first_month_year_round_last():
    assert season_sort_key("Jan–Mar")[0] == 1
    assert season_sort_key("Mar–May")[0] == 3
    assert season_sort_key("Dec–Feb")[0] == 12      # by first month, not wrap
    assert season_sort_key("Year-round")[0] == 99    # bottom
    assert season_sort_key("")[0] == 99
    seasons = ["Year-round", "Mar–May", "Jan–Mar", "Dec–Feb", "Jun–Aug"]
    assert sorted(seasons, key=season_sort_key) == [
        "Jan–Mar", "Mar–May", "Jun–Aug", "Dec–Feb", "Year-round"]
