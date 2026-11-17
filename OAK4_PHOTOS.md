# OAK4: Standard- und HQ-Fotodienst

Stand: 2026-11-13, Ubuntu26.04 / ROS2 Lyrical. Für die physische Ethernet-OAK4
(`cameras.oak4` im zentralen Zellinventar) existiert **uwa-oak4-photo.service**.
Der installierte systemd-Benutzerdienst startet bei der Benutzeranmeldung und
wartet ohne offene Kamera auf einen Auftrag. Er arbeitet in **ROS-Domain65**
mit lokaler Discovery. Die Kamera wird nach jeder Transaktion wieder geschlossen.

Der gleiche Dienst bietet zusätzlich [statische HQ-Tiefendaten](OAK4_DEPTH.md)
über `/oak4/depth/capture_hq` bzw. CLI `--mode depth_hq` an. RGB und Tiefe
verwenden eine gemeinsame Kamerasperre.

Seit16.11. zusätzlich gemeinsamer [RGB-D-CLI-Modus](OAK4_RGBD.md): `--mode rgbd`
mit entzerrter Farbe und darauf ausgerichteter, zeitlich gepaarter Tiefe.
Er nutzt dieselbe Sperre; bestehende ROS-Trigger bleiben unverändert.

## Wiederholungsprüfung vor einem Roboterscan

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh check --count 3 --focus 116
```

Der Check startet drei einzelne native Standardaufnahmen über denselben Fotopfad.
Er verlangt dekodierbare8000×6000-Bilder, tatsächlichen Fokus116, dieselbe
Geräteidentität, steigende Gerätezeit und unterschiedliche Bilddateien. Beim
ersten Fehler endet die Reihe. JSON und Exitcode0/1 zeigen PASS/FAIL;
Prüfberichte bleiben unter `setup/oak4/checks/<Zeit-ID>/report.json`, Originale
unter `setup/oak4/photos/`. `--count` erlaubt1–10. Keine Roboterkommandos,
kein automatischer Reset/Update und keine automatische Wiederholung nach Fehler.
Eine bestandene kurze Reihe ist kein dauerhafter Zuverlässigkeitsnachweis.

Am13.11. half der vom Nutzer bestätigte OAK-Neustart nach Pipeline-Startfehlern.
Vier anschließende8K-Einzelaufnahmen und zwei komplette stationäre Fünfkamera-
Sätze bestanden. Später trat der OAK-Fehler wieder auf. Das danach ausdrücklich genehmigte
OS1.47-Update ist installiert, die Werkskalibrierung unverändert;15Startzyklen
und der abschließende Fünfkamera-Satz bestanden. Alte Fehlversuche bleiben ungültig. Diagnose und genaue
Grenzen: [OAK-Stabilitätsprüfung](OAK4_STABILITY_2026-11-13.md).

## Ein Foto aufnehmen

Für laufendes modellbasiertes RGB-Tracking gibt es im Zellrepo den expliziten
[CPU-Objekttracker](../multi_arm_manipulation_UWA/docs/object_tracking.md) mit
1600×1200/10fps, festerOptik und tatsächlicherCameraInfo. Er teilt dieselbe
Foto-Lease; vor HQ-Fotos dessen eigenePipeline mitCtrl+C schließen. Kein
parallelerSDK-Zugriff und keine automatische UR-Bewegung.

Aus `~/UWA_ws`, auch ohne ROS-Umgebung und ohne laufenden Fotodienst:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture
```

Standardmäßig: **native8000×6000, ISO100, acht gemittelte Frames**. Die
JSON-Antwort enthält die vollständigen Bildpfade. Weitere Varianten:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode standard
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode compare
# Optional: andere Zahl der Mittelungsframes oder manuelle Empfindlichkeit.
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode hq --frames 8 --iso 100
# Konstanter manueller Fokus für eine Bildserie (RGB, tatsächlicher Readback geprüft):
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode standard --focus 116
```

Die Zell-App **UWA Camera Capture** verwendet diesen Dienst mit einem einzelnen
8K-Standardfoto, festemFokus116 und beidenrechtenWristkameras. Ihre2fps-Vorschau
(`tools/oak4_board_preview.py`,2000×1500, voller4:3-Bildausschnitt) teilt dieselbe
Dateisperre. VorFoto schließt sie die eigeneSDK-Pipeline und wartet tatsächliche
Sperrfreigabe ab; **Pause live view** gibt dieOAK fürTiefen-/andereFototools frei.
Keine fremdenDienste werden beendet. Anleitung imZellrepo:
[gemeinsame mobile Board-Aufnahme](../multi_arm_manipulation_UWA/docs/three_camera_capture.md).
Ohne `--focus` bleibt das bisherige Autofokusverhalten unverändert. Unterschiedliche
Fokuswerte nicht ungeprüft in einem Intrinsics-Fit mischen.

Für Agenten/ROS-Knoten stehen vier `std_srvs/srv/Trigger`-Services bereit:

```bash
source /opt/ros/lyrical/setup.bash
export ROS_DOMAIN_ID=65 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 service call /oak4/photo/capture_hq std_srvs/srv/Trigger '{}'
ros2 service call /oak4/photo/capture_standard std_srvs/srv/Trigger '{}'
ros2 service call /oak4/photo/capture_compare std_srvs/srv/Trigger '{}'
ros2 service call /oak4/photo/status std_srvs/srv/Trigger '{}'
```

`capture_hq` und `capture_compare` verwenden ISO100/8Frames. Abweichende Werte
sind über die CLI möglich. Antworten: `success` und JSON mit Verzeichnis,
Metadatenpfad, Bildpfaden und `exposure_limited`. Fehler liefern `success=false`.
Status bleibt während der Aufnahme erreichbar (IDLE/CAPTURING/READY/FAILED).
Er zeigt den Auftragszustand, keine kontinuierliche Kamera-Erreichbarkeitsprüfung.
Der letzte Ergebniszeiger im Status ist pro Dienstlauf; Fotos bleiben nach
Neustarts erhalten. Ein Aufruf dauert typischerweise einige zehn Sekunden;
externe Clients sollten bis zu330s auf die Antwort warten können.

## Dateien und Bildverfahren

Pro Auftrag neuer Ordner, keine Überschreibung:

```
$UWA_WS/setup/oak4/photos/<Zeit>-<Modus>-<ID>/
  standard.png     # Standard/compare: Automatikfoto, natives 48-MP-PNG
  hq-single.png    # HQ/compare: ein ISO100-Foto
  hq.png           # HQ/compare: Mittelwert, ebenfalls natives 48-MP-PNG
  metadata.json    # tatsächlich gemeldete Einstellungen und Frame-IDs/-Zeiten
  capture.log      # SDK-Ausgabe/Diagnose
  result.json      # nur bei erfolgreicher vollständiger Transaktion
  failure.json     # bei fehlgeschlagenem Auftrag
```

SDK-Worker separat unter `.venvs/oak4`, aktuell DepthAI3.12.0. IP und erwartete
Geräte-ID kommen bei jedem Aufruf aus
`src/multi_arm_manipulation_UWA/config/hardware_inventory.yaml`, nicht aus einer
zweiten Netzwerkkonfiguration. `oakctl run-script` richtet die SDK-Verbindung ein;
keine Zugangsdaten werden in Quellcode/Logs/Dokumentation hinterlegt.

1. 48-MP-Sensor mit **10fps**, fünf Sekunden Automatik-Einlauf. Die volle
   Auflösung wird nur auf Anforderung übertragen, kein permanenter48-MP-Stream.
2. Autofokusstellung auslesen und festsetzen, Weißabgleich sperren. Beide
   Einstellungen bleiben innerhalb des Auftrags für Standard/HQ gleich.
3. Standardbelichtung messen. Für HQ ISO100 setzen und die Belichtungszeit
   anhand von Belichtungszeit×ISO auf ähnliche Helligkeit einstellen; tatsächlichen
   Readback prüfen und bis zu dreimal korrigieren. Bereich100–90000µs.
4. Acht verschiedene Frames bei denselben tatsächlichen ISO-/Belichtungs-/
   Fokus-/Weißabgleichswerten mitteln. Volle Auflösung und eindeutige, steigende
   Frame-IDs prüfen. Kontrolle bei Abweichung abbrechen.
5. Automatik wieder aktivieren und die eigene temporäre Pipeline schließen.
   Vorhandene Kalibrierdateien und Geräteeinstellungen im Flash bleiben erhalten.

Mittelung erfolgt in ISP-dekodiertem8-Bit-BGR, Ausgabe verlustfreiesPNG. Das ist
kein Sensor-RAW/HDR und keine garantierte Verbesserung von Geometriegenauigkeit.
**Kamera und Szene müssen während des gesamten Bursts stillstehen**; keine
Bewegungskompensation, bewegte Arme können Doppelkonturen verursachen. Der
Fotodienst bewegt keine Roboter und prüft keinen Roboterstillstand. Fokus wird
je Auftrag neu per AF bestimmt; diese Fotos nicht ungeprüft mit Kalibrierungen
für andere Fokusstellungen kombinieren. Gerätezeitstempel sind monoton, nicht
mit ROS-/Wanduhr synchronisiert. Falls90ms bei ISO100 nicht ausreichen, kann HQ
zu dunkel bleiben: `exposure_limited=true`, tatsächliche Differenz in EV im JSON.

## Dienst verwalten und erneut installieren

```bash
# Bestehende Laufzeit prüfen/bei Bedarf herstellen:
bash src/oak_camera_calibration/tools/setup_oak4.sh
# Installiert/aktiviert den Benutzerdienst und startet ihn:
bash src/oak_camera_calibration/tools/oak4_photo.sh install
bash src/oak_camera_calibration/tools/oak4_photo.sh status
bash src/oak_camera_calibration/tools/oak4_photo.sh logs
bash src/oak_camera_calibration/tools/oak4_photo.sh stop
bash src/oak_camera_calibration/tools/oak4_photo.sh start
```

Installation ist lokal unter `~/.config/systemd/user/uwa-oak4-photo.service`;
keine ROS-Neubaupflicht für diese quellbasierten Werkzeuge. `.venvs/oak4` und
`setup/oak4/bin/oakctl` werden durch das vorhandene Setup bereitgestellt; nicht
vom temporären Codex-Chatverzeichnis abhängig. Kein Kamerafirmwareupdate nötig.

SDK, ROS-Livestream und Kamerapps benötigen exklusiven Zugriff. Ein laufender
`uwa-oak4-live.service` wird vor Aufnahme abgewiesen. Andere Kamera-Nutzer
gezielt schließen, wenn ein SDK-Belegungsfehler entsteht; der Fotodienst stoppt
keine fremden Prozesse. Gleichzeitige eigene Fotoanfragen werden mit einer
Thread- und dateibasierten Sperre abgewiesen (auch CLI gegenüber ROS-Dienst).
Worker-Laufzeit begrenzt auf300s; bei Timeout eigenen Worker-Prozessbaum beenden,
Sperre freigeben und Fehlerartefakte erhalten. Einzelbildtimeout30s. Fehlerbilder
nicht als erfolgreiche Aufnahme übernehmen.

## Prüfnachweis, 2026-11-12

Installierten Dienst mit echtem `capture_compare` erfolgreich geprüft:
`setup/oak4/photos/20261112-135950-compare-cf3a4ee9/`. Alle drei PNGs intakt,
je8000×6000. Standard ISO309/16666µs; HQ ISO100/51498µs, Fokus107/WB4138K
identisch. Acht unterschiedliche Frames, Sequenzen115,151,157,163,168,173,178,183.
Status währenddessen CAPTURING erreichbar; paralleles Foto korrekt abgewiesen;
danach READY. Keine Aussage über unveränderte Szene während der parallelen
Arbeit anderer Agenten. Sechs automatisierte Tests für ungültige Anfragen,
Thread-/Prozesssperre, Erhaltung des Live-Dienstes, Workerfehler und Timeoutcleanup:

```bash
python3 -m unittest discover -s src/oak_camera_calibration/test -p test_oak4_photo_service.py -v
```

Regulären HQ-Endpunkt nach abschließendem Dienstupdate separat erfolgreich
geprüft: `setup/oak4/photos/20261112-140403-hq-f3cec77a/`, ISO100,
acht unterschiedliche native48MP-Frames, `exposure_limited=false`.
