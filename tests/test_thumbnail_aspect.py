"""Thumbnails must not distort their source.

The bug this guards: the Media page built tiles as
``QListWidgetItem(QIcon(str(path)), name)`` against ``setIconSize(160, 160)``.
A 1080x1920 lunar frame came out squashed into 160x160 and the Moon rendered as
a wide oval — vertically compressed by exactly 1920/1080.

**It is format-dependent, which is what made it so easy to miss.** The JPEG
handler advertises `ScaledSize`, so Qt asks it to decode straight to the target
size and it honours that literally, ignoring aspect ratio. PNG advertises no such
support, so Qt loads full-size and scales with `KeepAspectRatio` — correctly. The
same code is therefore right for one file and wrong for another, and the Seestar
writes JPEG. `test_qicon_distorts_jpeg_but_not_png` pins that contrast down, so a
future reader doesn't "simplify" the crop away after testing with a PNG.

The checks are subject-shaped rather than pixmap-shaped on purpose: asserting the
returned pixmap is 160x160 would have *passed* on the broken code. What the user
sees is a round Moon, so the test measures the round thing.

Pure arithmetic on image data — style-independent, so valid offscreen (unlike a
question about how a style *paints*, which offscreen cannot answer).
"""
import pytest

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QImageReader, qGray

pytestmark = pytest.mark.usefixtures("qapp")

TILE = 160


def _portrait_with_circle(path, w=1080, h=1920, r=370):
    """A black portrait frame with a white disc dead-centre — a synthetic Moon."""
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(Qt.black)
    cx, cy = w // 2, h // 2
    for y in range(cy - r, cy + r + 1):
        dy = y - cy
        dx = int((r * r - dy * dy) ** 0.5)
        for x in range(cx - dx, cx + dx + 1):
            img.setPixel(x, y, 0xFFFFFFFF)
    img.save(str(path))
    return path


def _subject_aspect(img: QImage, thr=128) -> float:
    """Width/height of the bright subject's bounding box."""
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            if qGray(img.pixel(x, y)) > thr:
                xs.append(x)
                ys.append(y)
    assert xs, "no subject found in the thumbnail"
    return (max(xs) - min(xs) + 1) / (max(ys) - min(ys) + 1)


def test_source_circle_is_round(tmp_path):
    """Sanity-check the fixture, so a failure below can't be blamed on it."""
    src = _portrait_with_circle(tmp_path / "moon.jpg")
    assert _subject_aspect(QImageReader(str(src)).read()) == pytest.approx(1.0, abs=0.05)


def test_thumbnail_loader_preserves_the_subject_shape(tmp_path):
    """The path the Media grid and every row icon actually use."""
    from m110.ui.widgets import _ThumbLoadTask, _ThumbSignals

    src = _portrait_with_circle(tmp_path / "moon.jpg")
    captured = {}
    signals = _ThumbSignals()
    signals.done.connect(lambda p, s, c, img: captured.update(img=img))
    _ThumbLoadTask(str(src), TILE, "square", signals).run()

    img = captured["img"]
    assert img is not None and not img.isNull()
    assert _subject_aspect(img) == pytest.approx(1.0, abs=0.1), (
        "the thumbnail squashed a round subject into an oval")


def test_square_icon_helper_preserves_the_subject_shape(tmp_path):
    """The object-detail gallery's helper — same guarantee, different call site."""
    from m110.ui.detail import _square_icon

    src = _portrait_with_circle(tmp_path / "moon.jpg")
    img = _square_icon(src, TILE).pixmap(QSize(TILE, TILE)).toImage()
    assert _subject_aspect(img) == pytest.approx(1.0, abs=0.1)


def test_qicon_distorts_jpeg_but_not_png(tmp_path):
    """Documents the trap, and the format-dependence that hid it.

    If a future Qt makes the JPEG path aspect-preserving this test fails, which is
    the signal we want: the hazard is gone and the reasoning above can be revisited.
    """
    jpg = _portrait_with_circle(tmp_path / "moon.jpg")
    png = _portrait_with_circle(tmp_path / "moon.png")

    jpg_pm = QIcon(str(jpg)).pixmap(QSize(TILE, TILE))
    assert jpg_pm.size() == QSize(TILE, TILE)              # filled the square
    assert _subject_aspect(jpg_pm.toImage()) > 1.5         # …into a wide oval

    png_pm = QIcon(str(png)).pixmap(QSize(TILE, TILE))
    assert png_pm.size() != QSize(TILE, TILE)              # fitted, not filled
    assert _subject_aspect(png_pm.toImage()) == pytest.approx(1.0, abs=0.1)


def test_no_view_builds_an_icon_straight_from_a_file_path():
    """Belt and braces: no view may construct `QIcon` from a path.

    A distorted thumbnail still renders, so a screenshot test would pass; the
    *policy* is what has to be asserted (the same reasoning as
    `test_ui_modal_safety`). Parsed rather than grepped so prose about the bug —
    including the docstrings explaining it — can't trip or satisfy the check.

    `QIcon(pixmap)` stays legal: by then the caller has already done the
    aspect-preserving work.
    """
    import ast
    from pathlib import Path

    offenders = []
    for f in sorted(Path("m110/ui").rglob("*.py")):
        tree = ast.parse(f.read_text(), filename=str(f))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "QIcon" and node.args):
                continue
            arg = node.args[0]
            # Catches the unambiguous path forms: QIcon(str(x)), QIcon("literal"),
            # QIcon(f"..."). A bare name is left alone — QIcon(pixmap) and
            # QIcon(path_var) are indistinguishable to a parser, and QIcon(pixmap)
            # is the correct, common form (the caller already did the scaling).
            builds_from_path = (
                (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Name)
                 and arg.func.id == "str")
                or isinstance(arg, ast.Constant)
                or (isinstance(arg, ast.JoinedStr)))
            if builds_from_path:
                offenders.append(f"{f}:{node.lineno}")
    assert not offenders, (
        "build icons through ThumbnailLoader / _square_icon — QIcon fills a fixed "
        f"icon size, distorting non-square JPEG sources: {offenders}")
