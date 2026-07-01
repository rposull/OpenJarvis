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

  function ensureHidden(form, name, value) {
    let el = form.querySelector(`input[type="hidden"][name="${name}"]`);
    if (!el) {
      el = document.createElement("input");
      el.type = "hidden";
      el.name = name;
      form.appendChild(el);
    }
    el.value = value;
  }

  function showSentConfirmation() {
    const success = document.getElementById("form-success");
    const params = new URLSearchParams(window.location.search);
    if (params.get("sent") !== "1") return;

    if (success) success.style.display = "block";
    document.getElementById("contact")?.scrollIntoView({ behavior: "smooth" });

    params.delete("sent");
    const qs = params.toString();
    const clean = `${window.location.pathname}${qs ? `?${qs}` : ""}#contact`;
    history.replaceState({}, "", clean);
  }

  function setupForm() {
    const form = document.getElementById("quote-form");
    const success = document.getElementById("form-success");
    const error = document.getElementById("form-error");
    const submitBtn = document.getElementById("form-submit-btn");
    if (!form) return;

    showSentConfirmation();

    if (cfg.formspreeId) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        if (success) success.style.display = "none";
        if (error) error.style.display = "none";

        const data = new FormData(form);
        if (data.get("_honey")) return;

        const payload = Object.fromEntries(
          [...data.entries()].filter(([key]) => !key.startsWith("_"))
        );

        const originalLabel = submitBtn ? submitBtn.textContent : "";
        if (submitBtn) {
          submitBtn.disabled = true;
          submitBtn.textContent = "Sending…";
        }

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
          /* fall through */
        } finally {
          if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = originalLabel;
          }
        }
        if (error) error.style.display = "block";
      });
      return;
    }

    if (!cfg.email) return;

    // Native POST to FormSubmit — reliable in Safari (no AJAX/CORS issues).
    // Do NOT encodeURIComponent the email; FormSubmit expects a literal @ in the URL.
    form.method = "POST";
    form.action = `https://formsubmit.co/${cfg.email}`;

    const returnUrl = `${window.location.origin}${window.location.pathname}?sent=1#contact`;
    ensureHidden(form, "_next", returnUrl);
    ensureHidden(form, "_captcha", "false");
    ensureHidden(form, "_template", "table");
    ensureHidden(form, "_subject", "New estimate request");

    form.addEventListener("submit", (e) => {
      const honey = form.querySelector('input[name="_honey"]');
      if (honey && honey.value) {
        e.preventDefault();
        return;
      }

      const project = form.querySelector('[name="project"]')?.value || "project";
      const town = form.querySelector('[name="town"]')?.value || "NH";
      const subj = form.querySelector('input[name="_subject"]');
      if (subj) subj.value = `Estimate request: ${project} — ${town}`;

      const visitorEmail = form.querySelector('[name="email"]')?.value?.trim();
      if (visitorEmail) {
        ensureHidden(form, "_replyto", visitorEmail);
      }

      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "Sending…";
      }
      // Allow native form navigation to FormSubmit → redirect back via _next
    });
  }

  applyConfig();
  setupNav();
  setupForm();
})();
