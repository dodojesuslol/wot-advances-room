# EZ ROOM for ADV

World of Tanks mod: modern web (Gameface) UI for the Stronghold / Advances battle room.

WG's Flash room keeps running underneath and keeps all of its logic. The mod records what the
room sends to its Flash UI and renders it in its own full-screen view; actions are sent back
through the room's own request methods.

- Build: `python3 build.py` -> `dist/ez.advances_room_<ver>.wotmod` (needs `python2.7` for the .pyc files)
- Install: copy the .wotmod to `<game>/mods/<game version>/`
- Toggle the overlay: "EZ ROOM for ADV" in the mods list button (ModsListAPI); "Show original" / Esc hides it
- Dev mode: `<game>/mods/configs/ez_room/dev.json` = `{"src": "X:/path/to/wot-advances-room/src"}`;
  impl.py/app.js/style.css are reloaded on every open, F5 in the overlay reopens it, and the last
  room state is written to `mods/configs/ez_room/last_room.json`.
- Preview: `tools/preview/shot.sh <mock|last_room.json> out.png`

Status: step 1 (display only). Next: actions, then chat/map/context menus, then merge with EZ TANK PICKER.
