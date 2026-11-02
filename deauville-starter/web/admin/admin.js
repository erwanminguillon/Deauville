// Admin of the festival: schedule, edit and cancel performances, add artists.
// It only calls the API (see API.md); every rule is checked by the server.

let editedId = null; // id of the performance being edited, or null
let performancesById = {};

async function callApi(method, url, body) {
  const options = { method: method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(url, options);
  if (response.status === 204) {
    return null;
  }
  const data = await response.json();
  if (!response.ok) {
    throw new Error(errorText(data));
  }
  return data;
}

// FastAPI validation errors are a list, festival errors a sentence.
function errorText(data) {
  if (typeof data.detail === "string") {
    return data.detail;
  }
  const lines = [];
  for (const problem of data.detail) {
    lines.push(`${problem.loc.slice(1).join(".")}: ${problem.msg}`);
  }
  return lines.join(" / ");
}

function showMessage(text, kind) {
  const box = document.getElementById("message");
  box.innerHTML = "";
  const div = document.createElement("div");
  div.className = `message ${kind}`;
  div.textContent = text;
  box.appendChild(div);
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// --- Loading ---------------------------------------------------------------

async function loadChoices() {
  const venues = await callApi("GET", "/api/venues");
  const artists = await callApi("GET", "/api/artists");

  for (const select of document.querySelectorAll(".venue-select")) {
    select.innerHTML = "";
    for (const venue of venues) {
      select.add(new Option(`${venue.name} (${venue.capacity})`, venue.slug));
    }
  }
  for (const select of document.querySelectorAll(".artist-select")) {
    const current = select.value;
    select.innerHTML = "";
    for (const artist of artists) {
      select.add(new Option(artist.name, artist.slug));
    }
    if (current) {
      select.value = current;
    }
  }

  const acts = document.getElementById("acts");
  acts.innerHTML = "";
  for (const artist of artists) {
    const label = document.createElement("label");
    label.innerHTML = `<input type="checkbox" value="${artist.slug}" /> `;
    label.append(artist.name);
    acts.appendChild(label);
  }
}

async function loadSchedule() {
  const performances = await callApi("GET", "/api/programme");
  performancesById = {};
  const rows = document.getElementById("rows");
  rows.innerHTML = "";
  for (const performance of performances) {
    performancesById[performance.id] = performance;
    const row = document.createElement("tr");
    if (performance.id === editedId) {
      row.className = "editing";
    }
    row.innerHTML = `
      <td>${performance.festival_day}</td>
      <td>${performance.start.slice(11)}-${performance.end.slice(11)}</td>
      <td></td><td></td><td></td>
      <td class="buttons"></td>`;
    row.children[2].textContent = performance.venue_name;
    row.children[3].textContent = `${performance.title} (${performance.kind})`;
    row.children[4].textContent = performance.summary;

    const buttons = row.children[5];
    if (performance.kind === "workshop") {
      buttons.appendChild(
        button("Register", () => registerParticipant(performance)),
      );
    }
    buttons.appendChild(button("Edit", () => startEdit(performance.id)));
    buttons.appendChild(
      button("Cancel", () => cancelPerformance(performance), "danger"),
    );
    rows.appendChild(row);
  }
}

function button(text, onClick, className) {
  const element = document.createElement("button");
  element.type = "button";
  element.textContent = text;
  if (className) {
    element.className = className;
  }
  element.addEventListener("click", onClick);
  return element;
}

// --- Performance form ------------------------------------------------------

function showFieldsOfKind() {
  const kind = document.getElementById("kind").value;
  for (const fieldset of document.querySelectorAll("fieldset[data-kind]")) {
    fieldset.hidden = fieldset.dataset.kind !== kind;
  }
}

function readPerformanceForm() {
  const form = document.getElementById("performance-form");
  const kind = form.elements.kind.value;
  const body = {
    kind: kind,
    title: form.elements.title.value,
    venue: form.elements.venue.value,
    start: form.elements.start.value,
    duration_minutes: Number(form.elements.duration_minutes.value),
    description: form.elements.description.value,
  };
  if (kind === "solo") {
    body.artist = form.elements.artist.value;
    body.min_age = Number(form.elements.min_age.value);
  }
  if (kind === "lineup") {
    body.host = form.elements.host.value;
    body.acts = [];
    for (const box of document.querySelectorAll("#acts input:checked")) {
      body.acts.push(box.value);
    }
  }
  if (kind === "workshop") {
    body.teacher = form.elements.teacher.value;
    body.max_participants = Number(form.elements.max_participants.value);
    if (editedId !== null) {
      body.participants = performancesById[editedId].participants || [];
    }
  }
  return body;
}

async function submitPerformance(event) {
  event.preventDefault();
  const body = readPerformanceForm();
  try {
    if (editedId === null) {
      const created = await callApi("POST", "/api/performances", body);
      showMessage(
        `Scheduled: ${created.title}, ${created.start.replace("T", " ")}.`,
        "ok",
      );
    } else {
      const updated = await callApi(
        "PUT",
        `/api/performances/${editedId}`,
        body,
      );
      showMessage(`Updated: ${updated.title}.`, "ok");
      stopEdit();
    }
    await loadSchedule();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

function startEdit(id) {
  const performance = performancesById[id];
  const form = document.getElementById("performance-form");
  editedId = id;
  form.elements.kind.value = performance.kind;
  form.elements.title.value = performance.title;
  form.elements.venue.value = performance.venue;
  form.elements.start.value = performance.start;
  form.elements.duration_minutes.value = performance.duration_minutes;
  form.elements.description.value = performance.description;
  if (performance.kind === "solo") {
    form.elements.artist.value = performance.artist;
    form.elements.min_age.value = performance.min_age;
  }
  if (performance.kind === "lineup") {
    form.elements.host.value = performance.host;
    for (const box of document.querySelectorAll("#acts input")) {
      box.checked = performance.acts.includes(box.value);
    }
  }
  if (performance.kind === "workshop") {
    form.elements.teacher.value = performance.teacher;
    form.elements.max_participants.value = performance.max_participants;
  }
  showFieldsOfKind();
  document.getElementById("form-title").textContent =
    `Edit: ${performance.title}`;
  document.getElementById("submit").textContent = "Save changes";
  document.getElementById("cancel-edit").hidden = false;
  form.scrollIntoView({ behavior: "smooth" });
  loadSchedule();
}

function stopEdit() {
  editedId = null;
  document.getElementById("performance-form").reset();
  document.getElementById("form-title").textContent = "New performance";
  document.getElementById("submit").textContent = "Schedule";
  document.getElementById("cancel-edit").hidden = true;
  showFieldsOfKind();
  loadSchedule();
}

async function cancelPerformance(performance) {
  if (
    !confirm(
      `Cancel "${performance.title}" (${performance.start.replace("T", " ")})?`,
    )
  ) {
    return;
  }
  try {
    await callApi("DELETE", `/api/performances/${performance.id}`);
    showMessage(`Cancelled: ${performance.title}.`, "ok");
    if (editedId === performance.id) {
      stopEdit();
    }
    await loadSchedule();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

async function registerParticipant(performance) {
  const name = prompt(`Name of the participant for "${performance.title}":`);
  if (name === null) {
    return;
  }
  try {
    const updated = await callApi(
      "POST",
      `/api/performances/${performance.id}/participants`,
      { name: name },
    );
    showMessage(
      `${name} registered. ${updated.places_left} place(s) left.`,
      "ok",
    );
    await loadSchedule();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

// --- Artist form -----------------------------------------------------------

async function submitArtist(event) {
  event.preventDefault();
  const form = event.target;
  try {
    const artist = await callApi("POST", "/api/artists", {
      name: form.elements.name.value,
      bio: form.elements.bio.value,
      photo_url: form.elements.photo_url.value,
    });
    showMessage(`Artist added: ${artist.name}.`, "ok");
    form.reset();
    await loadChoices();
  } catch (error) {
    showMessage(error.message, "error");
  }
}

// --- Start -----------------------------------------------------------------

async function start() {
  document.getElementById("kind").addEventListener("change", showFieldsOfKind);
  document
    .getElementById("performance-form")
    .addEventListener("submit", submitPerformance);
  document.getElementById("cancel-edit").addEventListener("click", stopEdit);
  document
    .getElementById("artist-form")
    .addEventListener("submit", submitArtist);
  showFieldsOfKind();
  try {
    await loadChoices();
    await loadSchedule();
  } catch (error) {
    showMessage(`The API does not answer: ${error.message}`, "error");
  }
}

start();
