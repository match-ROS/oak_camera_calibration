# OAK-Kamera: Arbeitsregeln

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
