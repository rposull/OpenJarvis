(function () {
  const cfg = window.SITE_CONFIG || {};
  const page = window.PAGE_SEO || {};

  function absoluteUrl(path) {
    const base = (cfg.siteUrl || "").replace(/\/$/, "");
    const rel = path.startsWith("/") ? path : `/${path}`;
    return base ? `${base}${rel}` : rel;
  }

  function injectMeta(name, content, attr) {
    if (!content) return;
    const key = attr || "name";
    let el = document.querySelector(`meta[${key}="${name}"]`);
    if (!el) {
      el = document.createElement("meta");
      el.setAttribute(key, name);
      document.head.appendChild(el);
    }
    el.setAttribute("content", content);
  }

  function injectLink(rel, href) {
    if (!href) return;
    let el = document.querySelector(`link[rel="${rel}"]`);
    if (!el) {
      el = document.createElement("link");
      el.setAttribute("rel", rel);
      document.head.appendChild(el);
    }
    el.setAttribute("href", href);
  }

  function injectJsonLd(data) {
    const script = document.createElement("script");
    script.type = "application/ld+json";
    script.textContent = JSON.stringify(data);
    document.head.appendChild(script);
  }

  function phoneDigits() {
    return (cfg.phone || "").replace(/\D/g, "").slice(-10);
  }

  function applyPageSeo() {
    const title = page.title || `${cfg.businessName} — ${cfg.tagline}`;
    const description =
      page.description ||
      `Licensed general contractor in southern New Hampshire. Custom decks, garages, and home additions. Free estimates.`;
    const canonical = page.canonical || cfg.siteUrl || "";

    document.title = title;
    injectMeta("description", description);
    if (canonical) injectLink("canonical", canonical);

    injectMeta("og:title", title, "property");
    injectMeta("og:description", description, "property");
    injectMeta("og:type", page.ogType || "website", "property");
    if (canonical) injectMeta("og:url", canonical, "property");
    injectMeta("og:locale", "en_US", "property");

    injectMeta("twitter:card", "summary_large_image");
    injectMeta("twitter:title", title);
    injectMeta("twitter:description", description);
  }

  function applyLocalBusinessSchema() {
    const digits = phoneDigits();
    const schema = {
      "@context": "https://schema.org",
      "@type": "GeneralContractor",
      name: cfg.businessName,
      description: cfg.tagline,
      url: cfg.siteUrl || undefined,
      telephone: digits ? `+1-${digits.slice(0, 3)}-${digits.slice(3, 6)}-${digits.slice(6)}` : undefined,
      email: cfg.email,
      areaServed: {
        "@type": "State",
        name: "New Hampshire",
      },
      address: {
        "@type": "PostalAddress",
        addressRegion: "NH",
        addressCountry: "US",
      },
      priceRange: "$$",
      knowsAbout: ["Deck construction", "Garage construction", "Home additions"],
    };
    injectJsonLd(schema);
  }

  function applyBreadcrumbSchema(items) {
    if (!items || !items.length) return;
    injectJsonLd({
      "@context": "https://schema.org",
      "@type": "BreadcrumbList",
      itemListElement: items.map((item, i) => ({
        "@type": "ListItem",
        position: i + 1,
        name: item.name,
        item: item.url,
      })),
    });
  }

  function loadAnalytics() {
    if (cfg.ga4Id) {
      const s = document.createElement("script");
      s.async = true;
      s.src = `https://www.googletagmanager.com/gtag/js?id=${cfg.ga4Id}`;
      document.head.appendChild(s);
      window.dataLayer = window.dataLayer || [];
      function gtag() {
        window.dataLayer.push(arguments);
      }
      window.gtag = gtag;
      gtag("js", new Date());
      gtag("config", cfg.ga4Id);
    }
    if (cfg.plausibleDomain) {
      const s = document.createElement("script");
      s.defer = true;
      s.dataset.domain = cfg.plausibleDomain;
      s.src = "https://plausible.io/js/script.js";
      document.head.appendChild(s);
    }
  }

  applyPageSeo();
  if (page.schema !== false) applyLocalBusinessSchema();
  if (page.breadcrumbs) applyBreadcrumbSchema(page.breadcrumbs);
  if (page.jsonLd) injectJsonLd(page.jsonLd);
  loadAnalytics();
})();
