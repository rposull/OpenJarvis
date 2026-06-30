# Southern NH GC — Business Website

Static marketing site for your general contracting business (decks, garages, additions).

## Quick start

1. Edit **`site-config.js`** with your business name, phone, and email.
2. Open locally:

   ```bash
   cd examples/southern_nh_gc/website
   python3 -m http.server 8080
   ```

   Visit http://localhost:8080

## Contact form

**Option A — Formspree (recommended, free tier)**

1. Sign up at https://formspree.io
2. Create a form and copy your form ID
3. Set `formspreeId: "your_id"` in `site-config.js`

**Option B — mailto fallback**

Leave `formspreeId` empty. Submitting opens the visitor's email client with a pre-filled message.

## Deploy (free)

**Netlify / Vercel**

- Drag the `website/` folder into the dashboard, or connect your GitHub repo with root directory `examples/southern_nh_gc/website`.

**GitHub Pages**

```bash
# From repo root — push website folder to gh-pages branch or use Actions
```

**Any web host**

Upload all files in `website/` to your `public_html` or static bucket.

## Customize

| File | Purpose |
|------|---------|
| `site-config.js` | Business name, phone, email, service area |
| `index.html` | Page structure and copy |
| `styles.css` | Colors and layout |

## Connect to lead automation

Quote requests from the form can later feed into `lead_scan.py` / your CRM by wiring Formspree webhooks to a small endpoint or Zapier.
