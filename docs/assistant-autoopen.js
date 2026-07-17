/* Auto-open the Mintlify AI assistant on the landing page ("/").
   Mintlify auto-loads .js files in the content directory on every page. */

(function () {
  if (typeof window === "undefined") return;
  if (window.location.pathname !== "/") return;

  var openAssistant = function () {
    var html = document.documentElement;
    // If Mintlify hasn't opened it yet, flip the state attribute — Mintlify
    // reads this to render the sheet as visible.
    if (html.getAttribute("data-assistant-state") === "closed") {
      html.setAttribute("data-assistant-state", "open");
    }
    // Also click the trigger button if we can find one — the click path also
    // wires up focus, keyboard handlers, and the "?assistant" URL state.
    var btn =
      document.getElementById("assistant-entry-mobile") ||
      document.querySelector('button[aria-label*="ssistant" i]') ||
      document.querySelector('a[href="/?assistant"]');
    if (btn && html.getAttribute("data-assistant-state") !== "open") {
      btn.click();
    }
  };

  // Kick a few times — Mintlify's UI hydrates asynchronously and the trigger
  // element may only appear after the initial render.
  var kick = function () {
    setTimeout(openAssistant, 200);
    setTimeout(openAssistant, 700);
    setTimeout(openAssistant, 1500);
  };
  if (document.readyState === "complete") kick();
  else window.addEventListener("load", kick);
})();
