"""QSS generation from tokens."""
from m110.ui.theme import tokens
from m110.ui.theme.qss import build_qss


def test_build_qss_nonempty_for_both():
    assert build_qss(tokens.LIGHT).strip()
    assert build_qss(tokens.DARK).strip()


def test_light_and_dark_qss_differ():
    assert build_qss(tokens.LIGHT) != build_qss(tokens.DARK)


def test_qss_contains_key_selectors_and_palette():
    qss = build_qss(tokens.DARK)
    for sel in ("QTableWidget", 'QLabel[muted="true"]', 'QLabel[caption="true"]',
                "QListWidget::item:selected", "QMenu", "QHeaderView::section"):
        assert sel in qss, f"missing selector {sel}"
    assert tokens.DARK.window in qss
    assert tokens.DARK.accent in qss


def test_pushbutton_has_min_height():
    """QPushButton needs a min-height so a styled button in a tight layout doesn't
    clip its label top-and-bottom (esp. on macOS)."""
    qss = build_qss(tokens.LIGHT)
    btn_block = qss.split("QPushButton {", 1)[1].split("}", 1)[0]
    assert "min-height" in btn_block
