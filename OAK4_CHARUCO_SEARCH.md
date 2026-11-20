# OAK4: ChArUco-Suchmodus

Stand20.11.2026. Eine Kamerasitzung sucht für jedes der beiden festen Tischboards
gute Fokus-/Belichtungswerte, speichert native Bilder und schätzt daraus die
Kamerapose relativ zu den Boards und den bereits übernommenen Roboterbasen.
Die Auswahl ist die beste **unter den geprüften Kandidaten**, kein Nachweis
eines globalen Optimums. Kamera, Boards und Szene während der Suche stillhalten.

## Bedienung

Aus `~/UWA_ws`:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode charuco
# Optional: andere feste Empfindlichkeit oder angepasste Suchkonfiguration.
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode charuco --iso 200
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode charuco --search-config /path/search.json
```

Fokus wird automatisch durchsucht; `--focus` ist hier nicht zulässig.
`--frames` bleibt1: Die Bilder sind einzelne Hypothesen, keine Mittelungsframes.
Der Modus verwendet dieselbe Kamera-/Transaktions-Lease wie Standard/HQ/HDR/
RGB-D. Bei belegter Kamera wird abgewiesen; bestehende Vorschau regulär über
**Pause live view** freigeben. Keine fremden Dienste automatisch stoppen.
Nach Abschluss schließt der Worker seine Kamera. Keine Roboterdienste nötig.

ROS-Domain65/LOCALHOST: `/oak4/photo/capture_charuco` (`std_srvs/srv/Trigger`).
Der Fotodienst muss nach der erstmaligen Ergänzung im untätigen Zustand neu
geladen werden. `/oak4/photo/status` bleibt während des Auftrags erreichbar.
`success=true` bedeutet eine vollständig gespeicherte Suche, keine garantierte
Boarderkennung oder gültige Registrierung: `search_summary` getrennt prüfen.

## Ablauf und Auswahl

1. Übersicht2000×1500 mit Automatikmessung bei Fokus107. Erkannte Marker-IDs
   ordnen die Boards eindeutig zu: links0–16, rechts50–66, jeweils7×5/40mm,
   Marker28mm. Die Definition kommt aus dem zentralen Zelllayout. Das mobile
  38mm-Board mitIDs75–91 wird nicht damit verwechselt. Aus der Übersicht werden
   Bildregion, Helligkeit und eine grobe Boardpose/Entfernung geschätzt.
2. Gemeinsame Fokusreihe91/99/103/107/111/115/123 bei gleicher Belichtung,
   ISO und Weißabgleich. Jede Aufnahme wird für beide Boards bewertet.
   Vordergrund sind erkennbare ChArUco-Ecken und Marker, danach die
   kontrastnormalisierte Laplace-Schärfe im jeweiligen Boardbereich.
3. Pro Board −1/0/+1EV relativ zur Startbelichtung durchsuchen. ISO bleibt
   standardmäßig100; Grenzen100–90000µs. Doppelte begrenzte Belichtungen werden
   nicht mehrfach aufgenommen. Erkennungszahl geht vor; danach wird eine
   helle Boardfläche nahe Grauwert220 gegenüber Clipping bevorzugt.
4. Die zwei besten Fokuswerte der Übersicht werden mit der gewählten
   Boardbelichtung nativ8000×6000 kontrolliert. Falls nötig kommt der beste
   gefundene Fokus mit eigenem Intrinsics-Profil hinzu. Detektion/Schärfe nur
   im vergrößerten nativen Boardausschnitt; kein umfangreicher Vision-Batch.
   Die native Bewertung darf die kleine Übersicht korrigieren.
5. Einstellungen werden jeweils an zwei aufeinanderfolgenden Vorschauframes
   und nochmals an jedem Vollbild bestätigt. Native Sequenzen müssen steigen.
   Vollbilder/Metadaten und Posepakete vollständig speichern, Kamera schließen.

Die kleine Ausgabe wird über ImageManip aus demselben8K-Ausgabestrom abgeleitet,
entsprechend dem [Luxonis-8K-Beispiel](https://docs.luxonis.com/software-v3/depthai/examples/camera/camera_still_max_res).
Der Sensor läuft nativ; die Übersicht wird nicht als8K-Bild übertragen.
Helligkeits-/Schärfemetriken sind Auswahlheuristiken, keine Genauigkeitsmessung.

## Fokusgebundene Poseberechnung

Eine Fokusänderung kann die Intrinsics verändern. Deshalb sind zwei Auswahlen
getrennt: **bildlich beste Aufnahme** und **verwendbare Poseaufnahme**.
Konfiguration `config/oak4_charuco_search.json` enthält `intrinsics_by_focus`.
Jedes Profil muss zur physischen OAK4, Fokusposition und8000×6000 passen.
Zurzeit liegt ein eigenes Fokus107-Kandidatenprofil vor; weitere vorhandene
Kalibrierungen können ergänzt werden. Neue Profile werden nicht aus einer
einzigen statischen Boardaufnahme erfunden oder durch Skalieren der
Fokus107-Brennweite als kalibriert ausgegeben.

Wird z.B. Fokus103 bildlich besser, bleibt sein Rohbild erhalten. Ohne
103-Profil steht dort `NEEDS_FOCUS_INTRINSICS`; die Poseaufnahme kann separat
bei107 liegen. Factory-/fokusfremde Intrinsics liefern ausschließlich eine
als grob gekennzeichnete Suchpose. Wenn kein passendes brauchbares Bild
existiert, bleibt `pose_selection=null` und wird kein Basisbezug ausgegeben.

Pose: planarer IPPE-Kandidat mit positiver Tiefe und LM-Verfeinerung. Ganze
Marker werden zum unabhängigen Bildgegencheck zurückgehalten, keine
Nachbarecken desselben Markers gleichzeitig fitten/prüfen. Benötigt mindestens
vier verteilte Marker; Gegencheckgrenze2nativePixel RMS. Das ist eine lokale
Bildkonsistenzprüfung, keine absolute metrische Genauigkeitsqualifikation.
Die zusätzliche ChArUco-Erkennung bleibt als Bildqualitätsmaß dokumentiert;
die Pose nutzt alle geeigneten Markeraußenecken, auch bei Teilverdeckung.

Mit passender Aufnahme: `T_camera_board` bildet Boardkoordinaten ins
Kamera-Koordinatensystem ab. Die übernommenen `T_base_board` liefern
`T_base_camera = T_base_board @ inverse(T_camera_board)` für die Arme am
jeweiligen Tisch. Aus beiden passenden Aufnahmen entsteht außerdem ein
Kandidat `T_left_board_right_board`; Voraussetzung sind unveränderte Kamera/
Boards zwischen den Aufnahmen. Eine gemeinsame Weltpose wird nicht aus der
nominellen Tischanordnung erfunden. Keine automatische Aktivierung neuer
Kamera-/Basis-/Weltkalibrierungen und keine Roboterbewegung.

## Dateien

Ordner `setup/oak4/photos/<Zeit>-charuco-<ID>/`:

- `search-config.json`: eingefrorene Boarddefinition, Suchwerte, K/D und
  übernommene Basisbindungen einschließlich Quellenhashes.
- `overview.png`:2000×1500, grobe Beobachtungen in `metadata.json`.
- `right/focus-*.png`, `left/focus-*.png`: alle nativen Kontrollkandidaten.
- `right/metadata.json`, `left/metadata.json`: tatsächliche Einstellungen der
  bildlich besten Aufnahme. `intrinsics.json` nur bei passendem Profil.
- `right/pose/`, `left/pose/` nur bei brauchbarer fokusgebundener Pose:
  `standard.png`, `metadata.json`, `intrinsics.json`, `pose.json`. Standardbild
  ist ein lokaler Hardlink auf den passenden unveränderten Kandidaten.
- `metadata.json`: alle Suchbeobachtungen/Settings, Gewinner, Poseauswahl,
  zurückgehaltene Fehler, Kameraposen je Basis und Zusammenfassung.
- `capture.log`, `result.json` bzw. `failure.json`: bestehender Fotodienstpfad.

Fehlendes/verdeckt gebliebenes Board: `NOT_FOUND` bzw. `NATIVE_NOT_FOUND`.
Eine vollständig gespeicherte Suche kann trotzdem erfolgreich abgeschlossen
sein; `both_boards_found` und `both_pose_candidates_available` sind getrennt.
Fokus-/Belichtungsänderungen betreffen die temporäre Pipeline, kein EEPROM.

## Erster Realnachweis20.11.

`20261120-121811-charuco-0366271e`:21,75s, beide native Gewinner107,
rechts37,165ms/links18,582ms beiISO100; je24ChArUco-Ecken/17Marker.
Zurückgehaltener RMS rechts1,735px/links1,027px.
`20261120-121950-charuco-682d3590`:21,72s, rechts107/49,998ms,
links bildlich103/24,999ms. Beide Bilder24Ecken/17Marker. Linke Pose korrekt
aus der separaten107-Aufnahme: rechts1,652px/links1,240px Prüf-RMS.
Grobe Boardursprungsentfernungen aus Übersicht etwa1,53m/2,23m, keine
unabhängige Abstandsmessung. Wechsel des nah beieinanderliegenden
Schärfegewinners ist kein Nachweis einer physischen Boardbewegung.

57Tests/17Subtests PASS: Boardidentität, Crop-Koordinaten, Defokusbewertung,
synthetische Pose mit disjunkten Markern, falsche ID/Fokus/Bildgröße und
Dienstdispatch. Die realen Quelldateien bleiben im Workspace, nicht im Git.

Finaler ROS-Triggerlauf `20261120-122215-charuco-b38fa2e7`:21,93s, bildlich
beide103, rechts44,332ms/links22,166ms; je24Ecken/17Marker. Posepakete beide
bei107 mit Prüf-RMS1,703/1,077px. Basisbezogene Kameraposen und relativer
Zweiboard-Kandidat exportiert. Alle drei Datensätze offline erneut geprüft;
Kamera nachher frei. Nachweise und Bildvergleich:
`setup/oak4/charuco_validation_20261120/{validation.json,board-comparison.jpg,
camera-release.json}`.
