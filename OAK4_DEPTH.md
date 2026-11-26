# Statischer HQ-Tiefenmodus der OAK4

Seit2026-11-12 als Erweiterung des installierten **uwa-oak4-photo.service**.
Er verwendet dieselbe exklusive Kamerasperre wie der RGB-Fotodienst und öffnet
die Kamera nur während eines Auftrags. ROS2 Lyrical, Domain65/LOCALHOST.

## Aufnehmen

Aus `~/UWA_ws`, auch ohne ROS-Umgebung:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode depth_hq
# Einzelbild oder Vergleich mit einem zusätzlichen, vorher aufgenommenen Einzelbild:
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode depth_standard
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode depth_compare
# Optional 4..32 Frames; Standard 16:
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode depth_hq --frames 16
# Vier Stereo-Einstellungen mit je vier Frames und einem IR-Block:
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode depth_hdr
```

ROS-Aufrufe mit festen16Frames:

```bash
source /opt/ros/lyrical/setup.bash
export ROS_DOMAIN_ID=65 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 service call /oak4/depth/capture_hq std_srvs/srv/Trigger '{}'
ros2 service call /oak4/depth/capture_compare std_srvs/srv/Trigger '{}'
ros2 service call /oak4/depth/capture_standard std_srvs/srv/Trigger '{}'
ros2 service call /oak4/depth/capture_hdr std_srvs/srv/Trigger '{}'
ros2 service call /oak4/depth/status std_srvs/srv/Trigger '{}'
```

Antwort ist `success` plus JSON mit Verzeichnis, Metadaten, Bildern und
Zusatzdateien. Der Status gehört zum gemeinsamen Foto-/Tiefendienst; bei RGB-
Aufnahmen zeigt er deren Auftrag an. Gleichzeitige Foto-/Tiefenaufträge werden
abgewiesen. Dienstverwaltung/Installation wie in [OAK4_PHOTOS.md](OAK4_PHOTOS.md).
Kein zweiter permanenter Kameratreiber und kein neuer ROS-Build nötig.

## Stereo-HDR für ruhende Szenen

`depth_hdr` verwendet die native rektifizierte rechte Ansicht mit 1280×800
Pixeln. Nach bestätigter Automatikmessung laufen auf derselben Kamera
vier Blöcke mit je vier Stereo-Paaren. Bei ISO 200 werden kurze und lange
Belichtungen (¼× und 4× der mittleren Zeit) sowie die mittlere Belichtung
mit IR aus aufgenommen. Im letzten Block bleibt die mittlere Zeit
eingestellt und der Punktprojektor läuft auf 100 %. Nach bestätigtem
SDK-Befehl wartet die Aufnahme bis zur gemessenen Umschaltgrenze von
350 ms auf der SDK-Bildzeitachse. Beim Ende der Kamerasitzung wird der
Projektor ausgeschaltet.

Je Einstellung braucht ein Pixel mindestens drei passende Messwerte
innerhalb `max(10 mm, 1 % der Tiefe)` um den Median. Der zweite Median
kombiniert pro Pixel die stabilen Einstellungen. Widersprechen sich
diese Werte über der Toleranz, bleibt der Pixel ungültig. Die Vorschau
markiert solche Konflikte magenta. Eine einzige stabile Einstellung
kann Tiefe liefern, etwa am Kartonboden im aktiven Block.

`standard-depth-mm.png` enthält ein mittleres, passives Einzelbild.
`hq-depth-mm.png` enthält das Ergebnis der vier Einstellungen.
Die unkomprimierte NPZ speichert die 16 Rohkarten als [4, 4, 800, 1280],
Stufentiefen, Stufenzählwerte und Konfliktmaske verlustfrei. Die Reihenfolge,
tatsächliche Belichtung beider Mono-Sensoren, Gerätestempel und Laufzeiten
stehen in `metadata.json`. Ausgabegröße des geprüften Satzes ca. 53 MiB.
Der Datensatz lässt sich mit `view-depth` anzeigen. Die Abdeckung ist
szenenabhängig und vom absoluten Tiefenfehler getrennt zu bewerten.

## HQ-Punktwolke in RViz öffnen

```bash
# Aus ~/UWA_ws; zeigt die jüngste erfolgreiche Aufnahme mit Projektionsdaten:
bash src/oak_camera_calibration/tools/oak4_photo.sh view-depth
# Bestimmte Aufnahme auswählen:
bash src/oak_camera_calibration/tools/oak4_photo.sh view-depth --capture /voller/pfad/zur/aufnahme
```

Eigene RViz-Ansicht auf Domain65/LOCALHOST; **HQ DEPTH - static snapshot**
standardmäßig aktiv. **STANDARD - single frame (optional)** kann alternativ
angehakt werden; zum direkten Vergleich HQ vorher deaktivieren. Beide Wolken
liegen im gleichen Kameraframe und würden sich sonst überlagern. Move Camera,
Orbit und Zoom sind vorhanden. Nach dem Schließen dieses Fensters beendet sich
nur der zugehörige Datei-Publisher, nicht der Foto-/Tiefenservice.

Die Ansicht zeigt eine **statische Aufnahme**, keinen Livestream. Aufnahmezeit
und Hinweis stehen sichtbar in der Szene. Alle gültigen Pixel werden in Meter
zurückprojiziert. Neue Aufnahmen sichern dafür die tatsächliche rektifizierte
`ImgFrame.getTransformation().getIntrinsicMatrix()` als `projection.K` und die
Ausgabegröße in `metadata.json`. Ältere Aufnahmen ohne diese Daten werden
abgewiesen; die ursprüngliche Factory-K wird nicht als Ersatz eingesetzt.

Publisher: `/oak4/depth_snapshot/hq/points` und
`/oak4/depth_snapshot/standard/points` (`sensor_msgs/PointCloud2`, reliable,
transient-local). Metadaten auf `/oak4/depth_snapshot/info`; TF ausschließlich
`oak4_snapshot_view` → `oak4_snapshot_rectified_right_optical`. Der View-Frame
stellt die optischen Achsen Xrechts/Yunten/Zvorne als Xvorne/Ylinks/Zoben dar.
**Kein world-/Zelltransform, keine behauptete Registrierung zur Roboterzelle.**
ROS-Header verwenden Wiederveröffentlichungszeit für die Anzeige; echte
Aufnahmezeiten bleiben separat im unveränderten Metadaten-/Infoinhalt.

Generierte Konfiguration: `setup/oak4/rviz/depth-snapshot.rviz`, aktueller
Anzeige-Nachweis: `setup/oak4/rviz/latest-view.json`. Am2026-11-12 geöffnet:
`uwa-oak4-depth-rviz.service` (temporärer Benutzerdienst),273323HQ-/429717
Standardpunkte aus `setup/oak4/depth/20261112-145646-depth_hq-437c09ec/`.
Paketinhalt, positive endliche Tiefen, TF und tatsächlicher RViz-Abonnent geprüft;
RViz-Oberfläche meldet Global Status: Ok. Vorhandene Domain70-Zellvorschau erhalten.

## Verfahren und Aussagekraft

- Zwei native Mono-/Global-Shutter-Sensoren OV9282, **1280×800** bei10fps.
  Diese Tiefenauflösung ist unabhängig von den48MP des RGB-Sensors.
- FAST_ACCURACY-Stereo mit zusätzlicher Software-Links-/Rechtsprüfung,
  Decimation1, rectified-right/CAM_C-Perspektive, kein Extended Disparity.
  RVC4-Subpixel4bit. Software-Spatial-/Temporal-/Speckle-/Medianfilter aus,
  um die zeitliche Fusion aus den unvermittelten Stereoausgaben nachvollziehbar
  zu berechnen. Dies ist ein eigenes Static-Profil, kein Geschwindigkeitsbenchmark.
- Fünf Sekunden AE-Einlauf, dann Belichtung/Gain beider Mono-Kameras einfrieren.
  Tatsächliche Werte je Kamera und Stabilität während des Bursts prüfen.
  Der RGB-Parameter `--iso` ist für Tiefe nicht anwendbar. Dieses Profil nutzt
  gehaltene Mono-Automatikwerte und erzwingt weder ISO100 noch lange Belichtung.
- Standard ist ein neues einzelnes Tiefenbild nach dem Einregeln. Danach16
  unterschiedliche native Tiefenframes aufnehmen. Aus gültigen Werten je Pixel
  den zeitlichen Median bilden; Nullwerte niemals als Messung einbeziehen.
- HQ akzeptiert einen Pixel nur bei mindestens75% gültigen Messungen, mindestens
  75% Messungen innerhalb `max(10mm,1% der Tiefe)` um den Median und zeitlichem
  MAD unter dieser Toleranz. Bei16Frames sind mindestens12 nötig. Sonst bleibt
  der Pixel0/ungültig. Kein räumliches Glätten, keine Lochfüllung/Interpolation.
  Masken und Grenzwerte sind eine dokumentierte Stabilitätsheuristik, keine
  kalibrierte statistische Konfidenz und kein zertifizierter Bewegungsdetektor.

**Kamera und Szene müssen während des Bursts stillstehen.** Der Dienst fährt
keine Arme und garantiert keinen Stillstand; parallele Roboterarbeit kann
Messwerte verändern. HQ kann zufälliges Rauschen/Ausreißer reduzieren und dafür
weniger gültige Pixel liefern. Texturarme, reflektierende oder verdeckte Flächen
bleiben problematisch. Wiederholt falsche Stereo-Zuordnungen und systematische
Kalibrierfehler können bestehen bleiben; absolute Genauigkeit separat an einer
vermessenen Referenz prüfen. Zeitliche Stabilität ist keine Genauigkeitsmessung.

## Dateien

Neuer unverwechselbarer Ordner je Aufnahme:

```
$UWA_WS/setup/oak4/depth/<Zeit>-<Modus>-<ID>/
  standard-depth-mm.png  # uint16, Z-Tiefe in mm, 0 = ungültig
  hq-depth-mm.png        # uint16, robuste zeitliche Fusion, 0 = ungültig
  stable-mask.png       # 0/255: akzeptierte HQ-Pixel
  depth-data.npz        # rohe Einzelbilder + Qualitätskarten
  mono-left.png         # native, unrektifizierte Monoansicht
  mono-right.png
  comparison.png        # gleiche Tiefenfarbskala + zeitliche Streuung
  factory-calibration.json
  metadata.json
  capture.log
  result.json           # nur bei vollständigem Erfolg
  failure.json          # bei Fehlern
```

`depth_standard` liefert nur Einzelbild, Monoansichten, Factory-Backup und
Metadaten; der Burst entfällt. HQ/compare speichern zusätzlich immer das
vorherige Standardbild als Referenz. NPZ-Felder:

| Feld | Bedeutung |
|---|---|
| `raw_depth_mm` | N×800×1280 uint16, alle16 originalen Stereoausgaben |
| `standard_depth_mm` | vorheriges Einzelbild |
| `hq` | 800×1280 uint16, akzeptierter Median |
| `valid_counts` | Anzahl ursprünglicher gültiger Messungen je Pixel |
| `inlier_counts` | Anzahl Messungen innerhalb der Stabilitätstoleranz |
| `temporal_mad_mm` | beobachtete mediane absolute Abweichung, float32/mm |
| `stable` | bool, HQ-Akzeptanzmaske |

All-null-Pixel haben MAD0 und Count0; MAD nur zusammen mit Count/Mask interpretieren.
Tiefe ist Z in der rektifizierten rechten Perspektive, keine Strahldistanz oder
Weltkoordinate. Factory-Backup enthält die ursprüngliche Kamerakalibrierung und
ist keine fertig bestimmte Projektionsmatrix dieser rektifizierten Ausgabe.
Seit RViz-Erweiterung enthält `metadata.json` zusätzlich die tatsächliche
rektifizierte Ausgabe-K und ihren Transform zum Referenzsensor; ältere Dateien
ohne `projection` nicht für die3D-Anzeige verwenden.
Kein implizites Alignment auf das RGB-Foto, keine Punktwolke/Extrinsics aktiviert.
Gerätezeitstempel monoton, nicht mit ROS-/Wanduhr synchronisiert. Daten bleiben
lokal unter `setup/`, keine privaten Bilder insGit.

## Echte Probe und Tests,2026-11-12

Installierter `/oak4/depth/capture_compare` erfolgreich. Artefakte:
`setup/oak4/depth/20261112-144815-depth_compare-97e070f4/`.
Native1280×800/uint16,16 verschiedene Sequenzen57–72 über1,500s.
Mono links3000µs/ISO188, rechts3135µs/ISO200, während Burst konstant.
Standard41,67% gültige Pixel, HQ26,87% nach strenger Stabilitätsprüfung.
Median des zeitlichen MAD auf akzeptierten Pixeln3mm; **keine ±3mm-Genauigkeitsangabe**.
Andere Hardwarearbeit war parallel aktiv; kein unabhängiger Szenenstillstandsnachweis.

Automatisierte Hardware-unabhängige Tests prüfen Nullwerte, Ausreißer, bewegte
Kanten, Erhaltung räumlicher Tiefensprünge und Rauschreduktion an synthetischer
statischer Oberfläche. Hinzu kommen gemeinsame Sperr-/Fehler-/Timeouttests:

```bash
python3 -m unittest discover -s src/oak_camera_calibration/test -p 'test_oak4*.py' -v
```

Quellen zum Verfahren: [Luxonis StereoDepth](https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/stereo_depth),
[OV9282/RVC4-Sensorauflösung](https://docs.luxonis.com/hardware/sensors/OV9282).


Finaler regulärer HQ-Service ebenfalls real PASS:
`setup/oak4/depth/20261112-145220-depth_hq-29c6117c/`.
Status während Aufnahme CAPTURING erreichbar; paralleles RGB-Foto abgewiesen,
danach READY. **14 automatisierte Tests bestanden**. Eigener gemeinsamer Dienst
bleibt aktiv; Kamera nach dem Auftrag freigegeben.
