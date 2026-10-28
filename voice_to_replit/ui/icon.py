"""Draws the microphone icon used for the tray, windows and shortcuts."""
from PIL import Image, ImageDraw

COLORS = {"idle": "#f26207", "recording": "#f85149", "busy": "#d29922"}


def make(state: str = "idle", size: int = 64) -> Image.Image:
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill=COLORS.get(state, COLORS["idle"]))
    w = "white"
    d.rounded_rectangle([24 * s, 12 * s, 40 * s, 38 * s], radius=8 * s, fill=w)
    d.arc([18 * s, 22 * s, 46 * s, 46 * s], start=0, end=180, fill=w, width=max(2, int(3 * s)))
    d.line([32 * s, 46 * s, 32 * s, 52 * s], fill=w, width=max(2, int(3 * s)))
    d.line([25 * s, 52 * s, 39 * s, 52 * s], fill=w, width=max(2, int(3 * s)))
    return img


def save_ico(path) -> None:
    make("idle", 256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
