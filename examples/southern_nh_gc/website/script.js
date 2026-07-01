(function () {
  const cfg = window.SITE_CONFIG || {};

  function applyConfig() {
    const name = cfg.businessName || "Southern NH Construction";
    const tagline = cfg.tagline || "Decks · Garages · Home Additions";
    const phone = cfg.phone || "(603) 555-0123";
    const email = cfg.email || "hello@example.com";
    const area = cfg.serviceArea || "Southern New Hampshire and surrounding towns.";

    if (!window.PAGE_SEO?.title) {
      document.title = `${name} — ${tagline}`;
    }

    const logo = document.getElementById("logo-text");
    if (logo) {
      const parts = name.split(" ");
      const last = parts.pop() || "";
      logo.innerHTML = `${parts.join(" ")} <span>${last}</span>`.trim();
    }

    const heroTag = document.getElementById("hero-tagline");
    if (heroTag) {
      heroTag.textContent = `${tagline} across southern NH. Clear quotes, detailed scope, and quality craftsmanship.`;
    }

    const phoneDigits = phone.replace(/\D/g, "");
    const tel = phoneDigits.length >= 10 ? `tel:+1${phoneDigits.slice(-10)}` : `tel:${phone}`;

    ["hero-phone", "contact-phone"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.textContent = phone;
        el.href = tel;
      }
    });

    const emailEl = document.getElementById("contact-email");
    if (emailEl) {
      emailEl.textContent = email;
      emailEl.href = `mailto:${email}`;
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

  function setupForm() {
    const form = document.getElementById("quote-form");
    const success = document.getElementById("form-success");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = new FormData(form);
      const payload = Object.fromEntries(data.entries());

      if (cfg.formspreeId) {
        try {
          const res = await fetch(`https://formspree.io/f/${cfg.formspreeId}`, {
            method: "POST",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          if (res.ok) {
            form.reset();
            if (success) success.style.display = "block";
            return;
          }
        } catch (_) {
          /* fall through to mailto */
        }
      }

      const subject = encodeURIComponent(
        `Estimate request: ${payload.project || "project"} — ${payload.town || "NH"}`
      );
      const body = encodeURIComponent(
        `Name: ${payload.name}\nPhone: ${payload.phone}\nEmail: ${payload.email || ""}\nTown: ${payload.town || ""}\nProject: ${payload.project}\n\n${payload.message}`
      );
      window.location.href = `mailto:${cfg.email || "hello@example.com"}?subject=${subject}&body=${body}`;
    });
  }

  applyConfig();
  setupNav();
  setupForm();
})();
