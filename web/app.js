// Web TJ Sokol Huštěnovice – vykresluje data z data/club.json.
// Data se v prohlížeči znovu načítají každých 15 minut.
const DATA_URL = "data/club.json";
const REFRESH_MS = 15 * 60 * 1000;
const TZ = "Europe/Prague"; // časy vždy v českém čase

let data = null;
let currentTeamId = new URLSearchParams(location.search).get("tym");

const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const fmtDate = (iso) => new Date(iso).toLocaleDateString("cs-CZ", { day: "numeric", month: "numeric", year: "2-digit", timeZone: TZ });
const fmtTime = (iso) => new Date(iso).toLocaleTimeString("cs-CZ", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
const fmtFull = (iso) => new Date(iso).toLocaleString("cs-CZ", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: TZ });

function isUs(name) {
  return name === data.club.name || name === data.club.shortName;
}

function resultClass(m) {
  const [h, a] = m.score;
  const ours = isUs(m.home) ? h : a;
  const theirs = isUs(m.home) ? a : h;
  return ours > theirs ? "w" : ours < theirs ? "l" : "d";
}

function teamCell(name) {
  return `<span class="${isUs(name) ? "us" : ""}">${esc(name)}</span>`;
}

function matchRow(m) {
  const right = m.score
    ? `<span class="score ${resultClass(m)}">${m.score[0]}:${m.score[1]}</span>`
    : `<span class="score time">${fmtTime(m.date)}</span>`;
  return `<li>
    <span class="date">${m.round ? m.round + ". kolo<br>" : ""}${fmtDate(m.date)}</span>
    <span>${teamCell(m.home)} – ${teamCell(m.away)}</span>
    ${right}
  </li>`;
}

function countdown(iso) {
  const diff = new Date(iso) - Date.now();
  if (diff <= 0) return "Zápas právě probíhá nebo už skončil";
  const d = Math.floor(diff / 864e5);
  const h = Math.floor((diff % 864e5) / 36e5);
  if (d > 0) return `Za ${d} ${d === 1 ? "den" : d < 5 ? "dny" : "dní"} a ${h} h`;
  const min = Math.floor((diff % 36e5) / 6e4);
  return `Za ${h} h ${min} min`;
}

function renderTabs() {
  const nav = $("#team-tabs");
  nav.innerHTML = data.teams
    .map((t) => `<button role="tab" data-id="${esc(t.id)}" aria-selected="${t.id === currentTeamId}">${esc(t.name)}</button>`)
    .join("");
  nav.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      currentTeamId = b.dataset.id;
      history.replaceState(null, "", `?tym=${encodeURIComponent(currentTeamId)}`);
      render();
    })
  );
}

function renderTeam(team) {
  const now = Date.now();
  const played = team.matches.filter((m) => m.score).sort((a, b) => new Date(b.date) - new Date(a.date));
  const upcoming = team.matches.filter((m) => !m.score && new Date(m.date) > now - 3 * 36e5).sort((a, b) => new Date(a.date) - new Date(b.date));

  // Příští zápas
  const next = upcoming[0];
  $("#next-match .body").innerHTML = next
    ? `<div class="teams">
         <div class="team">${esc(next.home)}</div><div class="vs">vs</div><div class="team">${esc(next.away)}</div>
       </div>
       <div class="meta">${esc(fmtFull(next.date))}${next.venue ? " · " + esc(next.venue) : ""}</div>
       <div class="countdown">${countdown(next.date)}</div>`
    : `<p class="empty">Další zápas zatím není naplánovaný.</p>`;

  $("#results").innerHTML = played.slice(0, 5).map(matchRow).join("") || `<li class="empty">Zatím žádné odehrané zápasy.</li>`;
  $("#fixtures").innerHTML = upcoming.map(matchRow).join("") || `<li class="empty">Rozpis zatím není k dispozici.</li>`;

  // Tabulka
  $("#competition").textContent = [team.competition, team.season].filter(Boolean).join(" · ");
  $("#table tbody").innerHTML = (team.table || [])
    .map(
      (r, i) => `<tr class="${isUs(r.team) ? "us" : ""}">
        <td>${r.position ?? i + 1}.</td><td class="l">${esc(r.team)}</td>
        <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td>
        <td>${r.gf}:${r.ga}</td><td>${r.points}</td>
      </tr>`
    )
    .join("");

  // Střelci (sekce se skryje, když data nejsou)
  const scorers = team.scorers || [];
  $("#scorers-card").hidden = scorers.length === 0;
  $("#scorers").innerHTML = scorers.map((s) => `<li>${esc(s.player)} <b>${s.goals}</b></li>`).join("");
}

function render() {
  if (!data.teams.some((t) => t.id === currentTeamId)) currentTeamId = data.teams[0]?.id;
  $("#club-name").textContent = data.club.name;
  $("#sample-notice").hidden = data.source !== "sample";
  $("#updated").textContent = data.updatedAt ? new Date(data.updatedAt).toLocaleString("cs-CZ", { timeZone: TZ }) : "–";

  const c = data.club;
  $("#club-contact").innerHTML = [
    c.stadium && `🏟 ${esc(c.stadium)}`,
    c.email && `✉ <a href="mailto:${esc(c.email)}">${esc(c.email)}</a>`,
    c.facebook && `<a href="${esc(c.facebook)}" rel="noopener">Facebook</a>`,
  ].filter(Boolean).join(" · ");

  renderTabs();
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
    if (!data) $("main").innerHTML = `<p class="card wide empty">Data se nepodařilo načíst. Zkuste stránku obnovit.</p>`;
  }
}

load();
setInterval(load, REFRESH_MS);
