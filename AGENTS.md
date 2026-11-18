# OAK-Kamera: Arbeitsregeln

- HDR seit18.11. auf Geschwindigkeit optimiert: native48MP/Mertens und
  Belichtungsstufen erhalten; Metadaten aus ImageManip desselben8K-ISP-Outputs,
  keine zweite Camera-Ausgabe im8K-Modus. Controls anhand kleiner Vorschau
  und zusätzlich jedes Vollbilds bestätigen; begrenzter Einlauf/Timeout,
  keine blinde Übernahme unbestätigter Belichtungen. Fusion aus RAM,
  parallele verlustfreie PNG-Level1-Archive. Timing pro Phase in metadata.json;
  Transaktions-Lease bis zum vollständigen Ergebnis halten. OAK4_PHOTOS.md.

- Optionaler HDR-Fotomodus seit17.11.: bestehenden Fotopfad `capture --mode hdr`
  nutzen; drei native Belichtungsstufen −2/0/+2EV bei festem ISO/Fokus/WB,
  Originalstufen erhalten. Mertens-Ausgabe ist ISP-Belichtungsfusion als8-Bit-PNG,
  kein radiometrisch kalibriertes RAW-HDR. Kamera/Szene statisch, keine
  Bewegungskompensation. Real am17.11. mit ISO100/400 geprüft: ISO100 kann die
  Basis wegen90ms-Grenze abdunkeln; ISO400 passt hier zur vollständigen Reihe,
  Schattenrauschen bleibt sichtbar. Kein pauschaler Qualitätsgewinn gegenüber
  HQ. Bestehendes HQ und gemeinsame Kamera-Lease erhalten. OAK4_PHOTOS.md.

- Gemeinsame RGB-D-Aufnahme seit16.11.: vorhandenes Fototool `capture --mode rgbd`,
  Anleitung OAK4_RGBD.md. ImageAlign auf entzerrtes RGB1280×960, tatsächliche
  Ausgabe-K/Zeiten/Masken sichern, gemeinsame Foto-Lease erhalten. Stereo bleibt
  nativ1280×800; Ausgabegröße nicht als höhere Tiefenauflösung ausgeben.
  Erste8Paare real geprüft; geometrische Genauigkeit/Objektpose noch offen.
  Offline-Boardprüfung16.11.: Prüf-RMS≤0,323px, aber SDK-Z gegen RGB-Boardebene
  etwa+11mm; Ursache/absolute Genauigkeit offen. Nicht pauschal korrigieren oder
  als Millimetergenauigkeit ausgeben. Details OAK4_RGBD.md, board-check-v1/.
  Mobiles Brett separat mit38mm/IDs75–91 auswerten; Nutzer-Linealmessung
  5Felder191mm am16.11. nur als unsichere Sensitivitätsannahme erhalten,
  nicht stillschweigend als globale38,2mm-Definition oder Tiefenkorrektur setzen.

- CPU-Objekttracking seit13.11. ist ein expliziter Kamera-only-Nutzer der
  bestehenden Foto-Lease. Opt-in-Stream1600×1200/10fps/Fokus116; eigeneWorker
  sauber schließen, keine konkurrierenden Kamerasitzungen stoppen. Bestehende
  GUI-Vorschau bleibt2000×1500/2fps. Ausgabe-K direkt aus Frame-Transformation,
  Factory-D und SDK-Bildalter erhalten; keine UR-Zeitsynchronisation behaupten.
  Zell-Anleitung docs/object_tracking.md; keine Armbewegung aus Tracking.

- Verifizierter Stand seit13.11.2026: OAK4-D R9/1479883285, LuxonisOS1.47.0,
  Agent0.28.0 und HostSDK3.12.0. Ausdrücklich freigegebenes OTA; Factorybackup
  identisch,15nativeStartzyklen plus kompletter stationärer Fünfkamera-Satz PASS.
  Details und Grenzen: OAK4_STABILITY_2026-11-13.md / HANDOVER.md.


- Wiederholbarer nativer Start-/Foto-Check: `tools/oak4_photo.sh check --count 3 --focus 116`.
  Bei erstem Fehler Ende, kein automatischer Reset/Update. Ein kurzer PASS nach
  Neustart ist keine dauerhafte Stabilitätsfreigabe. Rohdaten und Fehlerflags
  erhalten; laufende Kamerasitzungen/Dateisperren vor weiteren Tests beachten.


- Seit2026-11-12: Zell-App **UWA Camera Capture** nutzt bestehendenFotodienst
  mit `--mode standard --focus 116` (ein8K-Frame,keineHandheld-Mittelung).
  EigeneSDK-Vorschau `tools/oak4_board_preview.py` teilt `.capture.lock`;
  Wrapperende ist noch kein Nachweis der SDK-/Dateisperrfreigabe. Eigene
  Pipeline schließen und Freigabeabwarten, fremdeKameranutzererhalten.


## Vorhandener statischer HQ-Tiefenmodus (2026-11-12)

- HQ-Snapshot in RViz: `bash src/oak_camera_calibration/tools/oak4_photo.sh view-depth`
  aus Workspace. Eigene Domain65-Ansicht, Standardwolke optional; Datum/STATIC
  sichtbar, keine Kameraoffenhaltung und kein world-/Zelltransform. Nur Aufnahmen
  mit tatsächlicher rektifizierter `projection.K` anzeigen, keine Factory-K raten.

- Für statische Tiefenschnappschüsse den bestehenden Fotodienst verwenden:
  `bash src/oak_camera_calibration/tools/oak4_photo.sh capture --mode depth_hq`
  aus Workspace; ROS `/oak4/depth/capture_hq`, Trigger, Domain65/LOCALHOST.
- Native1280×800-Mono-Stereo,16Frames/Median mit Gültigkeits-/Stabilitätsmasken,
  keine Lochfüllung, Rohframes/Metadaten in `setup/oak4/depth/`. Belichtung/Gain
  beider Monos gehalten; RGB-ISO100 nicht als Tiefeneinstellung behaupten.
- Teilt Kamera-/Transaktionssperre und Dienst `uwa-oak4-photo.service` mit RGB.
  Kamera/Szene stillhalten, keine Roboterfahrten auslösen. Weniger Streuung ist
  kein Genauigkeitsnachweis; Maskierung kann die gültige Fläche verringern.
- Anleitung: OAK-Repo `OAK4_DEPTH.md` (Aufruf/Format/Grenzen/echte Prüfergebnisse).

## Wiederverwendbarer HQ-Fotodienst (2026-11-12)

- Für neue Standard-/HQ-/Vergleichsfotos den vorhandenen [Fotodienst](OAK4_PHOTOS.md)
  verwenden, keine neuen Einmalskripte im Chatverzeichnis anlegen.
- Einstieg aus Workspace: `bash src/oak_camera_calibration/tools/oak4_photo.sh capture`.
  ROS: `/oak4/photo/capture_hq` (Trigger), Domain65/LOCALHOST; weitere Modi/Status
  stehen in der Anleitung. Benutzerdienst `uwa-oak4-photo.service` wartet idle
  ohne Kamera; öffnet sie nur pro Foto. Laufzeit `.venvs/oak4`/`setup/oak4/bin/oakctl`.
- Native8000×6000, Sensor10fps und gegatete Einzelbilder; HQ ISO100, max90ms,
  acht Frames, fester Fokus/WB je Auftrag. Kein ungeprüfter1fps-Sensormodus.
- Bilder/Metadaten unter `setup/oak4/photos/`, keine privaten Fotos insGit.
  SDK-/ROS-Livenutzer exklusiv behandeln, keine fremden Dienste automatisch stoppen.
  Kamera/Szene stillhalten; kein bewegungskompensierter oder RAW-Kalibriermodus.

- Übergeordnete Regeln in `~/UWA_ws/AGENTS.md` beachten; Kommunikation auf Deutsch.
- Ziele, Profilentscheidungen, Gerätegrenzen, Messwerte und offene Punkte parallel
  in `HANDOVER.md` dokumentieren. Vorhandene Kalibrierungen und Nutzerdateien erhalten.
- Plattform dieses Rechners ist ROS 2 Lyrical / Ubuntu 26.04. Alte Jazzy-/
  `colcon_ws`-Beispiele sind historisch und vor Nutzung an die lokale Installation anzupassen.
- Auftrag vom 2026-11-09: echte Ethernet-OAK4 erkennen, fehlende Hostsoftware
  einrichten, Livebild sowie maximale Auflösung/FPS und Tiefe Qualität/Tempo testen.
- Kameratests erteilen keine Freigabe für UR-Bewegungen, Jogging oder automatische
  Hand-Eye-Sitzungen. Dafür weder Hardware-Roboter starten noch deren Parameter ändern.
- Gerätetyp und tatsächliche Sensorfähigkeiten abfragen; Modellnamen aus alten
  Launch-Dateien und GUI-Grenzen nicht als gemessene Hardwaregrenzen behandeln.
- Sensor-FPS, Pipeline-Ausgaberate und am Host empfangene FPS unterscheiden.
  Einstellungen und gemessene Ergebnisse pro Profil getrennt dokumentieren.
- Bestehende Netzwerkrouten/Internetverbindung erhalten. Firmware-Updates oder
  Gerätezurücksetzungen nicht als unbemerkte Nebenwirkung einer Treiberinstallation ausführen.
- Keine Passwörter, Tokens oder private Kamerabilder in Git aufnehmen.
