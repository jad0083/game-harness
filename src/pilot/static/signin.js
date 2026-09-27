// The sign-in page's behaviour (/pair). The typed-words form works without this script.
//  - A link's code rides in the fragment (/pair#c=<id>.<secret>): it never reaches a request line, a
//    log, a Referer or a link preview. This script shows the confirm view, and only the tap sends it
//    (POST /pair, JSON). Afterwards, and on any error, history.replaceState drops it from the address bar.
//  - Brave looks like Chrome in its user agent; navigator.brave tells them apart for the device name.
//  - The fragment of the page the browser came from (e.g. #tab=strategy) is carried through `next`.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const client = navigator.brave ? "Brave" : "";
  const hash = location.hash || "";
  const code = hash.startsWith("#c=") ? hash.slice(3) : "";
  const next = $("next");
  $("client").value = client;
  if (hash && !code) next.value = next.value.split("#")[0] + hash;
  const addr = $("inapp-address");
  if (addr) addr.value = location.href;              // the full address, with the unspent code, to open elsewhere
  if (client && $("name")) $("name").value = $("name").value.replace(/^Chrome\b/, "Brave");

  // "Too many tries": a live countdown, then the form comes back
  const wait = Number(document.body.dataset.wait) || 0;
  const count = $("count");
  if (wait > 0 && count) {
    const submit = $("submit");
    let left = wait;
    submit.disabled = true;
    const tick = () => {
      count.textContent = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
      if (left <= 0) { submit.disabled = false; return; }
      left -= 1;
      setTimeout(tick, 1000);
    };
    tick();
  }
  $("words-form").addEventListener("submit", () => {
    const b = $("submit");
    setTimeout(() => { b.disabled = true; b.textContent = "Signing in…"; }, 0);
  });

  // Copy the address (in-app browsers): no clipboard API on plain HTTP, so select and execCommand
  const copy = $("inapp-copy");
  if (copy && addr) {
    copy.addEventListener("click", () => {
      addr.focus(); addr.select(); addr.setSelectionRange(0, addr.value.length);
      let ok = false;
      try { ok = document.execCommand("copy"); } catch { ok = false; }
      copy.textContent = ok ? "Copied" : "Press Ctrl+C";
    });
  }

  if (!code) return;
  $("v-signin").hidden = true;
  $("v-confirm").hidden = false;
  const go = $("confirm-go"), err = $("confirm-error");
  const fail = (msg) => { err.textContent = msg; err.hidden = false; go.disabled = false; go.textContent = "Sign in"; };
  $("confirm-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    go.disabled = true; go.textContent = "Signing in…";
    let r, j = {};
    try {
      r = await fetch("/pair", { method: "POST", headers: { "Content-Type": "application/json" },
                                 body: JSON.stringify({ link: code, name: $("name").value, client, next: next.value }) });
      j = await r.json().catch(() => ({}));
    } catch {
      history.replaceState(null, "", "/pair");
      return fail("The dashboard can't be reached. Check the network and try again.");
    }
    history.replaceState(null, "", "/pair");          // the code leaves the address bar
    if (r.ok) { location.replace(j.next || "/"); return; }
    fail(j.reason || `Sign-in failed (${r.status}).`);
    if (["expired", "conflict", "wrong_code"].includes(j.error)) go.hidden = true;
  });
})();
