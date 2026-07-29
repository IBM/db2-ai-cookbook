"use strict";
/* "Start here" — a StoryBrand doorway tab. One screen, dark-navy flat, sentence case.
   Static content; the before/after illustrates a "you describe the idea, keyword
   grabs the wrong book, hybrid gets the one you meant" case (verified live):

     query : "how to build better habits"
     before (keyword #1) : Rise            — Patty Azzarello, word overlap, wrong book
     after  (hybrid  #1) : Atomic Habits — James Clear

   Re-verify against the LIVE /api/search if the corpus/index changes — the vector
   leg's ANN pool (FETCH APPROX) can rank a borderline query differently per session.
*/

const START_QUERY = "how to build better habits";
const sq = (s) => document.querySelector(s);

const HP = `<svg class="glyph-hp" viewBox="0 0 32 32" width="15" height="15" fill="none" aria-hidden="true">
  <path d="M7 19v-3a9 9 0 0 1 18 0v3" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" />
  <rect x="4.4" y="18.4" width="5.2" height="8.2" rx="2.3" stroke="currentColor" stroke-width="2.3" />
  <rect x="22.4" y="18.4" width="5.2" height="8.2" rx="2.3" stroke="currentColor" stroke-width="2.3" /></svg>`;
const CHECK = `<svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
  <path d="M3 8.5l3.2 3.2L13 4.2" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" /></svg>`;
const CROSS = `<svg viewBox="0 0 16 16" width="12" height="12" fill="none" aria-hidden="true">
  <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" /></svg>`;

function startView() {
  return `
  <div class="door">
    <div class="door-hero">
      <div class="eyebrow">${HP} searching your audiobook library</div>
      <h2 class="door-head">You've forgotten more<br>than you can find</h2>
      <p class="door-sub">Hybrid search gives back the library you already own.</p>
    </div>

    <div class="door-grid">
      <div class="door-problem">
        <div class="prob"><span class="kicker">what breaks</span><p>You remember the idea, not the title.</p></div>
        <div class="prob"><span class="kicker">how it feels</span><p>You paid for these. Now they're lost to you.</p></div>
        <div class="prob"><span class="kicker">why it matters</span><p>You should find a book just by describing it.</p></div>
      </div>

      <div class="door-right">
        <div class="ba-wrap">
          <div class="ba-query">you describe &middot; <span>&ldquo;${START_QUERY}&rdquo;</span></div>
          <div class="ba">
            <div class="ba-panel ba-before">
              <div class="ba-label">before &middot; keyword</div>
              <div class="ba-title">Rise</div>
              <div class="ba-verdict miss">${CROSS} not the book you meant</div>
            </div>
            <div class="ba-arrow" aria-hidden="true"></div>
            <div class="ba-panel ba-after">
              <div class="ba-label">after &middot; hybrid</div>
              <div class="ba-found">
                <img class="ba-cover" src="covers/B07GBGQJSW.jpg" loading="lazy"
                     alt="Atomic Habits — cover"
                     onerror="this.style.display='none'" />
                <div class="ba-found-meta">
                  <div class="ba-title">${HP} Atomic Habits</div>
                  <div class="ba-by">James Clear</div>
                  <div class="ba-verdict found">${CHECK} found it</div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <ol class="door-plan">
          <li><span class="pnum">1</span><span>Describe what you remember.</span></li>
          <li><span class="pnum">2</span><span>It searches by keyword and meaning at once.</span></li>
          <li><span class="pnum">3</span><span>The match surfaces — never empty.</span></li>
        </ol>
      </div>
    </div>

    <div class="door-foot">
      <div class="door-ctas">
        <button id="start-cta-try" class="cta cta-primary" type="button">Try it on your library</button>
        <button id="start-cta-arch" class="cta cta-secondary" type="button">See how it's built</button>
      </div>
      <p class="door-guide">Built by an AI architect who lost his own library the same way.</p>
    </div>
  </div>`;
}

function startBoot() {
  const host = sq("#start-canvas");
  if (!host) return;
  host.innerHTML = startView();

  // Primary CTA: close the loop — switch to Search, pre-fill the SAME query, run it.
  // (setPage + run live in app.js, loaded before this module. Offline, run() lands on
  //  Search and shows the "needs live backend" note — the prefilled query stays visible.)
  const tryBtn = sq("#start-cta-try");
  if (tryBtn) tryBtn.addEventListener("click", () => {
    const box = document.querySelector("#searchbox");
    if (box) box.value = START_QUERY;
    if (typeof setPage === "function") setPage("search");
    if (typeof run === "function") run();
  });

  // Secondary CTA: switch to the Architecture tab.
  const archBtn = sq("#start-cta-arch");
  if (archBtn) archBtn.addEventListener("click", () => {
    if (typeof setPage === "function") setPage("arch");
  });
}

startBoot();
