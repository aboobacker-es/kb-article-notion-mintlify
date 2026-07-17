/* Landing page ("/"): auto-open the Mintlify AI assistant AND inject a
   "Hi, how can we help?" hero above the chat card.
   Mintlify auto-loads .js files in the content directory on every page. */

(function () {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/") return;

  var openAssistant = function () {
    var html = document.documentElement;
    if (html.getAttribute("data-assistant-state") === "closed") {
      html.setAttribute("data-assistant-state", "open");
    }
    var btn =
      document.getElementById("assistant-entry-mobile") ||
      document.querySelector('button[aria-label*="ssistant" i]') ||
      document.querySelector('a[href="/?assistant"]');
    if (btn && html.getAttribute("data-assistant-state") !== "open") {
      btn.click();
    }
  };

  var injectHero = function () {
    if (document.getElementById("landing-hero")) return;
    var hero = document.createElement("div");
    hero.id = "landing-hero";
    hero.innerHTML =
      '<h1>Hi, how can we help?</h1>' +
      '<p>Ask HackerRank Docs anything. Every answer includes citations to the exact article.</p>';
    document.body.appendChild(hero);
  };

  var kick = function () {
    setTimeout(function () { openAssistant(); injectHero(); }, 200);
    setTimeout(function () { openAssistant(); injectHero(); }, 700);
    setTimeout(function () { openAssistant(); injectHero(); }, 1500);
  };

  if (document.readyState === "complete") kick();
  else window.addEventListener("load", kick);
})();
