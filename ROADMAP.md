# EZ ROOM – Roadmap: Funktionsgleichheit mit dem WG-Original

Stand: v0.7.35 (2026-10-18). Ziel: Jede Funktion des Flash-Raums (`fortClanBattleRoom.swf` + `fortBattleRoomWindow.swf`)
einzeln mit dem Original vergleichen und alles, was fehlt, nachbauen. Zum Vergleich in einem echten Raum über den
„Original“-Button umschalten (Esc / Mods-Button bringt die neue Oberfläche zurück).

Legende: ✅ vorhanden · 🟡 teilweise · ❌ fehlt · 🚫 bewusst weggelassen

**Vorgehen pro Punkt:**
1. Im Original ansehen (Screenshot vom Nutzer oder `spectacle -b -n -f -o <scratchpad>/x.png`, das ist ein 3840×1080-Doppelbildschirm, links zuschneiden).
2. WG-Code nachlesen: Python unter `/tmp/wot-decompiled/source/res/scripts/client/…` (bei Bedarf neu klonen, siehe HANDOFF §0) und AS3 unter `~/wot-webcache-backup/ref/as3`.
3. Einbauen, mit `tools/preview/shot.sh` prüfen, Version erhöhen, bauen, installieren, committen.
4. Den Nutzer im Spiel testen lassen und den Punkt erst dann auf ✅ setzen.

---

## A. Kopfbereich

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| A1 | Titel des Fensters („Vorstoß vom Brückenkopf Süd (x2)“) | ✅ | v0.7.17: eigener Titel entfernt (Nutzer), steht schon in WGs Fensterrahmen |
| A2 | Beschreibung + ⓘ-Icon mit Tooltip (`headerDescr`) | ✅ | v0.7.27 (im Spiel bestätigt): WGs infoIcon hinter der Beschreibung, Tooltip = `SortieDivisionTooltipData` (Name, Stufe, Spieler, Legionäre, Dauer, Bonus) mit WGs Beschriftungen |
| A3 | Zurück-Link „Zur Abteilungszusammenstellung gehen“ (`backBtn`) | ✅ | v0.7.14 (im Spiel bestätigt): Link unter der Beschreibung, Text + Tooltip aus WGs Sprachdateien, Klick = `StrongholdBattleRoomWindow.onBackClick()` → verlässt die Abteilung (wie Original, ohne Rückfrage) |
| A4 | Richtungs-/Gebäudegrafik (grüne Burg → Flaggen → ⚔ → rote Burg) | ✅ | v0.7.15 (im Spiel bestätigt): eigene Zeile unter dem Kopf, Clans links/rechts, Timer genau mittig im Kopf; 13 Endbilder aus `fortCmp.swf` (`ConnectedDirectsUI`, jeweils ruhiges Bild vor dem nächsten Label) in `gui/maps/icons/ez_room/direction/<value>.png`; `as_updateReadyDirectionsS(false)` → Text „Richtungen werden ermittelt …“; keine Animation. Teamzeilen 27→22 px, damit alle 15 passen; v0.7.46: auch ohne Gegner („Abteilung im Gefecht“), WGs echte Tooltips (BackportTooltipWindow: DIRECT_MODULE 0–5, Schwerter = crossSwords) |
| A5 | Eigener Clan / Gegner-Clan mit Bereit-Anzeige | ✅ | Namen + Glow da; WGs Bereit-Lämpchen dort nicht gewünscht (Nutzer, 2026-10-18) |
| A6 | Gefechts-Timer, normale und Alarm-Farbe (#ffdd99 / #ff7f00) | ✅ | v0.7.7: letzte 10 s sofort orange + oranger Rand (Farben aus dem Timer-VO), ohne Animation |
| A7 | Timer-Alarm-Ton (Flash ruft `onTimerAlert()` → `playBattleRoomTimerAlert`) | 🚫 | nicht nachbauen (Nutzer): der Flash-Timer läuft unter der Oberfläche weiter und spielt den Original-Ton selbst |
| A8 | „Warten auf Gefecht“-Text (`waitForBattleDescr`) | ✅ | |
| A9 | 4 Reserve-Plätze + Auswahl | ✅ | eigene Liste statt Popover |
| A10 | Reserve-Liste: erweiterte Werte (Schaden, Radius, Crew-Bonus …) | ❌ | `FortReserveSelectPopover.__buildReserveParams` |
| A11 | Konfigurieren-Button (Modus ändern) + `divisionInfo` | ✅ | v0.7.27 (im Spiel bestätigt): Button für den Kommandanten immer da, ausgegraut wenn WG ihn sperrt, WGs Tooltips (settingsBtn / disabled); divisionInfo = A2 |

## B. Team (Abteilungsmitglieder)

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| B1 | Kopfzeile „Mitglieder: x/15 (Legionäre x/y)“ | ✅ | `as_setTableHeaderS` |
| B2 | Spalten Clan / Name / Wertung / Panzer, sortierbar | ✅ | eigene Erweiterung (v0.7.0); v0.7.32 (im Spiel bestätigt): nach Panzer sortiert → erste Zeile je Panzer mit ×Anzahl (ab 2) und Pfeil ▼/▶ zum Zuklappen der übrigen Zeilen (nicht gespeichert) |
| B3 | Platznummer, Spielername in WG-Farbe, eigener Name hervorgehoben | ✅ | |
| B4 | Status-Icon pro Spieler (bereit / nicht bereit / im Gefecht) | ✅ | v0.7.26 (im Spiel bestätigt): WGs IndicationOfStatus_UI (guiControlsLobby.swf Sprite 571: normal / ready / inBattle / locked) am Zeilenende; ganze Zeile grün bei „bereit“ bleibt |
| B5 | **Sprach-Indikator** (Spieler spricht gerade, `isPlayerSpeaking`) | ✅ | v0.7.18 (vom Nutzer so abgenommen, nicht live getestet): WGs VoiceWaves (`Voice.swf` Sprite 38, Endbild von „show“, rotes Mute-X entfernt) 100×20 hinter dem Namen, Team + Freiwillige; live über `g_messengerEvents.voip.onPlayerSpeaking`, Startwert `voipController.isPlayerSpeaking`. Nur WoT-Voice-Chat, nicht Discord |
| B6 | Abzeichen (Badge) vor dem Namen (`badgeVisualVO`) | ✅ | v0.7.29 (im Spiel bestätigt): WGs Badge-Bild (badgeVisualVO.icon, 24x24 als 18 px) vor dem Namen, nach der Kommandanten-Mütze |
| B7 | Kommandanten-Icon | ✅ | v0.7.26 (im Spiel bestätigt): WGs Offiziersmütze (IconLibrary.swf commanderMc, Sprite 126) vor dem Namen, Tooltip „Kommandant“ |
| B8 | Rollen-Icons Artillerieschlag / Inspiration (`roleIcon`, `gunnerIcon0-14`) | ✅ | v0.7.19–0.7.20 (im Spiel bestätigt): Buttons nur, wo WGs Kontextmenü den Punkt anbieten würde (`roleRights`, WGs Prüfungen); WGs Icons (`fortClanBattleRoom.swf` Sprite 142) hinter dem Panzernamen; Kommandant: Bild-Buttons beim Überfahren der Zeile (eigene Zeile: links neben „Verlassen“) = `GiveEquipmentCommanderCtx` wie WGs Kontextmenü (Nutzerwunsch). Panzerbilder in der Teamliste entfernt (Nutzer) |
| B9 | Legionär-Kennzeichnung | ✅ | |
| B10 | Panzer: Icon, Stufe, Name; Nationsflagge im Hintergrund | 🟡 | Stufe + Name da; Panzerbild seit v0.7.19 bewusst weg (Nutzer, mehr Platz); Flagge fehlt |
| B11 | Panzer-Zustand (nicht bereit, „Zu reparieren“ …) | ✅ | |
| B12 | **Eingefrorene Panzer** + „Auftauen“-Button (`vehBrokenIcon`) | 🟡 | v0.7.42 (Vorschau ok, im Spiel noch nicht gesehen – nur während eines Festungs-Events): WGs rotes Zahnrad (`fortClanBattleRoom.swf` Sprite 120) am Ende der Panzerspalte; Clan-Rollen mit `canUnfrozeVehicles` bekommen WGs Zahnrad-Knopf → `onUnfrozenVehicleSlotClick(slot)` (WGs Dialog mit Reparaturteile-Preis), grau bei `unfrozeVehiclesBtnEnabled == false`; WG-Tooltips |
| B13 | Prestige-Stufe (`prestigeLevel`) | 🚫 | nicht gewünscht (Nutzer, 2026-10-18) |
| B14 | Freien Platz nehmen | ✅ | `assignSlotRequest(slot, -1)` |
| B15 | Platz verlassen / Kommandant: Spieler raus, kicken | ✅ | v0.7.6: „Raus“ + „✕“ (Kick, ein Klick, keine Rückfrage) erscheinen sofort beim Überfahren über dem Zeilenende, ohne Flackern; Freiwillige: „✕“. `leaveSlotRequest`, `requestToKickUser` |
| B16 | Drag & Drop Freiwillige → Platz | ✅ | v0.7.5: Kommandant klickt Freiwilligen → nächster freier erlaubter Platz (`getAvailableSlots`, kleinste Nummer); ziehen → grüne Plätze, loslassen = genau dieser Platz. Zwei-Klick-Verfahren entfernt (Nutzerwunsch); v0.7.13 (im Spiel bestätigt): Mitglied aus dem Team auf die Freiwilligen-Liste ziehen = `leaveSlotRequest` (wie „Raus“) |
| B17 | Gesperrte / geschlossene Plätze, Legionärs-Suchplätze („Spieler wird gesucht“) | 🟡 | Label kommt mit, Optik prüfen |
| B18 | Rechtsklick-Menü | ✅ | `BackportContextMenuWindow` mit `UNIT_USER` |
| B19 | Spieler-Tooltip (WG-Nutzerinfo) und Panzer-Tooltip | ❌ | WG-Backport-Tooltips statt eigener |
| B20 | Panzer wählen | ✅ | EZ TANK PICKER, sonst WG-Auswahl |
| B21 | Slot-Filter für Legionäre | 🚫 | vom Nutzer entfernt (v0.7.0) |

## C. Freiwillige (Warteliste)

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| C1 | Liste mit Gruppen „Clanmitglieder“ / „Legionäre“ | ✅ | |
| C2 | Spalten Spieler / Wertung | ✅ | v0.7.25 (im Spiel bestätigt): Kopfzeile Spieler / Wertung, sortierbar (auf → ab → WG-Reihenfolge) innerhalb der Gruppen, Spieler nicht im Raum (isOffline) beim Sortieren immer unten, gespeichert als `candSort` |
| C9 | Lange Freiwilligen-Liste scrollt (Fenster wächst nicht mehr) + eigene Scrollleiste, auch im Chat | ✅ | v0.7.16 (im Spiel bestätigt): `.pwrap` mit height 0 (Gameface ignoriert min-height 0), Leiste ziehen / auf die Leiste klicken / Mausrad |
| C3 | Online-/Beschäftigt-Status-Icon (`statusIcon`) | ✅ | v0.7.21 (im Spiel bestätigt): WGs `library/userStatus/small/online|busy|offline.png` (16 px) vor dem Namen, Wert kommt fertig von WG (`makeCandidateIconPath`: grün nur Clan/Freunde, rot = Nicht stören, sonst grau) |
| C4 | Eingeladen-Markierung | ✅ | blauer Punkt |
| C5 | Abzeichen | ✅ | v0.7.29 (im Spiel bestätigt): wie B6, zwischen Status-Lämpchen und Name |
| C6 | Rechtsklick-Menü | ✅ | |
| C7 | „Freunde einladen“ | ✅ | |
| C8 | Raum vor Legionären verbergen/anzeigen + Statustext | ✅ | |

## D. Karte

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| D1 | Kartenname / „Zufallskarte“ (mit Würfel-Grafik) | ✅ | v0.7.24 (im Spiel bestätigt): bei `isMapEnabled == false` WGs Würfel (MinimapLobby.swf Sprite 9) auf dunklem Grund, Klicks gesperrt (wie FortClanBattleRoom.as:213) |
| D2 | Minimap-Bild mit Raster A–K / 1–0 | ✅ | v0.7.12 (Raster 10 feste Zeilen, border-box; 0.7.11 brach in Gameface nach 9 Feldern um), im Spiel bestätigt: echte quadratische Minikarte `gui/maps/icons/map/<geometry>.png` (300×300; vorher fälschlich map/stats = 500×235 Landschaftsbild), Raster in festen px (200×200, Felder 20×20), mittig. WGs eigener Pfad (`MinimapLobby._resilientMapIconPathGetter`: map/<gameplay>/c_<geometry>) existiert im Client nicht |
| D3 | Basen / Startpunkte auf der Minimap | ✅ | v0.7.46 (im Spiel bestätigt): Punkte des aktuellen Gefechts aus WGs Richtungs-Tooltip (`ToolTipRefSysDirects.mapPoints`, sonst MinimapLobby-Daten), WG-Marker aus `MinimapLobby.swf` (MinimapEntry teamPoint, 48 px auf 300 px Karte), px = 150 + x, py = 150 − y |
| D4 | **Minimap-Markierungen des Kommandanten** (`MinimapGrid`, Unit-Chat-Befehl ATTENTIONTOCELL) | ✅ | v0.7.23 (im Spiel bestätigt): Klick aufs Raster → `MinimapGrid.setClick(x, y)` im 207-px-Raum von WG (nur wenn `as_clickEnabledS(true)`); Anzeige über Hooks auf `MinimapGrid.as_addPointS/as_clearPointsS`, WGs MinimapClick-Punkt (MinimapLobby.swf Sprite 402) ruhig, 5 s |

## E. Chat

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| E1 | Verlauf, live, Farben, Smileys | ✅ | `cohinline` nötig! |
| E2 | Senden (Enter / ↵) | ✅ | |
| E3 | Raum-Kommentar / Beschreibung anzeigen | ✅ | Fußzeile |
| E4 | **Kommentar bearbeiten (Kommandant)** | 🚫 | vom Nutzer nicht gewünscht (2026-10-18), Entwurf verworfen |
| E5 | Rechtsklick auf Namen im Chat | ✅ | v0.7.28 (im Spiel bestätigt): Autor (erstes `<font>`) mit `data-chatname`; Spieler im Raum → WGs Raum-Menü (UNIT_USER), sonst WGs normales Spielermenü (BASE_USER) über den UsersStorage; eigener Name ohne Menü |
| E6 | Links im Chat klickbar | ✅ | Original kann es nicht (ChannelComponent.onLinkClick: „not longer supported“). Eigene Erweiterung v0.7.30 (im Spiel bestätigt): Links blau/unterstrichen, Klick kopiert in die Zwischenablage (`BigWorld.wg_copyToClipboard`), nichts wird geöffnet |

## F. Fenster- und Zustandslogik

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| F1 | **Automatische Gegnersuche / Warteschlange** (Panel im Fenster) | ✅ | bleibt WG-Original (Nutzerwunsch): Oberfläche blendet sich während der Suche aus und kommt danach zurück (v0.7.3, im Spiel bestätigt) |
| F2 | **Warte-Overlay** („Daten werden geladen“, `showStrongholdWaiting`) | ✅ | v0.7.4: Hook auf `StrongholdBattleRoomWindow.as_setWaitingS` → eigener Schleier mit Kreisel + WG-Text über dem Raum (Variante 1, Nutzerwahl) |
| F3 | Wartungsmodus (`onStrongholdMaintenance`) | ❌ | |
| F4 | Cooldowns: Buttons kurz gesperrt (`as_setCoolDownS`) | 🟡 | v0.7.43 (im Spiel testen): nur Bereit/Nicht-bereit wie WG (SET_PLAYER_STATE = 6, WGs Sekunden, kein Countdown); Loader merkt sich die Sperre pro Anfrage (`bridge.coolDowns`). Raum schließen / Kommentar sperrt WG wegen falscher ID (24 statt 27) selbst nie → nicht nachgebaut |
| F5 | UI-Klänge (`g_strongholdSoundController`, Klick-Sounds) | ❌ | |
| F6 | FAQ-Fenster (`showFAQWindow`) | ❌ | falls im Original erreichbar |
| F7 | Minimieren / Schließen | ✅ | v0.7.36–0.7.39 (im Spiel bestätigt): Overlay 1038×707 deckt WGs ganzes Fenster ab, eigene Titelleiste mit WGs Knöpfen (`windows.swf` Sprites 29/39) → `onWindowMinimize` / `onWindowClose`; Ziehen an der Titelleiste schiebt WGs Fenster mit (`as_setGeometryS`). Aus dem Bild schieben geht nicht (Engine begrenzt Gameface-Fenster, 0.7.40 zurückgenommen). Ab 0.7.38 kann kein anderes Fenster das Overlay schließen (`canBeClosed`) |
| F8 | Fenster verschieben | ✅ | Abfrage jedes Frame |
| F9 | Kontextmenüs / Popups / WG-Fenster über der Oberfläche | ✅ | `_whileWgWindow`, `_reopenAfterExternalClose` |

## G. Eigene Erweiterungen und Abschluss

| # | Punkt | Status |
|---|---|---|
| G1 | Oberfläche in mehreren Sprachen (Texte über `L(de, en)` + Tabelle `TR`) | 🟡 | v0.7.35 (im Spiel testen): de, en, pl, cs, fr, es, it, tr, ru nach Spielsprache (`getClientLanguage`), fehlende Einträge → Englisch; WG-Texte kommen ohnehin aus WGs Sprachdateien |
| G2 | WG-eigene Tooltips (Backport) statt eigener Tooltip-Box | ❌ |
| G3 | Schritt 4: EZ ROOM und EZ TANK PICKER zu einer Mod zusammenlegen | 🚫 | bleibt eigene Mod (Nutzer, 2026-10-19)
| G4 | README / Release auf GitHub (Konto dodojesuslol, kein Klarname!) | ❌ |
| G5 | Dev-Modus vor Release aus (`mods/configs/ez_room/dev.json` löschen) | ❌ |
| G6 | Zurück-Knopf ohne Mods-Liste | ✅ | v0.7.34 (im Spiel bestätigt): nach „Original“ / Esc / Mods-Liste-aus ein kleiner „EZ ROOM“-Knopf (eigenes Fenster, 96×22) mittig in WGs Titelleiste, folgt dem Fenster; Klick = Oberfläche zurück. Auch nach einem Absturz-Schutz (opening.guard) |

## Empfohlene Reihenfolge

1. **Kritisch fürs Spielen:** F1 Gegnersuche, F2 Warte-Overlay, A7 Timer-Alarm-Ton, B12 eingefrorene Panzer, A6 Alarmfarbe
2. **Sichtbare Lücken:** A4 Richtungsgrafik, A3 Zurück-Link, B5 Sprach-Indikator, B8 Rollen-Icons, C3 Status-Icons, E4 Kommentar bearbeiten
3. **Karte:** D3 Basen, D4 Kommandanten-Markierungen, D1 Würfel
4. **Feinschliff:** B6/C5 Badges, B10 Flaggen, B13 Prestige, A10 Reserve-Werte, B19/G2 WG-Tooltips, F4 Cooldowns, F5 Klänge, E5/E6
5. **Abschluss:** G1, G3 Zusammenlegen, G4/G5 Release
