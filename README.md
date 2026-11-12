# EZ ROOM for ADV

World of Tanks mod (EU 2.4.1): its own Gameface room for Stronghold / Advances battles.

Since 0.8.0 WG's Flash room window is not opened at all. The mod listens to WG's stronghold unit
entity directly (the same listener callbacks and events WG's room uses), builds the room data with
WG's own Python builders and runs every action through WG's prb API (the same request contexts WG's
room sends). If anything fails, WG's own room opens instead.

Languages: English, Deutsch, Polski, Čeština, Français, Español, Italiano, Türkçe, Русский
(follows the game language; WG's own texts come from the game's localisation anyway).

## Install

1. Download `EZ_ROOM_<version>.zip` from [Releases](../../releases) and unzip it.
2. Put `ez.advances_room_<version>.wotmod` into `<WoT folder>\mods\<game version>\`
   (e.g. `C:\Games\World_of_Tanks_EU\mods\2.4.1.1\`).
3. Delete any older `ez.advances_room_*.wotmod` there (two versions make the client hang on start).
4. Start the game. The zip contains the same guide as `README.txt` (EN) and `LIESMICH.txt` (DE).

`EZ_ROOM_<version>_DEV.zip` is the same mod plus dev mode: also copy its `mods\configs\ez_room\`
folder into the WoT folder (raw data view, F5 reload of the UI from `mods\configs\ez_room\src`).

## Features

- Own window (1038 x 707): drag the title bar to move it (position is saved), minimize into the
  chat bar like WG's room, X = leave the room (with WG's confirmation); the garage around it
  stays usable
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
- Enemy / legionnaire search with timer and cancel, WG's maintenance notice with retry, WG's
  loading cover, WG's timer alarm sound
- Invites, configure, unfreeze, leave dialogs and the vehicle selector are WG's own windows
- Fallback: "WG room" button in the title bar = WG's room once (minimize it and click it in the
  chat bar again = EZ ROOM; the mods list entry also brings EZ ROOM back); WG's room also opens by
  itself if EZ ROOM fails to open, its UI does not start, or the client crashed while it was opening
- If the game closes the room window (e.g. the vehicle hub), it comes back with the garage
- `mods/configs/ez_room/settings.json`: `"useWgRoom": true` = always WG's room,
  `"windowMode": "panel"` = small window instead of the screen-sized transparent one

## Development

- Build: `python3 build.py` -> `dist/ez.advances_room_<ver>.wotmod` (needs `python2.7` for the .pyc files)
- Dev mode: `<game>/mods/configs/ez_room/dev.json` = `{"src": "X:/path/to/wot-advances-room/src"}`;
  impl.py / app.js / style.css are reloaded on every open, F5 in the room reopens it, and the
  last room state is written to `mods/configs/ez_room/last_room.json`.
- Browser preview: `tools/preview/shot.sh <mock|last_room.json> out.png`
- Feature list against WG's original room: [ROADMAP.md](ROADMAP.md) (German)

Mod by dodojesuslol
