# OAK4: gemeinsame entzerrte RGB-D-Aufnahme

Stand16.11.2026: erster realer Datensatz erfolgreich, geometrische Genauigkeit
noch nicht unabhängig geprüft. Für die Aufnahme kann ein beliebiger ruhender
Gegenstand verwendet werden; ein bekanntes Mesh wird erst für dessen Pose benötigt.

## Bedienung

OAK und fest montierte Tischboards stehen lassen. Gegenstand und vorhandenes
Board sichtbar halten; Szene während Aufnahme ruhig. Eigene OAK-Vorschau
pausieren. Fremde Kameranutzer werden nicht beendet; belegte Lease wird abgewiesen.

Aus `~/UWA_ws`:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode rgbd --frames 8 --focus 116
```

Der CLI verwendet dieselbe `.capture.lock` wie RGB-/Tiefenfotodienst und
Vorschau. Kein Dienstneustart/ROS-Build nötig. Eigener isolierter SDK-Worker,
keine Arm-/Power-/Programmaktion, kein Firmware- oder Kalibrier-Flash.
Kamera wird anschließend geschlossen. Standard8Paare, zulässig1–32.
RGB-Automatikbelichtung, manueller Fokus standard116; `--iso` ist hier keine
Einstellmöglichkeit. Bestehende Foto-/HQ-Tiefenmodi behalten ihren Ablauf.

## Daten und Prüfungen

RVC4/DepthAI3.12: native1280×800-Stereoausgaben, FAST_ACCURACY mit Software-
Links-/Rechtsprüfung, keine Extended Disparity, räumliche/zeitliche/Speckle-/
Medianfilter aus, Decimation1. RGB aus8K-Sensorfeld auf1280×960/10fps,
`enableUndistortion=True`/alpha0. ImageAlign reprojiziert Stereo-Z auf das
entzerrte RGB-Gitter; die Ausgabegröße ist keine höhere native Tiefenauflösung.
Sync gruppiert mit maximal25ms Zeitabstand, danach erneute Hostprüfung.

Gespeichert unter `setup/oak4/rgbd/<Zeit-ID>/`:

- `rgb/000000.png` usw.: entzerrte Farbbilder.
- `depth/000000.png`: RGB-ausgerichtete Z-Tiefe, uint16/mm,0ungültig.
- `valid/000000.png`: Gültigkeit,0/255; keine Lochfüllung.
- `cam_K.txt`, `factory-calibration.json`: tatsächliche Ausgabe-K und Werksbackup.
- `metadata.json`: RGB-/Tiefensequenzen und Gerätezeiten jePaar, tatsächlicher
  Fokus/Belichtung, SDK-RGB-Alter, K beider Ausgaben, Qualitätsanteile.
- `preview.png`: Farbe/Tiefe/Überlagerung mit kontrastreichen Beschriftungen.
- `capture.log`, `result.json` bei vollständigem Erfolg, sonst `failure.json`.

Worker prüft Formate, übereinstimmende tatsächliche K, steigende Sequenzen/
Gerätezeiten, Zeitdifferenz, Fokus und SDK-Bildalter≤1s. Pixel ohne Tiefe bleiben
ungültig. RGB ist bereits entzerrt; D=0 gilt für diese Ausgabe, Factory-D darf
nicht nochmals darauf angewendet werden. Daten sind kamera-lokal, ohne Welt-TF.
Zeitstempelgruppierung beweist keine gleichzeitige Belichtung oder UR-Synchronität.
`success` bedeutet vollständige technisch geprüfte Aufnahme, keine Genauigkeits-
oder Manipulationsfreigabe; Kantenüberlagerung/Board/Messreferenz separat prüfen.

## Erstnachweis16.11.2026

- Nutzer: studentischer Roboter steht aktuell an der früheren Kartonstelle.
  Für RGB-D-Aufnahmetest geeignet, noch kein getestetes FoundationPose-Objekt.
- Datensatz `setup/oak4/rgbd/20261116-102913-rgbd-fa320e7a/`:
  acht unterschiedliche Paare,1280×960, tatsächliche Paarrate10,00Hz über0,7s.
- Maximale Gerätezeitdifferenz1,727ms, maximales SDK-RGB-Alter144,567ms.
  K/Größe beider SDK-Ausgaben identisch, Fokus116 in allen RGB-Frames bestätigt.
- Vorschau visuell geprüft: Roboter und Tischboard sichtbar; Zuordnung im
  Übersichtsbild plausibel, deutlich sichtbare Tiefenlücken. Gültig42,01–42,72%
  über das Gesamtbild, kein Qualitätswert ausschließlich am Roboter.
- Gespeicherte PNGs erneut dekodiert, Zeit-/Geometrieprüfungen bestanden;
  Validmasken stimmen exakt mit Tiefe>0 überein. Lease nach Abschluss frei.
  `initial-check.json` enthält diese Nachprüfung. Kein absoluter Tiefenfehler
  gemessen, keine Modellpose oder Weltregistrierung aus dieser Aufnahme.
- Offline-Suite:31Tests und9Subtests bestanden, einschließlich Busy-/Timeout-
  Verhalten, RGB-D-Auswahl sowie falscher Projektion/Zeit/Einheit/Sequenz.

Nächster Schritt: vorhandenes Board mit tatsächlicher Ausgabe-K prüfen und
Tiefe an Bildkanten/Referenzmaßen bewerten. Die Modellpose benötigt anschließend
ein passendes metrisches Mesh und eine Initialmaske; dafür ggf. Karton verwenden,
sobald er wieder verfügbar ist.

## Board-/Tiefenkonsistenz16.11.2026

Die erste Offlineprüfung ist abgeschlossen. Befehl aus dem Workspace:

```bash
python3 src/oak_camera_calibration/tools/oak4_rgbd_board_check.py \
  --capture setup/oak4/rgbd/20261116-102913-rgbd-fa320e7a \
  --layout src/multi_arm_manipulation_UWA/uwa_cell_description/config/cell_layout.yaml \
  --output setup/oak4/rgbd/20261116-102913-rgbd-fa320e7a/board-check-NEUE-ID
```

Nur gespeicherte Daten, keine Kamera/ROS/UR/GPU. Bestehenden Ausgabeordner
nicht überschreiben. K bleibt fest; Boardidentität und40mm-Maß aus Zelllayout.
Rechtes/vorderes Board IDs50–66:24Ecken in allen8Bildern.16Ecken für planare
Bildpose,8vorab über Ecke-ID ausgeschlossene Ecken zur Prüfung. Kein bekannter
Welt-/Board-/Roboterzustand als Poseprior. Linkes Board unzureichend sichtbar.

- Maximales Prüf-RMS0,3222px, unter bestehendem1px-Bildkriterium. Das prüft die
  lokale Bildkonsistenz, keine vollständige Intrinsicskalibrierung aus acht
  fast identischen Ansichten.
- Median95,27% gültige Tiefenpixel im erodierten Boardinneren; das ist etwas
  anderes als der42%-Anteil über das ganze Bild.
- SDK-Tiefe gegenüber der RGB-Boardebene median **+11,05mm** in Z-Richtung,
  Einzelbilder+10,63bis+11,11mm.95%-Absolutreste jeBild22,86bis23,95mm.
- Robust gefittete Tiefenebene: unabhängige räumliche Trainings-/Prüfblöcke;
  Winkel zur RGB-Ebene median1,11°. Tiefenpunkte werden nicht zum RGB-Posefit
  verwendet, Ausreißer nicht aus der getrennten Tiefenprüfung entfernt.
- Nutzer hat fünf ganze Felder am vorderen Board mit dem Lineal als200mm
  nachgemessen. Das passt zum40mm-Nominalmaß; keine kalibrierte Unsicherheit
  angegeben. Die Aussage ist in operator-reference.json getrennt gespeichert.

Bericht/Bilder: Datensatz-Unterordner `board-check-v1/`. Status bewusst
`REVIEW_REQUIRED`, keine nachgewiesene absolute Millimetergenauigkeit. Ursache
der Abweichung aus diesem statischen Blick noch nicht trennbar: interne
Stereo-/RGB-Kalibrierung, Restgeometrie und Referenz-/Messunsicherheit bleiben
zu prüfen. Keine pauschale11mm-Korrektur und keine Profil-/EEPROMänderung.

Nächster vorgeschlagener Nachweis: separates mobiles38mm-A4-Board bei mehreren
ruhenden Entfernungen/Neigungen aufnehmen; fest montierte Tischboards bleiben
unverändert. Unterschiedliche Ansichten und Prüfaufnahmen trennen, bevor eine
Nachkalibrierung erwogen wird. Ein Karton ist dafür keine gleichwertige metrische
Referenz. Seine spätere Poseerkennung ist ein eigener Funktionstest.

36Offline-Tests/9Subtests PASS, einschließlich synthetischem12mm-Tiefenbias,
Z- statt Strahldistanz, Tiefenlöchern und gezielter Störung der ausgeschlossenen
Bildpunkte ohne Änderung der geschätzten Pose. Board-Overlays visuell geprüft.

## Mobile Referenzansichten und Karton16.11.2026

Nutzer bestätigt separates mobiles38mm-Brett und misst fünf Felder mit Lineal
als191mm (nominal190mm). Unkalibrierte Linealmessung; globale Definition bleibt
unverändert. Prüfer unterstützt jetzt `--mobile-definition` mit der zentralen
`mobile_charuco_a4.yaml` (IDs75–91), getrennt von40mm-Tischboards. Pro Board
getrennte Statistiken;38Tests/9Subtests bestanden.

Fünf RGB-D-Aufträge mit je8Paaren: drei mobile Ansichten auswertbar, zwei wegen
zu flachem Blick bzw. abgeschnittenem Muster nicht als mobile Referenz gezählt.
Alle Rohdaten und Gründe bleiben erhalten. Messung mit unverändertem Ausgabe-K:

| Capture16.11. | Kamera-Z des Boardzentrums, aus RGB | MaxPrüf-RMS | Gültige Tiefe im Muster | Z-Abweichung, Nominalmaß | Nur Rechenbeispiel mit191/190 |
|---|---:|---:|---:|---:|---:|
| 105958-…67777ded |1,152m |0,332px |96,7% |+16,08mm |+10,10mm |
| 110510-…b9ede6fe |1,330m |0,191px |98,6% |+2,51mm |−4,44mm |
| 110823-…dd33bfc2 |0,922m |0,452px |42,6% |+13,15mm |+8,10mm |

Das Rechenbeispiel nimmt eine isotrope Druckskalierung an; ein einzelnes
Linealmaß beweist diese nicht. Es ändert weder Rohwerte noch aktive Kalibrierung.
Unterschiedliche Perspektiven/Orte/Abstände sind hier gekoppelt; keine einzelne
Ursache oder universelle Offsetkorrektur identifiziert. Insbesondere die nähere
Ansicht zeigt viele Tiefenlücken. Keine Millimetergenauigkeitsfreigabe.

Vergleich `setup/oak4/rgbd/validation_20261116/mobile-comparison-v1.json`,
Benutzermaße in operator-references.json. Wiederverwendbares Offlinewerkzeug
`tools/oak4_rgbd_compare.py`; Eingaben/Definitionen/Berichte gehasht.

Anschließend bekannter Karton neu aufgenommen:
`setup/oak4/rgbd/20261116-111619-rgbd-5a8d0ae9/`. Erste statische FoundationPose-
Auswertung auf titanpc mit640×480-Arbeitsdaten und manueller Startmaske visuell
plausibel; Details im Zell-Repo docs/foundationpose_titanpc.md. Keine neue
Kamera-/Weltkalibrierung, kein Live-/Manipulationsnachweis. Kamera-Lease frei.
