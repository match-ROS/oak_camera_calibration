# OAK4: Standard-, HQ- und HDR-Fotodienst

Zusätzlich seit20.11.: [ChArUco-Suchmodus](OAK4_CHARUCO_SEARCH.md) über
`capture --mode charuco` bzw. `/oak4/photo/capture_charuco`. Übersicht und
boardweise Fokus-/Belichtungssuche mit nativen Bildern/Posekandidaten;
derselbe Dienst, dieselbe Kamera-Lease.

Stand: 2026-11-18, Ubuntu26.04 / ROS2 Lyrical. Für die physische Ethernet-OAK4
(`cameras.oak4` im zentralen Zellinventar) existiert **uwa-oak4-photo.service**.
Der installierte systemd-Benutzerdienst startet bei der Benutzeranmeldung und
wartet ohne offene Kamera auf einen Auftrag. Er arbeitet in **ROS-Domain65**
mit lokaler Discovery. Die Kamera wird nach jeder Transaktion wieder geschlossen.

Der gleiche Dienst bietet zusätzlich [statische HQ-Tiefendaten](OAK4_DEPTH.md)
über `/oak4/depth/capture_hq` bzw. CLI `--mode depth_hq` an. RGB und Tiefe
verwenden eine gemeinsame Kamerasperre.

In der Sechskamera-GUI teilen Vorschau und Einzelbild eine native
8000×6000-Pipeline. Der einmalige Einlauf findet beim Öffnen der Vorschau
statt. Für die Dauer der Sitzung bleibt der Fokus auf 107 und der
Weißabgleich auf dem eingemessenen Wert. Die Belichtungsautomatik bleibt
aktiv. Auf einen Klick fordert der Worker ein neues Vollbild an und prüft
anhand des SDK-Zeitstempels, dass dessen Belichtung nach dem Trigger begonnen
hat. Die GUI erhält die Aufnahmebestätigung vor dem PNG-Schreiben.
Zeitstempel, tatsächlich gemeldete Optik und Gerätekalibrierung stehen im
Kameradatensatz. **Release cameras** und das Beenden der GUI geben die
gemeinsame Kamera-Lease frei.

Am 23.11. wurden in einer warmen Sitzung zwei native Einzelbilder geprüft.
Vom lokalen Trigger bis zum am Host bestätigten Bild vergingen 0,64 und 0,74 s,
bis zum fertigen verlustfreien PNG 2,48 und 2,83 s. Die Vorschau hatte
2000×1500 Pixel bei nominell 2 fps. Beide nativen PNGs wurden erneut
dekodiert und die Freigabe der Kamera wurde geprüft.
[Messdaten des OAK4-Einzeltests](../../setup/calibration/six_camera_speed_20261123/oak4-2gfcm6te/validation.json)

Seit16.11. zusätzlich gemeinsamer [RGB-D-CLI-Modus](OAK4_RGBD.md): `--mode rgbd`
mit entzerrter Farbe und darauf ausgerichteter, zeitlich gepaarter Tiefe.
Er nutzt dieselbe Sperre; bestehende ROS-Trigger bleiben unverändert.

## Standardfoto mit festem Fokus, 24.11.2026

`capture --mode standard --focus 107` verwendet denselben nativen
Aufnahmepfad wie die warme Sitzung. Drei fortschreitende Vorschau-Frames
mit bestätigtem Fokus und stabilen Belichtungs-/Weißabgleichsdaten bilden
den Einlauf. Nach bestätigtem Weißabgleich löst der Worker ein frisches
8000 × 6000-Foto aus und schreibt `standard.png` und `metadata.json`.
Dieser Pfad greift auch beim Standardfoto des Objekt-Scan-Bootstraps
und bei der direkten Standardaufnahme ohne laufende Capture-GUI.

Supported carton grasp startet den Worker einmal pro Run. Registrierung
und Einfahrbild nutzen dasselbe SDK-Gerät und native PNG-Ausgaben. Die
Gerätefreigabe folgt dem Einfahrbild oder dem Abbruch des Runs. Die
Vollbildbestätigung dauerte bei zwei Aufnahmen aus derselben Sitzung
je 0,66 s, das gespeicherte PNG lag nach 2,56 und 2,51 s vor.
[Messdaten](../../setup/calibration/oak_pipeline_20261124/benchmark.json)

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

### Optional: Belichtungsreihe / HDR-artige Fusion

Seit18.11. läuft `--mode hdr` automatisch über den schnelleren Pfad. Die
bewährten Einstellungen bleiben verwendbar:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode hdr --focus 107 --iso 400 --frames 2
```

Bei sechs nativen48MP-Frames wurden **18,47–19,31s statt36,18s** mit dem
vorherigen Pfad am selben Tag gemessen. Die41,07s vom17.11. sind ein früherer
Messwert unter anderer Auslastung/Beleuchtung. Kein allgemeines Laufzeitversprechen.
Auflösung, Mittelung, Belichtungsabstände und Mertens-Gewichte bleiben erhalten.

Fokusvorgabe: mindestens2s Einlauf und fünf stabile Metadatenframes;
Autofokus: mindestens5s. Belichtungswechsel warten auf bestätigte Einstellungen
anstelle fester1,5s-Pausen. Kleine Metadatenbilder entstehen über ImageManip
aus demselben8K-Ausgabestrom; jedes Vollbild wird nochmals geprüft.
Dieses Vorgehen folgt dem [offiziellen Luxonis-8K-Beispiel](https://docs.luxonis.com/software-v3/depthai/examples/camera/camera_still_max_res).

Die drei Stufen bleiben zur Fusion im RAM. Nach Schließen der Kamera werden
sie parallel zur Fusion verlustfrei als PNG gespeichert, Kompressionsstufe1
statt3; dadurch können die Dateien größer werden. Kein erneutes Einlesen.
Ein Auftrag ist erst erfolgreich, wenn HDR **und alle drei Archive** fertig
sind. Transaktionssperre bleibt bis dahin erhalten, auch wenn die physische
Kameraverbindung schon beendet ist. Im letzten Test: Kamerasitzung9,06s,
Fusion7,58s, finales PNG1,83s. `metadata.json` enthält `hdr_timing_s`; Zeiten
paralleler PNG-Schreiber nicht addieren. Nachweise:
`setup/oak4/hdr_speed_20261118/validation.json`,50Tests/17Subtests PASS.

Die folgenden Hinweise zu Verfahren und Optik gelten weiter; die historischen
Laufzeiten unten beziehen sich auf die frühere Umsetzung.

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode hdr --focus 107
# Optional zusätzlich zwei Frames je Belichtungsstufe mitteln (insgesamt sechs):
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode hdr --focus 107 --frames 2
```

Fokus107 stammt aus der vorläufigen Montageprüfung vom17.11.; kein universelles
Optimum und keine Intrinsics-Freigabe. Ohne `--focus` wird wie bisher einmal
Autofokus bestimmt und für die Reihe gehalten.

HDR nimmt drei verschiedene Belichtungsstufen **−2/0/+2EV** auf: viermal kürzer,
Basiszeit, viermal länger. ISO bleibt standardmäßig100, Fokus und Weißabgleich
bleiben fest. Metadaten bestätigen die tatsächlichen Werte jeder Aufnahme;
nicht angewandte Belichtungen/Optikänderungen führen zum Fehler. `--frames`
zählt hier **pro Stufe**, Standard1, Bereich1–8. Damit sind auch HDR und
Rauschmittelung kombinierbar. HQ bleibt der bisherige Standardmodus.

Die Basiszeit wird aus der Automatikmessung abgeleitet und auf400–22500µs
begrenzt, damit alle drei Stufen im bewährten Bereich100–90000µs bleiben.
In dunklen Szenen kann die Basis dadurch dunkler als die Automatik sein;
`exposure_difference_ev` und `exposure_limited` beziehen sich auf diese
Abweichung. Die einzelnen tatsächlichen EV-Abstände stehen in `hdr_brackets`.
Auch die längste Stufe kann bei wenig Licht noch unzureichend sein.

Ergebnisse unter `setup/oak4/photos/<Zeit>-hdr-<ID>/`:

- `hdr-short.png`, `hdr-base.png`, `hdr-long.png`: native8000×6000-Stufen,
  bei mehreren Frames jeweils deren Mittelwert; unverarbeitet durch Fusion.
- `hdr.png`: gleich großes, normal anzeigbares8-Bit-PNG, OpenCV-Mertens-Fusion.
- `metadata.json`: Einstellungen, eindeutige Sequenzen/Gerätezeiten je Frame,
  Stufen und Verfahren; `result.json` mit `images.hdr` und `brackets`-Pfaden.

Die Fusion läuft nach dem Schließen der Kamera. Sie kombiniert die
ISP-dekodierten Bilder ohne geometrische Ausrichtung/Bewegungskompensation.
**Kamera und gesamte Szene müssen stillstehen.** Bewegungen können Geisterbilder
erzeugen. Das Ergebnis ist eine Belichtungsfusion mit normalem Anzeigeumfang,
kein RAW, kein lineares HDR-Strahlungsbild und kein Genauigkeitsnachweis.
Einzelstufen bleiben für Vergleiche und spätere Auswertung erhalten.
Verfahrensgrundlage: [OpenCV HDR/Exposure Fusion](https://docs.opencv.org/5.0/py_tutorials/py_photo/py_hdr/py_hdr.html),
[Luxonis CameraControl](https://docs.luxonis.com/software-v3/depthai/depthai-components/messages/camera_control/).

CLI funktioniert sofort aus dem Quellstand. Der zusätzliche ROS-Trigger
`/oak4/photo/capture_hdr` benötigt einen neu geladenen Fotodienst
(`oak4_photo.sh restart`, nur ohne laufenden Fotoauftrag). Er verwendet
ISO100/einen Frame je Stufe und Autofokus wie die bisherigen Trigger.
Gemeinsame Kamerasperre, Domain65/LOCALHOST,300s-Workerlimit und Fehlerartefakte
gelten unverändert. Fremde Vorschauen werden nicht beendet.

Prüfung17.11.:45Tests/17Subtests mit System-Python/pytest bestanden, darunter
Belichtungsgrenzen, ignorierte Controls, Optikänderungen, HDR-Dispatch und
synthetische Struktur in hellen/dunklen Bereichen. Zusätzlich native48MP-Fusion
mit synthetischer Szene bestanden:11,80s, ca4,93GiB Spitzen-RSS auf diesem PC.
Rechen-/Speicherbedarf hängt von der Auslastung ab. Beleg:
`setup/oak4/hdr_validation_20261117/native-fusion.json` imWorkspace.
Reale Fortsetzung17.11. nach ausdrücklicher Nutzerfreigabe: bestehende
Fünfkamera-GUI regulär mit **Pause live view** pausiert; Leasefreigabe abgewartet.
HDR ISO100/ein Frame je Stufe, Standard/HQ ISO100/acht Frames und HDR ISO400/
zwei Frames je Stufe erfolgreich. Alle elf gespeicherten PNGs erneut nativ
dekodiert; ISO/Fokus/WB und eindeutige steigende Sequenzen/Gerätezeiten geprüft.

In dieser Szene war ISO100-HDR eher dunkel (Basis−1,708EV zur Automatik).
ISO400 erlaubt dagegen4531/18125/72500µs mit vollständigen −2/0/+2EV um
die gemessene Automatikhelligkeit, Fokus107/WB3896K konstant. Diese Reihe
benötigte41,07s einschließlich Fusion. Geeigneter Aufruf für diese Beleuchtung:

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode hdr --focus 107 --iso 400 --frames 2
```

Visuell werden helle Tischreflexe zurückgenommen; dunkle Bereiche zeigen weiter
Rauschen, HQ wirkt dort sauberer. HDR deshalb optional lassen, kein pauschales
Qualitätsversprechen. Der deskriptive Anteil Luma≥250 beträgt HQ0,330% und
HDR4000,046%; das allein beweist keinen größeren nutzbaren Dynamikumfang.
Getrennte Aufträge können Licht-/Szenenänderungen enthalten; keine unabhängige
Stillstands- oder geometrische Genauigkeitsprüfung.
Belege imWorkspace: `setup/oak4/hdr_validation_20261117/real-validation.json`,
`real-comparison.jpg`, `real-crops-native.jpg`. Rohdaten unter
`setup/oak4/photos/20261117-{173451-hdr-a4552d0c,173538-compare-c45d8cc8,173652-hdr-d0c5805e}/`.
Kamera danach geschlossen, unabhängiger Sperrerwerb bestätigt
(`camera-release.json`,17:38:11+08:00). GUI bleibt pausiert; **Resume live view**
aktiviert sie bei Bedarf wieder. Keine Roboterbewegung/Firmware-/Kalibrieränderung.

### Standard und HQ

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

Für Agenten/ROS-Knoten stehen `std_srvs/srv/Trigger`-Services bereit:

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
