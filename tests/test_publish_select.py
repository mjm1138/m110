"""Selection / privacy filtering for publishing (the testable core)."""
from m110.publish import select
from m110.publish.options import PublishOptions


def test_publishable_excludes_opt_out():
    library = {
        "m31": {"id": "M31"},
        "m51": {"id": "M51", "publish": True},
        "m81": {"id": "M81", "publish": False},
    }
    assert select.publishable_slugs(library) == {"m31", "m51"}


def test_is_publishable_default_true():
    assert select.is_publishable({"id": "M1"}) is True
    assert select.is_publishable({"id": "M1", "publish": False}) is False


def test_journal_hidden_when_globally_excluded(tmp_path):
    opts = PublishOptions(output_dir=tmp_path, exclude_journals=True)
    assert select.journal_visible("m31", opts, frontmatter={}) is False


def test_journal_hidden_when_section_off(tmp_path):
    opts = PublishOptions(output_dir=tmp_path, sections={"library"})
    assert select.journal_visible("m31", opts, frontmatter={}) is False


def test_journal_hidden_when_private(tmp_path):
    opts = PublishOptions(output_dir=tmp_path)  # journal section on by default
    assert select.journal_visible("m31", opts, frontmatter={"private": "true"}) is False
    assert select.journal_visible("m31", opts, frontmatter={}) is True


def test_filter_sessions_keeps_only_publishable():
    sessions = [
        {"object_dir": "M31", "slugs": ["m31"]},
        {"object_dir": "M81", "slugs": ["m81"]},
    ]
    assert select.filter_sessions(sessions, {"m31"}) == [sessions[0]]


def test_filter_processing_recomputes_counts():
    processing = {
        "folders": {
            "M31": {"slugs": ["m31"], "status": "up_to_date"},
            "M81": {"slugs": ["m81"], "status": "out_of_date"},
        },
        "queue": [
            {"folder": "M31", "slugs": ["m31"], "status": "up_to_date"},
            {"folder": "M81", "slugs": ["m81"], "status": "out_of_date"},
        ],
        "counts": {"out_of_date": 1, "not_processed": 0, "up_to_date": 1, "dismissed": 0},
    }
    out = select.filter_processing(processing, {"m31"})
    assert list(out["folders"]) == ["M31"]
    assert out["counts"] == {"out_of_date": 0, "not_processed": 0,
                             "up_to_date": 1, "dismissed": 0}
