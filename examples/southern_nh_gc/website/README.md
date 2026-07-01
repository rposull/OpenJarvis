# Southern NH GC — Traffic-Ready Website

SEO-focused static site for your general contracting business. Built to rank for local searches like **"deck builder Nashua NH"** and capture leads into your OpenJarvis workflow.

## What's included

| Layer | Purpose |
|-------|---------|
| **Homepage** | Hero, services, process, town links, guides, contact form |
| **Service pages** | `/decks/`, `/garages/`, `/additions/` — target trade keywords |
| **Town pages** | 10 southern NH towns — target "contractor in [town]" searches |
| **Guides** | 3 articles — deck cost, garage permits, deck vs patio |
| **SEO** | Schema.org, Open Graph, sitemap, robots.txt, canonical URLs |
| **Analytics** | GA4 and Plausible hooks in `site-config.js` |

## Quick start

1. Edit **`data/business.json`** — business name, phone, email, domain, analytics.
2. Regenerate pages after any change:

   ```bash
   cd examples/southern_nh_gc/website
   python3 build_site.py
   ```

3. Preview locally:

   ```bash
   python3 -m http.server 8080
   ```

   Visit http://localhost:8080

## Contact form → your inbox

Submissions go **directly to the email in `data/business.json`** via [FormSubmit](https://formsubmit.co) (free, no account needed).

**One-time setup after deploy:** submit a test request on your live site. FormSubmit emails you an activation link — click it once and all future leads arrive in your inbox.

Optional override: set `formspreeId` in `business.json` if you prefer Formspree instead.

## Deploy (free)

**Netlify (recommended)**

1. Connect repo with publish directory `examples/southern_nh_gc/website`
2. Build command: `python3 build_site.py` (already in `netlify.toml`)
3. Add your custom domain and set `siteUrl` in `site-config.js`

**Vercel / Cloudflare Pages**

Same folder, same build command.

## Get traffic — action checklist

The site is the foundation. Traffic comes from doing these steps after deploy:

### 1. Google Business Profile (highest ROI)

- Claim your listing at https://business.google.com
- Category: **General Contractor** + **Deck Builder**
- Service areas: every town in `data/towns.json`
- Add 10+ photos (before/after, crew, trucks)
- Link website to your live domain
- Ask every happy customer for a Google review

### 2. Submit to Google Search Console

1. Verify domain ownership
2. Submit `sitemap.xml` (e.g. `https://yoursite.com/sitemap.xml`)
3. Request indexing for homepage + top 3 town pages

### 3. Local citations (NAP consistency)

List your **exact** name, address, phone on:

- Yelp, Angi, HomeAdvisor, BBB
- Facebook Business Page
- NH contractor directories

Use the same phone and business name everywhere — Google matches citations.

### 4. Content that compounds

- Add one guide per month (`guides/` — edit `build_site.py` or add HTML)
- Post project photos on Google Business with town names in captions
- Add towns to `data/towns.json` and re-run `build_site.py`

### 5. Connect leads to automation

Form submissions email **rposull@hotmail.com** automatically via FormSubmit.

**FormSubmit → OpenJarvis** (advanced): forward FormSubmit emails to a webhook or parse with Zapier/Make for `lead_scan.py` / `follow_up.py`.

### 6. Track what works

Set `ga4Id` in `site-config.js`. Watch:

- Which town pages get traffic (Search Console → Pages)
- Contact form submissions
- Phone calls (use a tracking number or ask "how did you find us?")

## Customize

| File | Purpose |
|------|---------|
| `data/business.json` | **Single source of truth** — name, phone, domain (regenerates site-config.js) |
| `site-config.js` | Auto-generated from business.json — do not edit by hand |
| `data/towns.json` | Town landing page content — add more towns here |
| `build_site.py` | Regenerates town/service/guide pages + sitemap |
| `index.html` | Homepage copy |
| `styles.css` | Colors and layout |

## Page count

After `build_site.py`:

- 1 homepage
- 3 service pages
- 11 location pages (index + 10 towns)
- 4 guide pages (index + 3 articles)
- **19 URLs** in sitemap

Add more towns → more indexed pages → more local search surface area.
