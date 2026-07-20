"""Direct unit test for the publish gallery-tier logic (`m110.publish.images`).

`_image_tier` + the three `GALLERY_LEVELS` decide which images reach the public
site; today they're only exercised transitively through `site.render`. These
pin the classification, the curation override, and the level nesting directly.
"""
from m110.publish import images


def test_image_tier_follows_source_label():
    assert images._image_tier("M42_processed.png", "Finished render", {}) == "finished"
    assert images._image_tier("stacked.jpg", "Seestar in-app stack", {}) == "device"
    assert images._image_tier("M42_stack.fit", "Siril stack", {}) == "working"


def test_curation_override_wins_both_ways():
    # a device stack promoted to finished publishes as finished…
    assert images._image_tier("stacked.jpg", "Seestar in-app stack",
                              {"stacked.jpg": "finished"}) == "finished"
    # …and a finished render demoted to working drops to working
    assert images._image_tier("M42_processed.png", "Finished render",
                              {"M42_processed.png": "working"}) == "working"


def test_gallery_levels_are_nested():
    lv = images._LEVEL_TIERS
    assert images.GALLERY_LEVELS == ("finished", "device-stacks", "all")
    assert lv["finished"] == {"finished"}
    assert lv["device-stacks"] == {"finished", "device"}
    assert lv["all"] == {"finished", "device", "working"}
    assert lv["finished"] <= lv["device-stacks"] <= lv["all"]


def test_promoted_stack_and_demoted_render_respect_levels():
    """A curated-finished device stack survives the strictest level; a demoted
    finished render appears only under 'all'."""
    cur = {"stacked.jpg": "finished", "M42_processed.png": "working"}
    finished = images._LEVEL_TIERS["finished"]
    all_ = images._LEVEL_TIERS["all"]
    assert images._image_tier("stacked.jpg", "Seestar in-app stack", cur) in finished
    demoted = images._image_tier("M42_processed.png", "Finished render", cur)
    assert demoted not in finished and demoted in all_
