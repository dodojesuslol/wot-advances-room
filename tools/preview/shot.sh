#!/bin/sh
# Browser preview of the room UI (Firefox headless).
# usage: tools/preview/shot.sh <data.json|mock> <out.png> [click selector] [WxH]
# "mock" = generated test data; a real snapshot is written in dev mode to
# <game>/mods/configs/ez_room/last_room.json. Game images/fonts: ~/.cache/wot-picker-preview.
H=$(cd "$(dirname "$0")" && pwd)
RES=${RES:-$HOME/.cache/wot-picker-preview}
D=$1
if [ "$D" = mock ]; then D=$H/mock.json; python3 -I "$H/mock.py" "$D"; fi
python3 -I "$H/preview.py" "$H/../../src/res/gui/gameface/mods/ez_room" "$RES" "$D" "$H/p_shot.html" "$3"
P=$H/.ffprofile; mkdir -p "$P"
echo 'user_pref("layout.css.devPixelsPerPx", "1.0"); user_pref("font.minimum-size.x-western", 0);' > "$P/user.js"
timeout 60 firefox --headless --no-remote --profile "$P" --window-size=${4:-1920,1080} --screenshot "$(realpath "$2")" "file://$H/p_shot.html" >/dev/null 2>&1
