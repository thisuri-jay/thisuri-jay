"""Generate assets/stats.svg (contributions + streaks) and
assets/languages.svg (top languages across public repos).

Needs GITHUB_TOKEN for live data. Without it, stats show 0 and languages
use `fallback_languages` from profile.json, so the layout can still be previewed.
"""

from datetime import date, datetime, timedelta

from common import (CYAN, FONT, GREEN, MUTED, PANEL, PINK, PURPLE, TEXT,
                    defs_glow, esc, frame, graphql, lang_color, load_profile,
                    write_svg)


# ====================================================================
# 1. Fetch data
# ====================================================================
def fetch_calendar(login):
    """Return {date: count} for every day since the account was created."""
    data = graphql(
        "query($login:String!){user(login:$login){contributionsCollection{contributionYears}}}",
        {"login": login},
    )
    if not data:
        return None
    days = {}
    for year in data["user"]["contributionsCollection"]["contributionYears"]:
        # one request per year (GitHub limits a collection to one year)
        q = """query($login:String!,$from:DateTime!,$to:DateTime!){
          user(login:$login){contributionsCollection(from:$from,to:$to){
            contributionCalendar{weeks{contributionDays{date contributionCount}}}}}}"""
        d = graphql(q, {"login": login, "from": f"{year}-01-01T00:00:00Z",
                        "to": f"{year}-12-31T23:59:59Z"})
        if not d:
            return None
        for week in d["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for day in week["contributionDays"]:
                days[date.fromisoformat(day["date"])] = day["contributionCount"]
    return days


def compute_stats(days):
    """Total contributions, current streak and longest streak (with date ranges)."""
    today = date.today()
    days = {d: c for d, c in days.items() if d <= today}
    if not days:
        return {"total": 0, "current": 0, "longest": 0, "since": None,
                "current_range": "", "longest_range": ""}

    ordered = sorted(days)
    total = sum(days.values())

    # longest streak: scan forward, counting consecutive days with > 0
    longest, run, best_end, run_start, best_start = 0, 0, None, None, None
    for d in ordered:
        if days[d] > 0:
            if run == 0:
                run_start = d
            run += 1
            if run > longest:
                longest, best_start, best_end = run, run_start, d
        else:
            run = 0

    # current streak: walk back from today (today may still be 0 - that's ok)
    cur, d = 0, today if days.get(today, 0) > 0 else today - timedelta(days=1)
    end = d
    while days.get(d, 0) > 0:
        cur += 1
        d -= timedelta(days=1)

    fmt = lambda x: x.strftime("%b %d")
    return {
        "total": total,
        "current": cur,
        "longest": longest,
        "since": ordered[0],
        "current_range": f"{fmt(d + timedelta(days=1))} - {fmt(end)}" if cur else "start one today",
        "longest_range": f"{fmt(best_start)} - {fmt(best_end)}" if longest else "-",
    }


def fetch_languages(login):
    """Return [(name, bytes)] summed over the user's public, non-fork repos."""
    q = """query($login:String!){user(login:$login){
      repositories(first:100, ownerAffiliations:OWNER, isFork:false, privacy:PUBLIC){
        nodes{languages(first:10, orderBy:{field:SIZE, direction:DESC}){
          edges{size node{name}}}}}}}"""
    data = graphql(q, {"login": login})
    if not data:
        return None
    totals = {}
    for repo in data["user"]["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            totals[e["node"]["name"]] = totals.get(e["node"]["name"], 0) + e["size"]
    return sorted(totals.items(), key=lambda kv: -kv[1]) or None


# ====================================================================
# 2. Draw
# ====================================================================
W = 900


def stats_svg(s):
    H = 200
    since = s["since"].strftime("%b %Y") if s["since"] else "-"

    def card(x, title, number, sub, color):
        return f"""
<g transform="translate({x} 52)">
  <rect width="270" height="128" rx="10" fill="{PANEL}" stroke="{color}" stroke-opacity=".45"/>
  <text x="135" y="62" fill="{color}" font-size="38" font-weight="bold" text-anchor="middle" filter="url(#glow)">{number}
    <animate attributeName="opacity" values="0;1" dur="1.2s" fill="freeze"/></text>
  <text x="135" y="92" fill="{TEXT}" font-size="13" text-anchor="middle">{esc(title)}</text>
  <text x="135" y="112" fill="{MUTED}" font-size="11" text-anchor="middle">{esc(sub)}</text>
</g>"""

    # ring gauge for the current streak: share of the longest streak
    r = 40
    circ = 2 * 3.14159 * r
    frac = s["current"] / s["longest"] if s["longest"] else 0
    target = circ * (1 - frac)
    ring = f"""
<g transform="translate(315 52)">
  <rect width="270" height="128" rx="10" fill="{PANEL}" stroke="{PURPLE}" stroke-opacity=".6"/>
  <g transform="translate(70 64) rotate(-90)">
    <circle r="{r}" fill="none" stroke="{MUTED}" stroke-opacity=".25" stroke-width="8"/>
    <circle r="{r}" fill="none" stroke="url(#neon)" stroke-width="8" stroke-linecap="round"
      stroke-dasharray="{circ:.1f}" stroke-dashoffset="{target:.1f}" filter="url(#glow)">
      <animate attributeName="stroke-dashoffset" values="{circ:.1f};{target:.1f}" dur="1.6s" fill="freeze"/>
    </circle>
  </g>
  <text x="70" y="76" fill="{PINK}" font-size="30" font-weight="bold" text-anchor="middle" filter="url(#glow)">{s['current']}</text>
  <text x="190" y="58" fill="{TEXT}" font-size="13" text-anchor="middle">Current Streak</text>
  <text x="190" y="80" fill="{MUTED}" font-size="11" text-anchor="middle">{esc(s['current_range'])}</text>
  <text x="190" y="100" fill="{MUTED}" font-size="11" text-anchor="middle">days in a row</text>
</g>"""

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<title>GitHub contribution stats</title>
{defs_glow()}
{frame(W, H)}
<text x="24" y="32" fill="{GREEN}" font-size="13">$ <tspan fill="{TEXT}">./stats.sh --streaks</tspan></text>
{card(30, "Total Contributions", f"{s['total']:,}", f"since {since}", CYAN)}
{ring}
{card(600, "Longest Streak", s['longest'], s['longest_range'], PURPLE)}
</svg>"""


def languages_svg(langs, note):
    total = sum(v for _, v in langs) or 1
    top = langs[:6]
    rest = total - sum(v for _, v in top)
    if rest > 0:
        top.append(("Other", rest))

    bar_x, bar_w, bar_y = 30, W - 60, 60
    rows = (len(top) + 2) // 3
    H = 110 + rows * 24

    segs, legend, x = [], [], bar_x
    for i, (name, val) in enumerate(top):
        pct = 100 * val / total
        w = bar_w * val / total
        color = MUTED if name == "Other" else lang_color(name, i)
        segs.append(f'<rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" height="14" fill="{color}"/>')
        x += w
        lx = 30 + (i % 3) * 290
        ly = 104 + (i // 3) * 24
        legend.append(
            f'<circle cx="{lx + 6}" cy="{ly - 4}" r="5" fill="{color}" filter="url(#glow)"/>'
            f'<text x="{lx + 18}" y="{ly}" fill="{TEXT}" font-size="13">{esc(name)} '
            f'<tspan fill="{MUTED}">{pct:.1f}%</tspan></text>')

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">
<title>Top languages</title>
{defs_glow()}
{frame(W, H)}
<text x="24" y="32" fill="{GREEN}" font-size="13">$ <tspan fill="{TEXT}">cat languages.log</tspan></text>
<text x="{W - 24}" y="32" fill="{MUTED}" font-size="11" text-anchor="end">{esc(note)}</text>
<!-- the clip grows left to right, so the whole bar "fills up" once -->
<clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="14" rx="7">
  <animate attributeName="width" values="0;{bar_w}" dur="1.4s" fill="freeze"/></rect></clipPath>
<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="14" rx="7" fill="{PANEL}"/>
<g clip-path="url(#bar)">{''.join(segs)}</g>
{''.join(legend)}
</svg>"""


# ====================================================================
if __name__ == "__main__":
    p = load_profile()
    login = p["username"]

    days = fetch_calendar(login)
    if days is None:
        print("!! no GITHUB_TOKEN (or API error) - stats.svg will show zeros")
        days = {}
    write_svg("stats.svg", stats_svg(compute_stats(days)))

    langs = fetch_languages(login)
    note = "computed from public repos"
    if not langs:
        print("!! no language data - using fallback_languages from profile.json")
        langs = sorted(p["fallback_languages"].items(), key=lambda kv: -kv[1])
        note = "self-rated focus"
    write_svg("languages.svg", languages_svg(langs, note))
