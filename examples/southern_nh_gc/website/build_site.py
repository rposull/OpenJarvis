#!/usr/bin/env python3
"""Generate SEO landing pages, guides, and sitemap for the GC website.

Run from repo root or website folder:
    python3 examples/southern_nh_gc/website/build_site.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
BIZ: dict = json.loads((DATA / "business.json").read_text(encoding="utf-8"))
SITE_URL = BIZ["siteUrl"].rstrip("/")
BUSINESS_NAME = BIZ["businessName"]
LOGO_SHORT = BIZ.get("logoShort") or BUSINESS_NAME


def load_json(name: str) -> list | dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def phone_tel() -> str:
    digits = "".join(c for c in BIZ.get("phone", "") if c.isdigit())[-10:]
    return f"tel:+1{digits}" if len(digits) == 10 else "tel:"


def write_site_config() -> None:
    lines = [
        "/** Auto-generated from data/business.json — edit that file, then run build_site.py */",
        "window.SITE_CONFIG = " + json.dumps(BIZ, indent=2) + ";",
        "",
    ]
    write(ROOT / "site-config.js", "\n".join(lines))


def rel(depth: int, path: str) -> str:
    prefix = "../" * depth if depth else ""
    return f"{prefix}{path}"


def page_shell(
    *,
    depth: int,
    body: str,
    page_seo: dict,
    nav_extra: str = "",
) -> str:
    assets = rel(depth, "")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Loading…</title>
  <link rel="stylesheet" href="{assets}styles.css">
  <script>
    window.PAGE_SEO = {json.dumps(page_seo)};
  </script>
  <script src="{assets}site-config.js"></script>
  <script src="{assets}seo.js"></script>
</head>
<body>
  <header class="site-header">
    <div class="container header-inner">
      <a href="{assets}index.html" class="logo" id="logo-text">{LOGO_SHORT}</a>
      <nav class="nav" id="main-nav">
        <a href="{assets}decks/">Decks</a>
        <a href="{assets}garages/">Garages</a>
        <a href="{assets}additions/">Additions</a>
        <a href="{assets}locations/">Service Areas</a>
        <a href="{assets}guides/">Guides</a>
        <a href="{assets}index.html#contact" class="nav-cta">Free Estimate</a>
        {nav_extra}
      </nav>
      <button class="menu-btn" id="menu-btn" aria-label="Open menu">☰</button>
    </div>
  </header>

  <main>
{body}
  </main>

  <footer class="site-footer">
    <div class="container footer-inner">
      <span id="footer-copy">© {date.today().year} {BUSINESS_NAME}. All rights reserved.</span>
      <span><a href="{assets}locations/">Service areas</a> · <a href="{assets}guides/">Guides</a></span>
    </div>
  </footer>

  <script src="{assets}script.js"></script>
</body>
</html>
"""


def cta_block(depth: int, headline: str = "Get a free estimate") -> str:
    a = rel(depth, "")
    return f"""
    <section class="cta-band">
      <div class="container cta-band-inner">
        <h2>{headline}</h2>
        <p>Written quote with scope of work — we respond within one business day.</p>
        <div class="hero-actions" style="justify-content:center">
          <a href="{a}index.html#contact" class="btn btn-primary">Request Estimate</a>
          <a href="{phone_tel()}" class="btn btn-secondary" id="hero-phone">Call {BIZ.get("phone", "Now")}</a>
        </div>
      </div>
    </section>"""


def breadcrumbs_html(items: list[tuple[str, str]]) -> str:
    parts = []
    for i, (label, href) in enumerate(items):
        if i < len(items) - 1:
            parts.append(f'<a href="{href}">{label}</a>')
        else:
            parts.append(f"<span>{label}</span>")
    return f'<nav class="breadcrumbs" aria-label="Breadcrumb">{" › ".join(parts)}</nav>'


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def build_service_pages() -> list[str]:
    urls: list[str] = []
    services = [
        {
            "slug": "decks",
            "title": "Deck Builder Southern NH",
            "h1": "Custom deck builder in southern New Hampshire",
            "description": "Licensed deck builder in southern NH. New decks, rebuilds, composite & pressure-treated. Permits included. Free estimates.",
            "intro": "We build decks that handle New Hampshire winters — proper footings below frost line, corrosion-resistant fasteners, and railings to code.",
            "bullets": [
                "Pressure-treated and composite decking",
                "New builds, tear-offs, and expansions",
                "Stairs, landings, and multi-level designs",
                "Permits and inspections handled for you",
            ],
            "faq": [
                ("How long does a deck take?", "Most residential decks take 5–10 crew-days depending on size, height, and railing complexity."),
                ("Do you pull permits?", "Yes. We handle permit applications and schedule inspections with your town."),
                ("Composite or wood?", "Both. We'll recommend based on budget, maintenance preference, and sun exposure."),
            ],
        },
        {
            "slug": "garages",
            "title": "Garage Builder Southern NH",
            "h1": "Garage construction in southern New Hampshire",
            "description": "Detached and attached garage builder in southern NH. Slab, framing, roof, siding. Licensed GC. Free estimates.",
            "intro": "From single-car detached garages to larger shop spaces, we deliver slab, framing, roof, siding, and openings with a clear materials-and-labor quote.",
            "bullets": [
                "Detached and attached garages",
                "Concrete slab and frost-wall foundations",
                "Framing, roof, siding, and door openings",
                "Sized for vehicles, storage, or workshop use",
            ],
            "faq": [
                ("Detached vs attached?", "Detached is often simpler for permits and fire separation. Attached can add convenience — we'll advise for your lot."),
                ("What's included in the quote?", "Materials package and labor package with a detailed scope — foundation through dried-in shell."),
                ("Do I need a permit?", "Almost always in NH. We handle the application and inspections."),
            ],
        },
        {
            "slug": "additions",
            "title": "Home Addition Contractor Southern NH",
            "h1": "Home additions & bump-outs in southern New Hampshire",
            "description": "Home addition contractor in southern NH. Room additions, bump-outs, foundation to shell. Licensed GC. Free estimates.",
            "intro": "Single-story additions tied into your existing home — foundation, framing, roof tie-in, and exterior envelope with a written scope before we start.",
            "bullets": [
                "Room additions and bump-outs",
                "Foundation and structural tie-in",
                "Roof integration with existing home",
                "Exterior siding and weather barrier",
            ],
            "faq": [
                ("How do you price additions?", "Per square foot with separate materials and labor lines so you see where the budget goes."),
                ("Do you finish interiors?", "We focus on shell and structural work. Interior finish can be quoted separately or by your preferred trades."),
                ("Timeline?", "Typical single-story additions run several weeks after permits — we'll give a realistic schedule in your quote."),
            ],
        },
    ]

    for svc in services:
        slug = svc["slug"]
        depth = 1
        canonical = f"{SITE_URL}/{slug}/"
        crumbs = breadcrumbs_html(
            [
                ("Home", rel(depth, "index.html")),
                (svc["title"].split(" Southern")[0], ""),
            ]
        )
        faq_html = "\n".join(
            f"""          <details class="faq-item">
            <summary>{q}</summary>
            <p>{a}</p>
          </details>"""
            for q, a in svc["faq"]
        )
        bullets = "\n".join(f"            <li>{b}</li>" for b in svc["bullets"])
        body = f"""
    <section class="page-hero">
      <div class="container">
        {crumbs}
        <h1>{svc["h1"]}</h1>
        <p class="lead">{svc["intro"]}</p>
      </div>
    </section>

    <section>
      <div class="container content-narrow">
        <h2>What's included</h2>
        <ul class="check-list">
{bullets}
        </ul>
        <h2>Common questions</h2>
        <div class="faq-list">
{faq_html}
        </div>
      </div>
    </section>
{cta_block(depth)}
"""
        page_seo = {
            "title": f"{svc['title']} | {BUSINESS_NAME}",
            "description": svc["description"],
            "canonical": canonical,
            "breadcrumbs": [
                {"name": "Home", "url": f"{SITE_URL}/"},
                {"name": svc["title"].split(" Southern")[0], "url": canonical},
            ],
        }
        write(ROOT / slug / "index.html", page_shell(depth=depth, body=body, page_seo=page_seo))
        urls.append(canonical)
    return urls


def build_location_pages() -> list[str]:
    urls: list[str] = []
    towns = load_json("towns.json")

    # Index page listing all towns
    depth = 1
    cards = "\n".join(
        f"""        <a class="location-card" href="{t["slug"]}.html">
          <h3>{t["name"]}, NH</h3>
          <p>{t["blurb"][:120]}…</p>
          <span class="card-link">View services →</span>
        </a>"""
        for t in towns
    )
    index_body = f"""
    <section class="page-hero">
      <div class="container">
        {breadcrumbs_html([("Home", rel(depth, "index.html")), ("Service Areas", "")])}
        <h1>Deck, garage &amp; addition contractor — southern NH towns</h1>
        <p class="lead">We serve homeowners across Hillsborough and Rockingham counties with permitted, code-compliant construction.</p>
      </div>
    </section>
    <section>
      <div class="container location-grid">
{cards}
      </div>
    </section>
{cta_block(depth)}
"""
    write(
        ROOT / "locations" / "index.html",
        page_shell(
            depth=depth,
            body=index_body,
            page_seo={
                "title": f"Service Areas — {BUSINESS_NAME}",
                "description": "Deck builder, garage builder, and home addition contractor serving Nashua, Manchester, Merrimack, Bedford, and southern NH.",
                "canonical": f"{SITE_URL}/locations/",
                "breadcrumbs": [
                    {"name": "Home", "url": f"{SITE_URL}/"},
                    {"name": "Service Areas", "url": f"{SITE_URL}/locations/"},
                ],
            },
        ),
    )
    urls.append(f"{SITE_URL}/locations/")

    for town in towns:
        name = town["name"]
        slug = town["slug"]
        depth = 1
        canonical = f"{SITE_URL}/locations/{slug}.html"
        body = f"""
    <section class="page-hero">
      <div class="container">
        {breadcrumbs_html([
            ("Home", rel(depth, "index.html")),
            ("Service Areas", rel(depth, "locations/index.html")),
            (f"{name}, NH", ""),
        ])}
        <h1>Deck, garage &amp; addition contractor in {name}, NH</h1>
        <p class="lead">{town["blurb"]}</p>
      </div>
    </section>

    <section>
      <div class="container content-narrow">
        <h2>Services in {name}</h2>
        <div class="services-grid">
          <article class="service-card">
            <h3><a href="{rel(depth, "decks/")}">Decks</a></h3>
            <p>Custom decks built to NH code — footings, framing, decking, and railings. Free estimates in {name}.</p>
          </article>
          <article class="service-card">
            <h3><a href="{rel(depth, "garages/")}">Garages</a></h3>
            <p>Detached and attached garages with slab, framing, roof, and siding for {name} homeowners.</p>
          </article>
          <article class="service-card">
            <h3><a href="{rel(depth, "additions/")}">Home additions</a></h3>
            <p>Room additions and bump-outs with foundation, structural tie-in, and exterior shell.</p>
          </article>
        </div>
        <h2>Why {name} homeowners work with us</h2>
        <ul class="check-list">
          <li>Licensed general contractor — permits and inspections handled</li>
          <li>Written quotes with detailed scope of work</li>
          <li>Local crew familiar with {town["county"]} County building requirements</li>
          <li>Decks, garages, and additions — our focus, not a side job</li>
        </ul>
        <p>Also serving nearby towns: <a href="{rel(depth, "locations/index.html")}">view all service areas</a>.</p>
      </div>
    </section>
{cta_block(depth, f"Free estimate in {name}")}
"""
        page_seo = {
            "title": f"Deck & Garage Builder {name} NH | {BUSINESS_NAME}",
            "description": f"Licensed contractor in {name}, NH. Decks, garages, and home additions. Permits included. Free estimates.",
            "canonical": canonical,
            "breadcrumbs": [
                {"name": "Home", "url": f"{SITE_URL}/"},
                {"name": "Service Areas", "url": f"{SITE_URL}/locations/"},
                {"name": f"{name}, NH", "url": canonical},
            ],
            "jsonLd": {
                "@context": "https://schema.org",
                "@type": "Service",
                "name": f"Deck and garage construction in {name}, NH",
                "provider": {"@type": "GeneralContractor", "name": BUSINESS_NAME},
                "areaServed": {"@type": "City", "name": name, "containedInPlace": "New Hampshire"},
            },
        }
        write(ROOT / "locations" / f"{slug}.html", page_shell(depth=depth, body=body, page_seo=page_seo))
        urls.append(canonical)
    return urls


def build_guides() -> list[str]:
    urls: list[str] = []
    guides = [
        {
            "slug": "deck-cost-southern-nh",
            "title": "How Much Does a Deck Cost in Southern New Hampshire?",
            "description": "Deck pricing in southern NH: typical cost per square foot, what affects price, and how to budget for permits and materials.",
            "h1": "How much does a deck cost in southern New Hampshire?",
            "content": """
        <p>Most installed decks in southern NH fall in the <strong>$100–$120 per square foot</strong> range for a standard
        pressure-treated deck with railing and stairs. Composite decking runs higher. A typical 12×16 deck (192 sqft)
        often lands between <strong>$19,000 and $24,000</strong> all-in, including permits.</p>
        <h2>What drives deck price</h2>
        <ul>
          <li><strong>Size and height</strong> — Larger decks and raised designs need more footings and lumber.</li>
          <li><strong>Material</strong> — Composite costs more upfront but needs less maintenance.</li>
          <li><strong>Railing & stairs</strong> — Cable, aluminum, and multi-level stairs add labor.</li>
          <li><strong>Site access</strong> — Tight backyards or rocky soil can increase excavation time.</li>
          <li><strong>Permits</strong> — Town fees vary; we include permit handling in our quotes.</li>
        </ul>
        <h2>Get a real number for your yard</h2>
        <p>Online calculators miss frost depth, ledger details, and local code. A site visit and written scope
        is the only way to know your true price. We provide free estimates across southern NH.</p>
""",
        },
        {
            "slug": "garage-building-permit-nh",
            "title": "Garage Building Permits in NH: What Homeowners Need to Know",
            "description": "NH garage permit requirements: setbacks, frost walls, electrical, and what your town inspector checks.",
            "h1": "Garage building permits in New Hampshire",
            "content": """
        <p>Almost every detached or attached garage in New Hampshire requires a building permit from your town or city.
        Skipping permits can block future home sales and insurance claims — it's not worth the risk.</p>
        <h2>What towns typically require</h2>
        <ul>
          <li>Plot plan showing setbacks from property lines</li>
          <li>Foundation details — slab or frost-wall depth (4 ft in most of southern NH)</li>
          <li>Framing and roof plans scaled to the structure</li>
          <li>Electrical permit if you're adding panels, lights, or outlets</li>
        </ul>
        <h2>Setbacks and HOA rules</h2>
        <p>Each town has minimum setbacks from side and rear lines. HOAs may add design rules on top.
        We verify requirements before quoting so there are no surprises after you sign.</p>
        <h2>We handle permits for you</h2>
        <p>Our quotes include permit applications, revision cycles, and scheduling inspections —
        so you don't spend evenings in the building department lobby.</p>
""",
        },
        {
            "slug": "deck-vs-patio-nh",
            "title": "Deck vs Patio in NH: Which Is Right for Your Home?",
            "description": "Deck or patio in New Hampshire? Compare cost, frost heave, maintenance, and resale for sloped vs flat yards.",
            "h1": "Deck vs patio in New Hampshire",
            "content": """
        <p>Both decks and patios extend living space, but NH's freeze-thaw cycles and sloped lots favor different solutions.</p>
        <h2>Choose a deck when…</h2>
        <ul>
          <li>Your yard slopes away from the house</li>
          <li>You want elevated views or walk-out access from a second floor</li>
          <li>You prefer wood or composite underfoot (warmer than concrete in spring)</li>
        </ul>
        <h2>Choose a patio when…</h2>
        <ul>
          <li>You have a flat, well-drained area close to grade</li>
          <li>You want pavers or stamped concrete aesthetics</li>
          <li>Budget is tight for a small ground-level space (we focus on decks — ask for referrals)</li>
        </ul>
        <h2>Maintenance in NH winters</h2>
        <p>Decks need periodic sealing (wood) or simple cleaning (composite). Patios can heave if base prep is wrong.
        Proper footings and drainage matter for both — that's where a licensed contractor earns their fee.</p>
""",
        },
    ]

    depth = 1
    cards = "\n".join(
        f"""        <a class="guide-card" href="{g["slug"]}.html">
          <h3>{g["title"]}</h3>
          <p>{g["description"][:100]}…</p>
          <span class="card-link">Read guide →</span>
        </a>"""
        for g in guides
    )
    write(
        ROOT / "guides" / "index.html",
        page_shell(
            depth=depth,
            body=f"""
    <section class="page-hero">
      <div class="container">
        {breadcrumbs_html([("Home", rel(depth, "index.html")), ("Guides", "")])}
        <h1>Home improvement guides for southern NH</h1>
        <p class="lead">Practical advice on decks, garages, permits, and budgeting — from a local contractor.</p>
      </div>
    </section>
    <section>
      <div class="container guide-grid">
{cards}
      </div>
    </section>
{cta_block(depth)}
""",
            page_seo={
                "title": f"Guides — {BUSINESS_NAME}",
                "description": "Deck cost, garage permits, and home improvement guides for southern New Hampshire homeowners.",
                "canonical": f"{SITE_URL}/guides/",
            },
        ),
    )
    urls.append(f"{SITE_URL}/guides/")

    for g in guides:
        canonical = f"{SITE_URL}/guides/{g['slug']}.html"
        body = f"""
    <section class="page-hero">
      <div class="container">
        {breadcrumbs_html([
            ("Home", rel(depth, "index.html")),
            ("Guides", rel(depth, "guides/index.html")),
            (g["title"][:40] + "…" if len(g["title"]) > 40 else g["title"], ""),
        ])}
        <h1>{g["h1"]}</h1>
      </div>
    </section>
    <article class="container content-narrow prose">
{g["content"]}
      <p class="article-cta"><a href="{rel(depth, "index.html")}#contact" class="btn btn-primary">Get a free estimate</a></p>
    </article>
"""
        write(
            ROOT / "guides" / f"{g['slug']}.html",
            page_shell(
                depth=depth,
                body=body,
                page_seo={
                    "title": f"{g['title']} | {BUSINESS_NAME}",
                    "description": g["description"],
                    "canonical": canonical,
                    "ogType": "article",
                    "jsonLd": {
                        "@context": "https://schema.org",
                        "@type": "Article",
                        "headline": g["title"],
                        "description": g["description"],
                        "author": {"@type": "Organization", "name": BUSINESS_NAME},
                    },
                },
            ),
        )
        urls.append(canonical)
    return urls


def build_sitemap(urls: list[str]) -> None:
    today = date.today().isoformat()
    entries = "\n".join(
        f"""  <url>
    <loc>{u}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>{"1.0" if u == SITE_URL + "/" else "0.8"}</priority>
  </url>"""
        for u in sorted(set(urls))
    )
    write(
        ROOT / "sitemap.xml",
        f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{entries}
</urlset>
""",
    )


def build_robots() -> None:
    write(
        ROOT / "robots.txt",
        f"""User-agent: *
Allow: /

Sitemap: {SITE_URL}/sitemap.xml
""",
    )


def main() -> None:
    print(f"Building SEO pages for {BUSINESS_NAME}…")
    write_site_config()
    urls = [f"{SITE_URL}/"]
    urls.extend(build_service_pages())
    urls.extend(build_location_pages())
    urls.extend(build_guides())
    build_sitemap(urls)
    build_robots()
    print(f"Done — {len(urls)} URLs in sitemap.")


if __name__ == "__main__":
    main()
