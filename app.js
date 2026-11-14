(() => {
  const $ = (id) => document.getElementById(id);
  const NS = "http://www.w3.org/2000/svg";
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let current = null; // last dashboard payload
  let currentLogin = "";

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k" : String(n));
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const api = async (url, opts) => {
    const r = await fetch(url, opts);
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || `Request failed (${r.status})`);
    return body;
  };

  // ---------- motion helpers ----------
  let twTimer;
  function typewrite(el, text) {
    clearInterval(twTimer);
    el.setAttribute("aria-label", text);
    if (reduce) { el.textContent = text; el.classList.remove("typing"); return; }
    el.textContent = "";
    el.classList.add("typing");
    let i = 0;
    twTimer = setInterval(() => {
      el.textContent = text.slice(0, ++i);
      if (i >= text.length) { clearInterval(twTimer); el.classList.remove("typing"); }
    }, 38);
  }

  // Elements with data-count animate from 0 to that number (data-fmt="k" -> 1.8k style).
  function animateCounts(root) {
    root.querySelectorAll("[data-count]").forEach((el) => {
      const target = Number(el.dataset.count) || 0, k = el.dataset.fmt === "k";
      const show = (v) => { el.textContent = k ? fmt(Math.round(v)) : Math.round(v).toLocaleString(); };
      if (reduce) { show(target); return; }
      const t0 = performance.now(), dur = 800 + Math.min(target, 2000) / 5;
      const step = (now) => {
        const p = Math.min(1, (now - t0) / dur);
        show(target * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    });
  }
  const num = (n, k) => `<span data-count="${n}"${k ? ' data-fmt="k"' : ""}>${k ? fmt(n) : n.toLocaleString()}</span>`;

  function timeAgo(ts) {
    const s = Math.max(0, Math.round((Date.now() - ts) / 1000));
    if (s < 60) return "just now";
    if (s < 3600) return Math.round(s / 60) + "m ago";
    if (s < 86400) return Math.round(s / 3600) + "h ago";
    return Math.round(s / 86400) + "d ago";
  }

  // ---------- state ----------
  function showState(title, text, isError) {
    const s = $("state");
    s.hidden = false;
    s.className = "state" + (isError ? " error" : "");
    s.innerHTML = `<h1>${esc(title)}</h1><p>${esc(text)}</p>`;
    $("app").hidden = true;
    $("statusbar").hidden = true;
  }

  async function load(login, refresh = false) {
    login = (login || "").trim();
    if (!login) return;
    currentLogin = login;
    showState("Loading " + login, "Fetching from the local cache or GitHub.", false);
    $("refreshBtn").hidden = true;
    try {
      current = await api(`/api/dashboard/${encodeURIComponent(login)}${refresh ? "?refresh=1" : ""}`);
      try { localStorage.setItem("lastLogin", login); } catch (e) {}
      render(current);
    } catch (e) {
      showState("Couldn't load " + login, e.message + " You can still try the demo data.", true);
    }
  }

  // ---------- render ----------
  function render(d) {
    $("state").hidden = true;
    $("app").hidden = false;
    $("refreshBtn").hidden = d.profile.login === "demo";
    const p = d.profile;
    document.title = `${p.name} - Devfolio`;
    renderStatus(d);

    const av = $("avatar");
    av.src = p.avatar_url || "data:image/svg+xml," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="76" height="76"><rect width="76" height="76" fill="#0e7f94"/></svg>');
    typewrite($("heroTitle"), p.name);
    $("bio").textContent = p.bio;
    const bits = [p.login !== p.name ? "@" + p.login : "", p.company, p.location].filter(Boolean);
    $("meta").textContent = bits.join(" // ");

    renderMatchBadge(d.match);
    renderHeatmap(d.contributions);
    renderFacts(d);
    renderDonut(d.languages);
    renderPersona(d);
    renderEmbeds(p.login);
    $("jd").value = d.job_description || "";
    setRunLabel();
    renderMatchResult(d.match);
    buildLangFilter(d.repos);
    renderRepos();
  }

  function renderStatus(d) {
    const m = d.meta, o = m.origins;
    const stale = Object.values(o).includes("stale-cache");
    const demo = Object.values(o).every((v) => v === "demo");
    const parts = [
      `<span class="live${stale ? " stale" : ""}">${demo ? "demo mode" : stale ? "serving stale cache" : "connected"}</span>`,
      `<span>profile <b>${esc(o.profile)}</b></span>`,
      `<span>repos <b>${esc(o.repos)}</b></span>`,
      `<span>contributions <b>${esc(o.contributions)}</b></span>`,
      `<span>cache ttl <b>${m.ttl_minutes}m</b></span>`,
    ];
    if (m.cached_at) parts.push(`<span>cached <b>${timeAgo(m.cached_at * 1000)}</b></span>`);
    if (!demo) parts.push(`<span>auth <b>${m.authenticated ? "token" : "anonymous"}</b></span>`);
    $("statusbar").innerHTML = parts.join("");
    $("statusbar").hidden = false;
  }

  function renderMatchBadge(m) {
    const b = $("matchBadge");
    if (m && m.percent != null) {
      b.className = "match-badge";
      b.setAttribute("aria-label", `Stack match ${m.percent} percent, ${m.label}. Open the stack match panel.`);
      b.innerHTML = `<span class="ring-box"><svg viewBox="0 0 36 36" aria-hidden="true"><circle class="ring-bg" cx="18" cy="18" r="15.9155"/><circle class="ring-fg" cx="18" cy="18" r="15.9155" stroke-dasharray="${m.percent} ${100 - m.percent}"/></svg><span class="ring-num" data-count="${m.percent}">${m.percent}</span></span>
        <span class="mb-text"><strong>Stack match</strong><span>${esc(m.label)}</span></span><span class="mb-go" aria-hidden="true">&#9654;</span>`;
      animateCounts(b);
    } else {
      b.className = "match-badge empty";
      b.setAttribute("aria-label", "Run stack match. Open the stack match panel.");
      b.innerHTML = `<span class="radar" aria-hidden="true"></span>
        <span class="mb-text"><strong>Run stack match</strong><span>Score your fit for a job</span></span><span class="mb-go" aria-hidden="true">&#9654;</span>`;
    }
  }

  function renderHeatmap(c) {
    const days = c.days, svg = $("heatmap");
    const cell = 11, gap = 3, step = cell + gap, left = 26, top = 16;
    const first = new Date(days[0].date + "T00:00:00Z").getUTCDay();
    const cols = Math.floor((days.length - 1 + first) / 7) + 1;
    svg.setAttribute("viewBox", `0 0 ${left + cols * step} ${top + 7 * step}`);
    svg.innerHTML = "";
    const mk = (tag, attrs, text) => {
      const el = document.createElementNS(NS, tag);
      for (const k in attrs) el.setAttribute(k, attrs[k]);
      if (text != null) el.textContent = text;
      svg.appendChild(el);
      return el;
    };
    ["Mon", "Wed", "Fri"].forEach((n, i) => mk("text", { x: 0, y: top + (i * 2 + 1) * step + 9 }, n));
    let lastMonth = -1, lastLabelCol = -10;
    days.forEach((d, i) => {
      const idx = i + first, col = Math.floor(idx / 7), row = idx % 7;
      const dt = new Date(d.date + "T00:00:00Z");
      if (row === 0 || i === 0) {
        const m = dt.getUTCMonth();
        if (m !== lastMonth && col - lastLabelCol >= 3) {
          mk("text", { x: left + col * step, y: 10 }, dt.toLocaleString("en", { month: "short", timeZone: "UTC" }));
          lastLabelCol = col;
        }
        lastMonth = m;
      }
      const r = mk("rect", { class: `day l${d.level}`, x: left + col * step, y: top + row * step, width: cell, height: cell });
      r.style.animationDelay = col * 14 + row * 5 + "ms"; // wave sweeps left to right
      r.dataset.tip = `${d.count} contribution${d.count === 1 ? "" : "s"} on ${dt.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" })}`;
    });
    const s = c.stats, st = c.streaks;
    const tc = $("totalContribs");
    tc.dataset.count = s.total;
    tc.textContent = s.total.toLocaleString();
    animateCounts(tc.parentNode);
    $("heatSource").textContent = c.source === "events"
      ? "Based on public events (last ~90 days). Set GITHUB_TOKEN for the full-year calendar."
      : c.source === "demo" ? "Sample data" : "";
    $("streaks").innerHTML = [
      ["Current streak", `${num(st.current)} <small>days</small>`],
      ["Longest streak", `${num(st.longest)} <small>days</small>`],
      ["Active days", `${num(s.active_days)} <small>of ${days.length}</small>`],
      ["Busiest weekday", s.busiest_weekday ? `<span style="font-size:1.15rem">${esc(s.busiest_weekday)}</span>` : "-"],
      ["Last 30 days", `${num(s.last_30_days)} <small>contributions</small>`],
    ].map(([t, v]) => `<div><dt>${t}</dt><dd>${v}</dd></div>`).join("");
    animateCounts($("streaks"));
  }

  function renderFacts(d) {
    const p = d.profile, t = d.totals;
    $("facts").innerHTML = [
      ["Followers", num(p.followers, true)], ["Total stars", num(t.total_stars, true)],
      ["Public repos", num(t.repo_count)], ["Total forks", num(t.total_forks, true)],
      ["Languages", num(t.language_count)], ["Top repo", `<span style="font-size:0.95rem">${esc(t.top_repo || "-")}</span>`],
    ].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join("");
    animateCounts($("facts"));
  }

  function renderDonut(langs) {
    const svg = $("donut");
    svg.innerHTML = "";
    const total = langs.reduce((a, l) => a + l.percent, 0) || 1;
    let offset = 0;
    langs.forEach((l, i) => {
      const len = (l.percent / total) * 100;
      const seg = Math.max(len - 0.8, 0.1);
      const c = document.createElementNS(NS, "circle");
      c.setAttribute("cx", 21); c.setAttribute("cy", 21); c.setAttribute("r", 15.9155);
      c.setAttribute("stroke", l.color);
      c.setAttribute("stroke-dasharray", `${seg} ${100 - seg}`);
      c.setAttribute("stroke-dashoffset", -offset);
      c.style.animationDelay = i * 0.12 + "s";
      c.dataset.tip = `${l.language}: ${l.percent}%`;
      svg.appendChild(c);
      offset += len;
    });
    $("donutHole").innerHTML = langs.length ? `<b>${langs[0].percent}%</b>${esc(langs[0].language)}` : "";
    $("langLegend").innerHTML = langs.length
      ? langs.map((l) => `<li><i style="background:${esc(l.color)};color:${esc(l.color)}"></i>${esc(l.language)}<span class="pct">${l.percent}%</span></li>`).join("")
      : `<li class="note">No language data yet.</li>`;
  }

  function renderPersona(d) {
    $("personaName").textContent = d.persona.title;
    $("personaBlurb").textContent = d.persona.blurb;
    $("achievements").innerHTML = d.achievements.map((a) =>
      `<li class="${a.unlocked ? "on" : "off"}"><span class="mark">${a.unlocked ? "&#10003;" : "&#9675;"}</span><span>${esc(a.name)}<small>${esc(a.goal)} (${esc(a.detail)})</small></span></li>`
    ).join("");
  }

  function renderEmbeds(login) {
    const base = location.origin;
    $("embeds").innerHTML = ["match", "streak", "stars"].map((k) => {
      const url = `${base}/badge/${encodeURIComponent(login)}/${k}.svg`;
      const md = `![${k}](${url})`;
      return `<div class="embed"><img src="${esc(url)}?t=${Date.now()}" alt="${k} badge"><code>${esc(md)}</code><button class="btn ghost" data-copy="${esc(md)}">Copy markdown</button></div>`;
    }).join("");
  }

  // ---------- vibe check ----------
  function setRunLabel() {
    $("matchBtn").querySelector(".run-label").textContent = current && current.match ? "Re-run stack match" : "Run stack match";
  }

  function renderMatchResult(m) {
    const box = $("matchResult");
    if (!m) { box.hidden = true; box.innerHTML = ""; return; }
    box.hidden = false;
    if (m.percent == null) {
      box.innerHTML = `<p class="note" style="margin-top:12px">${esc(m.message)}</p>`;
      return;
    }
    const chips = (list, cls) => list.map((e, i) => `<li class="chip ${cls}" style="--i:${i}" title="${esc(e.evidence || "")}">${esc(e.term)}</li>`).join("");
    const gaps = m.missing.map((e, i) => `<li style="--i:${i}"><b>${esc(e.term)}</b> - ${esc(e.suggestion)}</li>`).join("");
    box.innerHTML = `
      <div class="match-big"><span class="num"><span data-count="${m.percent}">${m.percent}</span>%</span><span class="lab">${esc(m.label)}</span>
        <span class="note">${m.terms_found} technologies found in the job description${m.language_percent != null ? `, ${m.language_percent}% match on languages alone` : ""}</span></div>
      <div class="bar" aria-hidden="true"><i style="width:0"></i></div>
      ${m.matched.length ? `<p class="chips-title">You have these</p><ul class="chips">${chips(m.matched, "ok")}</ul>` : ""}
      ${m.partial.length ? `<p class="chips-title">Partial credit</p><ul class="chips">${m.partial.map((e, i) => `<li class="chip part" style="--i:${i}" title="${esc(e.evidence)}">${esc(e.term)} (${Math.round(e.credit * 100)}%)</li>`).join("")}</ul>` : ""}
      ${m.missing.length ? `<p class="chips-title">Skill gaps and how to close them</p><ul class="gaps">${gaps}</ul>` : `<p class="chips-title">No gaps found.</p>`}`;
    animateCounts(box);
    requestAnimationFrame(() => requestAnimationFrame(() => { box.querySelector(".bar i").style.width = m.percent + "%"; }));
  }

  async function runMatch() {
    const text = $("jd").value.trim();
    $("matchMsg").textContent = "";
    if (!text) { $("matchMsg").textContent = "Paste a job description first."; $("jd").focus(); return; }
    const btn = $("matchBtn");
    btn.disabled = true;
    btn.classList.add("busy");
    btn.querySelector(".run-label").textContent = "Scanning";
    try {
      // minimum scan time so the scanning state is visible even on a fast cache hit
      const [{ match }] = await Promise.all([
        api(`/api/match/${encodeURIComponent(currentLogin)}`, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job_description: text }),
        }),
        sleep(reduce ? 0 : 900),
      ]);
      current.match = match;
      renderMatchBadge(match);
      renderMatchResult(match);
      renderEmbeds(currentLogin);
    } catch (e) {
      $("matchMsg").textContent = e.message;
    } finally {
      btn.disabled = false;
      btn.classList.remove("busy");
      setRunLabel();
    }
  }

  async function clearJd() {
    $("jd").value = "";
    await api(`/api/match/${encodeURIComponent(currentLogin)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job_description: "" }),
    });
    current.match = null;
    renderMatchBadge(null); renderMatchResult(null); renderEmbeds(currentLogin); setRunLabel();
  }

  // ---------- repos ----------
  function buildLangFilter(repos) {
    const langs = [...new Set(repos.map((r) => r.language).filter(Boolean))].sort();
    $("langFilter").innerHTML = `<option value="">All</option>` + langs.map((l) => `<option>${esc(l)}</option>`).join("");
  }

  function renderRepos() {
    if (!current) return;
    const sort = $("sortBy").value, lang = $("langFilter").value, hide = $("hideForks").checked;
    let list = current.repos.filter((r) => (!hide || !r.fork) && (!lang || r.language === lang));
    const key = { stars: (r) => r.stars, forks: (r) => r.forks, updated: (r) => Date.parse(r.updated_at || 0) };
    list.sort((a, b) => key[sort](b) - key[sort](a));
    const colors = Object.fromEntries(current.languages.map((l) => [l.language, l.color]));
    $("repos").innerHTML = list.length ? list.map((r, i) => {
      const color = colors[r.language] || "#8b949e";
      return `<article class="repo${i === 0 && list.length > 2 ? " lead" : ""}" style="--i:${Math.min(i, 14)}">
        <a class="name" href="${esc(r.html_url)}" target="_blank" rel="noopener">${esc(r.name)}</a>
        <p class="desc">${esc(r.description) || "No description yet."}</p>
        ${r.topics.length ? `<div class="topics">${r.topics.slice(0, 5).map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
        <div class="stats">
          ${r.language ? `<span class="lang-tag"><i style="background:${esc(color)};color:${esc(color)}"></i>${esc(r.language)}</span>` : ""}
          <span title="Stars"><b>${fmt(r.stars)}</b> stars</span>
          <span title="Forks"><b>${fmt(r.forks)}</b> forks</span>
        </div></article>`;
    }).join("") : `<p class="empty">No repositories match these filters.</p>`;
  }

  // ---------- tooltip, copy ----------
  const tip = $("tip");
  document.addEventListener("mousemove", (e) => {
    const t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) { tip.hidden = true; return; }
    tip.textContent = t.dataset.tip;
    tip.hidden = false;
    tip.style.left = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8) + "px";
    tip.style.top = e.clientY + 14 + "px";
  });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    try { await navigator.clipboard.writeText(b.dataset.copy); b.textContent = "Copied"; }
    catch (err) { b.textContent = "Copy failed - select the text instead"; }
    setTimeout(() => (b.textContent = "Copy markdown"), 1600);
  });

  // ---------- settings ----------
  async function openSettings() {
    const s = await api("/api/settings");
    $("setUser").value = s.default_username; $("setTtl").value = s.cache_ttl_minutes;
    $("settingsDlg").showModal();
  }

  // ---------- wiring ----------
  $("searchForm").addEventListener("submit", (e) => { e.preventDefault(); load($("username").value); });
  $("demoBtn").addEventListener("click", () => { $("username").value = "demo"; load("demo"); });
  $("refreshBtn").addEventListener("click", () => load(currentLogin, true));
  $("matchBtn").addEventListener("click", runMatch);
  $("clearJd").addEventListener("click", clearJd);
  $("matchBadge").addEventListener("click", (e) => {
    e.preventDefault();
    $("vibe").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    setTimeout(() => $("jd").focus({ preventScroll: true }), reduce ? 0 : 450);
  });
  ["sortBy", "langFilter", "hideForks"].forEach((id) => $(id).addEventListener("change", renderRepos));
  $("settingsBtn").addEventListener("click", openSettings);
  $("cancelSettings").addEventListener("click", () => $("settingsDlg").close());
  $("settingsForm").addEventListener("submit", async () => {
    await api("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ default_username: $("setUser").value, cache_ttl_minutes: Number($("setTtl").value) || 60 }),
    });
  });
  $("clearCacheBtn").addEventListener("click", async () => {
    await api("/api/cache", { method: "DELETE" });
    $("clearCacheBtn").textContent = "Cache cleared";
  });

  (async function init() {
    try {
      const s = await api("/api/settings");
      let start = s.default_username;
      try { start = start || localStorage.getItem("lastLogin") || ""; } catch (e) {}
      if (start) { $("username").value = start; load(start); }
    } catch (e) { /* settings are optional */ }
  })();
})();
