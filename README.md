# EZ ROOM for ADV

World of Tanks mod (EU 2.4.1): a modern Gameface UI for the Stronghold / Advances battle room.

WG's Flash room keeps running underneath and keeps all of its logic. The mod records what the
room sends to its Flash UI and renders it in its own view laid exactly over WG's window; every
action goes back through the room's own request methods (the same ones WG's UI calls).

Languages: English, Deutsch, Polski, Čeština, Français, Español, Italiano, Türkçe, Русский
(follows the game language; WG's own texts come from the game's localisation anyway).

## Install

1. Download `EZ_ROOM_<version>.zip` from [Releases](../../releases) and unzip it.
2. Put `ez.advances_room_<version>.wotmod` into `<WoT folder>\mods\<game version>\`
   (e.g. `C:\Games\World_of_Tanks_EU\mods\2.4.1.0\`).
3. Delete any older `ez.advances_room_*.wotmod` there (two versions make the client hang on start).
4. Start the game. The zip contains the same guide as `README.txt` (EN) and `LIESMICH.txt` (DE).

`EZ_ROOM_<version>_DEV.zip` is the same mod plus dev mode: also copy its `mods\configs\ez_room\`
folder into the WoT folder (raw data view, F5 reload of the UI from `mods\configs\ez_room\src`).

## Features

- Own title bar like WG's window (same size, 1038 x 707): drag to move, minimize, X = leave
  the room (with WG's confirmation)
- Team table: sortable columns (clan, name, rating, tank), WG's status lamps, commander cap,
  badges, voice indicator, roles (artillery strike / inspiration) with commander buttons,
  WG's class icon before the tank name, tanks per class and total next to the title; one click
  sorts (clan/name A-Z, rating highest first), the second goes back to WG's order; by tank =
  by class (heavy, medium, TD, light, SPG), single tanks first, then by count and A-Z, with
  tank count and fold arrow; frozen vehicles with WG's unfreeze button
- Volunteers: WG's online status, sortable (players in the room on top, then invited, then
  offline), click = next free
  slot, drag = that slot, drag a member back out
- Header: WG's direction graphic (also while the unit is in battle) with WG's own tooltips,
  timer with alert colour, reserves, division info tooltip, back link
- Ready button with WG's cooldown after a click
- Map: square minimap with grid, bases of the current battle (WG's markers), commander markings
  for everyone (WG's MinimapGrid), dice for a random map; skirmishes have no map (more room for
  the chat)
- Chat: live, colours, smileys, right click on a name = WG's player menu, click a link = copy it;
  keeps its scroll position on room changes
- "Original" / Esc shows WG's room; a small "EZ ROOM" button in its title bar brings the view back
- Enemy search and WG's popups stay WG's own

## Development

- Build: `python3 build.py` -> `dist/ez.advances_room_<ver>.wotmod` (needs `python2.7` for the .pyc files)
- Dev mode: `<game>/mods/configs/ez_room/dev.json` = `{"src": "X:/path/to/wot-advances-room/src"}`;
  impl.py / app.js / style.css are reloaded on every open, F5 in the overlay reopens it, and the
  last room state is written to `mods/configs/ez_room/last_room.json`.
- Browser preview: `tools/preview/shot.sh <mock|last_room.json> out.png`
- Feature list against WG's original room: [ROADMAP.md](ROADMAP.md) (German)

Mod by dodojesuslol
