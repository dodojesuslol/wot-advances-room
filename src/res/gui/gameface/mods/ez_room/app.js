// EZ ROOM for ADV: web UI for the Advances battle room. Data comes from the Python view as one
// JSON string (model.data) built from what WG's room sends to its Flash UI; actions go back
// through model.onAction({...}), which runs the room's own handlers (same as WG's Flash UI).

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"];
const STATUS = { NORMAL: 0, READY: 2, BATTLE: 3, LOCKED: 4, CREATOR: 5 };

let data = {};
let sizeLogged = false;
const ui = {
    raw: false,
    selCand: 0, // commander: volunteer being dragged onto a slot (green slots = WG's allowed ones)
    dragOut: 0, // commander: team member being dragged onto the volunteers list (= leaveSlot)
    hoverRow: "", // data-user of the row under the mouse (its buttons are shown, see markHover)
    sort: null, // team table sort {key: "clan"|"name"|"rating"|"tank", dir: 1|-1}; null = slot order
};

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

// one click kicks the player out of the room (requestToKick)
function kickButton(dbID) {
    return `<div class="ibtn kick" data-act="kick" data-id="${dbID}" data-tip="${esc(L("Aus dem Raum werfen", "Kick from the room"))}">✕</div>`;
}

// --- parts -----------------------------------------------------------------------

// WG's voice chat: player is speaking right now (data.speaking = dbIDs, live from Python)
function speaking(dbID) {
    return (data.speaking || []).indexOf(dbID) >= 0;
}

function renderHeader() {
    const room = data.room || {};
    const ready = data.readyStatus || [];
    const mine = txt(room.mineClanName);
    const enemy = txt(room.enemyClanName);
    const wait = txt(room.waitForBattleDescr);
    // WG's direction graphic (as_setDirectionS: definition / attack0-5 / defense0-5), own row under
    // the header with the clan names left and right; exported from fortCmp.swf (ConnectedDirectsUI)
    const dir = data.direction && data.direction[0];
    const showDir = !!dir && (mine || enemy);
    let center = "";
    if (showDir) {
        center = "";
    } else if (mine || enemy) {
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
                <!-- no own title: WG's window frame above already shows it -->
                <div class="sub">${esc(txt(room.headerDescr))}</div>
                ${data.back && data.back.label ? `<div class="back" data-act="back" data-tip="${esc(data.back.tip)}">‹ ${esc(data.back.label)}</div>` : ""}
            </div>
            <div class="center">${center}</div>
            ${showDir ? `<div class="hcenter"><div class="timer" id="timer">${esc(timerText())}</div></div>` : ""}
            ${renderReserves()}
            <div class="tools">
                ${data.dev ? `<div class="btn ghost" data-act="raw">${ui.raw ? L("Raum", "Room") : L("Rohdaten", "Raw data")}</div>` : ""}
                <div class="btn" data-act="hide">${L("Original", "Original")}</div>
            </div>
        </div>
        ${showDir ? `
        <div class="dirrow">
            <div class="clan mine ${ready[0] ? "ready" : ""}">${esc(mine)}</div>
            ${data.readyDirections === false
                ? `<div class="dirimg dirwait">${L("Richtungen werden ermittelt …", "Determining directions …")}</div>`
                : `<div class="dirimg" style="background-image:url(img://gui/maps/icons/ez_room/direction/${esc(dir)}.png)"></div>`}
            <div class="clan enemy ${ready[1] ? "ready" : ""}">${esc(enemy)}</div>
        </div>` : ""}`;
}

// reserve slots (top right like in WG's room); click opens the list (data.reserveOptions)
function renderReserves() {
    const list = data.reserves || [];
    if (!list.length) return "";
    const enabled = data.reservesEnabled || [];
    const open = data.reserveOptions ? data.reserveOptions.slot : -1;
    return `<div class="reserves">${list
        .map((r, i) => {
            const on = !!enabled[i];
            const tip = txt(String(r.tooltip || "").replace(/\{\/?HEADER\}/g, "").replace(/\{BODY\}/g, " – ").replace(/\{\/BODY\}/g, ""));
            return `<div class="rslot ${on ? "on" : "off"} ${open === i ? "open" : ""} ${r.id ? "set" : ""}" ${on ? `data-act="reserveOpen" data-slot="${i}"` : ""} data-tip="${esc(tip)}">
                <div class="ricon" style="background-image:url(img://gui/maps/icons/reserveTypes/${esc(r.slotType)}.png)"></div>
                ${r.id && r.level ? `<div class="rlvl">${ROMAN[r.level] || r.level}</div>` : ""}
            </div>`;
        })
        .join("")}</div>`;
}

function renderReservePopup() {
    const o = data.reserveOptions;
    if (!o) return "";
    const items = (o.items || [])
        .map(
            (it) => `
        <div class="ropt ${it.selected ? "sel" : ""} ${!it.selected && it.count <= 0 ? "none" : ""}" ${it.selected || it.count > 0 ? `data-act="reserveSelect" data-id="${it.id}" data-remove="${it.selected ? 1 : 0}"` : ""}>
            <div class="ricon" style="background-image:url(img://gui/maps/icons/reserveTypes/${esc(it.type)}.png)"></div>
            <div class="rtext">
                <div class="rtitle">${esc(it.title)} <span class="muted">${ROMAN[it.level] || it.level}</span></div>
                <div class="rdesc">${esc(it.bonus ? it.bonus + " " : "")}${esc(it.desc)}</div>
            </div>
            <div class="rcount">${it.selected ? L("Entfernen", "Remove") : "×" + it.count}</div>
        </div>`
        )
        .join("");
    return `
        <div class="rpopup" data-popup="1">
            <div class="ptitle">${esc(o.title)}</div>
            ${items || `<div class="empty">${L("Keine Reserven", "No reserves")}</div>`}
        </div>`;
}

// volunteers table head "Spieler / Wertung": click asc -> desc -> WG's order; sorted inside each
// group (clan members / legionaries), saved in settings.json as candSort
function candSortValue(p, key) {
    if (key === "rating") {
        const n = parseInt(String(p.rating || "").replace(/[^0-9]/g, ""), 10);
        return isNaN(n) ? -1 : n;
    }
    return String(p.userName || p.fullName || "").toLowerCase();
}

function sortedCandidates(list) {
    const sort = ui.candSort;
    if (!sort || !sort.key || !sort.dir) return list;
    const out = [];
    let group = [];
    const flush = () => {
        group.sort((a, b) => {
            // players who are not in the room (offline) always at the bottom of their group
            const oa = !!a[0].isOffline;
            const ob = !!b[0].isOffline;
            if (oa !== ob) return oa ? 1 : -1;
            const va = candSortValue(a[0], sort.key);
            const vb = candSortValue(b[0], sort.key);
            const c = typeof va === "number" ? va - vb : va < vb ? -1 : va > vb ? 1 : 0;
            return c * sort.dir || a[1] - b[1];
        });
        group.forEach((g) => out.push(g[0]));
        group = [];
    };
    list.forEach((p, i) => {
        if (p.dbID) group.push([p, i]);
        else {
            flush();
            out.push(p);
        }
    });
    flush();
    return out;
}

function renderCandColumns() {
    const sort = ui.candSort || {};
    const head = (key, label, cls) => {
        const on = sort.key === key && sort.dir;
        const arrow = on ? (sort.dir > 0 ? "▲" : "▼") : "";
        return `<div class="col ${cls} ${on ? "on" : ""}" data-act="candSort" data-key="${key}">${esc(label)}<span class="arrow">${arrow}</span></div>`;
    };
    return `
        <div class="cols ccols">
            ${head("name", L("Spieler", "Player"), "cc-name")}
            ${head("rating", L("Wertung", "Rating"), "cc-rating")}
        </div>`;
}

function renderCandidates() {
    // the list also holds group headers ({headerText}) and spacers ({emptyRender})
    const list = data.candidates || [];
    const players = list.filter((p) => p.dbID);
    const me = (data.me || {}).dbID;
    const rows = players.length
        ? sortedCandidates(list)
              .map((p) => {
                  if (p.headerText) return `<div class="cgroup">${esc(txt(p.headerText))}</div>`;
                  if (!p.dbID) return "";
                  const own = p.dbID === me;
                  const c = own ? "" : color((p.colors || [])[0]);
                  const pick = isCommander() && rally().canAssignToSlot;
                  return `
                    <div data-user="${p.dbID}" class="cand ${p.isOffline ? "offline" : ""} ${own ? "own" : ""} ${pick ? "pickable" : ""} ${ui.selCand === p.dbID ? "sel" : ""}" ${pick ? `data-cand="${p.dbID}" data-tip="${esc(L("Klick: nächster freier Platz · Ziehen: auf einen Platz", "Click: next free slot · Drag: onto a slot"))}"` : ""}>
                        ${p.isInvite ? `<div class="inv" title="invited"></div>` : ""}
                        ${p.statusIcon ? `<div class="ustatus" style="background-image:url(${img(p.statusIcon)})"></div>` : ""}
                        <div class="name ${speaking(p.dbID) ? "speak" : ""}" ${c ? `style="color:${c}"` : ""}>${esc(p.userName || p.fullName)}</div>
                        <div class="rating">${esc(p.rating || "")}</div>
                        ${isCommander() && !own ? `<div class="acts">${kickButton(p.dbID)}</div>` : ""}
                    </div>`;
              })
              .join("")
        : `<div class="empty">${L("Niemand wartet", "Nobody waiting")}</div>`;
    return `
        <div class="panel cands ${ui.dragOut ? "dropout" : ""}" ${ui.dragOut ? `data-dropout="1"` : ""}>
            <div class="ptitle">${L("Freiwillige", "Volunteers")}<span class="count">${players.length}</span></div>
            ${players.length ? renderCandColumns() : ""}
            <div class="pwrap">
                <div class="plist" id="candlist" data-scroll="60">${rows}</div>
                ${scrollbar("candlist")}
            </div>
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
    // WG's IndicationOfStatus_UI frames (guiControlsLobby.swf): normal / ready / inBattle / locked
    let frame = "normal";
    if (slot.playerStatus === STATUS.BATTLE) frame = "inBattle";
    else if (slot.playerStatus === STATUS.LOCKED) frame = "locked";
    else if (slot.playerStatus === STATUS.READY || p.readyState) frame = "ready";
    return `<div class="sicon" style="background-image:url(img://gui/maps/icons/ez_room/status/${frame}.png)"></div>`;
}

function renderSlot(slot, idx) {
    if (!slot || typeof slot !== "object") return "";
    const me = (data.me || {}).dbID;
    const p = slot.player;
    const v = slot.selectedVehicle;
    const highlight = ui.selCand && (data.highlight || []).indexOf(idx) !== -1;
    if (slot.isLocked) return "";
    const mine = !!(p && p.dbID === me);
    // ready players: whole row green (same info as the green status dot)
    const ready = !!(p && slot.playerStatus !== STATUS.BATTLE && (slot.playerStatus === STATUS.READY || p.readyState));
    // what a click on the row does
    let rowAct = "";
    if (!p && slot.canBeTaken && !(data.me || {}).isInSlot && !isCommander()) rowAct = `data-act="takeSlot" data-slot="${idx}"`;
    const acts = [];
    if (mine) acts.push(`<div class="ibtn" data-act="leaveSlot" data-id="${p.dbID}" title="leave">${L("Verlassen", "Leave")}</div>`);
    else if (p && isCommander() && slot.isRemoveAvailable) {
        acts.push(`<div class="ibtn" data-act="leaveSlot" data-id="${p.dbID}" data-tip="${esc(L("Zurück zu den Freiwilligen", "Back to the volunteers"))}">${L("Raus", "Out")}</div>`);
        acts.push(kickButton(p.dbID));
    }
    // equipment roles (slot.roleIcon from WG: gunner / inspire / gunnerAndInspire): icons after the
    // tank name for everyone; the commander gets a give/take button per role in the row
    const role = String(slot.roleIcon || "");
    const hasArt = role.indexOf("gunner") === 0;
    const hasIns = role.indexOf("nspire") !== -1;
    // shown on hover like Raus / kick; in the own row on hover left of "Verlassen" (.roleover)
    // only where WG's context menu would offer the item (data.roleRights from Python, WG's checks)
    const rights = p ? (data.roleRights || {})[String(p.dbID)] : null;
    const roleActs = rights ? `${rights.artillery ? roleButton(p.dbID, "artillery", rights.artillery === "take") : ""}${rights.inspire ? roleButton(p.dbID, "inspire", rights.inspire === "take") : ""}` : "";
    const roleIcons = p ? `${hasArt ? roleIcon("artillery") : ""}${hasIns ? roleIcon("inspire") : ""}` : "";
    let who;
    if (p) {
        const own = p.dbID === me;
        const c = own ? "" : color((p.colors || [])[0]);
        who = `
            <div class="clan">${esc(p.clanAbbrev ? "[" + p.clanAbbrev + "]" : "")}</div>
            <div class="who">
                ${p.isCommander ? `<div class="crown" data-tip="${esc(L("Kommandant", "Commander"))}"></div>` : ""}
                <div class="name ${own ? "own" : ""} ${p.isOffline ? "offline" : ""} ${speaking(p.dbID) ? "speak" : ""}" ${c ? `style="color:${c}"` : ""}>${esc(p.userName || p.fullName)}</div>
                ${slot.isLegionaries ? `<div class="tag leg">${L("Legionär", "Legionnaire")}</div>` : ""}
            </div>`;
    } else {
        const label = txt(slot.slotLabel) || (slot.isClosed ? L("Gesperrt", "Closed") : L("Freier Platz", "Free slot"));
        who = `<div class="clan"></div><div class="who"><div class="name free">${esc(label)}</div></div>`;
    }
    const vehAct = mine ? `data-act="chooseVehicle" data-cd="${v ? v.intCD : 0}"` : "";
    const veh = v
        ? `
            <div class="veh ${mine ? "pick" : ""} ${v.isReadyToFight === false || v.enabled === false ? "bad" : ""}" ${vehAct} data-tip="${esc(v.userName || "")}">
                <!-- no tank image (user, 0.7.19): more room for the name and the role icons -->
                <div class="tier">${ROMAN[v.level] || ""}</div>
                <div class="vname">${esc(v.shortUserName || v.userName)}</div>
                ${roleIcons}
                ${v.state ? `<div class="vstate">${esc(txt(v.state))}</div>` : ""}
            </div>`
        : mine
          ? `<div class="veh none pick" ${vehAct}>${L("Panzer wählen", "Choose tank")}</div>`
          : `<div class="veh none">${p ? L("Kein Panzer", "No tank") : rowAct.indexOf("takeSlot") !== -1 ? `<span class="take">${L("Platz nehmen", "Take slot")}</span>` : ""}</div>`;
    return `
        <div ${p ? `data-user="${p.dbID}"` : ""} class="slot ${p ? "taken" : "open"} ${mine ? "mine" : ""} ${ready ? "ready" : ""} ${slot.isClosed ? "closed" : ""} ${highlight ? "hl" : ""} ${rowAct ? "clickable" : ""}" ${rowAct} ${highlight && !p ? `data-drop="${idx}"` : ""} ${p && !mine && isCommander() && slot.isRemoveAvailable ? `data-member="${p.dbID}"` : ""}>
            <div class="no">${idx + 1}</div>
            ${who}
            <div class="rating">${p ? esc(slot.rating || "") : ""}</div>
            ${veh}
            <div class="status">${slotStatus(slot)}</div>
            ${mine
                ? `<div class="acts always">${roleActs ? `<div class="roleover">${roleActs}</div>` : ""}${acts.join("")}</div>`
                : roleActs || acts.length ? `<div class="acts">${roleActs}${acts.join("")}</div>` : ""}
        </div>`;
}

const ROLE = {
    artillery: { img: "gunner", name: () => L("Artillerieschlag", "Artillery strike") },
    inspire: { img: "inspire", name: () => L("Inspiration", "Inspiration") },
};

function canChangeRoles() {
    return !!(data.me || {}).canChangeRoles;
}

function roleIcon(kind) {
    return `<div class="ricon2" style="background-image:url(img://gui/maps/icons/ez_room/role/${ROLE[kind].img}.png)" data-tip="${esc(ROLE[kind].name())}"></div>`;
}

function roleButton(dbID, kind, has) {
    const tip = has ? L(`${ROLE[kind].name()} entziehen`, `Take ${ROLE[kind].name()} away`) : L(`${ROLE[kind].name()} geben`, `Give ${ROLE[kind].name()}`);
    return `<div class="ibtn rolebtn ${has ? "on" : ""}" data-act="role" data-id="${dbID}" data-kind="${kind}" data-give="${has ? 0 : 1}" data-tip="${esc(tip)}"><div class="ricon2" style="background-image:url(img://gui/maps/icons/ez_room/role/${ROLE[kind].img}.png)"></div></div>`;
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
            ${renderColumns()}
            <div class="slots" data-scroll="60">${sortedSlots().map(([slot, idx]) => renderSlot(slot, idx)).join("")}</div>
            ${renderReadyBar()}
        </div>`;
}

// --- team table sorting (display only; empty slots always stay below, in slot order) ---
const SORT_COLS = [
    ["clan", () => L("Clan", "Clan")],
    ["name", () => L("Name", "Name")],
    ["rating", () => L("Wertung", "Rating")],
    ["tank", () => L("Panzer", "Tank")],
];

function ratingValue(slot) {
    const n = parseInt(String(slot.rating || (slot.player && slot.player.rating) || "").replace(/[^0-9]/g, ""), 10);
    return isNaN(n) ? -1 : n;
}

function sortValue(slot, key) {
    const p = slot.player;
    const v = slot.selectedVehicle;
    if (key === "clan") return (p.clanAbbrev || "").toLowerCase();
    if (key === "name") return (p.userName || p.fullName || "").toLowerCase();
    if (key === "rating") return ratingValue(slot);
    if (key === "tank") return v ? (v.shortUserName || v.userName || "").toLowerCase() : null;
    return 0;
}

function sortedSlots() {
    const rows = (data.slots || []).map((slot, idx) => [slot, idx]);
    const sort = ui.sort;
    if (!sort || !sort.key || !sort.dir) return rows;
    const taken = rows.filter(([s]) => s && s.player);
    const rest = rows.filter(([s]) => !(s && s.player));
    taken.sort((a, b) => {
        const va = sortValue(a[0], sort.key);
        const vb = sortValue(b[0], sort.key);
        // players without a value (no clan / no tank) always go below the others
        const ea = va === null || va === "" || va === -1;
        const eb = vb === null || vb === "" || vb === -1;
        if (ea !== eb) return ea ? 1 : -1;
        let c = 0;
        if (typeof va === "number") c = va - vb;
        else c = va < vb ? -1 : va > vb ? 1 : 0;
        return c * sort.dir || a[1] - b[1];
    });
    return taken.concat(rest);
}

function renderColumns() {
    const sort = ui.sort || {};
    const head = (key, label, cls) => {
        const on = sort.key === key && sort.dir;
        const arrow = on ? (sort.dir > 0 ? "▲" : "▼") : "";
        return `<div class="col ${cls} ${on ? "on" : ""}" data-act="sort" data-key="${key}">${esc(label())}<span class="arrow">${arrow}</span></div>`;
    };
    return `
        <div class="cols">
            <div class="col no"></div>
            ${head("clan", SORT_COLS[0][1], "c-clan")}
            ${head("name", SORT_COLS[1][1], "c-name")}
            ${head("rating", SORT_COLS[2][1], "c-rating")}
            ${head("tank", SORT_COLS[3][1], "c-tank")}
        </div>`;
}

function renderReadyBar() {
    const ab = data.actionButton || {};
    const state = txt(ab.stateString);
    const hint = ui.selCand ? L("Auf einen grünen Platz ziehen (Esc = abbrechen)", "Drop onto a green slot (Esc = cancel)") : state;
    const label = txt(ab.label) || L("Bereit!", "Ready!");
    return `
        <div class="readybar">
            <div class="state ${ui.selCand ? "hint" : ""}">${esc(hint)}</div>
            <div class="btn readybtn ${ab.isEnabled ? "" : "off"} ${ab.isReady ? "unready" : "ready"}" ${ab.isEnabled ? `data-act="ready"` : ""} data-tip="${esc(ab.toolTipData || "")}">${esc(label)}</div>
        </div>`;
}

// text smileys -> WG's emoji icons (gui/maps/icons/emoji), like the Flash chat shows them
const SMILEYS = [
    [">:(", "mad"], [">:-(", "mad"], [":@", "madah"],
    [":-)", "happy"], [":)", "happy"], ["=)", "happy"], [":D", "happy"], [":-D", "happy"],
    [";-)", "wink"], [";)", "wink"],
    [":-(", "sad"], [":(", "sad"],
    [":-P", "tongue"], [":P", "tongue"], [":p", "tongue"],
    [":-O", "oh"], [":O", "oh"], [":o", "oh"],
    [":-*", "kiss"], [":*", "kiss"],
    [":-|", "norm"], [":|", "norm"],
    [":-/", "hmm"], [":/", "hmm"],
];
function smileys(text) {
    // only stand-alone smileys (start/space before, end/space after), so links like https:// stay
    return text.replace(/(^|\s|&nbsp;)(\S+)(?=$|\s|&nbsp;)/g, (all, pre, word) => {
        const w = word.replace(/&gt;/g, ">");
        const hit = SMILEYS.find((sm) => sm[0] === w);
        return hit ? `${pre}<img class="smiley" src="img://gui/maps/icons/emoji/smiley_${hit[1]}.png" />` : all;
    });
}

// WG's chat lines are Flash HTML: keep <font color> as coloured spans, drop every other tag
// (the user text inside is already escaped by WG). Gameface puts spans below each other unless
// the parent has the cohinline attribute (WG's own Gameface text components do the same).
function chatHtml(line) {
    let out = "";
    let open = 0;
    String(line || "")
        .replace(/<br\s*\/?>/gi, " ")
        .split(/(<[^>]*>)/)
        .forEach((part) => {
            if (!part) return;
            if (part[0] !== "<") {
                out += smileys(part);
                return;
            }
            const m = /^<font\b[^>]*color\s*=\s*['"]?(#[0-9a-fA-F]{6})/i.exec(part);
            if (m) {
                out += `<span style="color:${m[1]}">`;
                open++;
            } else if (/^<font\b/i.test(part)) {
                out += "<span>";
                open++;
            } else if (/^<\/font>/i.test(part) && open > 0) {
                out += "</span>";
                open--;
            }
        });
    while (open-- > 0) out += "</span>";
    return out;
}

function renderChat() {
    const chat = data.chat || {};
    const lines = chat.lines || [];
    return `
        <div class="panel chat">
            <div class="ptitle chattitle">${L("Chat-Kanal", "Chat channel")}</div>
            <div class="pwrap">
                <div class="chatlog" id="chatlog" data-scroll="40">${lines.map((l) => `<p class="cline" cohinline="true">${chatHtml(l)}</p>`).join("")}</div>
                ${scrollbar("chatlog")}
            </div>
            <div class="chatin">
                <input id="chatinput" type="text" maxlength="512" ${chat.joined ? "" : `placeholder="${L("Nicht verbunden", "Not connected")}"`} />
                <div class="sendbtn" data-act="chatSend"><div class="ret-v"></div><div class="ret-h"></div><div class="ret-tip"></div></div>
            </div>
        </div>`;
}

function sendChat() {
    const input = document.getElementById("chatinput");
    if (!input) return;
    const text = (input.value || "").trim();
    if (!text) return;
    send({ action: "chatSend", text: text });
    input.value = "";
    chatDraft = "";
    chatStick = true;
}

// 10 x 10 grid with A-K / 1-0 labels like WG's lobby minimap, map image below it
const GRID_ROWS = ["A", "B", "C", "D", "E", "F", "G", "H", "J", "K"];
const GRID_COLS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"];
// commander markings (WG's MinimapGrid): data.grid.points in 0..1 of the map, still visible for
// "left" seconds; shown as WG's orange MinimapClick dot, steady (no pulsing), gone after ~5 s
function gridClickable() {
    return !!(data.grid && data.grid.clickEnabled) && !randomMap();
}

// random map: WG shows its dark back + dice over the grid and blocks clicks (FortClanBattleRoom:
// minimapGrid.back.visible = minimapGrid.dices.visible = !isMapEnabled)
function randomMap() {
    const room = data.room || {};
    return room.isMapEnabled === false;
}

let gridTimer = null;
function renderGridPoints() {
    const points = ((data.grid || {}).points || []).filter((p) => p.left > 0);
    if (gridTimer) clearTimeout(gridTimer);
    gridTimer = null;
    if (points.length) {
        const next = Math.min.apply(null, points.map((p) => p.left));
        const at = Date.now();
        gridTimer = setTimeout(() => {
            const gone = (Date.now() - at) / 1000;
            (data.grid.points || []).forEach((p) => (p.left -= gone));
            render();
        }, next * 1000 + 30);
    }
    return points.map((p) => `<div class="gpoint" style="left:${Math.round(p.x * 200) - 20}rem;top:${Math.round(p.y * 200) - 20}rem"></div>`).join("");
}

function renderMapGrid() {
    const cols = GRID_COLS.map((c) => `<div class="gcol">${c}</div>`).join("");
    const rows = GRID_ROWS.map((r) => `<div class="grow-l">${r}</div>`).join("");
    // 10 fixed rows of 10 cells: nothing can wrap into an extra row if a pixel is missing
    let cells = "";
    for (let r = 0; r < 10; r++) {
        let row = "";
        for (let c = 0; c < 10; c++) row += `<div class="gcell"></div>`;
        cells += `<div class="grow-c">${row}</div>`;
    }
    return `
        <div class="mapgrid">
            <div class="gtop"><div class="gcorner"></div>${cols}</div>
            <div class="gmid">
                <div class="gleft">${rows}</div>
                <div class="gmap ${gridClickable() ? "clickable" : ""} ${randomMap() ? "random" : ""}" id="gmap" ${data.mapIcon && !randomMap() ? `style="background-image:url(${data.mapIcon})"` : ""} ${gridClickable() ? `data-tip="${esc(L("Klick: Stelle für alle markieren", "Click: mark a spot for everyone"))}"` : ""}>${cells}${randomMap() ? `<div class="gdice"></div>` : ""}${renderGridPoints()}</div>
            </div>
        </div>`;
}

function renderSide() {
    const room = data.room || {};
    const map = txt(room.mapName);
    return `
        <div class="side">
            <div class="panel map">
                <div class="ptitle">${esc(map || L("Karte", "Map"))}</div>
                ${renderMapGrid()}
            </div>
            ${renderChat()}
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

// WG's waiting animation of the room window ("loading data"): dark cover over the whole room
function renderWaiting() {
    if (data.waiting == null) return "";
    return `
        <div class="waitcover">
            <div class="waitbox">
                <div class="spinner"></div>
                <div class="waittext">${esc(txt(data.waiting))}</div>
            </div>
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

function timerLeft() {
    const t = data.timer;
    if (!t || typeof t.deltaTime !== "number") return -1;
    const elapsed = timerBase ? (Date.now() - timerBase.at) / 1000 : 0;
    return Math.max(0, Math.round(t.deltaTime - (data.timerAge || 0) - elapsed));
}

function timerText() {
    const left = timerLeft();
    if (left < 0) return "--:--";
    const m = Math.floor(left / 60);
    const s = left % 60;
    return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
}

// last 10 s: alert colour like WG's AdvancedClanBattleTimer (colour from the timer VO's
// alertHtmlFormatter); switches at once, no animation
const TIMER_ALERT_SEC = 10;
function fmtColor(f, fallback) {
    const m = /color\s*=\s*['"]?(#[0-9a-fA-F]{6})/.exec(String(f || ""));
    return m ? m[1] : fallback;
}
function updateTimer(el) {
    if (!el) return;
    const t = data.timer || {};
    const left = timerLeft();
    const alert = left >= 0 && left <= TIMER_ALERT_SEC;
    el.textContent = timerText();
    el.className = "timer" + (alert ? " alert" : "");
    el.style.color = alert ? fmtColor(t.alertHtmlFormatter, "#ff7f00") : fmtColor(t.htmlFormatter, "#ffdd99");
}

setInterval(() => updateTimer(document.getElementById("timer")), 500);

// --- render ----------------------------------------------------------------------

// view size = room content area of WG's window (px); Gameface windows are sized from JS
// (viewEnv.resizeViewPx, same as WG's own OfferBannerWindow)
// Right after the view opens, resizeViewPx can be ignored (game.log: viewSizePx 0x0, only the
// top-left corner drawn): check the real size and set it again every 0.2 s until it sticks.
const RESIZE_RETRY_MS = 200;
const RESIZE_RETRY_MAX = 25; // 5 s
let appliedSize = "";
let resizeTimer = 0;

function viewSizeOk(w, h) {
    try {
        const size = viewEnv.getViewSizePx();
        return Math.abs(size.width - w) <= 1 && Math.abs(size.height - h) <= 1;
    } catch (e) {
        return true; // no way to check (browser preview)
    }
}

function resizeView(w, h, attempt) {
    try {
        if (window.viewEnv && viewEnv.resizeViewPx) viewEnv.resizeViewPx(w, h);
    } catch (e) {
        send({ action: "log", msg: "resizeViewPx failed: " + e });
    }
    resizeTimer = setTimeout(() => {
        resizeTimer = 0;
        if (appliedSize !== w + "x" + h) return; // a newer size is being applied
        if (viewSizeOk(w, h)) {
            if (attempt > 0) send({ action: "log", msg: "view size " + w + "x" + h + " ok after " + (attempt + 1) + " tries" });
            return;
        }
        if (attempt + 1 >= RESIZE_RETRY_MAX) {
            send({ action: "log", msg: "view size " + w + "x" + h + " not applied after " + RESIZE_RETRY_MAX + " tries" });
            return;
        }
        send({ action: "log", msg: "view size not applied yet, retry " + (attempt + 1) });
        resizeView(w, h, attempt + 1);
    }, RESIZE_RETRY_MS);
}

function applyFrame() {
    const f = data.frame;
    if (!f || f.length < 4 || f[2] <= 0 || f[3] <= 0) return;
    const key = f[2] + "x" + f[3];
    if (key === appliedSize) return;
    appliedSize = key;
    if (resizeTimer) clearTimeout(resizeTimer);
    resizeView(f[2], f[3], 0);
    document.documentElement.style.width = document.body.style.width = "100%";
    document.documentElement.style.height = document.body.style.height = "100%";
}

let chatDraft = "";
let chatFocus = false;
let chatStick = true; // keep the chat scrolled to the newest line

function render() {
    applyFrame();
    lastKey = JSON.stringify(Object.assign({}, data, { timer: null, timerAge: null }));
    const root = document.getElementById("root");
    const input = document.getElementById("chatinput");
    if (input) {
        chatDraft = input.value || "";
        chatFocus = document.activeElement === input;
    }
    const log = document.getElementById("chatlog");
    if (log) chatStick = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
    const keep = {};
    root.querySelectorAll("[data-scroll]").forEach((el, i) => (keep[i] = el.scrollTop));
    const body = ui.raw ? renderRaw() : `${renderCandidates()}${renderTeam()}${renderSide()}`;
    root.innerHTML = `${renderHeader()}<div class="body">${body}${ui.raw ? "" : renderWaiting()}</div>${renderFooter()}${renderReservePopup()}<div id="tip" class="tip"></div>`;
    tipTarget = null;
    markHover();
    root.querySelectorAll("[data-scroll]").forEach((el, i) => {
        if (keep[i]) el.scrollTop = keep[i];
    });
    const newInput = document.getElementById("chatinput");
    if (newInput) {
        newInput.value = chatDraft;
        if (chatFocus) newInput.focus();
    }
    updateTimer(document.getElementById("timer"));
    const newLog = document.getElementById("chatlog");
    if (newLog && chatStick) newLog.scrollTop = newLog.scrollHeight;
    updateScrollbars();
}

// own scrollbars for the volunteers list and the chat (Gameface draws none): thumb size/position
// from the list, updated after render and wheel; drag the thumb or click the track to scroll
const SBAR_MIN_THUMB = 20;
let sbarDrag = null; // {bar, y, top}

function scrollbar(listId) {
    return `<div class="sbar" data-sbar="${listId}"><div class="sthumb"></div></div>`;
}

function updateScrollbars() {
    document.querySelectorAll("[data-sbar]").forEach((bar) => {
        const list = document.getElementById(bar.getAttribute("data-sbar"));
        const thumb = bar.firstElementChild;
        if (!list || !thumb) return;
        const ch = list.clientHeight;
        const sh = list.scrollHeight;
        if (sh <= ch + 1) {
            bar.style.visibility = "hidden";
            return;
        }
        bar.style.visibility = "visible";
        const track = bar.clientHeight;
        const th = Math.max(SBAR_MIN_THUMB, Math.round((track * ch) / sh));
        thumb.style.height = th + "px";
        thumb.style.top = Math.round(((track - th) * list.scrollTop) / (sh - ch)) + "px";
    });
}

function scrollFromThumb(bar, top) {
    const list = document.getElementById(bar.getAttribute("data-sbar"));
    const thumb = bar.firstElementChild;
    if (!list || !thumb) return;
    const free = bar.clientHeight - thumb.clientHeight;
    const t = Math.max(0, Math.min(free, top));
    list.scrollTop = free > 0 ? ((list.scrollHeight - list.clientHeight) * t) / free : 0;
    updateScrollbars();
}

document.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    const bar = closest(e.target, "data-sbar");
    if (!bar) return;
    e.preventDefault();
    e.stopPropagation();
    const thumb = bar.firstElementChild;
    if (e.target !== thumb) scrollFromThumb(bar, e.clientY - bar.getBoundingClientRect().top - thumb.clientHeight / 2);
    sbarDrag = { bar: bar, y: e.clientY, top: thumb.offsetTop };
});

document.addEventListener("mousemove", (e) => {
    if (sbarDrag) scrollFromThumb(sbarDrag.bar, sbarDrag.top + e.clientY - sbarDrag.y);
});

document.addEventListener("mouseup", () => {
    sbarDrag = null;
});

// Row buttons (Raus / kick) belong to the row under the mouse. Tracked here instead of CSS :hover:
// in Gameface the row lost :hover when the mouse reached its own button (flicker) and after every
// re-render until the mouse moved again.
function markHover() {
    const root = document.getElementById("root");
    if (!root) return;
    root.querySelectorAll(".hov").forEach((el) => {
        el.className = el.className.replace(/\s*\bhov\b/g, "");
    });
    if (!ui.hoverRow) return;
    root.querySelectorAll(`[data-user="${ui.hoverRow}"]`).forEach((el) => {
        el.className += " hov";
    });
}

document.addEventListener("mousemove", (e) => {
    const row = closest(e.target, "data-user");
    const id = row ? row.getAttribute("data-user") : "";
    if (id === ui.hoverRow) return;
    ui.hoverRow = id;
    markHover();
});

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
    // a click outside the reserve list closes it
    if (data.reserveOptions && !closest(e.target, "data-popup") && !(el && el.getAttribute("data-act") === "reserveOpen")) {
        data.reserveOptions = null;
        send({ action: "reserveOpen", slot: -1 });
        render();
    }
    if (!el) return;
    e.stopPropagation();
    const act = el.getAttribute("data-act");
    const id = Number(el.getAttribute("data-id"));
    const slot = Number(el.getAttribute("data-slot"));
    if (act === "hide") send({ action: "hide" });
    else if (act === "raw") {
        ui.raw = !ui.raw;
        render();
    } else if (act === "takeSlot") send({ action: "takeSlot", slot: slot });
    else if (act === "leaveSlot") send({ action: "leaveSlot", dbID: id });
    else if (act === "kick") send({ action: "kick", dbID: id });
    else if (act === "role") send({ action: "role", dbID: id, kind: el.getAttribute("data-kind"), give: el.getAttribute("data-give") === "1" });
    else if (act === "reserveOpen") {
        const open = data.reserveOptions && data.reserveOptions.slot === slot;
        send({ action: "reserveOpen", slot: open ? -1 : slot });
    } else if (act === "reserveSelect") {
        send({ action: "reserveSelect", id: id, remove: el.getAttribute("data-remove") === "1" });
    } else if (act === "sort") {
        // first click ascending, second descending, third back to slot order
        const key = el.getAttribute("data-key");
        const cur = ui.sort || {};
        let dir = 1;
        if (cur.key === key) dir = cur.dir === 1 ? -1 : cur.dir === -1 ? 0 : 1;
        ui.sort = dir ? { key: key, dir: dir } : null;
        send({ action: "sort", key: dir ? key : "", dir: dir });
        render();
    } else if (act === "candSort") {
        const key = el.getAttribute("data-key");
        const cur = ui.candSort || {};
        let dir = 1;
        if (cur.key === key) dir = cur.dir === 1 ? -1 : cur.dir === -1 ? 0 : 1;
        ui.candSort = dir ? { key: key, dir: dir } : null;
        send({ action: "sort", target: "cand", key: dir ? key : "", dir: dir });
        render();
    } else if (act === "chatSend") sendChat();
    else if (act === "chooseVehicle") send({ action: "chooseVehicle", cd: Number(el.getAttribute("data-cd")) || 0 });
    else if (act === "ready" || act === "invite" || act === "toggleOpen" || act === "configure" || act === "back") send({ action: act });
});

// commander: click a volunteer = WG puts him into the next free allowed slot (Python picks it),
// drag him onto a green slot = exactly that slot; drag a team member onto the volunteers list =
// back to the volunteers (leaveSlot, like "Raus"). Mouse events only (Gameface has no HTML5 DnD).
const DRAG_START_PX = 6;
let drag = null; // {kind: "cand"|"member", id, x, y, started, name}

function dragGhost(show, e, name) {
    let g = document.getElementById("dragghost");
    if (!show) {
        if (g) g.parentNode.removeChild(g);
        return;
    }
    if (!g) {
        g = document.createElement("div");
        g.id = "dragghost";
        g.className = "dragghost";
        g.textContent = name || "";
        document.body.appendChild(g);
    }
    // beside the cursor, so the slot under the cursor gets the mouse events
    g.style.left = e.clientX + 14 + "px";
    g.style.top = e.clientY + 10 + "px";
}

function endDrag() {
    drag = null;
    dragGhost(false);
    if (ui.selCand || ui.dragOut) {
        ui.selCand = ui.dragOut = 0;
        render();
    }
}

document.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    if (closest(e.target, "data-act")) return; // kick / Raus buttons inside the row
    const cand = closest(e.target, "data-cand");
    const member = cand ? null : closest(e.target, "data-member");
    const el = cand || member;
    if (!el) return;
    e.preventDefault();
    const nameEl = el.querySelector(".name");
    drag = { kind: cand ? "cand" : "member", id: Number(el.getAttribute(cand ? "data-cand" : "data-member")), x: e.clientX, y: e.clientY, started: false, name: nameEl ? nameEl.textContent : "" };
});

document.addEventListener("mousemove", (e) => {
    if (!drag) return;
    if (!drag.started) {
        if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) < DRAG_START_PX) return;
        drag.started = true;
        if (drag.kind === "cand") {
            ui.selCand = drag.id;
            send({ action: "highlight", dbID: drag.id });
        } else ui.dragOut = drag.id;
        render();
    }
    dragGhost(true, e, drag.name);
});

document.addEventListener("mouseup", (e) => {
    if (!drag || e.button !== 0) return;
    const d = drag;
    if (!d.started) {
        drag = null;
        if (d.kind === "cand") send({ action: "assignNext", dbID: d.id }); // a click on a member does nothing
        return;
    }
    if (d.kind === "cand") {
        const target = closest(e.target, "data-drop");
        if (target) send({ action: "assign", slot: Number(target.getAttribute("data-drop")), dbID: d.id });
    } else if (closest(e.target, "data-dropout")) send({ action: "leaveSlot", dbID: d.id });
    endDrag();
});

// tooltips: any element with data-tip; WG format "{HEADER}..{/HEADER}{BODY}..{/BODY}" or plain text
function tipHtml(raw) {
    const t = String(raw || "");
    const h = /\{HEADER\}([\s\S]*?)\{\/HEADER\}/.exec(t);
    const b = /\{BODY\}([\s\S]*?)\{\/BODY\}/.exec(t);
    if (!h && !b) return t.trim() ? `<div class="tbody">${esc(txt(t))}</div>` : "";
    return `${h ? `<div class="thead">${esc(txt(h[1]))}</div>` : ""}${b ? `<div class="tbody">${esc(txt(b[1])).replace(/\n/g, "<br/>")}</div>` : ""}`;
}
let tipTarget = null;
document.addEventListener("mousemove", (e) => {
    const tip = document.getElementById("tip");
    if (!tip) return;
    const el = closest(e.target, "data-tip");
    if (el !== tipTarget) {
        tipTarget = el;
        const html = el ? tipHtml(el.getAttribute("data-tip")) : "";
        tip.innerHTML = html;
        tip.style.display = html ? "block" : "none";
    }
    if (tipTarget) {
        const w = document.body.offsetWidth || 1013;
        const h = document.body.offsetHeight || 653;
        const tw = tip.offsetWidth || 260;
        const th = tip.offsetHeight || 60;
        tip.style.left = Math.min(e.clientX + 14, w - tw - 4) + "px";
        tip.style.top = (e.clientY + 18 + th > h ? e.clientY - th - 8 : e.clientY + 18) + "px";
    }
});

// commander: left click on the minimap = mark that spot for everyone (WG's MinimapGrid.setClick)
document.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || !gridClickable()) return;
    const map = document.getElementById("gmap");
    if (!map || !closest(e.target, "id") || closest(e.target, "id") !== map) return;
    const r = map.getBoundingClientRect();
    const x = Math.max(0, Math.min(200, e.clientX - r.left - 1)) / 200;
    const y = Math.max(0, Math.min(200, e.clientY - r.top - 1)) / 200;
    e.preventDefault();
    send({ action: "gridClick", x: x, y: y });
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
        updateScrollbars();
    },
    { capture: true, passive: false }
);

document.addEventListener("keydown", (e) => {
    const inChat = document.activeElement && document.activeElement.id === "chatinput";
    if (inChat) {
        if (e.keyCode === 13) {
            e.preventDefault();
            sendChat();
        } else if (e.keyCode === 27) document.activeElement.blur();
        return;
    }
    if (e.keyCode === 116 && data.dev) send({ action: "devReload" });
    else if (e.keyCode === 27) {
        if (data.reserveOptions) {
            data.reserveOptions = null;
            send({ action: "reserveOpen", slot: -1 });
            render();
        } else if (ui.selCand || ui.dragOut) {
            if (drag) endDrag();
            else {
                ui.selCand = 0;
                render();
            }
        } else send({ action: "hide" });
    }
});

// --- model binding ---------------------------------------------------------------

// WG pushes the battle timer every second (with the same room data again): only rebuild the
// DOM when something besides the timer changed, so clicks and hover are not interrupted
let lastKey = "";
let sortLoaded = false;

function readModel() {
    try {
        const raw = window.model && window.model.data;
        if (!raw) return;
        const next = JSON.parse(raw);
        const key = JSON.stringify(Object.assign({}, next, { timer: null, timerAge: null }));
        data = next;
        timerBase = { at: Date.now() };
        if (key === lastKey) {
            updateTimer(document.getElementById("timer"));
            return;
        }
        lastKey = key;
        if (!sortLoaded) {
            sortLoaded = true;
            const saved = (data.settings || {}).sort;
            if (saved && saved.key && saved.dir) ui.sort = { key: saved.key, dir: saved.dir };
            const savedCand = (data.settings || {}).candSort;
            if (savedCand && savedCand.key && savedCand.dir) ui.candSort = { key: savedCand.key, dir: savedCand.dir };
        }
        if (ui.selCand && (!(data.candidates || []).some((c) => c.dbID === ui.selCand) || slotOf(ui.selCand) !== -1)) ui.selCand = 0;
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
