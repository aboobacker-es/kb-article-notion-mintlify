/* Landing page ("/"): Slack-style help-center layout.
   - Purple background (via styles.css)
   - Big "Hi, how can we help?" heading (injected)
   - Big pill input (Mintlify's own textarea, restyled by styles.css)
   - 3 starter question pills below (injected)
   - Decorative shapes at corners (injected)
   Mintlify auto-loads .js files in the content directory on every page. */

(function () {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/") return;

  var STARTERS = [
    "How do I invite candidates to a test?",
    "How does Proctor Mode work?",
    "How do I download a candidate's test report?"
  ];

  var submitQuery = function (q) {
    // Mintlify supports ?assistant=<message> to auto-open with a pre-filled prompt.
    window.location.href = "/?assistant=" + encodeURIComponent(q);
  };

  var openAssistant = function () {
    var btn =
      document.getElementById("assistant-entry-mobile") ||
      document.querySelector('button[aria-label="Toggle assistant panel"]');
    if (btn && document.documentElement.getAttribute("data-assistant-state") === "closed") {
      btn.click();
    }
  };

  var injectHero = function () {
    if (document.getElementById("landing-hero")) return;
    var hero = document.createElement("div");
    hero.id = "landing-hero";
    hero.innerHTML = "<h1>Hi, how can we help?</h1>";
    document.body.appendChild(hero);
  };

  var injectStarters = function () {
    if (document.getElementById("landing-starters")) return;
    var wrap = document.createElement("div");
    wrap.id = "landing-starters";
    STARTERS.forEach(function (q) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = q;
      btn.onclick = function () { submitQuery(q); };
      wrap.appendChild(btn);
    });
    document.body.appendChild(wrap);
  };

  var injectDecor = function () {
    if (document.getElementById("landing-decor")) return;
    var d = document.createElement("div");
    d.id = "landing-decor";
    d.innerHTML =
      // Top-left: coral half-circle
      '<svg style="position:absolute;left:-40px;top:80px;" width="200" height="240" viewBox="0 0 200 240" fill="none"><path d="M-10 0 C 120 20, 200 120, 100 240 L -10 240 Z" fill="#E85A6A"/></svg>' +
      // Top-center-left: green teardrop
      '<svg style="position:absolute;left:22%;top:0;" width="120" height="120" viewBox="0 0 120 120" fill="none"><path d="M60 0 C 100 30, 100 100, 60 120 C 20 100, 20 30, 60 0 Z" fill="#3AA76D"/></svg>' +
      // Top-right: yellow crescent
      '<svg style="position:absolute;right:-30px;top:220px;" width="180" height="180" viewBox="0 0 180 180" fill="none"><path d="M20 90 A 90 90 0 1 1 180 90 A 60 60 0 1 0 20 90 Z" fill="#F1B02F"/></svg>' +
      // Right-middle: orange arc
      '<svg style="position:absolute;right:60px;top:180px;" width="180" height="180" viewBox="0 0 180 180" fill="none"><circle cx="90" cy="90" r="70" stroke="#E85A6A" stroke-width="8" fill="none"/></svg>' +
      // Bottom-right: blue teardrop
      '<svg style="position:absolute;right:15%;bottom:80px;" width="90" height="90" viewBox="0 0 90 90" fill="none"><path d="M45 0 C 75 22, 75 75, 45 90 C 15 75, 15 22, 45 0 Z" fill="#3AA6D8"/></svg>' +
      // Bottom-left: pink circle
      '<svg style="position:absolute;left:12%;bottom:20px;" width="80" height="80" viewBox="0 0 80 80" fill="none"><circle cx="40" cy="40" r="40" fill="#D45C7A"/></svg>';
    document.body.appendChild(d);
  };

  var run = function () {
    injectDecor();
    injectHero();
    injectStarters();
    openAssistant();
    setTimeout(openAssistant, 400);
    setTimeout(openAssistant, 1000);
    setTimeout(openAssistant, 2000);
  };

  if (document.readyState === "complete") run();
  else window.addEventListener("load", run);
})();
