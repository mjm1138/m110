"""Publisher registry + dispatch + missing-deps behaviour."""
import builtins

import pytest

from m110 import config, publish
from m110.publish.options import PublishOptions
from tests._helpers import seed_root


def test_default_target_is_static_site(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    assert publish.enabled_target_ids() == ["static-site"]


def test_enabled_targets_reads_setting(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    config.save_setting(publish.SETTING_KEY, ["static-site", "github-pages"])
    assert publish.enabled_target_ids() == ["static-site", "github-pages"]


def test_run_publish_skips_unavailable(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    config.save_setting(publish.SETTING_KEY, ["github-pages"])  # registered-disabled
    res = publish.run_publish(PublishOptions(output_dir=tmp_path / "site"))
    assert res == {}  # nothing available ran


def test_static_site_is_available():
    assert publish.PUBLISHERS_BY_ID["static-site"].available is True
    assert publish.PUBLISHERS_BY_ID["github-pages"].available is False


def test_missing_deps_raises_clear_error(tmp_path, monkeypatch):
    seed_root(tmp_path, monkeypatch)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jinja2":
            raise ImportError("no jinja2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from m110.publish import site
    with pytest.raises(publish.PublishDepsMissing):
        site.render(PublishOptions(output_dir=tmp_path / "site"))
