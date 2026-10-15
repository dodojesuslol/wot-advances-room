// EZ ROOM for ADV: web UI for the Advances battle room. Data comes from the Python view as one
// JSON string (model.data) built from what WG's room sends to its Flash UI; actions go back
// through model.onAction({...}), which runs the room's own handlers (same as WG's Flash UI).

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"];
const STATUS = { NORMAL: 0, READY: 2, BATTLE: 3, LOCKED: 4, CREATOR: 5 };

let data = {};
let sizeLogged = false;
const ui = {
    raw: false,
    selCand: 0, // commander: candidate picked to be put into a slot
    kickArm: 0, // dbID whose kick button was clicked once (second click kicks)
};
let kickTimer = 0;

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

function me() {
    return data.me || {};
}
function rally() {
    return data.rally || {};
}
function isCommander() {
    return !!(me().isCommander || rally().isCommander);
}
function slotOf(dbID) {
    return (data.slots || []).findIndex((s) => s && s.player && s.player.dbID === dbID);
}

function kickButton(dbID) {
    const armed = ui.kickArm === dbID;
    return `<div class="ibtn kick ${armed ? "armed" : ""}" data-act="kick" data-id="${dbID}" title="kick">${armed ? L("Sicher?", "Sure?") : "✕"}</div>`;
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
                <div class="btn" data-act="hide">${L("Original", "Original")}</div>
            </div>
        </div>`;
}

function renderCandidates() {
    // the list also holds group headers ({headerText}) and spacers ({emptyRender})
    const list = data.candidates || [];
    const players = list.filter((p) => p.dbID);
    const me = (data.me || {}).dbID;
    const rows = players.length
        ? list
              .map((p) => {
                  if (p.headerText) return `<div class="cgroup">${esc(txt(p.headerText))}</div>`;
                  if (!p.dbID) return "";
                  const own = p.dbID === me;
                  const c = own ? "" : color((p.colors || [])[0]);
                  const pick = isCommander() && rally().canAssignToSlot;
                  return `
                    <div data-user="${p.dbID}" class="cand ${p.isOffline ? "offline" : ""} ${own ? "own" : ""} ${pick ? "pickable" : ""} ${ui.selCand === p.dbID ? "sel" : ""}" ${pick ? `data-act="pickCand" data-id="${p.dbID}"` : ""}>
                        ${p.isInvite ? `<div class="inv" title="invited"></div>` : ""}
                        <div class="name" ${c ? `style="color:${c}"` : ""}>${esc(p.userName || p.fullName)}</div>
                        <div class="rating">${esc(p.rating || "")}</div>
                        ${isCommander() && !own ? `<div class="acts">${kickButton(p.dbID)}</div>` : ""}
                    </div>`;
              })
              .join("")
        : `<div class="empty">${L("Niemand wartet", "Nobody waiting")}</div>`;
    return `
        <div class="panel cands">
            <div class="ptitle">${L("Freiwillige", "Volunteers")}<span class="count">${players.length}</span></div>
            <div class="plist" data-scroll="60">${rows}</div>
            ${renderRoomActions()}
        </div>`;
}

function renderRoomActions() {
    const opened = data.opened || [];
    const conf = data.configure || {};
    const btns = [];
    if (rally().canInvite) btns.push(`<div class="btn wide" data-act="invite">${L("Einladen", "Invite")}</div>`);
    if (isCommander() && opened[0] && conf.isRoomStatusEnabled !== false) btns.push(`<div class="btn wide" data-act="toggleOpen" title="${esc(txt(opened[2]))}">${esc(txt(opened[0]))}</div>`);
    if (isCommander() && conf.isEnabled) btns.push(`<div class="btn wide" data-act="configure">${L("Konfigurieren", "Configure")}</div>`);
    const status = txt(opened[1]);
    if (!btns.length && !status) return "";
    return `<div class="pfoot">${btns.join("")}${status ? `<div class="pnote">${esc(status)}</div>` : ""}</div>`;
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
    const highlight = ui.selCand && (data.highlight || []).indexOf(idx) !== -1;
    if (slot.isLocked) return "";
    const mine = !!(p && p.dbID === me);
    // what a click on the row does
    let rowAct = "";
    if (highlight) rowAct = `data-act="assign" data-slot="${idx}"`;
    else if (!p && slot.canBeTaken && !(data.me || {}).isInSlot && !isCommander()) rowAct = `data-act="takeSlot" data-slot="${idx}"`;
    const acts = [];
    if (mine) acts.push(`<div class="ibtn" data-act="leaveSlot" data-id="${p.dbID}" title="leave">${L("Verlassen", "Leave")}</div>`);
    else if (p && isCommander() && slot.isRemoveAvailable) {
        acts.push(`<div class="ibtn" data-act="leaveSlot" data-id="${p.dbID}" title="to volunteers">${L("Raus", "Out")}</div>`);
        acts.push(kickButton(p.dbID));
    }
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
    const vehAct = mine ? `data-act="chooseVehicle" data-cd="${v ? v.intCD : 0}"` : "";
    const veh = v
        ? `
            <div class="veh ${mine ? "pick" : ""} ${v.isReadyToFight === false || v.enabled === false ? "bad" : ""}" ${vehAct}>
                ${v.smallIconPath ? `<div class="vicon" style="background-image:url(${img(v.smallIconPath)})"></div>` : ""}
                <div class="tier">${ROMAN[v.level] || ""}</div>
                <div class="vname">${esc(v.shortUserName || v.userName)}</div>
                ${v.state ? `<div class="vstate">${esc(txt(v.state))}</div>` : ""}
            </div>`
        : mine
          ? `<div class="veh none pick" ${vehAct}>${L("Panzer wählen", "Choose tank")}</div>`
          : `<div class="veh none">${p ? L("Kein Panzer", "No tank") : rowAct.indexOf("takeSlot") !== -1 ? `<span class="take">${L("Platz nehmen", "Take slot")}</span>` : ""}</div>`;
    return `
        <div ${p ? `data-user="${p.dbID}"` : ""} class="slot ${p ? "taken" : "open"} ${mine ? "mine" : ""} ${slot.isClosed ? "closed" : ""} ${highlight ? "hl" : ""} ${rowAct ? "clickable" : ""}" ${rowAct}>
            <div class="no">${idx + 1}</div>
            ${who}
            <div class="rating">${p ? esc(slot.rating || "") : ""}</div>
            ${veh}
            ${acts.length ? `<div class="acts ${mine ? "always" : ""}">${acts.join("")}</div>` : ""}
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
            ${renderReadyBar()}
        </div>`;
}

function renderReadyBar() {
    const ab = data.actionButton || {};
    const state = txt(ab.stateString);
    const hint = ui.selCand ? L("Grün markierten Platz anklicken (Esc = abbrechen)", "Click a green slot (Esc = cancel)") : state;
    const label = txt(ab.label) || L("Bereit!", "Ready!");
    return `
        <div class="readybar">
            <div class="state ${ui.selCand ? "hint" : ""}">${esc(hint)}</div>
            <div class="btn main ${ab.isEnabled ? "" : "off"} ${ab.isReady ? "isready" : ""}" ${ab.isEnabled ? `data-act="ready"` : ""}>${esc(label)}</div>
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
                <div class="empty">${L("Chat kommt in Schritt 3 – bis dahin „Original“.", "Chat comes in step 3 – until then \"Original\".")}</div>
            </div>
        </div>`;
}

function renderFooter() {
    const comment = txt(data.comment);
    return `
        <div class="footer">
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

// view size = room content area of WG's window (px); Gameface windows are sized from JS
// (viewEnv.resizeViewPx, same as WG's own OfferBannerWindow)
let appliedSize = "";
function applyFrame() {
    const f = data.frame;
    if (!f || f.length < 4 || f[2] <= 0 || f[3] <= 0) return;
    const key = f[2] + "x" + f[3];
    if (key === appliedSize) return;
    appliedSize = key;
    try {
        if (window.viewEnv && viewEnv.resizeViewPx) viewEnv.resizeViewPx(f[2], f[3]);
    } catch (e) {
        send({ action: "log", msg: "resizeViewPx failed: " + e });
    }
    document.documentElement.style.width = document.body.style.width = "100%";
    document.documentElement.style.height = document.body.style.height = "100%";
}

function render() {
    applyFrame();
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
    e.stopPropagation();
    const act = el.getAttribute("data-act");
    const id = Number(el.getAttribute("data-id"));
    const slot = Number(el.getAttribute("data-slot"));
    if (act === "hide") send({ action: "hide" });
    else if (act === "raw") {
        ui.raw = !ui.raw;
        render();
    } else if (act === "pickCand") {
        ui.selCand = ui.selCand === id ? 0 : id;
        if (ui.selCand) send({ action: "highlight", dbID: id });
        render();
    } else if (act === "assign") {
        send({ action: "assign", slot: slot, dbID: ui.selCand });
        ui.selCand = 0;
        render();
    } else if (act === "takeSlot") send({ action: "takeSlot", slot: slot });
    else if (act === "leaveSlot") send({ action: "leaveSlot", dbID: id });
    else if (act === "kick") {
        if (ui.kickArm === id) {
            ui.kickArm = 0;
            send({ action: "kick", dbID: id });
        } else {
            ui.kickArm = id;
            if (kickTimer) clearTimeout(kickTimer);
            kickTimer = setTimeout(() => {
                ui.kickArm = 0;
                render();
            }, 3000);
        }
        render();
    } else if (act === "chooseVehicle") send({ action: "chooseVehicle", cd: Number(el.getAttribute("data-cd")) || 0 });
    else if (act === "ready" || act === "invite" || act === "toggleOpen" || act === "configure") send({ action: act });
});

// right click on a player: WG's player context menu (opened by Python)
document.addEventListener("mousedown", (e) => {
    if (e.button !== 2) return;
    const el = closest(e.target, "data-user");
    if (!el) return;
    e.preventDefault();
    e.stopPropagation();
    const id = Number(el.getAttribute("data-user"));
    if (id && id !== (data.me || {}).dbID) send({ action: "contextMenu", dbID: id });
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
    else if (e.keyCode === 27) {
        if (ui.selCand || ui.kickArm) {
            ui.selCand = ui.kickArm = 0;
            render();
        } else send({ action: "hide" });
    }
});

// --- model binding ---------------------------------------------------------------

function readModel() {
    try {
        const raw = window.model && window.model.data;
        if (!raw) return;
        data = JSON.parse(raw);
        if (ui.selCand && (!(data.candidates || []).some((c) => c.dbID === ui.selCand) || slotOf(ui.selCand) !== -1)) ui.selCand = 0;
        timerBase = { at: Date.now() };
        render();
        if (data.frame && !sizeLogged) {
            sizeLogged = true;
            setTimeout(() => {
                let env = "";
                try {
                    env = " viewSizePx " + JSON.stringify(viewEnv.getViewSizePx()) + " posRem " + JSON.stringify(viewEnv.getViewGlobalPositionRem()) + " scale " + viewEnv.getScale();
                } catch (e) {
                    env = " viewEnv: " + e;
                }
                send({ action: "log", msg: "frame " + JSON.stringify(data.frame) + " body " + document.body.offsetWidth + "x" + document.body.offsetHeight + env });
            }, 500);
        }
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
