# OAK4-Einrichtung und Live-/Grenztests

Stand: 2026-11-09, Australia/Perth. Status: **Host eingerichtet, echte Streams
und Extremprofile erfolgreich getestet**.

## Nutzerauftrag

Eine per Ethernet angeschlossene Luxonis OAK4-D auf dem Ubuntu-26.04-Rechner
einrichten; vorhandenen Code in diesem Repository berücksichtigen. Ein Livebild
öffnen und getrennt maximale Auflösung, maximale Bildfrequenz, Tiefendaten mit
höchster Qualität sowie mit höchster Geschwindigkeit untersuchen. Gewünschte
Extrema sind Prüfaufträge, noch keine bestätigten Leistungswerte.

## Ausgangslage

- ROS 2 Lyrical vorhanden; DepthAI-ROS-Pakete Version 3.4.0 installiert.
- Alter Repository-Code erwartet teils `depthai_ros_driver_v3`, Jazzy und
  `~/colcon_ws`; lokal heißt das installierte Treiberpaket `depthai_ros_driver`.
- Alte GUI begrenzt RGBD auf 1920×1080 / 15 Hz. Das ist eine damalige
  Stabilitätsentscheidung dieser GUI und kein ermitteltes OAK4-Hardwarelimit.
- Ethernet-Hostadresse zu Beginn 192.168.8.243/24 auf `enp87s0`, Internetroute
  über 192.168.8.1. Bestehende Verbindung nicht für die Kamera ersetzen.
- Der Auftrag betrifft nur Kamera und Hostsoftware; keine Roboterbewegungen.

## Einrichtung und Ergebnis

- OAK-Agent: OAK4-D R9, IP **192.168.8.238**, Luxonis OS **1.32.1**, Agent0.20.0.
  DepthAI identifiziert dasselbe Gerät als OAK-4-PRO / RVC4. RGB IMX586,
  Stereo OV9282. Link auf `enp87s0` **2500 Mbit/s**; Netzwerkroute erhalten.
- `setup/oak4/bin/oakctl` **0.31.1** aus offizieller Luxonis-Quelle installiert.
  Discovery und Geräteinfos erfolgreich. Kein Geräte-Reset/Firmware-Update.
- `.venvs/oak4`: Python3.14.4, DepthAI3.12.0, opencv-python5.0.0.93,
  numpy2.5.4. Venv mit `--without-pip` und offiziellem get-pip aufgebaut,
  weil systemweites ensurepip fehlt. ROS-/System-Python unverändert.
- Livefenster über OpenCV / eigenen Benutzerdienst **uwa-oak4-live** erfolgreich;
  RGB-Vorschau ungefähr30fps. Nur dieser Dienst wird vom Helfer ersetzt/gestoppt.
  Sauberer SIGINT-Stopp mit erfolgreicher Messdatei und anschließender Neustart
  geprüft. Fehlenden gebündelten Qt-Schriftpfad nach cv2-Import auf Systemfonts
  korrigiert. Zuletzt bleibt die RGB-Vorschau geöffnet; ROS-Testprozesse beendet.
- Wiederholbares Setup: `tools/setup_oak4.sh`, gepinnte SDK-Abhängigkeiten,
  `tools/oak4.sh` für Live/Test/Stop/Status. Kein globaler pip-Eingriff.
- DepthAI-WHEEL hat Leerzeile vor unterstützten Plattform-Tags; `pip check`
  meldet deshalb irreführend unsupported platform. Native Imports und alle
  Hardwaretests funktionieren; keine installierte Metadatei verändert.
- Alte Launch-Dateien und Paketmanifest verwenden jetzt `depthai_ros_driver`.
  Historische Hand-Eye-TFs erhalten; neuer neutraler Standalone-Start
  `oak4_ethernet.launch.py` mit `config/oak4_ethernet.yaml`.
- Paket mit Lyrical erfolgreich gebaut. ROS-RGB und Tiefe plus je CameraInfo
  tatsächlich empfangen. Nicht ausgerichtete Stereo-Tiefe benötigt ausdrücklich
  `stereo.i_board_socket_id: 2`, sonst benennt Treiber3.4.0 sie fälschlich RGB.
  `i_aligned: false` ist der gültige Parameter, nicht `i_align_depth`.
  Testdomain65 und lokale Discovery; keine Roboter-Hardware gestartet.

## Echte Leistungsmessungen

15s nach4s Warmup, ohne GUI, IR aus, Kamera sehr nah am Tisch / vor heller Wand.
Lokale vollständige JSONs/Logs/PNG/JPEG unter `~/UWA_ws/setup/oak4/measurements/`;
keine privaten Bilder ins Git übernehmen. Profile und Interpretation siehe
[OAK4_ETHERNET.md](OAK4_ETHERNET.md).

| Profil | Am Host | Empfang |
|---|---|---:|
| RGB volle Auflösung, 4fps angefordert | 8000×6000 NV12 | 3,99fps |
| RGB schnell, Sensor720p@480 | 320×180 NV12 | 476,10fps |
| RGB Sensor1080p@240 | 640×360 NV12 | 239,56fps |
| Stereo ACCURACY + Softwarefilter | 1280×800 mm | 25,48fps |
| Stereo HIGH_DETAIL + extended + Filter | 1280×800 mm | 25,34fps |
| NeuralDepth EXTRA_LARGE | 1248×780 mm | 10,15fps |
| Stereo FAST_DENSITY | 640×400 mm | 59,98fps |
| Stereo FAST_DENSITY volle Größe | 1280×800 mm | 44,88fps |

- Keine Behauptung, dass480 vollständige720p-Bilder/s am PC ankommen: hohe
  FPS-Tests verkleinern die Ausgaben und nutzen beschnittene HFR-Sensormodi.
- Sensor meldet48MP bis18,9fps,720p bis480,42fps,1080p bis240,18fps;
  Stereo-Sensoren maximal60fps. Sensor- und Übertragungsgrenzen trennen.
- 48MP@4fps erreicht knapp295MB/s Nutzdaten. Erfolgreicher Betriebspunkt,
  keine abschließend bewiesene Transportobergrenze. Standardprofil jetzt4fps.
- Nur etwa11% gültige Pixel im strengen klassischen Tiefenprofil,35% beiNeural,
  99% im schnellen Profil. Szene teils unterhalb Nahgrenze/strukturarm.
  Punktdichte ist kein Genauigkeitsnachweis; keine vermessene Referenz vorhanden.
- Im letzten ROS-Test ohne RGB-Ausrichtung RGB ca19,6fps und Stereo ca29,5fps
  gemessen; ROS-Treiber3.4.0 nutzt nicht denselben expliziten HFR-Sensormodus
  wie die SDK-Tests. Keine ROS-Maximalleistungsbehauptung daraus ableiten.
  RGB- und Stereo-CameraInfo stimmen jeweils in Dimensionen und optischen Frames
  mit ihren Bildern überein. `measurements/ros-preview.json` enthält Endstand.

## Bedienung und spätere Arbeit

- Nutzerfrage vom2026-11-09: Graustufen für höhere Kombination aus Auflösung/FPS
  und Global-Shutter-Verfügbarkeit. Herstellerabgleich: IMX586 ist Rolling
  Shutter; beide OV9282 sind echte Mono-/Global-Shutter-Sensoren, auf RVC4
  derzeit1280×800@60fps (bestätigt auch durch lokale Sensorabfrage). Der
  Farbsensor lässt sich durch Graustufenkonvertierung nicht auf Global umstellen.
- Geräteinterne GRAY8-Ausgabe/Konvertierung spart Übertragungsdaten, erhöht
  aber nicht die Sensor-Auslesegrenzen. GRAY8 hat1Byte/Pixel gegenüber1,5 bei
  dem bisher getesteten NV12, also theoretisch bis1,5-fache Transportkapazität,
  nicht3-fach. Erst am Host konvertieren spart keine Ethernet-Bandbreite.
  48MP@etwa6fps statt4fps ist nur eine Bandbreitenabschätzung; kein gemessener
  GRAY8-Betriebspunkt. Für diese Rückfrage keine Kamera-/Livestream-Unterbrechung
  und kein zusätzlicher Leistungsnachweis durchgeführt.
- Quellen: https://docs.luxonis.com/hardware/products/OAK%204%20D ,
  https://docs.luxonis.com/hardware/sensors/IMX586 ,
  https://docs.luxonis.com/hardware/sensors/OV9282 ; GRAY8-Konvertierung im
  offiziellen DepthAI-v3-FeatureTracker-Beispiel über ImageManip dokumentiert.

- Einstieg/Bedienung: [README.md](README.md), Details [OAK4_ETHERNET.md](OAK4_ETHERNET.md).
- Nach Tests RGB-Livebild wieder geöffnet. SDK und ROS können dasselbe Gerät
  nicht gleichzeitig exklusiv verwenden. `oak4.sh live` ersetzt nur eigenes SDK-
  Fenster; fremden ROS-Treiber vorab gezielt beenden.
- Für belastbare Tiefengenauigkeit später ebenes vermessenes Ziel, definierte
  Distanzen, Bewegung/Beleuchtung und optional IR-Projektion vergleichen.
  Aktuelle Tests verwenden IR aus; keine IR-Optimierung oder Langzeitlastprüfung.
- Bestehende MuR-GUI und Hand-Eye-/Roboterfunktionen sind damit nicht vollständig
  auf Lyrical portiert/geprüft. Diese Aufgabe testete ausschließlich Kamera.
