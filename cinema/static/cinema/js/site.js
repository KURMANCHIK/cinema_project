(function () {
  var KEY = "cinema-a11y";
  var body = document.body;
  var toolbar = document.getElementById("a11y-toolbar");
  var opener = document.getElementById("a11y-open");
  var defaults = { font: "1", theme: "", spacing: false, "hide-images": false, open: false };

  function load() {
    try {
      return Object.assign({}, defaults, JSON.parse(localStorage.getItem(KEY) || "{}"));
    } catch (e) {
      return Object.assign({}, defaults);
    }
  }

  function save(state) {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch (e) {}
  }

  var state = load();

  function apply() {
    document.documentElement.style.setProperty("--a11y-font-scale", state.font);
    ["bw", "wb", "blue"].forEach(function (name) {
      body.classList.toggle("a11y-theme-" + name, state.theme === name);
    });
    body.classList.toggle("a11y-on", Boolean(state.theme));
    body.classList.toggle("a11y-spacing", state.spacing);
    body.classList.toggle("a11y-hide-images", state["hide-images"]);
    if (toolbar) {
      toolbar.hidden = !state.open;
      opener.setAttribute("aria-expanded", state.open ? "true" : "false");
      toolbar.querySelectorAll("[data-a11y-font]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.dataset.a11yFont === state.font ? "true" : "false");
      });
      toolbar.querySelectorAll("[data-a11y-theme]").forEach(function (b) {
        b.setAttribute("aria-pressed", b.dataset.a11yTheme === state.theme ? "true" : "false");
      });
      toolbar.querySelectorAll("[data-a11y-toggle]").forEach(function (b) {
        b.setAttribute("aria-pressed", state[b.dataset.a11yToggle] ? "true" : "false");
      });
    }
    save(state);
  }

  if (toolbar) {
    opener.addEventListener("click", function () {
      state.open = !state.open;
      apply();
      if (state.open) toolbar.querySelector("button").focus();
    });
    toolbar.addEventListener("click", function (event) {
      var b = event.target.closest("button");
      if (!b) return;
      if (b.dataset.a11yFont) state.font = b.dataset.a11yFont;
      if (b.dataset.a11yTheme !== undefined) state.theme = b.dataset.a11yTheme;
      if (b.dataset.a11yToggle) state[b.dataset.a11yToggle] = !state[b.dataset.a11yToggle];
      if (b.id === "a11y-reset") {
        state = Object.assign({}, defaults, { open: true });
        if (window.speechSynthesis) speechSynthesis.cancel();
      }
      if (b.id === "a11y-speak") {
        if (!window.speechSynthesis) return;
        speechSynthesis.cancel();
        var selected = String(window.getSelection() || "").trim();
        var text = selected || document.getElementById("main").innerText;
        var phrase = new SpeechSynthesisUtterance(text.slice(0, 4000));
        phrase.lang = "ru-RU";
        speechSynthesis.speak(phrase);
        return;
      }
      apply();
    });
  }
  apply();

  var csrf = document.querySelector('meta[name="csrf-token"]');
  document.querySelectorAll(".fav-btn[data-movie-id]").forEach(function (btn) {
    btn.addEventListener("click", function (event) {
      event.preventDefault();
      var active = btn.getAttribute("aria-pressed") === "true";
      fetch("/api/movies/" + btn.dataset.movieId + "/favorite/", {
        method: active ? "DELETE" : "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": csrf ? csrf.content : "" }
      })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          btn.setAttribute("aria-pressed", data.is_favorite ? "true" : "false");
          btn.querySelector("i").className = data.is_favorite ? "bi bi-heart-fill" : "bi bi-heart";
          btn.title = data.is_favorite ? "Убрать из избранного" : "В избранное";
        });
    });
  });

  document.querySelectorAll("[data-print]").forEach(function (btn) {
    btn.addEventListener("click", function () { window.print(); });
  });
})();
