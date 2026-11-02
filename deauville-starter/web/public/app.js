// Public website of the festival. Every piece of data comes from the API
// (see API.md). No framework: plain functions that fetch JSON and build HTML.

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || `Error ${response.status}`);
  }
  return data;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function initials(name) {
  const parts = name.split(" ");
  let result = "";
  for (const part of parts.slice(0, 2)) {
    result += part.charAt(0);
  }
  return result.toUpperCase();
}

function avatarHtml(artist) {
  if (artist.photo_url) {
    return `<img src="${escapeHtml(artist.photo_url)}" alt="" />`;
  }
  return escapeHtml(initials(artist.name));
}

function formatDay(isoDay) {
  const day = new Date(isoDay + "T12:00");
  return day.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

function formatTime(isoDateTime) {
  return isoDateTime.slice(11, 16);
}

function cardHtml(performance) {
  const links = [];
  for (const artist of performance.artists) {
    links.push(
      `<a href="/artist.html?slug=${artist.slug}">${escapeHtml(artist.name)}</a>`,
    );
  }
  let extra = "";
  if (performance.kind === "solo" && performance.min_age > 0) {
    extra += `<span class="badge age">${performance.min_age}+</span>`;
  }
  if (performance.kind === "workshop") {
    extra += `<span class="muted">${performance.places_left} place(s) left</span>`;
  }
  const description = performance.description
    ? `<p class="muted">${escapeHtml(performance.description)}</p>`
    : "";
  return `
    <article class="card ${performance.kind}">
      <div class="time">
        ${formatTime(performance.start)}
        <small>to ${formatTime(performance.end)}</small>
      </div>
      <div>
        <h3>
          <span class="badge ${performance.kind}">${performance.kind}</span>
          ${escapeHtml(performance.title)}
        </h3>
        <p><strong>${escapeHtml(performance.venue_name)}</strong> ${extra}</p>
        <p class="artists-links">${links.join(" · ")}</p>
        ${description}
      </div>
    </article>`;
}

// --- Home page -------------------------------------------------------------

const state = { day: null, venue: "" };

async function showHomePage() {
  const festival = await getJson("/api/festival");
  document.getElementById("dates").textContent =
    `${formatDay(festival.first_day)} to ${formatDay(festival.last_day)}`;

  const days = document.getElementById("days");
  for (const day of festival.days) {
    const button = document.createElement("button");
    button.className = "tab";
    button.textContent = formatDay(day);
    button.dataset.day = day;
    button.addEventListener("click", () => selectDay(day));
    days.appendChild(button);
  }

  const venues = await getJson("/api/venues");
  const filter = document.getElementById("venue-filter");
  for (const venue of venues) {
    const option = document.createElement("option");
    option.value = venue.slug;
    option.textContent = venue.name;
    filter.appendChild(option);
  }
  filter.addEventListener("change", () => {
    state.venue = filter.value;
    showProgramme();
  });

  selectDay(festival.days[0]);
  showNow(festival);
  showArtists();
}

function selectDay(day) {
  state.day = day;
  for (const button of document.querySelectorAll("#days .tab")) {
    button.setAttribute("aria-pressed", button.dataset.day === day);
  }
  showProgramme();
}

async function showProgramme() {
  let url = `/api/programme?day=${state.day}`;
  if (state.venue) {
    url += `&venue=${state.venue}`;
  }
  const performances = await getJson(url);
  const cards = [];
  for (const performance of performances) {
    cards.push(cardHtml(performance));
  }
  document.getElementById("cards").innerHTML =
    cards.join("") || `<p class="muted">No performance.</p>`;
  document.getElementById("count").textContent =
    `${performances.length} performance(s)`;
}

async function showNow(festival) {
  // "?at=2027-06-11T21:00" in the address pretends it is that moment.
  const at = new URLSearchParams(window.location.search).get("at");
  const url = at ? `/api/now?at=${encodeURIComponent(at)}` : "/api/now";
  const now = await getJson(url);
  const box = document.getElementById("now");

  if (now.now_playing.length === 0 && now.up_next.length === 0) {
    box.innerHTML = `<h2>The festival is over. See you next year!</h2>`;
    return;
  }

  let html = "";
  if (now.now_playing.length > 0) {
    html += `<h2><span class="live-dot"></span>On stage now</h2><ul>`;
    for (const performance of now.now_playing) {
      html += `<li><strong>${escapeHtml(performance.title)}</strong>
        at ${escapeHtml(performance.venue_name)}, until ${formatTime(performance.end)}</li>`;
    }
    html += `</ul>`;
  } else if (now.at < festival.first_day) {
    html += `<h2>The festival starts on ${formatDay(festival.first_day)}</h2>
      <p class="muted">Preview a festival evening:
      <a href="?at=${festival.days[1]}T21:00">${formatDay(festival.days[1])}, 21:00</a></p>`;
  }
  if (now.up_next.length > 0) {
    html += `<h2>Up next</h2><ul>`;
    for (const performance of now.up_next) {
      html += `<li>${formatDay(performance.festival_day)}, ${formatTime(performance.start)}:
        <strong>${escapeHtml(performance.title)}</strong>
        at ${escapeHtml(performance.venue_name)}</li>`;
    }
    html += `</ul>`;
  }
  box.innerHTML = html;
}

async function showArtists() {
  const artists = await getJson("/api/artists");
  const tiles = [];
  for (const artist of artists) {
    tiles.push(`
      <a class="artist-tile" href="/artist.html?slug=${artist.slug}">
        <span class="avatar">${avatarHtml(artist)}</span>
        <span>${escapeHtml(artist.name)}</span>
      </a>`);
  }
  document.getElementById("artist-grid").innerHTML = tiles.join("");
}

// --- Artist page -----------------------------------------------------------

async function showArtistPage() {
  const slug = new URLSearchParams(window.location.search).get("slug");
  try {
    const artist = await getJson(`/api/artists/${slug}`);
    document.title = `${artist.name} - Deauville Festival du Rire`;
    document.getElementById("artist-name").textContent = artist.name;
    document.getElementById("avatar").innerHTML = avatarHtml(artist);
    document.getElementById("bio").textContent = artist.bio;
    const cards = [];
    for (const performance of artist.performances) {
      cards.push(
        `<h3 class="muted">${formatDay(performance.festival_day)}</h3>` +
          cardHtml(performance),
      );
    }
    document.getElementById("cards").innerHTML =
      cards.join("") || `<p class="muted">No performance yet.</p>`;
  } catch (error) {
    document.getElementById("artist-name").textContent = "Artist not found";
    document.getElementById("bio").textContent = error.message;
  }
}
