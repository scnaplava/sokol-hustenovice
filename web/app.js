// Web TJ Sokol Huštěnovice – vykresluje data z data/club.json.
// Data se v prohlížeči znovu načítají každých 15 minut.
const DATA_URL = "data/club.json";
const REFRESH_MS = 15 * 60 * 1000;
const TZ = "Europe/Prague"; // časy vždy v českém čase
const LOGO = "img/logo.jpg";

let data = null;
let currentTeamId = new URLSearchParams(location.search).get("tym");
let countdownTimer = null;

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (iso, opts) => new Date(iso).toLocaleString("cs-CZ", { timeZone: TZ, ...opts });
const fmtShort = (iso) => fmt(iso, { day: "numeric", month: "numeric" });
const fmtTime = (iso) => fmt(iso, { hour: "2-digit", minute: "2-digit" });
const fmtLong = (iso) => {
  const s = fmt(iso, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return s.charAt(0).toUpperCase() + s.slice(1);
};

const isUs = (name) => name === data.club.name || name === data.club.shortName;
const short = (name) => (isUs(name) ? data.club.shortName : name);

function outcome(m) {
  const [h, a] = m.score;
  const ours = isUs(m.home) ? h : a;
  const theirs = isUs(m.home) ? a : h;
  return ours > theirs ? "w" : ours < theirs ? "l" : "d";
}
const OUTCOME_LABEL = { w: "Výhra", d: "Remíza", l: "Prohra" };
const FORM_LETTER = { w: "V", d: "R", l: "P" };

function crest(name) {
  if (isUs(name)) return `<img src="${LOGO}" alt="" class="logo-sm">`;
  return `<span class="crest-ph">${esc(name.trim().charAt(0).toUpperCase())}</span>`;
}

function versus(m, middle, midClass = "") {
  return `<div class="versus">
    <div class="t ${isUs(m.home) ? "us" : ""}">${crest(m.home)}${esc(short(m.home))}</div>
    <div class="mid ${midClass}">${middle}</div>
    <div class="t ${isUs(m.away) ? "us" : ""}">${crest(m.away)}${esc(short(m.away))}</div>
  </div>`;
}

function matchRow(m) {
  const right = m.score
    ? `<span class="score ${outcome(m)}">${m.score[0]}:${m.score[1]}</span>`
    : `<span class="score tbd">–:–</span>`;
  const name = (n) => `<span class="${isUs(n) ? "us" : ""}">${esc(short(n))}</span>`;
  return `<li>
    <span class="date"><b>${fmtShort(m.date)}</b>${fmtTime(m.date)}</span>
    <span>${name(m.home)} – ${name(m.away)}</span>
    ${right}
  </li>`;
}

function renderCountdown(iso) {
  const el = $("#countdown");
  if (!el) return;
  const diff = Math.max(0, new Date(iso) - Date.now());
  const parts = [
    [Math.floor(diff / 864e5), "dní"],
    [Math.floor((diff % 864e5) / 36e5), "hod"],
    [Math.floor((diff % 36e5) / 6e4), "min"],
    [Math.floor((diff % 6e4) / 1e3), "sek"],
  ];
  el.innerHTML = parts.map(([n, l]) => `<div><b>${n}</b><small>${l}</small></div>`).join("");
}

function renderTabs() {
  const nav = $("#team-tabs");
  nav.innerHTML = data.teams
    .map((t) => `<button role="tab" data-id="${esc(t.id)}" aria-selected="${t.id === currentTeamId}">${esc(t.name)}</button>`)
    .join("");
  nav.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => selectTeam(b.dataset.id)));
}

function selectTeam(id, scroll = false) {
  currentTeamId = id;
  history.replaceState(null, "", `?tym=${encodeURIComponent(id)}`);
  render();
  if (scroll) $("#team-tabs").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderTeam(team) {
  const now = Date.now();
  const played = team.matches.filter((m) => m.score).sort((a, b) => new Date(b.date) - new Date(a.date));
  const upcoming = team.matches
    .filter((m) => !m.score && new Date(m.date) > now - 3 * 36e5)
    .sort((a, b) => new Date(a.date) - new Date(b.date));

  $("#hero-competition").textContent = [team.competition, team.season].filter(Boolean).join(" · ");

  // Příští zápas
  const next = upcoming[0];
  clearInterval(countdownTimer);
  $("#next-match").innerHTML = next
    ? `<div class="mcard-head"><span class="badge">Příští zápas</span><span class="side">${isUs(next.home) ? "Doma" : "Venku"}</span></div>
       ${versus(next, "vs")}
       <div class="when">
         <div class="d">${esc(fmtLong(next.date))}</div>
         <div class="h">${fmtTime(next.date)}</div>
         ${next.venue ? `<div class="v">Hřiště ${esc(next.venue)}</div>` : ""}
         <div class="countdown" id="countdown"></div>
       </div>`
    : `<div class="mcard-head"><span class="badge">Příští zápas</span></div><p class="empty">Další zápas zatím není naplánovaný.</p>`;
  if (next) {
    renderCountdown(next.date);
    countdownTimer = setInterval(() => renderCountdown(next.date), 1000);
  }

  // Poslední zápas
  const last = played[0];
  $("#last-match").innerHTML = last
    ? `<div class="mcard-head"><span class="badge">Poslední zápas</span><span class="side">${OUTCOME_LABEL[outcome(last)]}</span></div>
       ${versus(last, `${last.score[0]}:${last.score[1]}`, "bigscore")}
       ${last.scorers?.length ? `<ul class="goals">${last.scorers.map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
       <div class="date-line">${esc(fmtLong(last.date))}${last.halftime ? ` · poločas ${last.halftime[0]}:${last.halftime[1]}` : ""}</div>`
    : `<div class="mcard-head"><span class="badge">Poslední zápas</span></div><p class="empty">Zatím žádný odehraný zápas.</p>`;

  // Statistiky
  const table = team.table || [];
  const idx = table.findIndex((r) => isUs(r.team));
  const row = table[idx];
  const form = played.slice(0, 5).reverse().map(outcome);
  $("#stats").innerHTML = row
    ? `<div class="stat"><small>Pozice</small><b>${row.position ?? idx + 1}.</b><span>z ${table.length} týmů</span></div>
       <div class="stat"><small>Body</small><b>${row.points}</b><span>${row.played} zápasů</span></div>
       <div class="stat"><small>Skóre</small><b>${row.gf}:${row.ga}</b><span>${row.won}V ${row.drawn}R ${row.lost}P</span></div>
       <div class="stat"><small>Forma</small><div class="form">${form.map((f) => `<i class="${f}">${FORM_LETTER[f]}</i>`).join("") || '<span class="empty">–</span>'}</div></div>`
    : "";

  // Zápasy
  $("#results").innerHTML = played.slice(0, 6).map(matchRow).join("") || `<li class="empty">Zatím žádné odehrané zápasy.</li>`;
  $("#fixtures").innerHTML = upcoming.slice(0, 6).map(matchRow).join("") || `<li class="empty">Rozpis zatím není k dispozici.</li>`;

  // Tabulka
  $("#competition").textContent = [team.name, team.competition].filter(Boolean).join(" · ");
  $("#table tbody").innerHTML = table
    .map(
      (r, i) => `<tr class="${isUs(r.team) ? "us" : ""}">
        <td>${r.position ?? i + 1}</td><td class="l">${esc(r.team)}</td>
        <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
        <td>${r.gf}:${r.ga}</td><td>${r.points}</td>
      </tr>`
    )
    .join("");

  // Střelci (sekce se skryje, když data nejsou)
  const scorers = team.scorers || [];
  $("#strelci-wrap").hidden = scorers.length === 0;
  $("#scorers").innerHTML = scorers.map((s) => `<li><span>${esc(s.player)} <b>${s.goals}</b></span></li>`).join("");
}

function renderTeamsGrid() {
  const grid = $("#teams-grid");
  grid.innerHTML = data.teams
    .map(
      (t) => `<button class="team-card" data-id="${esc(t.id)}">
        <span class="cat">${esc(t.category || "")}</span>
        <span class="tag">${esc(t.category || "Tým")}</span>
        <h3>${esc(t.name)}</h3>
        ${t.description ? `<p>${esc(t.description)}</p>` : ""}
        <span class="comp">${esc(t.competition || "")} →</span>
      </button>`
    )
    .join("");
  grid.querySelectorAll(".team-card").forEach((c) => c.addEventListener("click", () => selectTeam(c.dataset.id, true)));
}

function render() {
  if (!data.teams.some((t) => t.id === currentTeamId)) currentTeamId = data.teams[0]?.id;
  const c = data.club;
  if (c.founded) $("#founded").textContent = c.founded;
  $("#tagline").textContent = c.tagline || "";
  $("#sample-notice").hidden = data.source !== "sample";
  $("#updated").textContent = data.updatedAt ? fmt(data.updatedAt, {}) : "–";
  $("#club-contact").innerHTML = [
    c.stadium && esc(c.stadium),
    c.email && `<a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`,
    c.facebook && `<a href="${esc(c.facebook)}" rel="noopener">Facebook</a>`,
  ].filter(Boolean).join(" · ");

  renderTabs();
  renderTeamsGrid();
  const team = data.teams.find((t) => t.id === currentTeamId);
  if (team) renderTeam(team);
}

async function load() {
  try {
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    data = await res.json();
    render();
  } catch (err) {
    console.error("Nepodařilo se načíst data:", err);
    if (!data) $("main").innerHTML = `<p class="wrap empty">Data se nepodařilo načíst. Zkuste stránku obnovit.</p>`;
  }
}

load();
setInterval(load, REFRESH_MS);
