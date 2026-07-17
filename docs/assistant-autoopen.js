/* Landing page ("/"): auto-open the Mintlify AI assistant AND inject a
   "Hi, how can we help?" hero above the chat card.
   Mintlify auto-loads .js files in the content directory on every page. */

(function () {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/") return;

  var openAssistant = function () {
    // Trigger a real click — React state updates when the user clicks the
    // toggle button, so setting data-assistant-state directly on <html>
    // does NOT sync with Mintlify's internal state.
    var btn = document.getElementById("assistant-entry-mobile")
      || document.querySelector('button[aria-label="Toggle assistant panel"]');
    if (btn && document.documentElement.getAttribute("data-assistant-state") === "closed") {
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

  var run = function () {
    injectHero();
    openAssistant();
    // Retry in case Mintlify's button wasn't hydrated on the first pass.
    setTimeout(openAssistant, 400);
    setTimeout(openAssistant, 1000);
    setTimeout(openAssistant, 2000);
  };

  if (document.readyState === "complete") run();
  else window.addEventListener("load", run);
})();
