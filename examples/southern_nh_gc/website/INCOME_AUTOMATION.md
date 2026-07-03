# Automated income — both tracks

Two income layers on one site:

| Track | What runs automatically | You still do |
|-------|-------------------------|--------------|
| **A — Leads** | Site, SEO, form → email + phone alert | Quote & build (real money) |
| **B — Digital** | Shop page → Gumroad → PDF delivery | Film content to drive traffic (optional) |

---

## Track A — Automated leads (semi-passive)

### 1. Deploy site (one time)

Follow **`DEPLOY.md`** → live at **https://oconstructpm.netlify.app**

### 2. Activate FormSubmit (one time)

Submit the contact form once on the live site → check **rposull@hotmail.com** → click FormSubmit activation link.

### 3. Phone alerts on every lead (5 minutes)

When someone submits the estimate form, you get a **push notification** on your phone.

1. Install **ntfy** app ([iOS](https://apps.apple.com/app/ntfy/id1625396347) / [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy))
2. Subscribe to a **private** topic name (e.g. `oconstructpm-leads-yourname` — don't share it)
3. In **Netlify** → Site configuration → **Environment variables**:
   - `NTFY_TOPIC` = your topic name
4. Redeploy the site (Deploys → Trigger deploy)

The contact form sends a webhook to `/.netlify/functions/form-alert`, which pings ntfy. No code changes needed after this.

**Test:** Submit a test form on the live site. You should get a push within seconds.

### 4. Google Business Profile

Claim listing → link website → add photos → ask customers for reviews. Highest-ROI traffic source early on.

### 5. Optional — schedule follow-ups on a PC

```bash
cd examples/southern_nh_gc
cp .env.example .env   # set NTFY_TOPIC
python3 follow_up.py
```

---

## Track B — Automated digital sales (passive)

### 1. Create Gumroad products (one time, ~20 min)

1. Sign up at **https://gumroad.com** (free to start; they take a small fee per sale)
2. Create two products:

| Product | Price | PDF to upload |
|---------|-------|---------------|
| Southern NH Deck & Garage Permit Checklist | $19 | `products/deck-garage-permit-checklist.md` → export as PDF |
| How to Read a Contractor Quote | $9 | `products/how-to-read-contractor-quote.md` → export as PDF |

**Make PDFs:** Open the `.md` file in any editor → Print → Save as PDF. Or paste into Google Docs → Download PDF.

3. In Gumroad, enable **instant delivery** and attach the PDF to each product.
4. Copy each product's **link** (e.g. `https://yourname.gumroad.com/l/permit-checklist`)

### 2. Wire links into the site

Edit **`data/business.json`**:

```json
"digitalProducts": {
  "provider": "gumroad",
  "permitChecklistUrl": "https://YOURNAME.gumroad.com/l/permit-checklist",
  "quoteGuideUrl": "https://YOURNAME.gumroad.com/l/quote-guide",
  "bundleUrl": ""
}
```

Rebuild and redeploy:

```bash
cd examples/southern_nh_gc/website
python3 build_site.py
git add -A && git commit -m "Add Gumroad links" && git push
```

Buy buttons on `/shop/` will open Gumroad checkout overlay. **Payment and PDF delivery are fully automated.**

### 3. Drive traffic (batch monthly)

| Channel | Effort | Automation after post |
|---------|--------|------------------------|
| YouTube Shorts (job-site tips) | 2×/month | Video works forever |
| Free guides on site (`/guides/`) | Already built | SEO compounds |
| Link shop in video descriptions | Copy/paste once per video | Permanent |

**Example Short titles:**
- "What a deck permit costs in Nashua NH"
- "3 things missing from bad contractor quotes"
- "Garage setback mistake homeowners make"

Description template:
```
Free estimate: https://oconstructpm.netlify.app
Permit checklist ($19): https://oconstructpm.netlify.app/shop/permit-checklist.html
Call (978) 888-8068
```

---

## What runs without you

| Event | Automated response |
|-------|-------------------|
| Someone Googles "deck builder Nashua" | SEO pages work 24/7 |
| Form submit | Email to rposull@hotmail.com + ntfy push |
| Gumroad purchase | Payment processed + PDF emailed to buyer |
| Old quote sitting open | `follow_up.py` reminder (if scheduled) |

---

## Realistic expectations

| Source | Month 1–3 | Month 6+ |
|--------|-----------|----------|
| Construction leads | 0–5 inquiries | Grows with reviews + SEO |
| Digital PDF sales | $0–50 | $50–300 if you post content |
| YouTube AdSense | $0 | Ignore until 1k subs |

**One closed deck job (~$15k+) beats years of PDF sales.** Run both tracks: jobs fund life; digital products compound while you sleep.

---

## Quick checklist

- [ ] Netlify deploy live
- [ ] FormSubmit activated
- [ ] `NTFY_TOPIC` set in Netlify → test push alert
- [ ] Google Business Profile live
- [ ] Gumroad products created + PDFs uploaded
- [ ] `permitChecklistUrl` + `quoteGuideUrl` in `business.json`
- [ ] First YouTube Short with shop link in description
