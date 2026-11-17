"""Generate assets/hero.svg: a particle portrait that morphs into </>, a
triangle and a Python-style logo, next to a SYSTEM.INFO panel.

Also writes the three footer link buttons (assets/link-*.svg).

How the animation works
-----------------------
Each dot is one <circle> with two SMIL <animate> tags (cx and cy). Every
shape has exactly N points, so dot i simply travels from point i of one
shape to point i of the next. No JavaScript is used (GitHub strips it).
"""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from common import (BG, CYAN, FONT, GREEN, MUTED, PANEL, PINK, PURPLE, ROOT,
                    TEXT, defs_glow, esc, frame, load_profile, write_svg)

RNG = np.random.default_rng(7)   # fixed seed -> same SVG every run (no noisy diffs)
S = 280                          # size of the square drawing area, in px
W, H = 900, 420                  # hero size
MAP_X, MAP_Y = 40, 72            # top-left of the VISUAL.MAP frame (300x300)
DOT_X, DOT_Y = MAP_X + 10, MAP_Y + 10   # dots are drawn inside a 10px padding
DUR = 12                         # seconds per full loop


# ====================================================================
# 1. Point sets
# ====================================================================
def placeholder_photo():
    """A simple head-and-shoulders silhouette, used if assets/photo.jpg is missing."""
    img = Image.new("L", (S, S), 245)
    d = ImageDraw.Draw(img)
    d.ellipse((40, 200, 240, 360), fill=70)          # shoulders
    d.rectangle((115, 150, 165, 215), fill=95)       # neck
    d.ellipse((85, 45, 195, 185), fill=120)          # face
    d.pieslice((78, 35, 202, 175), 180, 360, fill=40)  # hair
    d.ellipse((108, 100, 128, 112), fill=30)         # eyes
    d.ellipse((152, 100, 172, 112), fill=30)
    d.arc((118, 130, 162, 160), 20, 160, fill=40, width=4)  # smile
    return img.filter(ImageFilter.GaussianBlur(2))


def load_photo(path, crop=None):
    if path.exists():
        img = Image.open(path).convert("L")
        if crop:
            # [left, top, right, bottom] from profile.json, in photo pixels
            img = img.crop(tuple(crop))
        else:
            # otherwise crop to a centred square so faces are not squashed
            side = min(img.size)
            left, top = (img.width - side) // 2, (img.height - side) // 2
            img = img.crop((left, top, left + side, top + side))
        print(f"using photo {path.relative_to(ROOT)}")
    else:
        print(f"!! {path.relative_to(ROOT)} not found - using a placeholder silhouette")
        img = placeholder_photo()
    img = img.resize((S, S), Image.LANCZOS)
    return ImageOps.autocontrast(img, cutoff=2)      # boost contrast


GRID = 110        # the photo is dithered on a GRID x GRID raster (then scaled up to S)
GAMMA = 0.7       # < 1 lifts mid-tones (the face) relative to very bright areas
EDGE_BOOST = 0.6  # extra dots on edges: glasses, eyes, hair outline


def portrait_points(img, n):
    """Turn the photo into exactly n evenly spread dots.

    1. Work out a 'tone' per pixel: how much it stands out from the background.
       (Dark background -> bright parts get dots. Light background -> dark parts.)
    2. Add edge strength so features like eyes and glasses stay visible.
    3. Floyd-Steinberg dither the tone map (Pillow's convert("1")). Dithering
       spreads dots evenly, which keeps far more detail than random sampling.
    4. Scale the tone up or down (binary search) until the dither gives ~n dots.
    """
    small = img.resize((GRID, GRID), Image.LANCZOS)
    a = np.asarray(small, dtype=np.float32) / 255.0
    # background = median of the top row and side columns (the bottom is usually clothes)
    bg = float(np.median(np.concatenate([a[0], a[:, 0], a[:, -1]])))
    if bg < 0.5:
        tone = np.clip((a - bg) / (1 - bg), 0, 1)
    else:
        tone = np.clip((bg - a) / bg, 0, 1)
    tone = tone ** GAMMA

    gy, gx = np.gradient(np.asarray(small.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255.0)
    edges = np.hypot(gx, gy)
    edges /= edges.max() + 1e-6
    tone = np.clip(tone + EDGE_BOOST * edges, 0, 1)

    def dither(k):
        scaled = (np.clip(tone * k, 0, 1) * 255).astype(np.uint8)
        return np.asarray(Image.fromarray(scaled).convert("1"))

    lo, hi = 0.01, 20.0
    for _ in range(30):                      # binary search for the brightness factor
        k = (lo + hi) / 2
        if dither(k).sum() > n:
            hi = k
        else:
            lo = k
    ys, xs = np.nonzero(dither(lo))
    pts = np.column_stack([xs, ys]).astype(np.float32) * (S / GRID)

    # drop lonely dots (background noise): keep a dot only if at least one
    # other dot is within 6.5 px (the count includes the dot itself)
    dist = np.hypot(*(pts[:, None, :] - pts[None, :, :]).transpose(2, 0, 1))
    keep = (dist < 6.5).sum(axis=1) >= 2
    print(f"portrait: removed {(~keep).sum()} lonely dots")
    pts = pts[keep]

    # make the count exactly n: drop extras, or duplicate a few if short
    if len(pts) > n:
        pts = pts[RNG.choice(len(pts), n, replace=False)]
    elif len(pts) < n:
        pts = np.vstack([pts, pts[RNG.choice(len(pts), n - len(pts))]])
    return jitter(pts)


def jitter(pts):
    return pts + RNG.uniform(-0.5, 0.5, pts.shape)


def mask_points(mask, n):
    """Sample n points uniformly inside a white-on-black mask image."""
    ys, xs = np.nonzero(np.asarray(mask) > 127)
    idx = RNG.choice(len(xs), size=n, replace=len(xs) < n)
    return jitter(np.column_stack([xs[idx], ys[idx]]).astype(np.float32))


def new_mask():
    m = Image.new("L", (S, S), 0)
    return m, ImageDraw.Draw(m)


def brackets_mask():
    m, d = new_mask()
    w = 20
    d.line([(92, 70), (25, 140), (92, 210)], fill=255, width=w, joint="curve")    # <
    d.line([(163, 55), (117, 225)], fill=255, width=w)                            # /
    d.line([(188, 70), (255, 140), (188, 210)], fill=255, width=w, joint="curve")  # >
    return m


def triangle_mask():
    m, d = new_mask()
    outer = [(140, 25), (260, 240), (20, 240)]
    inner = [(140, 110), (195, 205), (85, 205)]
    d.polygon(outer, outline=255, width=20)
    d.polygon(inner, outline=255, width=10)
    return m


def logo_mask():
    """Two interlocking rounded 'snakes', like the Python logo."""
    m, d = new_mask()

    def snake(draw):
        draw.rounded_rectangle((95, 25, 185, 92), 24, fill=255)     # head
        draw.rounded_rectangle((30, 98, 140, 172), 24, fill=255)    # body
        draw.rectangle((95, 70, 140, 120), fill=255)                # neck joining them
        draw.ellipse((112, 42, 134, 64), fill=0)                    # eye

    snake(d)

    # second snake = first one rotated 180 degrees, with a dark gap around it
    other, od = new_mask()
    snake(od)
    other = other.rotate(180)
    gap = other.filter(ImageFilter.MaxFilter(15))
    m.paste(0, mask=gap)
    m.paste(255, mask=other)
    return m


def sort_xy(pts):
    """Order points by x, then y, so dot i moves to a nearby spot in the next shape."""
    return pts[np.lexsort((pts[:, 1], pts[:, 0]))]


# ====================================================================
# 2. SVG building
# ====================================================================
# keyTimes: hold each shape, then a short flight to the next one.
KEY_TIMES = "0;.2;.27;.45;.52;.7;.77;.92;1"


def dots_svg(shapes):
    """shapes = [portrait, brackets, triangle, logo], each an (n, 2) array."""
    p, b, t, l = shapes
    order = [p, p, b, b, t, t, l, l, p]          # matches KEY_TIMES
    n = len(p)
    palette = [PURPLE] * 16 + [CYAN] * 3 + [PINK]
    out = []
    for i in range(n):
        xs = ";".join(f"{s[i, 0] + DOT_X:.1f}" for s in order)
        ys = ";".join(f"{s[i, 1] + DOT_Y:.1f}" for s in order)
        r = RNG.uniform(1.0, 1.7)
        op = RNG.uniform(0.55, 1.0)
        col = palette[RNG.integers(len(palette))]
        out.append(
            f'<circle cx="{p[i, 0] + DOT_X:.1f}" cy="{p[i, 1] + DOT_Y:.1f}" r="{r:.1f}" '
            f'fill="{col}" opacity="{op:.2f}">'
            f'<animate attributeName="cx" dur="{DUR}s" repeatCount="indefinite" '
            f'keyTimes="{KEY_TIMES}" values="{xs}"/>'
            f'<animate attributeName="cy" dur="{DUR}s" repeatCount="indefinite" '
            f'keyTimes="{KEY_TIMES}" values="{ys}"/></circle>'
        )
    return "\n".join(out)


def visual_map_frame():
    x, y, s, c = MAP_X, MAP_Y, 300, 16
    corners = "".join(
        f'<path d="M{cx},{cy + dy * c} V{cy} H{cx + dx * c}" />'
        for cx, cy, dx, dy in [(x, y, 1, 1), (x + s, y, -1, 1),
                               (x, y + s, 1, -1), (x + s, y + s, -1, -1)]
    )
    return f"""
<text x="{x}" y="{y - 10}" fill="{CYAN}" font-size="12" letter-spacing="2">VISUAL.MAP</text>
<text x="{x + s}" y="{y - 10}" fill="{MUTED}" font-size="11" text-anchor="end">[particles]</text>
<rect x="{x}" y="{y}" width="{s}" height="{s}" fill="{PANEL}" stroke="{PURPLE}" stroke-opacity=".35"/>
<g fill="none" stroke="{CYAN}" stroke-width="2.5" filter="url(#glow)">{corners}</g>
<rect x="{x}" y="{y}" width="{s}" height="2" fill="{CYAN}" opacity=".25">
  <animate attributeName="y" values="{y};{y + s - 2};{y}" dur="6s" repeatCount="indefinite"/>
</rect>"""


def info_panel(p):
    """The SYSTEM.INFO text block, with dotted leaders between key and value."""
    def row(key, value, y, max_len=40):
        value = str(value)
        if len(value) > max_len:
            value = value[: max_len - 1] + "…"
        dots = " " + "." * (16 - len(key)) + " "
        return (f'<text x="400" y="{y}" xml:space="preserve">'
                f'<tspan fill="{CYAN}">{esc(key)}</tspan>'
                f'<tspan fill="{MUTED}">{dots}</tspan>'
                f'<tspan fill="{TEXT}">{esc(value)}</tspan></text>')

    def header(label, y):
        return f'<text x="400" y="{y}" fill="{PURPLE}" font-size="12">// {esc(label)}</text>'

    def short(url):
        return url.replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")

    c, k = p["contact"], p["core"]
    lines = [
        ("h", "SYSTEM.INFO"),
        ("r", "Subject", p["display_name"]), ("r", "Role", p["role"]),
        ("r", "Origin", p["origin"]), ("r", "Education", p["education"]),
        ("r", "Status", p["status"]), ("r", "ToolChain", p["toolchain"]),
        ("h", "CORE.MODULES"),
        ("r", "Core.Lang", k["Lang"]), ("r", "Core.Frontend", k["Frontend"]),
        ("r", "Core.Backend", k["Backend"]), ("r", "Core.Database", k["Database"]),
        ("r", "Core.Infra", k["Infra"]),
        ("h", "CONTACT"),
        ("r", "Grid.Mail", c["email"]), ("r", "Grid.LinkedIn", short(c["linkedin"])),
        ("r", "Grid.GitHub", short(c["github"])),
    ]
    out, y = [], 72
    for item in lines:
        if item[0] == "h":
            if y > 72:
                y += 4
            out.append(header(item[1], y))
        else:
            out.append(row(item[1], item[2], y))
        y += 17
    # prompt line with a blinking cursor
    y += 4
    # the cursor is a tspan so it always sits right after the text, whatever the font
    out.append(f'<text x="400" y="{y}" fill="{GREEN}" xml:space="preserve">thisuri@grid:~$ '
               f'<tspan fill="{TEXT}">whoami </tspan><tspan fill="{CYAN}">█'
               f'<animate attributeName="opacity" values="1;0;1" dur="1s" calcMode="discrete" '
               f'repeatCount="indefinite"/></tspan></text>')
    return "\n".join(out)


def window_chrome(title):
    return f"""
<circle cx="24" cy="20" r="6" fill="#ff5f57"/><circle cx="44" cy="20" r="6" fill="#febc2e"/>
<circle cx="64" cy="20" r="6" fill="#28c840"/>
<text x="{W / 2}" y="24" fill="{MUTED}" font-size="12" text-anchor="middle">{esc(title)}</text>
<line x1="2" y1="38" x2="{W - 2}" y2="38" stroke="{PURPLE}" stroke-opacity=".35"/>"""


def build_hero(p):
    n = int(p.get("dot_count", 1500))
    photo = load_photo(ROOT / p.get("photo", "assets/photo.jpg"), p.get("photo_crop"))
    shapes = [
        portrait_points(photo, n),
        mask_points(brackets_mask(), n),
        mask_points(triangle_mask(), n),
        mask_points(logo_mask(), n),
    ]
    shapes = [sort_xy(s) for s in shapes]

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}" font-size="13">
<title>{esc(p['display_name'])} - SYSTEM.INFO</title>
{defs_glow()}
{frame(W, H)}
{window_chrome(f"{p['username']} / README.md")}
{visual_map_frame()}
<g>
{dots_svg(shapes)}
</g>
{info_panel(p)}
<text x="40" y="402" fill="{MUTED}" font-size="11">[ok] particles: {n}   mode: morph   loop: {DUR}s</text>
<text x="{W - 24}" y="402" fill="{GREEN}" font-size="11" text-anchor="end">● online</text>
</svg>"""
    write_svg("hero.svg", svg)


# ====================================================================
# 3. Footer link buttons (one SVG each, so each can be its own link)
# ====================================================================
ICONS = {
    # simple hand-made glyphs, drawn in a 24x24 box
    "linkedin": '<rect x="2" y="2" width="20" height="20" rx="4" fill="none" stroke-width="2"/>'
                '<text x="12" y="17" font-size="12" font-weight="bold" text-anchor="middle" '
                'stroke="none" fill="currentColor">in</text>',
    "github": '<path d="M8 6 L2 12 L8 18 M16 6 L22 12 L16 18 M14 4 L10 20" fill="none" stroke-width="2.2" '
              'stroke-linecap="round" stroke-linejoin="round"/>',
    "email": '<rect x="2" y="5" width="20" height="14" rx="2" fill="none" stroke-width="2"/>'
             '<path d="M3 6 L12 13 L21 6" fill="none" stroke-width="2"/>',
}


def build_links():
    for key, label, color in [("linkedin", "LinkedIn", CYAN), ("github", "GitHub", PURPLE),
                              ("email", "Email", PINK)]:
        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="170" height="46" viewBox="0 0 170 46" font-family="{FONT}">
<title>{label}</title>
{defs_glow()}
<rect x="2" y="2" width="166" height="42" rx="10" fill="{BG}" stroke="{color}" stroke-width="1.5" filter="url(#glow)"/>
<g transform="translate(18 11)" stroke="{color}" color="{color}" filter="url(#glow)">{ICONS[key]}</g>
<text x="56" y="28" fill="{TEXT}" font-size="14">{label}<tspan fill="{color}">_</tspan></text>
</svg>"""
        write_svg(f"link-{key}.svg", svg)


if __name__ == "__main__":
    profile = load_profile()
    build_hero(profile)
    build_links()
