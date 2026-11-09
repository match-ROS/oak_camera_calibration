# OAK4-D: Einrichtung, Livebild und Grenztests

Geprüft am **2026-11-09** auf Ubuntu 26.04 / ROS 2 Lyrical. Alle nachstehenden
Messwerte stammen von der angeschlossenen Kamera, nicht aus einem Datenblatt.

## Gerät und installierte Software

- Ethernet: `192.168.8.238`, Host `enp87s0`, 2,5-Gbit/s-Link. Die vorhandene
  Internetroute bleibt erhalten. Die IP kann sich bei anderer DHCP-Vergabe ändern.
- Geräte-Agent meldet **OAK4-D R9**, DepthAI meldet **OAK-4-PRO**, Plattform RVC4.
- Luxonis OS **1.32.1**, Agent **0.20.0**. Kein Firmware-Update durchgeführt.
- RGB: IMX586 mit Autofokus, 8000×6000; Stereo: zweimal OV9282, 1280×800.
- Offizielles `oakctl` **0.31.1** unter `~/UWA_ws/setup/oak4/bin/oakctl`.
- Isolierte Python-3.14-Umgebung `~/UWA_ws/.venvs/oak4`: DepthAI **3.12.0**,
  OpenCV-Python **5.0.0.93**, NumPy **2.5.4**. System-/ROS-OpenCV bleibt separat.
- Native ROS-Pakete `depthai_ros_driver` / `depthai_bridge` **3.4.0** bereits
  vorhanden. Die alten Launch-Verweise auf `depthai_ros_driver_v3` wurden angepasst.
- Für die Ethernet-Verbindung ist kein zusätzlicher USB-/Kernel-Treiber nötig.

Wiederholbare Host-Einrichtung (benötigt Internet, kein ROS- oder Geräte-Update):

```bash
cd ~/UWA_ws
bash src/oak_camera_calibration/tools/setup_oak4.sh
setup/oak4/bin/oakctl list --all --format json
setup/oak4/bin/oakctl device info -d 192.168.8.238 --format json
```

Die Paketversionen stehen in `tools/requirements-oak4.txt`. Bei DepthAI 3.12.0
steht in der gelieferten WHEEL-Metadatei eine Leerzeile vor den Plattform-Tags.
Dadurch meldet `pip check` hier irreführend „not supported on this platform“,
obwohl ein passender CPython-3.14-Tag und funktionierende native Bindings
vorliegen. Der Setup-Helfer prüft deshalb die nativen Imports; die
Hersteller-Metadaten werden nicht verändert.

## Livebilder und Bedienung

Aus `~/UWA_ws`:

```bash
# Farbbild, kontinuierlich, Empfang ungefähr 30 fps
bash src/oak_camera_calibration/tools/oak4.sh live --profile rgb_preview

# Qualitätsorientierte neuronale Tiefe, größtes Modell
bash src/oak_camera_calibration/tools/oak4.sh live --profile depth_neural_quality

# Schnelle Tiefe
bash src/oak_camera_calibration/tools/oak4.sh live --profile depth_fast

# Prozessstatus / sauber stoppen
bash src/oak_camera_calibration/tools/oak4.sh status
bash src/oak_camera_calibration/tools/oak4.sh stop
```

Ein erneuter `live`-Aufruf ersetzt nur den eigenen Dienst `uwa-oak4-live`.
Fenster schließen oder **Q / Esc** beendet den Stream ebenfalls. Die Darstellung
wird auf höchstens 15 Aktualisierungen/s begrenzt; die Empfangsrate wird separat
gemessen und eingeblendet. Das volle 48-MP-Bild wird nur für die Anzeige verkleinert.
Tiefenfarben entsprechen einem festen Bereich 0–5 m; schwarze Pixel sind ungültig,
Farben am oberen Ende können auch Entfernungen über 5 m bedeuten.

SDK und ROS-Treiber benötigen exklusiven Zugriff: Vor einem ROS-Start den
SDK-Livestream stoppen, vor SDK-Tests den eigenen ROS-Kamerastart mit Ctrl+C beenden.
Die Kalibrier-/Jogging-GUI ist für diese Standalone-Tests nicht erforderlich.

## Gemessene Profile

Je Profil ungefähr 15 Sekunden Messzeit nach 4 Sekunden Einlaufzeit, ohne
GUI-Rendering. Aktuelle Tisch-/Wandansicht, vorhandene Raumbeleuchtung, IR aus.
Das sind kurze Funktions-/Durchsatztests unter der aktuellen Rechnerlast.

| Profil | Sensor / Anforderung | Tatsächlich am PC | Empfang |
|---|---|---|---:|
| `rgb_full` | 8000×6000 @ 18 fps; Ausgabe 4 fps | 8000×6000, NV12 | **3,99 fps** |
| `rgb_fast` | 1280×720 @ 480 fps | 320×180, NV12 | **476,10 fps** |
| `rgb_1080_fast` | 1920×1080 @ 240 fps | 640×360, NV12 | **239,56 fps** |
| `depth_quality` | ACCURACY, 1280×800 @ 30 fps, strenge Filter | 1280×800, uint16 mm | **25,48 fps** |
| `depth_detail` | HIGH_DETAIL, erweiterte Disparität, Filter | 1280×800, uint16 mm | **25,34 fps** |
| `depth_neural_quality` | NeuralDepth EXTRA_LARGE, Eingang 30 fps | 1248×780, uint16 mm | **10,15 fps** |
| `depth_fast` | FAST_DENSITY, 640×400 @ 60 fps | 640×400, uint16 mm | **59,98 fps** |
| `depth_full_fast` | FAST_DENSITY, 1280×800 @ 60 fps | 1280×800, uint16 mm | **44,88 fps** |

Der zusätzliche 48-MP-Test mit 3 fps lieferte 3,00 fps. Bei 4 fps lagen knapp
295 MB/s Nutzdaten an; das beansprucht den 2,5-Gbit-Link bereits stark.
**4 fps sind ein erfolgreich geprüfter Betriebspunkt, keine bewiesene absolute
Obergrenze.** Die von der Kamera gemeldete volle Sensorauflösung erlaubt bis
18,9 fps; unkomprimiertes NV12 in dieser Auflösung passt damit nicht durch diesen Link.

Die 480-/240-fps-Sensormodi verwenden einen beschnittenen Bildausschnitt.
Für die hohe Empfangsrate sind ihre Ausgaben verkleinert. **Es wurden keine
480 vollständigen 1280×720-Bilder/s am PC nachgewiesen.** Die Sequenz-/Gerätezeit
ergab im schnellen Test rund 480/s, die tatsächlich empfangenen Frames rund 476/s.
Die OV9282-Stereo-Sensoren melden auf diesem Gerät maximal 60 fps.

Qualität ist kein einzelner maximaler Zahlenwert: ACCURACY verwendet zusätzlich
Software-LR-Prüfung, räumliche/zeitliche Filter, Speckle-Filter und 5×5-Median.
HIGH_DETAIL prüft ergänzend erweiterte Disparität für nähere Objekte. RVC4 arbeitet
mit festen 4 Subpixel-Bits. Das neuronale Profil verwendet das größte verfügbare
Modell (1248×780), Confidence 125, Edge 10 und zeitliche Filterung.
FAST_DENSITY verzichtet hier auf die zusätzlichen Softwarefilter.

In dieser sehr nahen, teils strukturlosen Szene waren im letzten Bild ungefähr
11 % der strengen klassischen Qualitäts-Tiefe, 35 % der neuronalen Tiefe und
99 % der schnellen Tiefe gültig. Eine dichtere Tiefenkarte beweist keine höhere
Genauigkeit. Für einen belastbaren Genauigkeitsvergleich fehlen ein vermessenes
Ziel und definierte Arbeitsabstände; die Werte sind **keine metrologische
Qualitätsabnahme**. Das Nahfeld vor der Kamera liegt teilweise unterhalb der
nutzbaren Stereodistanz.

Profile erneut messen, optional mit Vorschau:

```bash
cd ~/UWA_ws
bash src/oak_camera_calibration/tools/oak4.sh test \
  --profile depth_neural_quality --seconds 15 --warmup 4 --preview
```

Weitere Optionen: `--ip ADRESSE`, `--output VERZEICHNIS`, `--fps RATE`.
`--fps` verändert nur die Ausgaberate, nicht den gewählten Sensormodus.
`test` stoppt vorab nur den eigenen SDK-Livedienst.

Rohmesswerte, Logs und lokale Bilder liegen unter
`~/UWA_ws/setup/oak4/measurements/`. PNG-Tiefenbilder enthalten Millimeter,
JPEG-Dateien sind reine Farbvisualisierungen. Der 4-fps-48-MP-Test liegt im
Unterordner `rgb_full_4fps/`. `summary.json` enthält nur die erste Sechser-Serie;
die zusätzlichen Profil-JSONs sind separat. Diese Aufnahmen gehören nicht ins Git.

## ROS-2-Lyrical-Start

Einmal bauen, sofern noch nicht geschehen:

```bash
cd ~/UWA_ws
source setup/lyrical_env.bash
colcon --log-base log_lyrical build --build-base build_lyrical \
  --install-base install_lyrical --packages-select oak_camera_calibration --symlink-install
```

In einem frischen Terminal:

```bash
cd ~/UWA_ws
bash src/oak_camera_calibration/tools/oak4.sh stop
source setup/lyrical_env.bash
export ROS_DOMAIN_ID=65 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 launch oak_camera_calibration oak4_ethernet.launch.py
```

Domain 65 trennt diesen lokalen Test von Zell-/MuR-Simulationen. Der Start lädt
`config/oak4_ethernet.yaml` und veröffentlicht ohne Roboteranbindung:

- `/oak/rgb/image_raw` und `/oak/rgb/camera_info`
- `/oak/stereo/image_raw` und `/oak/stereo/camera_info`

Die Tiefenausrichtung auf RGB ist absichtlich abgeschaltet; RGB und Tiefe haben
eigene optische Frames und die jeweils passende Factory-Kalibrierung. Für eine
farbige Punktwolke muss eine RGB-/Depth-Ausrichtung gesondert eingeschaltet werden.
Im abschließenden 18-Sekunden-Empfangstest kamen RGB mit 1280×720 / rund
19,6 fps und native Tiefe mit 640×400 / rund 29,5 fps an. Bild- und CameraInfo-
Frames waren jeweils konsistent (`oak_rgb_camera_optical_frame` bzw.
`oak_right_camera_optical_frame`). Messdatei: `measurements/ros-preview.json`
im oben genannten lokalen Ausgabeordner.
Ein geänderter IP-Eintrag gehört in eine Kopie des YAML, dann
`params_file:=/absoluter/pfad.yaml` beim Launch angeben.

In einem zweiten Terminal mit denselben ROS-Umgebungsvariablen:

```bash
ros2 run rqt_image_view rqt_image_view /oak/rgb/image_raw
# Für Tiefe im Topic-Menü /oak/stereo/image_raw auswählen.
```

Der ROS-Start ist ein funktionaler RGBD-Vorschaustart, kein Hochgeschwindigkeits-
Benchmark. Die Extreme werden mit den SDK-Profilen gemessen. Die historischen
Hand-Eye-TFs des MuR werden hier nicht übernommen; sie gelten nicht automatisch
für die aktuell separat aufgestellte Kamera.

## Herstellerreferenzen

- [OAK4 Inbetriebnahme](https://docs.luxonis.com/hardware/platform/deploy/oak4-deployment-guide/oak4-getting-started)
- [oakctl](https://docs.luxonis.com/software-v3/oak-apps/oakctl)
- [Camera / Sensormodi](https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/camera)
- [StereoDepth / RVC4-Filter](https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/stereo_depth)
- [NeuralDepth](https://docs.luxonis.com/software-v3/depthai/depthai-components/nodes/neural_depth)
