"""Generate assets/projects.svg: a 2-column grid of repo cards.

Uses pinned repos first, then most-starred public repos. Without a token
(or with no public repos) it uses `fallback_projects` from profile.json.
"""

import textwrap

from common import (CYAN, FONT, GREEN, MUTED, PANEL, PURPLE, TEXT, defs_glow,
                    esc, frame, graphql, lang_color, load_profile, time_ago,
                    write_svg)

REPO_FIELDS = """
  name description pushedAt
  repositoryTopics(first:3){nodes{topic{name}}}
  languages(first:5, orderBy:{field:SIZE, direction:DESC}){totalSize edges{size node{name}}}
"""


def fetch_projects(login, limit=6):
    q = f"""query($login:String!){{user(login:$login){{
      pinnedItems(first:{limit}, types:REPOSITORY){{nodes{{... on Repository{{{REPO_FIELDS}}}}}}}
      repositories(first:{limit}, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC,
                   orderBy:{{field:STARGAZERS, direction:DESC}}){{nodes{{{REPO_FIELDS}}}}}
    }}}}"""
    data = graphql(q, {"login": login})
    if not data:
        return None
    user = data["user"]
    repos = user["pinnedItems"]["nodes"] or user["repositories"]["nodes"]
    repos = [r for r in repos if r["name"].lower() != login.lower()]   # skip this profile repo
    projects = []
    for r in repos:
        langs = r["languages"]
        main, pct = None, 0.0
        if langs["edges"]:
            main = langs["edges"][0]["node"]["name"]
            pct = 100 * langs["edges"][0]["size"] / max(langs["totalSize"], 1)
        projects.append({
            "name": r["name"],
            "description": r["description"] or "No description yet.",
            "topics": [t["topic"]["name"] for t in r["repositoryTopics"]["nodes"]],
            "language": main,
            "language_pct": pct,
            "updated": r["pushedAt"],
        })
    return projects or None


# ====================================================================
W = 900
CARD_W, CARD_H, GAP = 410, 140, 20


def card(p, x, y, i):
    color = lang_color(p["language"], i) if p["language"] else MUTED
    lines = textwrap.wrap(p["description"], 40)[:2]
    if len(textwrap.wrap(p["description"], 40)) > 2:
        lines[-1] = lines[-1][:37] + "..."
    desc = "".join(f'<text x="18" y="{58 + j * 17}" fill="{TEXT}" font-size="12">{esc(t)}</text>'
                   for j, t in enumerate(lines))

    # topic chips
    chips, cx = [], 18
    for t in p["topics"][:3]:
        w = len(t) * 7 + 16
        chips.append(f'<rect x="{cx}" y="96" width="{w}" height="18" rx="9" fill="none" '
                     f'stroke="{PURPLE}" stroke-opacity=".7"/>'
                     f'<text x="{cx + w / 2}" y="109" fill="{PURPLE}" font-size="11" '
                     f'text-anchor="middle">{esc(t)}</text>')
        cx += w + 6

    # language donut. Featured projects from profile.json have no measured
    # percentage, so their ring is drawn full and shows the language instead.
    r = 26
    circ = 2 * 3.14159 * r
    pct = p.get("language_pct")
    off = circ * (1 - (pct if pct is not None else 100) / 100)
    short = {"TypeScript": "TS", "JavaScript": "JS", "Python": "PY", "Jupyter Notebook": "IPY"}
    lang = p["language"] or "?"
    centre = f"{pct:.0f}%" if pct is not None else short.get(lang, lang[:4].upper())
    footer = (f"updated {time_ago(p['updated'])}" if p.get("updated")
              else p.get("period", ""))
    donut = f"""
  <g transform="translate({CARD_W - 50} 56) rotate(-90)">
    <circle r="{r}" fill="none" stroke="{MUTED}" stroke-opacity=".25" stroke-width="7"/>
    <circle r="{r}" fill="none" stroke="{color}" stroke-width="7" stroke-linecap="round"
      stroke-dasharray="{circ:.1f}" stroke-dashoffset="{off:.1f}" filter="url(#glow)">
      <animate attributeName="stroke-dashoffset" values="{circ:.1f};{off:.1f}" dur="1.4s" fill="freeze"/>
    </circle>
  </g>
  <text x="{CARD_W - 50}" y="60" fill="{TEXT}" font-size="11" text-anchor="middle">{esc(centre)}</text>
  <text x="{CARD_W - 50}" y="102" fill="{MUTED}" font-size="10" text-anchor="middle">{esc(p['language'] or 'n/a')}</text>"""

    return f"""
<g transform="translate({x} {y})">
  <rect width="{CARD_W}" height="{CARD_H}" rx="10" fill="{PANEL}" stroke="url(#neon)" stroke-opacity=".7"/>
  <text x="18" y="32" fill="{CYAN}" font-size="16" font-weight="bold" filter="url(#glow)">{esc(p['name'])}<tspan fill="{PURPLE}">_</tspan></text>
  {desc}
  {''.join(chips)}
  <text x="18" y="{CARD_H - 10}" fill="{MUTED}" font-size="10">{esc(footer)}</text>
  {donut}
</g>"""


def projects_svg(projects, note):
    rows = (len(projects) + 1) // 2
    H = 60 + rows * (CARD_H + GAP)
    cards = "".join(
        card(p, 30 + (i % 2) * (CARD_W + GAP), 50 + (i // 2) * (CARD_H + GAP), i)
        for i, p in enumerate(projects))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<title>Projects</title>
{defs_glow()}
{frame(W, H)}
<text x="24" y="32" fill="{GREEN}" font-size="13">$ <tspan fill="{TEXT}">./projects.sh --all</tspan></text>
<text x="{W - 24}" y="32" fill="{MUTED}" font-size="11" text-anchor="end">{esc(note)}</text>
{cards}
</svg>"""


if __name__ == "__main__":
    p = load_profile()
    projects = None if p.get("use_featured_projects") else fetch_projects(p["username"])
    note = f"{len(projects)} repos" if projects else ""
    if not projects:
        print("using featured_projects from profile.json")
        projects = p["featured_projects"]
        note = "featured"
    write_svg("projects.svg", projects_svg(projects, note))
