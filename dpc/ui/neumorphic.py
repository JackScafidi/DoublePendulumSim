"""Dual-shadow extrusion, painted by hand.

Qt stylesheets have no `box-shadow` -- it is parsed and discarded, verified by
rendering the same frame with and without it and getting identical pixels. And
QGraphicsDropShadowEffect casts exactly one shadow, one colour, one offset.
Neumorphism needs two per element, in opposite directions, plus inset variants.
So the shadows are rendered here.

The recipe, unchanged from the design language: one light source at the top
left, so negative offsets carry the light shadow and positive offsets the dark
one, on every element including inset ones. Blur is twice the offset. The
element's own fill is the same colour as what it sits on -- depth comes only
from the shadow.

Each shadow is rasterised once per size and cached, so a repaint is one pixmap
blit rather than a blur.
"""

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QFrame

from dpc.ui import theme as T


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    """Three box passes, which is close enough to a Gaussian for a shadow and
    far cheaper. Separable, so each pass is two 1-D convolutions."""
    if r < 1:
        return a
    k = 2 * r + 1
    out = a.astype(np.float32)
    for _ in range(3):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (r, r)
            padded = np.pad(out, pad, mode="edge")
            cs = np.cumsum(padded, axis=axis, dtype=np.float32)
            zero = np.zeros_like(np.take(cs, [0], axis=axis))
            cs = np.concatenate([zero, cs], axis=axis)
            n = out.shape[axis]
            lo = np.take(cs, np.arange(0, n), axis=axis)
            hi = np.take(cs, np.arange(k, k + n), axis=axis)
            out = (hi - lo) / k
    return out


def _rounded_mask(w: int, h: int, pad: int, radius: float) -> np.ndarray:
    """Alpha of a rounded rect, as float 0..1, on a padded canvas."""
    img = QImage(w + 2 * pad, h + 2 * pad, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    q = QPainter(img)
    q.setRenderHint(QPainter.Antialiasing)
    q.setPen(Qt.NoPen)
    q.setBrush(QColor(255, 255, 255))
    q.drawRoundedRect(QRectF(pad, pad, w, h), radius, radius)
    q.end()

    buf = np.frombuffer(img.constBits(), dtype=np.uint8)
    buf = buf.reshape(img.height(), img.bytesPerLine() // 4, 4)
    return buf[:, :img.width(), 3].astype(np.float32) / 255.0


def _tint(alpha: np.ndarray, colour: QColor, strength: float) -> np.ndarray:
    """Premultiplied BGRA planes for a single coloured shadow layer."""
    a = np.clip(alpha * strength, 0.0, 1.0)
    rgba = np.zeros(a.shape + (4,), dtype=np.float32)
    rgba[..., 0] = colour.blue() * a
    rgba[..., 1] = colour.green() * a
    rgba[..., 2] = colour.red() * a
    rgba[..., 3] = 255.0 * a
    return rgba


def _over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Source-over, on premultiplied planes."""
    inv = 1.0 - src[..., 3:4] / 255.0
    return src + dst * inv


def _to_pixmap(rgba: np.ndarray) -> QPixmap:
    buf = np.ascontiguousarray(np.clip(rgba, 0, 255).astype(np.uint8))
    h, w = buf.shape[:2]
    img = QImage(buf.data, w, h, w * 4, QImage.Format_ARGB32_Premultiplied)
    return QPixmap.fromImage(img.copy())


def raised_pixmap(w: int, h: int, offset: int, radius: float,
                  light: float = 1.0, dark: float = 1.0) -> QPixmap:
    """The two outer shadows, light up-left and dark down-right.

    Both are clipped to OUTSIDE the element, exactly as a CSS box-shadow is.
    Without that clip the blurred shape stays near-opaque across its whole
    middle and only the body covers it, so the offset leaves a hard-edged
    sliver -- a second shape peeking out from behind the first rather than a
    soft halo around it. Barely visible on a large card, glaring on a button,
    where the offset is a big fraction of the element.
    """
    blur = offset * 2
    pad = blur + offset + 2
    shape = _rounded_mask(w, h, pad, radius)
    mask = _blur_cache(w, h, pad, radius, blur)
    outside = 1.0 - shape

    hi = np.roll(mask, (-offset, -offset), axis=(0, 1)) * outside
    lo = np.roll(mask, (offset, offset), axis=(0, 1)) * outside

    out = _tint(lo, QColor(T.SHADOW_DARK), dark)
    out = _over(out, _tint(hi, QColor(T.SHADOW_LIGHT), light))
    return _to_pixmap(out)


def inset_pixmap(w: int, h: int, offset: int, radius: float) -> QPixmap:
    """The two inner shadows: dark along the top-left interior, light along the
    bottom-right, so the surface reads as pressed into the page."""
    blur = offset * 2
    pad = blur + offset + 2
    shape = _rounded_mask(w, h, pad, radius)
    outside = _box_blur(1.0 - shape, blur)

    dark = np.roll(outside, (offset, offset), axis=(0, 1)) * shape
    light = np.roll(outside, (-offset, -offset), axis=(0, 1)) * shape

    out = _tint(dark, QColor(T.SHADOW_DARK), 1.0)
    out = _over(out, _tint(light, QColor(T.SHADOW_LIGHT), 1.0))
    return _to_pixmap(out)


def inner_shade_pixmap(w: int, h: int, offset: int, radius: float,
                       shade: QColor) -> QPixmap:
    """The inner shade that gives a COLOURED mass its internal form.

    A colour fill still extrudes from the same surface under the same light: the
    outer dual shadow does that. What this adds is one inset layer in a darker
    step of the fill's OWN hue, gathered along the lower-right interior, so the
    mass reads as a solid object catching light from the upper left rather than
    a flat pill with a shadow under it. Without it the fill is, in the design
    language's words, a flat rectangle wearing a shadow.

    Deliberately NOT a white sheen: a strong inset highlight reads as a
    different material and composites over the label, wrecking its contrast.
    """
    blur = offset * 2
    pad = blur + offset + 2
    shape = _rounded_mask(w, h, pad, radius)
    outside = _box_blur(1.0 - shape, blur)
    inner = np.roll(outside, (-offset, -offset), axis=(0, 1)) * shape
    return _to_pixmap(_tint(inner, shade, shade.alphaF()))


_BLUR_CACHE: dict[tuple, np.ndarray] = {}


def _blur_cache(w, h, pad, radius, blur) -> np.ndarray:
    key = (w, h, pad, radius, blur)
    if key not in _BLUR_CACHE:
        if len(_BLUR_CACHE) > 64:
            _BLUR_CACHE.clear()
        _BLUR_CACHE[key] = _box_blur(_rounded_mask(w, h, pad, radius), blur)
    return _BLUR_CACHE[key]


class NeumorphicFrame(QFrame):
    """A panel that extrudes from, or is pressed into, the surface behind it.

    `fill` defaults to the page surface, which is the whole point: the element
    is the same colour as its parent and only the shadow makes it an object.
    An inset frame takes the sunken colour, because a well that holds data
    wants to be darker than the page.
    """

    def __init__(self, inset: bool = False, offset: int = 4,
                 radius: float | None = None, fill: str | None = None,
                 parent=None):
        super().__init__(parent)
        self.inset = inset
        self.offset = offset
        self.radius = T.RADIUS_PANEL if radius is None else radius
        self.fill = fill or (T.SURFACE_SUNKEN if inset else T.SURFACE)
        self.pad = offset * 3 + 2
        """How far the shadow reaches: the offset plus a blur of twice it,
        with a little slack. A raised frame reserves this as margin."""
        self._pixmap: QPixmap | None = None
        self._for_size = None
        self.setAttribute(Qt.WA_StyledBackground, False)

    def _body_size(self) -> tuple[int, int]:
        """A raised frame's shadow falls OUTSIDE its body, and Qt clips painting
        to the widget rectangle -- so the body is inset by the shadow's reach and
        the shadow lives in the margin. Without this the outer shadow is cropped
        at the widget edge and reads as a bevel rather than an extrusion.

        An inset frame needs no such margin: its shadow is inside the shape.
        """
        if self.inset:
            return max(self.width(), 1), max(self.height(), 1)
        return (max(self.width() - 2 * self.pad, 1),
                max(self.height() - 2 * self.pad, 1))

    def _shadow(self) -> QPixmap:
        size = self._body_size()
        if self._pixmap is None or self._for_size != size:
            make = inset_pixmap if self.inset else raised_pixmap
            self._pixmap = make(size[0], size[1], self.offset, self.radius)
            self._for_size = size
        return self._pixmap

    def paintEvent(self, event) -> None:
        q = QPainter(self)
        q.setRenderHint(QPainter.Antialiasing)

        w, h = self._body_size()
        origin = 0 if self.inset else self.pad
        body = QRectF(origin, origin, w, h)
        path = QPainterPath()
        path.addRoundedRect(body, self.radius, self.radius)

        # The pixmap already carries `pad` of transparent border around the
        # shape, so it is drawn `pad` before the body in both directions.
        at = origin - self.pad

        if self.inset:
            # Fill first: an inset shadow is drawn on top of its own surface.
            q.fillPath(path, QColor(self.fill))
            q.drawPixmap(at, at, self._shadow())
        else:
            q.drawPixmap(at, at, self._shadow())
            q.fillPath(path, QColor(self.fill))

        super().paintEvent(event)
