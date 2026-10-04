(() => {
  "use strict";

  const root = document.documentElement;
  const themeButton = document.querySelector("[data-theme-toggle]");
  const themeIcon = document.querySelector("[data-theme-icon]");
  const isArabic = root.lang !== "en";

  function applyTheme(theme, persist = true) {
    root.dataset.theme = theme;
    if (persist) localStorage.setItem("audit-ui-theme", theme);
    if (themeIcon) themeIcon.textContent = theme === "dark" ? "☀" : "☾";
    if (themeButton) {
      const label = theme === "dark"
        ? (isArabic ? "تفعيل المظهر الفاتح" : "Use light theme")
        : (isArabic ? "تفعيل المظهر الداكن" : "Use dark theme");
      themeButton.title = label;
      themeButton.setAttribute("aria-label", label);
    }
    if (window.Chart) {
      window.Chart.defaults.color = theme === "dark" ? "#b7c4d8" : "#5f6f85";
      window.Chart.defaults.borderColor = theme === "dark" ? "rgba(148,163,184,.18)" : "rgba(31,56,100,.1)";
    }
  }

  applyTheme(root.dataset.theme || "light", false);
  themeButton?.addEventListener("click", () => {
    const next = root.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    if (document.querySelector("canvas")) window.setTimeout(() => window.location.reload(), 120);
  });

  const currentPath = window.location.pathname.replace(/\/$/, "") || "/";
  const navLinks = [...document.querySelectorAll(".app-navbar a.nav-link[href], .app-navbar .dropdown-item[href]")];
  const matches = navLinks.filter((link) => {
    const path = new URL(link.href, window.location.origin).pathname.replace(/\/$/, "") || "/";
    return path === currentPath || (path !== "/" && currentPath.startsWith(`${path}/`));
  });
  const activeLink = matches.sort((a, b) => b.pathname.length - a.pathname.length)[0];
  if (activeLink) {
    activeLink.classList.add("active");
    activeLink.setAttribute("aria-current", "page");
    activeLink.closest(".dropdown")?.querySelector(":scope > .nav-link")?.classList.add("active");
  }

  document.querySelectorAll(".btn, .ui-action").forEach((button) => {
    button.addEventListener("pointerdown", (event) => {
      const ripple = document.createElement("span");
      const rect = button.getBoundingClientRect();
      ripple.className = "ui-ripple";
      ripple.style.left = `${event.clientX - rect.left}px`;
      ripple.style.top = `${event.clientY - rect.top}px`;
      button.appendChild(ripple);
      window.setTimeout(() => ripple.remove(), 560);
    });
  });

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      const submit = form.querySelector("button[type='submit']");
      if (!submit || submit.dataset.noLoading !== undefined) return;
      submit.classList.add("is-loading");
      submit.setAttribute("aria-busy", "true");
    });
  });

  const quickModalElement = document.getElementById("quickAccessModal");
  const quickSearch = document.getElementById("quickAccessSearch");
  const quickCommands = [...document.querySelectorAll(".quick-command")];
  const quickEmpty = document.querySelector(".quick-empty");

  function filterCommands() {
    const query = (quickSearch?.value || "").trim().toLocaleLowerCase("ar");
    let visible = 0;
    quickCommands.forEach((command) => {
      const matched = command.textContent.toLocaleLowerCase("ar").includes(query);
      command.hidden = !matched;
      if (matched) visible += 1;
    });
    if (quickEmpty) quickEmpty.hidden = visible !== 0;
  }

  quickSearch?.addEventListener("input", filterCommands);
  quickModalElement?.addEventListener("shown.bs.modal", () => {
    quickSearch.value = "";
    filterCommands();
    quickSearch.focus();
  });
  document.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k" && quickModalElement) {
      event.preventDefault();
      bootstrap.Modal.getOrCreateInstance(quickModalElement).show();
    }
  });

  const scrollButton = document.querySelector("[data-scroll-top]");
  function updateScrollButton() {
    scrollButton?.classList.toggle("is-visible", window.scrollY > 420);
  }
  window.addEventListener("scroll", updateScrollButton, { passive: true });
  scrollButton?.addEventListener("click", () => window.scrollTo({ top: 0, behavior: "smooth" }));
  updateScrollButton();

  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-revealed");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.06 });
    document.querySelectorAll(".app-main .card, .status-card, .workspace-card").forEach((element, index) => {
      element.classList.add("reveal-card");
      element.style.setProperty("--reveal-delay", `${Math.min(index * 35, 280)}ms`);
      observer.observe(element);
    });
  }
})();
