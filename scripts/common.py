"""Shared helpers for the profile generators: theme colours, file paths,
loading profile.json, XML escaping and a tiny GitHub GraphQL client."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import requests

# ---------------------------------------------------------------- paths
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

# ---------------------------------------------------------------- theme
# Every SVG paints its own opaque navy background so it looks the same
# on GitHub's light and dark themes.
BG = "#070b1f"          # deep navy page
PANEL = "#0d1433"       # slightly lighter panel
CYAN = "#22e4ff"
PURPLE = "#a855f7"
PINK = "#ff4fd8"
TEXT = "#c9d6ff"
MUTED = "#6b7aa8"
GREEN = "#3dffa0"

# GitHub-rendered SVGs cannot load web fonts, so we only name local fonts.
FONT = "'JetBrains Mono','Fira Code',Consolas,'Courier New',monospace"

# Colours for languages (falls back to a rotating neon list).
LANG_COLORS = {
    "Python": "#3572A5", "Java": "#f89820", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "HTML": "#e34c26", "CSS": "#663399",
    "C": "#a8b9cc", "C++": "#f34b7d", "C#": "#178600", "Go": "#00ADD8",
    "Jupyter Notebook": "#DA5B0B", "Kotlin": "#A97BFF", "Dart": "#00B4AB",
    "Shell": "#89e051", "PHP": "#4F5D95", "Rust": "#dea584",
}
NEON_CYCLE = [CYAN, PURPLE, PINK, GREEN, "#ffd84f", "#4f8bff"]


def lang_color(name, i=0):
    return LANG_COLORS.get(name, NEON_CYCLE[i % len(NEON_CYCLE)])


def esc(text):
    """Escape text so it is safe inside SVG/XML."""
    return escape(str(text), {'"': "&quot;"})


def load_profile():
    with open(ROOT / "profile.json", encoding="utf-8") as f:
        return json.load(f)


def write_svg(name, svg):
    path = ASSETS / name
    path.write_text(svg, encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)}  ({path.stat().st_size / 1024:.0f} KB)")


# Glow filter + neon frame reused by several SVGs.
def defs_glow():
    return f"""<defs>
  <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
    <feGaussianBlur stdDeviation="3" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <linearGradient id="neon" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="{CYAN}"/><stop offset="1" stop-color="{PURPLE}"/>
  </linearGradient>
</defs>"""


def frame(w, h):
    """Opaque background plus glowing gradient border."""
    return (f'<rect width="{w}" height="{h}" rx="14" fill="{BG}"/>'
            f'<rect x="2" y="2" width="{w-4}" height="{h-4}" rx="13" fill="none" '
            f'stroke="url(#neon)" stroke-width="1.6" filter="url(#glow)" opacity="0.9"/>')


# ---------------------------------------------------------------- GitHub
def github_token():
    return os.environ.get("GITHUB_TOKEN", "").strip()


def graphql(query, variables):
    """Run a GraphQL query. Returns the `data` dict, or None if no token / error."""
    token = github_token()
    if not token:
        return None
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"bearer {token}"},
        timeout=30,
    )
    if r.status_code != 200:
        print("GraphQL HTTP error:", r.status_code, r.text[:200])
        return None
    body = r.json()
    if "errors" in body:
        print("GraphQL errors:", body["errors"])
        return None
    return body["data"]


def time_ago(iso):
    """'2026-11-01T00:00:00Z' -> '16 days ago'."""
    then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    secs = (datetime.now(timezone.utc) - then).total_seconds()
    for unit, size in (("year", 31536000), ("month", 2592000), ("day", 86400),
                       ("hour", 3600), ("minute", 60)):
        if secs >= size:
            n = int(secs // size)
            return f"{n} {unit}{'s' if n > 1 else ''} ago"
    return "just now"
