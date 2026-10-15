# EZ ROOM – Roadmap: Funktionsgleichheit mit dem WG-Original

Stand: v0.7.12 (2026-10-15). Ziel: Jede Funktion des Flash-Raums (`fortClanBattleRoom.swf` + `fortBattleRoomWindow.swf`)
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
| A1 | Titel des Fensters („Vorstoß vom Brückenkopf Süd (x2)“) | ✅ | `_updateTitle` (Loader-Hook) |
| A2 | Beschreibung + ⓘ-Icon mit Tooltip (`headerDescr`) | 🟡 | Text da, ⓘ-Tooltip fehlt |
| A3 | Zurück-Link „Zur Abteilungszusammenstellung gehen“ (`backBtn`) | ❌ | Fenster-Meta `onBackClick()` auf `StrongholdBattleRoomWindow` |
| A4 | Richtungs-/Gebäudegrafik (grüne Burg → Flaggen → ⚔ → rote Burg) | ❌ | `as_setDirectionS(value, animationNotAvailable)`, `as_updateReadyDirectionsS`; `makeDirectionVO` liefert `attack1..5`/`defense1..5`/`definition` |
| A5 | Eigener Clan / Gegner-Clan mit Bereit-Anzeige | 🟡 | Namen + Glow da; WGs Bereit-Lämpchen-Optik fehlt |
| A6 | Gefechts-Timer, normale und Alarm-Farbe (#ffdd99 / #ff7f00) | ✅ | v0.7.7: letzte 10 s sofort orange + oranger Rand (Farben aus dem Timer-VO), ohne Animation |
| A7 | Timer-Alarm-Ton (Flash ruft `onTimerAlert()` → `playBattleRoomTimerAlert`) | 🚫 | nicht nachbauen (Nutzer): der Flash-Timer läuft unter der Oberfläche weiter und spielt den Original-Ton selbst |
| A8 | „Warten auf Gefecht“-Text (`waitForBattleDescr`) | ✅ | |
| A9 | 4 Reserve-Plätze + Auswahl | ✅ | eigene Liste statt Popover |
| A10 | Reserve-Liste: erweiterte Werte (Schaden, Radius, Crew-Bonus …) | ❌ | `FortReserveSelectPopover.__buildReserveParams` |
| A11 | Konfigurieren-Button (Modus ändern) + `divisionInfo` | 🟡 | Button da, Divisions-Info fehlt |

## B. Team (Abteilungsmitglieder)

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| B1 | Kopfzeile „Mitglieder: x/15 (Legionäre x/y)“ | ✅ | `as_setTableHeaderS` |
| B2 | Spalten Clan / Name / Wertung / Panzer, sortierbar | ✅ | eigene Erweiterung (v0.7.0) |
| B3 | Platznummer, Spielername in WG-Farbe, eigener Name hervorgehoben | ✅ | |
| B4 | Status-Icon pro Spieler (bereit / nicht bereit / im Gefecht) | 🟡 | eigene Punkte; seit v0.7.10 ganze Zeile grün bei „bereit“ (Nutzerwunsch, im Spiel bestätigt); WG-Icons fehlen |
| B5 | **Sprach-Indikator** (Spieler spricht gerade, `isPlayerSpeaking`) | ❌ | |
| B6 | Abzeichen (Badge) vor dem Namen (`badgeVisualVO`) | ❌ | |
| B7 | Kommandanten-Icon | 🟡 | eigene Raute statt WG-Icon |
| B8 | Rollen-Icons Richtschütze / Inspiration (`roleIcon`, `gunnerIcon0-14`) | ❌ | |
| B9 | Legionär-Kennzeichnung | ✅ | |
| B10 | Panzer: Icon, Stufe, Name; Nationsflagge im Hintergrund | 🟡 | Flagge fehlt |
| B11 | Panzer-Zustand (nicht bereit, „Zu reparieren“ …) | ✅ | |
| B12 | **Eingefrorene Panzer** + „Auftauen“-Button (`vehBrokenIcon`) | ❌ | `onUnfrozenVehicleSlotClick(slotIndex)`, Slot-VO `hasFrozenVehicle`, `canUnfrozeVehicles` |
| B13 | Prestige-Stufe (`prestigeLevel`) | ❌ | |
| B14 | Freien Platz nehmen | ✅ | `assignSlotRequest(slot, -1)` |
| B15 | Platz verlassen / Kommandant: Spieler raus, kicken | ✅ | v0.7.6: „Raus“ + „✕“ (Kick, ein Klick, keine Rückfrage) erscheinen sofort beim Überfahren über dem Zeilenende, ohne Flackern; Freiwillige: „✕“. `leaveSlotRequest`, `requestToKickUser` |
| B16 | Drag & Drop Freiwillige → Platz | ✅ | v0.7.5: Kommandant klickt Freiwilligen → nächster freier erlaubter Platz (`getAvailableSlots`, kleinste Nummer); ziehen → grüne Plätze, loslassen = genau dieser Platz. Zwei-Klick-Verfahren entfernt (Nutzerwunsch) |
| B17 | Gesperrte / geschlossene Plätze, Legionärs-Suchplätze („Spieler wird gesucht“) | 🟡 | Label kommt mit, Optik prüfen |
| B18 | Rechtsklick-Menü | ✅ | `BackportContextMenuWindow` mit `UNIT_USER` |
| B19 | Spieler-Tooltip (WG-Nutzerinfo) und Panzer-Tooltip | ❌ | WG-Backport-Tooltips statt eigener |
| B20 | Panzer wählen | ✅ | EZ TANK PICKER, sonst WG-Auswahl |
| B21 | Slot-Filter für Legionäre | 🚫 | vom Nutzer entfernt (v0.7.0) |

## C. Freiwillige (Warteliste)

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| C1 | Liste mit Gruppen „Clanmitglieder“ / „Legionäre“ | ✅ | |
| C2 | Spalten Spieler / Wertung | 🟡 | ohne Spaltenköpfe |
| C3 | Online-/Beschäftigt-Status-Icon (`statusIcon`) | ❌ | |
| C4 | Eingeladen-Markierung | ✅ | blauer Punkt |
| C5 | Abzeichen | ❌ | |
| C6 | Rechtsklick-Menü | ✅ | |
| C7 | „Freunde einladen“ | ✅ | |
| C8 | Raum vor Legionären verbergen/anzeigen + Statustext | ✅ | |

## D. Karte

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| D1 | Kartenname / „Zufallskarte“ (mit Würfel-Grafik) | 🟡 | Name da, Würfel-Grafik fehlt |
| D2 | Minimap-Bild mit Raster A–K / 1–0 | ✅ | v0.7.12 (Raster 10 feste Zeilen, border-box; 0.7.11 brach in Gameface nach 9 Feldern um), im Spiel bestätigt: echte quadratische Minikarte `gui/maps/icons/map/<geometry>.png` (300×300; vorher fälschlich map/stats = 500×235 Landschaftsbild), Raster in festen px (200×200, Felder 20×20), mittig. WGs eigener Pfad (`MinimapLobby._resilientMapIconPathGetter`: map/<gameplay>/c_<geometry>) existiert im Client nicht |
| D3 | Basen / Startpunkte auf der Minimap (`MinimapLobby.setArena`, `setPlayerTeam`) | ❌ | |
| D4 | **Minimap-Markierungen des Kommandanten** (`MinimapGrid`, eigener Chat-Kanal) | ❌ | Kommandant klickt Planquadrate, alle sehen sie |

## E. Chat

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| E1 | Verlauf, live, Farben, Smileys | ✅ | `cohinline` nötig! |
| E2 | Senden (Enter / ↵) | ✅ | |
| E3 | Raum-Kommentar / Beschreibung anzeigen | ✅ | Fußzeile |
| E4 | **Kommentar bearbeiten (Kommandant)** | ❌ | `editDescriptionRequest(text)` |
| E5 | Rechtsklick auf Namen im Chat | ❌ | |
| E6 | Links im Chat klickbar | ❌ | prüfen, ob das Original das kann |

## F. Fenster- und Zustandslogik

| # | Funktion im Original | Status | Hinweise / WG-API |
|---|---|---|---|
| F1 | **Automatische Gegnersuche / Warteschlange** (Panel im Fenster) | ✅ | bleibt WG-Original (Nutzerwunsch): Oberfläche blendet sich während der Suche aus und kommt danach zurück (v0.7.3, im Spiel bestätigt) |
| F2 | **Warte-Overlay** („Daten werden geladen“, `showStrongholdWaiting`) | ✅ | v0.7.4: Hook auf `StrongholdBattleRoomWindow.as_setWaitingS` → eigener Schleier mit Kreisel + WG-Text über dem Raum (Variante 1, Nutzerwahl) |
| F3 | Wartungsmodus (`onStrongholdMaintenance`) | ❌ | |
| F4 | Cooldowns: Buttons kurz gesperrt (`as_setCoolDownS`) | ❌ | |
| F5 | UI-Klänge (`g_strongholdSoundController`, Klick-Sounds) | ❌ | |
| F6 | FAQ-Fenster (`showFAQWindow`) | ❌ | falls im Original erreichbar |
| F7 | Minimieren / Schließen über die WG-Titelleiste | ✅ | Titelleiste bleibt frei |
| F8 | Fenster verschieben | ✅ | Abfrage jedes Frame |
| F9 | Kontextmenüs / Popups / WG-Fenster über der Oberfläche | ✅ | `_whileWgWindow`, `_reopenAfterExternalClose` |

## G. Eigene Erweiterungen und Abschluss

| # | Punkt | Status |
|---|---|---|
| G1 | Englische Oberfläche (Texte über `L(de, en)`) | 🟡 alles prüfen |
| G2 | WG-eigene Tooltips (Backport) statt eigener Tooltip-Box | ❌ |
| G3 | Schritt 4: EZ ROOM und EZ TANK PICKER zu einer Mod zusammenlegen | ❌ |
| G4 | README / Release auf GitHub (Konto dodojesuslol, kein Klarname!) | ❌ |
| G5 | Dev-Modus vor Release aus (`mods/configs/ez_room/dev.json` löschen) | ❌ |

## Empfohlene Reihenfolge

1. **Kritisch fürs Spielen:** F1 Gegnersuche, F2 Warte-Overlay, A7 Timer-Alarm-Ton, B12 eingefrorene Panzer, A6 Alarmfarbe
2. **Sichtbare Lücken:** A4 Richtungsgrafik, A3 Zurück-Link, B5 Sprach-Indikator, B8 Rollen-Icons, C3 Status-Icons, E4 Kommentar bearbeiten
3. **Karte:** D3 Basen, D4 Kommandanten-Markierungen, D1 Würfel
4. **Feinschliff:** B6/C5 Badges, B10 Flaggen, B13 Prestige, A10 Reserve-Werte, B19/G2 WG-Tooltips, F4 Cooldowns, F5 Klänge, E5/E6
5. **Abschluss:** G1, G3 Zusammenlegen, G4/G5 Release
