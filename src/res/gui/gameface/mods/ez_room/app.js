// EZ ROOM for ADV: web UI for the Advances battle room. Data comes from the Python view as one
// JSON string (model.data) built from what WG's room sends to its Flash UI; actions go back
// through model.onAction({...}). Step 1 (prototype): display only.

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"];
const STATUS = { NORMAL: 0, READY: 2, BATTLE: 3, LOCKED: 4, CREATOR: 5 };

let data = {};
const ui = { raw: false };

function L(de, en) {
    return data.lang === "de" ? de : en;
}

function send(args) {
    try {
        window.model.onAction(args);
    } catch (e) {
        console.error("onAction failed", e);
    }
}

function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// WG sends many labels as Flash HTML: keep the text only
function txt(s) {
    return String(s == null ? "" : s)
        .replace(/<br\s*\/?>/gi, " ")
        .replace(/<[^>]*>/g, "")
        .replace(/&nbsp;/g, " ")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/&quot;/g, '"')
        .replace(/&amp;/g, "&")
        .trim();
}

function img(path) {
    if (!path) return "";
    if (path.startsWith("../")) return "img://gui/" + path.slice(3);
    if (path.startsWith("gui/")) return "img://" + path;
    return path;
}

function color(c) {
    if (typeof c !== "number") return "";
    return "#" + ("000000" + c.toString(16)).slice(-6);
}

// --- parts -----------------------------------------------------------------------

function renderHeader() {
    const room = data.room || {};
    const ready = data.readyStatus || [];
    const mine = txt(room.mineClanName);
    const enemy = txt(room.enemyClanName);
    const wait = txt(room.waitForBattleDescr);
    let center = "";
    if (mine || enemy) {
        center = `
            <div class="vs">
                <div class="clan mine ${ready[0] ? "ready" : ""}">${esc(mine)}</div>
                <div class="timer" id="timer">${esc(timerText())}</div>
                <div class="clan enemy ${ready[1] ? "ready" : ""}">${esc(enemy)}</div>
            </div>`;
    } else if (wait) {
        center = `<div class="wait">${esc(wait)}</div>`;
    }
    return `
        <div class="header">
            <div class="titles">
                <div class="title">${esc(data.title || L("Vorstoß", "Advance"))}</div>
                <div class="sub">${esc(txt(room.headerDescr))}</div>
            </div>
            <div class="center">${center}</div>
            <div class="tools">
                ${data.dev ? `<div class="btn ghost" data-act="raw">${ui.raw ? L("Raum", "Room") : L("Rohdaten", "Raw data")}</div>` : ""}
                <div class="btn" data-act="hide">${L("Original anzeigen", "Show original")}</div>
            </div>
        </div>`;
}

function renderCandidates() {
    const list = data.candidates || [];
    const me = (data.me || {}).dbID;
    const rows = list.length
        ? list
              .map((p) => {
                  const own = p.dbID === me;
                  const c = own ? "" : color((p.colors || [])[0]);
                  return `
                    <div class="cand ${p.isOffline ? "offline" : ""} ${own ? "own" : ""}">
                        <div class="name" ${c ? `style="color:${c}"` : ""}>${esc(p.userName || p.fullName)}</div>
                        <div class="rating">${esc(p.rating || "")}</div>
                    </div>`;
              })
              .join("")
        : `<div class="empty">${L("Niemand wartet", "Nobody waiting")}</div>`;
    return `
        <div class="panel cands">
            <div class="ptitle">${L("Freiwillige", "Volunteers")}<span class="count">${list.length}</span></div>
            <div class="plist" data-scroll="60">${rows}</div>
        </div>`;
}

function slotStatus(slot) {
    const p = slot.player;
    if (!p) return "";
    if (slot.playerStatus === STATUS.BATTLE) return `<div class="dot battle" title="battle"></div>`;
    if (slot.playerStatus === STATUS.READY || p.readyState) return `<div class="dot ready"></div>`;
    return `<div class="dot"></div>`;
}

function renderSlot(slot, idx) {
    if (!slot || typeof slot !== "object") return "";
    const me = (data.me || {}).dbID;
    const p = slot.player;
    const v = slot.selectedVehicle;
    const highlight = (data.highlight || []).indexOf(idx) !== -1;
    if (slot.isLocked) return "";
    let who;
    if (p) {
        const own = p.dbID === me;
        const c = own ? "" : color((p.colors || [])[0]);
        who = `
            <div class="who">
                ${p.isCommander ? `<div class="crown" title="commander"></div>` : ""}
                <div class="name ${own ? "own" : ""} ${p.isOffline ? "offline" : ""}" ${c ? `style="color:${c}"` : ""}>${esc(p.userName || p.fullName)}</div>
                ${slot.isLegionaries ? `<div class="tag leg">${L("Legionär", "Legionnaire")}</div>` : ""}
            </div>`;
    } else {
        const label = txt(slot.slotLabel) || (slot.isClosed ? L("Gesperrt", "Closed") : L("Freier Platz", "Free slot"));
        who = `<div class="who"><div class="name free">${esc(label)}</div></div>`;
    }
    const veh = v
        ? `
            <div class="veh ${v.isReadyToFight === false || v.enabled === false ? "bad" : ""}">
                ${v.smallIconPath ? `<div class="vicon" style="background-image:url(${img(v.smallIconPath)})"></div>` : ""}
                <div class="tier">${ROMAN[v.level] || ""}</div>
                <div class="vname">${esc(v.shortUserName || v.userName)}</div>
                ${v.state ? `<div class="vstate">${esc(txt(v.state))}</div>` : ""}
            </div>`
        : `<div class="veh none">${p ? L("Kein Panzer", "No tank") : ""}</div>`;
    return `
        <div class="slot ${p ? "taken" : "open"} ${slot.isClosed ? "closed" : ""} ${highlight ? "hl" : ""}">
            <div class="no">${idx + 1}</div>
            ${who}
            <div class="rating">${p ? esc(slot.rating || "") : ""}</div>
            ${veh}
            <div class="status">${slotStatus(slot)}</div>
        </div>`;
}

function renderTeam() {
    const slots = data.slots || [];
    const header = (data.tableHeader || [])[0];
    const vt = data.vehiclesTitle;
    return `
        <div class="panel team">
            <div class="ptitle">
                ${esc(txt(header && header.label) || L("Team", "Team"))}
                <span class="grow"></span>
                ${vt ? `<span class="muted">${esc(txt(vt[0]))}</span>` : ""}
            </div>
            <div class="slots" data-scroll="60">${slots.map(renderSlot).join("")}</div>
        </div>`;
}

function renderSide() {
    const room = data.room || {};
    const map = txt(room.mapName);
    return `
        <div class="side">
            <div class="panel map">
                <div class="ptitle">${L("Karte", "Map")}</div>
                <div class="mapimg" ${data.mapIcon ? `style="background-image:url(${data.mapIcon})"` : ""}>
                    <div class="mapname">${esc(map)}</div>
                </div>
            </div>
            <div class="panel chat">
                <div class="ptitle">${L("Chat", "Chat")}</div>
                <div class="empty">${L("Der Chat kommt in Schritt 3. Bis dahin: „Original anzeigen“.", "Chat comes in step 3. Until then: \"Show original\".")}</div>
            </div>
        </div>`;
}

function renderFooter() {
    const opened = data.opened || [];
    const comment = txt(data.comment);
    return `
        <div class="footer">
            <div class="muted">${esc(txt(opened[1]))}</div>
            ${comment ? `<div class="comment">${esc(comment)}</div>` : ""}
            <div class="grow"></div>
            <div class="muted small">EZ ROOM ${esc(data.version || "")}${data.dev ? " · DEV (F5)" : ""}</div>
        </div>`;
}

function renderRaw() {
    const raw = data.raw || {};
    const names = Object.keys(raw.calls || {}).sort();
    const blocks = names.map((n) => `<div class="rawname">${esc(n)}</div><div class="rawval">${esc(JSON.stringify(raw.calls[n], null, 1))}</div>`);
    const slotNames = Object.keys(raw.slotCalls || {}).sort();
    slotNames.forEach((n) => blocks.push(`<div class="rawname">${esc(n)} (per slot)</div><div class="rawval">${esc(JSON.stringify(raw.slotCalls[n], null, 1))}</div>`));
    return `<div class="panel raw"><div class="plist" data-scroll="200">${blocks.join("")}</div></div>`;
}

// --- timer -----------------------------------------------------------------------

let timerBase = null; // {deltaTime, at}

function timerText() {
    const t = data.timer;
    if (!t || typeof t.deltaTime !== "number") return "--:--";
    const elapsed = timerBase ? (Date.now() - timerBase.at) / 1000 : 0;
    const left = Math.max(0, Math.round(t.deltaTime - (data.timerAge || 0) - elapsed));
    const m = Math.floor(left / 60);
    const s = left % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
}

setInterval(() => {
    const el = document.getElementById("timer");
    if (el) el.textContent = timerText();
}, 500);

// --- render ----------------------------------------------------------------------

function render() {
    const root = document.getElementById("root");
    const keep = {};
    root.querySelectorAll("[data-scroll]").forEach((el, i) => (keep[i] = el.scrollTop));
    const body = ui.raw ? renderRaw() : `${renderCandidates()}${renderTeam()}${renderSide()}`;
    root.innerHTML = `${renderHeader()}<div class="body">${body}</div>${renderFooter()}`;
    root.querySelectorAll("[data-scroll]").forEach((el, i) => {
        if (keep[i]) el.scrollTop = keep[i];
    });
}

// Gameface has no Element.closest
function closest(el, attr) {
    while (el && el.getAttribute) {
        if (el.getAttribute(attr) !== null && el.getAttribute(attr) !== undefined) return el;
        el = el.parentElement;
    }
    return null;
}

document.addEventListener("click", (e) => {
    const el = closest(e.target, "data-act");
    if (!el) return;
    const act = el.getAttribute("data-act");
    if (act === "hide") send({ action: "hide" });
    else if (act === "raw") {
        ui.raw = !ui.raw;
        render();
    }
});

document.addEventListener(
    "wheel",
    (e) => {
        let el = e.target;
        while (el && el.getAttribute && !el.getAttribute("data-scroll")) el = el.parentElement;
        if (!el || !el.getAttribute) return;
        e.preventDefault();
        e.stopPropagation();
        const step = Number(el.getAttribute("data-scroll")) || 60;
        el.scrollTop += e.deltaY > 0 ? -step : step; // Gameface: deltaY > 0 = wheel up
    },
    { capture: true, passive: false }
);

document.addEventListener("keydown", (e) => {
    if (e.keyCode === 116 && data.dev) send({ action: "devReload" });
    else if (e.keyCode === 27) send({ action: "hide" });
});

// --- model binding ---------------------------------------------------------------

function readModel() {
    try {
        const raw = window.model && window.model.data;
        if (!raw) return;
        data = JSON.parse(raw);
        timerBase = { at: Date.now() };
        render();
    } catch (e) {
        console.error("ez_room: bad model data", e);
        send({ action: "log", msg: "bad model data: " + e });
    }
}

engine.whenReady.then(() => {
    engine.on("viewEnv.onDataChanged", readModel);
    viewEnv.addDataChangedCallback("model", 0, true);
    readModel();
});
