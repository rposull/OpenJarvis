# Deploy — get your business URL live

Your branded site URL:

**https://osullivan-construction.netlify.app**

(Random preview links like `trycloudflare.com` cannot be renamed — deploy once to Netlify to get this permanent name.)

## 5-minute Netlify deploy (free)

1. Go to **https://app.netlify.com** and sign up (use `rposull@hotmail.com` or Google).
2. Click **Add new site** → **Import an existing project** → **GitHub**.
3. Choose repo **rposull/OpenJarvis** and branch **cursor/southern-nh-gc-automation-4d44**.
4. Set:
   - **Base directory:** `examples/southern_nh_gc/website`
   - **Build command:** `python3 build_site.py`
   - **Publish directory:** `examples/southern_nh_gc/website`
5. Click **Deploy site**.
6. After deploy: **Site configuration** → **Domain management** → **Options** → change site name to **`osullivan-construction`**.
7. Your live URL is now **https://osullivan-construction.netlify.app**

## Custom domain later (optional)

When you buy **osullivanconstructionpm.com**:

1. Netlify → **Domain management** → **Add domain** → enter `osullivanconstructionpm.com`
2. Point DNS at your registrar to Netlify (they show you the records)
3. Update `customDomain` in `data/business.json`, run `python3 build_site.py`, redeploy

## Form activation

First form submission → check **rposull@hotmail.com** (and junk) for FormSubmit activation email → click link once.
