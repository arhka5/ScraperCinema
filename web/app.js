// Cartelera Perú: lee cartelera.json (generado por el scraper en GitHub
// Actions) y lo muestra filtrado. Todo el DOM se arma con textContent:
// ningún dato externo se interpreta como HTML.

const LOCAL = ["localhost", "127.0.0.1"].includes(location.hostname);
const DATA_URL = LOCAL
  ? "/cartelera.json"
  : "https://raw.githubusercontent.com/arhka5/ScraperCinema/data/cartelera.json";

const CHAINS = {
  cinemark: { name: "Cinemark", host: ["www.cinemark-peru.com"] },
  cinepolis: { name: "Cinépolis", host: ["cinepolis.com.pe"] },
  cinestar: { name: "Cinestar", host: ["www.cinestar.com.pe"] },
  uvk: { name: "UVK", host: ["www.uvk.pe", "uvk.pe"] },
  cinerama: { name: "Cinerama", host: ["www.cinerama.com.pe"] },
};
// Solo se enlazan o cargan imágenes de estos dominios (defensa por si el
// JSON fuera manipulado).
const LINK_HOSTS = new Set(Object.values(CHAINS).flatMap((c) => c.host));
const IMAGE_HOSTS = new Set([
  "cdn.cinemark-peru.com", "static.cinepolis.com", "bucket.tumi-soft.com",
  "www.uvk.pe", "uvk.pe", "www.cinerama.com.pe",
]);
const CINEPLANET_URL = "https://www.cineplanet.com.pe/peliculas";
const LATE_LIMIT = 5 * 60; // las funciones antes de las 05:00 son "trasnoche"

const $ = (s) => document.querySelector(s);
const els = {
  dates: $("#dates"), city: $("#city"), query: $("#query"), chains: $("#chains"),
  status: $("#status"), results: $("#results"), empty: $("#empty"), sources: $("#sources"),
};

let data = null;
const state = loadState();

// La vista no se recuerda: al entrar siempre se ve la cartelera por película.
function loadState() {
  const defaults = { date: null, city: "Lima", chains: Object.keys(CHAINS) };
  try {
    const { city, chains } = JSON.parse(localStorage.getItem("cartelera") || "{}");
    return { ...defaults, ...(city !== undefined && { city }), ...(chains && { chains }), view: "movies" };
  } catch {
    return { ...defaults, view: "movies" };
  }
}

function saveState() {
  try {
    const { city, chains } = state;
    localStorage.setItem("cartelera", JSON.stringify({ city, chains }));
  } catch { /* almacenamiento no disponible */ }
}

function safeUrl(url, hosts) {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && hosts.has(u.hostname) ? u.href : null;
  } catch {
    return null;
  }
}

const fold = (s) => (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

// Hora de Lima (UTC-5, sin horario de verano), independiente del equipo.
function limaNow() {
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Lima", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date()).map((p) => [p.type, p.value]));
  return { date: `${parts.year}-${parts.month}-${parts.day}`, minutes: +parts.hour * 60 + +parts.minute };
}

function addDays(iso, n) {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

const daysBetween = (a, b) => Math.round((Date.parse(`${b}T12:00:00Z`) - Date.parse(`${a}T12:00:00Z`)) / 864e5);

// Minutos que faltan para la función (ambos en "día de cartelera").
const minutesUntil = (s, now) => daysBetween(now.date, s.date) * 1440 + s.minutes - now.minutes;

// "Día de cartelera": de madrugada sigue siendo el día anterior (trasnoche).
function carteleraNow() {
  const now = limaNow();
  return now.minutes < LATE_LIMIT
    ? { date: addDays(now.date, -1), minutes: now.minutes + 1440 }
    : now;
}

function sessionMinutes(s) {
  const [h, m] = s.time.split(":").map(Number);
  return h * 60 + m + (s.late ? 1440 : 0);
}

function dateLabel(iso, today) {
  if (iso === today) return "Hoy";
  if (iso === addDays(today, 1)) return "Mañana";
  const d = new Date(`${iso}T12:00:00Z`);
  const wd = d.toLocaleDateString("es-PE", { weekday: "short", timeZone: "UTC" }).replace(".", "");
  return `${wd} ${d.getUTCDate()}/${d.getUTCMonth() + 1}`;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c) node.append(c);
  return node;
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

function chainBadge(chain) {
  return el("span", { class: `badge chain-${chain}`, text: CHAINS[chain]?.name || chain });
}

// ---------- carga ----------

async function load() {
  try {
    const response = await fetch(DATA_URL, { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const raw = await response.json();
    const fields = raw.sessionFields;
    data = {
      ...raw,
      cinemaById: new Map(raw.cinemas.map((c) => [c.id, c])),
      movieByKey: new Map(raw.movies.map((m) => [m.key, m])),
      sessions: raw.sessions.map((row) => Object.fromEntries(fields.map((f, i) => [f, row[i]]))),
    };
    for (const s of data.sessions) {
      s.chain = data.cinemaById.get(s.cinema)?.chain;
      s.minutes = sessionMinutes(s);
    }
    setup();
  } catch (err) {
    els.status.textContent = "No se pudo cargar la cartelera. Inténtalo en unos minutos.";
    els.status.classList.add("error");
    console.error(err);
  }
}

function setup() {
  const cities = [...new Set(data.cinemas.map((c) => c.city))].sort((a, b) =>
    a === "Lima" ? -1 : b === "Lima" ? 1 : a.localeCompare(b, "es"));
  els.city.replaceChildren(
    el("option", { value: "", text: "Todas las ciudades" }),
    ...cities.map((c) => el("option", { value: c, text: c })));
  if (state.city && !cities.includes(state.city)) state.city = "";
  els.city.value = state.city;

  els.chains.replaceChildren(...Object.entries(CHAINS).map(([key, c]) =>
    el("button", { type: "button", class: `chip chain-${key}`, "data-chain": key,
      "aria-pressed": String(state.chains.includes(key)), text: c.name })));

  document.querySelectorAll("[data-view]").forEach((b) =>
    b.setAttribute("aria-pressed", String(b.dataset.view === state.view)));

  els.city.addEventListener("change", () => { state.city = els.city.value; saveState(); render(); });
  els.query.addEventListener("input", debounce(render, 150));
  // El botón (o Enter) aplica la búsqueda y cierra el teclado en el celular.
  $("#search").addEventListener("submit", (e) => {
    e.preventDefault();
    render();
    els.query.blur();
    els.status.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  els.chains.addEventListener("click", (e) => {
    const button = e.target.closest("[data-chain]");
    if (!button) return;
    const chain = button.dataset.chain;
    state.chains = state.chains.includes(chain)
      ? state.chains.filter((c) => c !== chain) : [...state.chains, chain];
    button.setAttribute("aria-pressed", String(state.chains.includes(chain)));
    saveState(); render();
  });
  document.querySelector(".toggle").addEventListener("click", (e) => {
    const view = e.target.closest("[data-view]")?.dataset.view;
    if (!view) return;
    state.view = view;
    document.querySelectorAll("[data-view]").forEach((b) =>
      b.setAttribute("aria-pressed", String(b.dataset.view === view)));
    saveState(); render();
  });
  els.dates.addEventListener("click", (e) => {
    const date = e.target.closest("[data-date]")?.dataset.date;
    if (!date) return;
    state.date = date;
    render();
  });

  renderSources();
  render();
  setInterval(render, 60_000); // oculta las funciones que van pasando
}

function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

// ---------- filtros ----------

function baseSessions(now) {
  const q = fold(els.query.value.trim());
  return data.sessions.filter((s) => {
    if (!state.chains.includes(s.chain)) return false;
    const cinema = data.cinemaById.get(s.cinema);
    if (state.city && cinema.city !== state.city) return false;
    if (s.date < now.date || (s.date === now.date && s.minutes < now.minutes)) return false;
    if (q) {
      const movie = data.movieByKey.get(s.movie);
      if (!fold(movie.title).includes(q) && !fold(cinema.name).includes(q)) return false;
    }
    return true;
  });
}

function renderDates(sessions, now) {
  const dates = [...new Set(sessions.map((s) => s.date))].sort().slice(0, 14);
  if (!dates.includes(state.date)) state.date = dates[0] || now.date;
  els.dates.replaceChildren(...dates.map((d) => el("button", {
    type: "button", class: "chip", "data-date": d, "aria-pressed": String(d === state.date),
    text: dateLabel(d, now.date),
  })));
}

function render() {
  if (!data) return;
  const now = carteleraNow();
  const pool = baseSessions(now);
  els.dates.hidden = state.view === "next";
  if (state.view === "next") return renderNext(pool, now);
  renderDates(pool, now);
  const sessions = pool.filter((s) => s.date === state.date);

  const groups = state.view === "movies" ? groupBy(sessions, "movie") : groupBy(sessions, "cinema");
  const cards = [...groups.entries()]
    .map(([key, list]) => state.view === "movies" ? movieCard(key, list) : cinemaCard(key, list))
    .filter(Boolean);
  // Pocas tarjetas → se muestran abiertas.
  if (cards.length <= 3) cards.forEach((c) => c.setAttribute("open", ""));

  els.results.replaceChildren(...cards);
  els.empty.hidden = cards.length > 0;
  const movies = new Set(sessions.map((s) => s.movie)).size;
  const cinemas = new Set(sessions.map((s) => s.cinema)).size;
  els.status.classList.remove("error");
  els.status.textContent = `${dateLabel(state.date, now.date)}: ` +
    `${plural(movies, "película", "películas")} en ${plural(cinemas, "cine", "cines")} · ` +
    plural(sessions.length, "función", "funciones");
}

function groupBy(list, field) {
  const map = new Map();
  for (const s of list) {
    if (!map.has(s[field])) map.set(s[field], []);
    map.get(s[field]).push(s);
  }
  // Primero lo que tiene más funciones.
  return new Map([...map.entries()].sort((a, b) => b[1].length - a[1].length));
}

// ---------- tarjetas ----------

function poster(movie) {
  const src = movie?.poster ? safeUrl(movie.poster, IMAGE_HOSTS) : null;
  if (!src) return el("div", { class: "poster placeholder", "aria-hidden": "true" });
  const img = el("img", { class: "poster", src, alt: "", loading: "lazy",
    referrerpolicy: "no-referrer", decoding: "async" });
  img.addEventListener("error", () => img.replaceWith(
    el("div", { class: "poster placeholder", "aria-hidden": "true" })), { once: true });
  return img;
}

function meta(movie) {
  const parts = [];
  if (movie.duration) parts.push(`${Math.floor(movie.duration / 60)} h ${movie.duration % 60} min`);
  if (movie.rating) parts.push(movie.rating);
  return parts.join(" · ");
}

function sessionHref(s) {
  const movie = data.movieByKey.get(s.movie);
  const cinema = data.cinemaById.get(s.cinema);
  return safeUrl(s.url, LINK_HOSTS) || safeUrl(movie?.urls?.[s.chain], LINK_HOSTS) ||
    safeUrl(cinema.url, LINK_HOSTS);
}

function sessionTags(s) {
  const tags = [];
  if (s.format && s.format !== "2D") tags.push(s.format);
  if (s.language) tags.push(s.language === "Subtitulada" ? "SUB" : "DOB");
  return tags;
}

function sessionLink(s) {
  const href = sessionHref(s);
  const tags = sessionTags(s);
  const title = [s.time, s.late ? "(trasnoche)" : "", s.format, s.language, s.room,
    `· comprar en ${CHAINS[s.chain]?.name}`].filter(Boolean).join(" ");
  return el(href ? "a" : "span", {
    class: `time${s.late ? " late" : ""}`, href, target: href ? "_blank" : null,
    rel: href ? "noopener noreferrer" : null, title,
  }, el("strong", { text: s.time }), tags.length ? el("small", { text: tags.join(" · ") }) : null);
}

function timesRow(list) {
  return el("div", { class: "times" }, list
    .sort((a, b) => a.minutes - b.minutes)
    .map(sessionLink));
}

function movieCard(key, list) {
  const movie = data.movieByKey.get(key);
  if (!movie) return null;
  const byCinema = groupBy(list, "cinema");
  const chains = [...new Set(list.map((s) => s.chain))];
  const rows = [...byCinema.entries()]
    .sort(([a], [b]) => data.cinemaById.get(a).name.localeCompare(data.cinemaById.get(b).name, "es"))
    .map(([cid, sessions]) => {
      const cinema = data.cinemaById.get(cid);
      return el("div", { class: "venue" },
        el("div", { class: "venue-head" },
          chainBadge(cinema.chain),
          el("span", { class: "venue-name", text: cinema.name }),
          !state.city ? el("span", { class: "muted", text: cinema.city }) : null),
        timesRow(sessions));
    });
  return el("details", { class: "card" },
    el("summary", {},
      poster(movie),
      el("div", { class: "card-info" },
        el("h2", { text: movie.title }),
        el("p", { class: "muted", text: meta(movie) }),
        el("p", { class: "count", text: `${plural(byCinema.size, "cine", "cines")} · ` +
          plural(list.length, "función", "funciones") }),
        el("div", { class: "badges" }, chains.map(chainBadge)))),
    el("div", { class: "card-body" }, rows,
      el("a", { class: "cineplanet", href: CINEPLANET_URL, target: "_blank",
        rel: "noopener noreferrer", text: "¿Y en Cineplanet? Ver su cartelera ↗" })));
}

function cinemaCard(cid, list) {
  const cinema = data.cinemaById.get(cid);
  const byMovie = groupBy(list, "movie");
  const rows = [...byMovie.entries()].map(([key, sessions]) => {
    const movie = data.movieByKey.get(key);
    return el("div", { class: "venue" },
      el("div", { class: "venue-head" },
        el("span", { class: "venue-name", text: movie.title }),
        el("span", { class: "muted", text: meta(movie) })),
      timesRow(sessions));
  });
  return el("details", { class: "card" },
    el("summary", {},
      el("div", { class: "card-info" },
        el("h2", { text: cinema.name }),
        el("p", { class: "muted", text: [cinema.city, cinema.address].filter(Boolean).join(" · ") }),
        el("p", { class: "count", text: `${plural(byMovie.size, "película", "películas")} · ` +
          plural(list.length, "función", "funciones") }),
        el("div", { class: "badges" }, chainBadge(cinema.chain)))),
    el("div", { class: "card-body" }, rows));
}

// ---------- próximas funciones (una tarjeta por cine) ----------

const NEXT_MORE = 3; // funciones que se listan después de la más próxima

function untilText(min) {
  if (min < 1) return "ahora";
  if (min < 60) return `en ${min} min`;
  if (min < 180) return `en ${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
  return null;
}

// "21:40" si es hoy; "Mañana 15:00" / "sáb 25/10 15:00" si no.
function whenText(s, now) {
  return s.date === now.date ? s.time : `${dateLabel(s.date, now.date)} ${s.time}`;
}

function renderNext(pool, now) {
  const byCinema = new Map();
  for (const s of pool) {
    if (!byCinema.has(s.cinema)) byCinema.set(s.cinema, []);
    byCinema.get(s.cinema).push(s);
  }
  const order = (a, b) => a.date.localeCompare(b.date) || a.minutes - b.minutes;
  const entries = [...byCinema.entries()].map(([cid, list]) => [cid, list.sort(order)]);
  entries.sort(([a, la], [b, lb]) => order(la[0], lb[0]) ||
    data.cinemaById.get(a).name.localeCompare(data.cinemaById.get(b).name, "es"));

  const cards = entries.map(([cid, list]) => nextCard(cid, list, now));
  els.results.replaceChildren(...cards);
  els.empty.hidden = cards.length > 0;
  const nowText = `${String(Math.floor(now.minutes / 60) % 24).padStart(2, "0")}:` +
    String(now.minutes % 60).padStart(2, "0");
  els.status.classList.remove("error");
  els.status.textContent = `Próxima función en ${plural(cards.length, "cine", "cines")} · ` +
    `son las ${nowText}`;
}

function nextCard(cid, list, now) {
  const cinema = data.cinemaById.get(cid);
  const [first, ...rest] = list;
  const movie = data.movieByKey.get(first.movie);
  const until = untilText(minutesUntil(first, now));
  const href = sessionHref(first);
  const tags = sessionTags(first);
  const details = [meta(movie || {}), tags.join(" · "), first.room].filter(Boolean).join(" · ");

  const main = el(href ? "a" : "div", {
    class: "next-main", href, target: href ? "_blank" : null,
    rel: href ? "noopener noreferrer" : null,
    title: href ? `Comprar en ${CHAINS[cinema.chain]?.name}` : null,
  },
  el("span", { class: "next-when" },
    el("strong", { text: whenText(first, now) }),
    until ? el("span", { class: "next-until", text: until }) : null,
    first.late ? el("span", { class: "muted", text: "trasnoche" }) : null),
  el("span", { class: "next-movie", text: movie?.title || "Función" }),
  details ? el("span", { class: "muted", text: details }) : null);

  const more = rest.slice(0, NEXT_MORE).map((s) => {
    const h = sessionHref(s);
    const t = sessionTags(s);
    return el(h ? "a" : "span", {
      class: "next-more-item", href: h, target: h ? "_blank" : null,
      rel: h ? "noopener noreferrer" : null,
    },
    el("strong", { text: whenText(s, now) }),
    ` ${data.movieByKey.get(s.movie)?.title || ""}`,
    t.length ? el("small", { text: ` ${t.join(" · ")}` }) : null);
  });

  return el("article", { class: "card next" },
    poster(movie),
    el("div", { class: "card-info" },
      el("div", { class: "venue-head" },
        chainBadge(cinema.chain),
        el("h2", { text: cinema.name }),
        !state.city ? el("span", { class: "muted", text: cinema.city }) : null),
      main,
      more.length ? el("div", { class: "next-more" },
        el("span", { class: "muted", text: "Después:" }), more) : null));
}

function renderSources() {
  const updated = new Date(data.generatedAt);
  const ago = Math.round((Date.now() - updated) / 60000);
  const agoText = ago < 60 ? `hace ${Math.max(ago, 1)} min` : `hace ${Math.round(ago / 60)} h`;
  const parts = [`Actualizado ${agoText}.`];
  for (const [chain, s] of Object.entries(data.sources || {})) {
    const name = CHAINS[chain]?.name || chain;
    if (!s.ok) parts.push(`⚠ ${name}: no se pudo actualizar; se muestran datos anteriores.`);
    if (s.note) parts.push(`ℹ ${s.note}`);
  }
  parts.push("Cineplanet no está incluido porque bloquea el acceso automatizado.");
  els.sources.textContent = parts.join(" ");
}

load();
