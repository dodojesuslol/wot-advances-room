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

## Features

- Team table: sortable columns (clan, name, rating, tank), WG's status lamps, commander cap,
  badges, voice indicator, roles (artillery strike / inspiration) with commander buttons,
  tank count and fold arrow when sorted by tank
- Volunteers: WG's online status, sortable (offline players at the bottom), click = next free
  slot, drag = that slot, drag a member back out
- Header: WG's direction graphic, timer with alert colour, reserves, division info tooltip,
  back link
- Map: square minimap with grid, commander markings for everyone (WG's MinimapGrid), dice for
  a random map
- Chat: live, colours, smileys, right click on a name = WG's player menu, click a link = copy it
- "Original" / Esc shows WG's room; a small "EZ ROOM" button in its title bar brings the view back
- Enemy search and WG's popups stay WG's own

Optional: with [EZ TANK PICKER for ADV](https://github.com/dodojesuslol/wot-advances-picker),
"Choose tank" opens the big tank selection.

## Development

- Build: `python3 build.py` -> `dist/ez.advances_room_<ver>.wotmod` (needs `python2.7` for the .pyc files)
- Dev mode: `<game>/mods/configs/ez_room/dev.json` = `{"src": "X:/path/to/wot-advances-room/src"}`;
  impl.py / app.js / style.css are reloaded on every open, F5 in the overlay reopens it, and the
  last room state is written to `mods/configs/ez_room/last_room.json`.
- Browser preview: `tools/preview/shot.sh <mock|last_room.json> out.png`
- Feature list against WG's original room: [ROADMAP.md](ROADMAP.md) (German)

Mod by dodojesuslol
