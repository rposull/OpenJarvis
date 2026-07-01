(function () {
  const cfg = window.SITE_CONFIG || {};

  function applyConfig() {
    const name = cfg.businessName || "O'Sullivan Construction & Property Management";
    const logoName = cfg.logoShort || name;
    const tagline = cfg.tagline || "Decks · Garages · Home Additions";
    const phone = cfg.phone || "(978) 888-8068";
    const email = cfg.email || "";
    const area = cfg.serviceArea || "Southern New Hampshire and surrounding towns.";

    if (!window.PAGE_SEO?.title) {
      document.title = `${name} — ${tagline}`;
    }

    const logo = document.getElementById("logo-text");
    if (logo) {
      if (cfg.logoShort) {
        logo.textContent = logoName;
      } else {
        const parts = name.split(" ");
        const last = parts.pop() || "";
        logo.innerHTML = `${parts.join(" ")} <span>${last}</span>`.trim();
      }
    }

    const heroTag = document.getElementById("hero-tagline");
    if (heroTag) {
      heroTag.textContent = `${tagline} across southern NH. Clear quotes, detailed scope, and quality craftsmanship.`;
    }

    const phoneDigits = phone.replace(/\D/g, "");
    const tel = phoneDigits.length >= 10 ? `tel:+1${phoneDigits.slice(-10)}` : `tel:${phone}`;

    document.querySelectorAll("#hero-phone, #contact-phone, .cta-phone").forEach((el) => {
      el.textContent = phone;
      el.href = tel;
    });

    const emailRow = document.getElementById("contact-email-row");
    const emailEl = document.getElementById("contact-email");
    if (emailEl && email) {
      emailEl.textContent = email;
      emailEl.href = `mailto:${email}`;
    } else if (emailRow) {
      emailRow.style.display = "none";
    }

    const areaEl = document.getElementById("service-area-text");
    if (areaEl) areaEl.textContent = area;

    const footer = document.getElementById("footer-copy");
    if (footer) footer.textContent = `© ${new Date().getFullYear()} ${name}. All rights reserved.`;
  }

  function setupNav() {
    const btn = document.getElementById("menu-btn");
    const nav = document.getElementById("main-nav");
    if (!btn || !nav) return;
    btn.addEventListener("click", () => nav.classList.toggle("open"));
    nav.querySelectorAll("a").forEach((a) => {
      a.addEventListener("click", () => nav.classList.remove("open"));
    });
  }

  applyConfig();
  setupNav();
})();
