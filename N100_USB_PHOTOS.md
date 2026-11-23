# USB-OAK am N100: native Fotos und Ausrichtung

Stand23.11.2026. Physische **OAK-D Pro AF**, USB-ID`18443010314F3B1300`,
RVC2/IMX378. Von der Ethernet-OAK4 mitID1479883285 getrennt. Nutzer hat sie
am zweiten Tisch gegenüber der OAK4 montiert; Ziel sind beide festen
Tischboards und der gemeinsame Arbeitsraum.

## Gemeinsame Aufnahme-GUI

Die **UWA Camera Capture** öffnet im interaktiven Sechskamera-Modus einen
dauerhaften USB-Stream am N100. Der Worker `tools/usb_oak_board_stream.py`
nutzt die USB-Kamera mit Fokus 112, nativen 4056×3040 Pixeln und gemeinsamer
`~/uwa-camera/.camera.lock`. Die Vorschau mit 1280×960 entsteht aus den
laufenden Vollbildern. Bis zum Klick hält der Worker Bilder nur im RAM.

**Capture** wählt das nächste native Bild, dessen Belichtung nach Eingang
der Anforderung am N100 beginnt. Die GUI erhält die Bildbestätigung, während
der Hintergrund das PNG verlustfrei kodiert und über die bestehende SSH-Verbindung
nach ROSmini überträgt. `image.png`, die Vorschau und die Metadaten liegen im
Aufnahmeordner. Nur die Bildschirmanzeige wird um 180° gedreht. Am Sitzungsende
vergleicht der Worker die gelesene Werkskalibrierung, schließt die Kamera und
gibt die Lease frei. Das eigenständige Einzelbildwerkzeug ist unten beschrieben.

Am 23.11. wurden in derselben echten Sitzung zwei Fotos gemessen. Der einmalige
Start bis zur ersten Vorschau dauerte 6,42 s. Vom Auftrag am Arbeitsplatz bis
zur Bestätigung des frischen Bilds vergingen 0,84 und 0,81 s, bis zur lokal
gespeicherten Aufnahme mit Metadaten 3,04 und 2,95 s. Der Sensor begann die
Belichtung 0,28 und 0,24 s nach dem jeweiligen Auftragseingang am N100.
Der USB-Link lief dabei mit USB 2.0. Nach beiden Bildern lief die Vorschau
weiter, am Ende wurde die Freigabe der Kamera-Lease geprüft.
[Messung](../../setup/calibration/mobile_volume_20261123/usb-stream-mg8zkgy2/summary.json)

## Aufnahme

Wiederverwendbares Werkzeug `tools/usb_oak_photo.py`, installiert auf N100
unter `~/uwa-camera/usb_oak_photo.py`. Nutzt dieselbe
`~/uwa-camera/.camera.lock` wie SDK-Test und USB-ROS-Start; keine fremden
Kameranutzer stoppen. Kein Kamera-Autostart, keine UR-Befehle/IR-Aktivierung
oder EEPROM-/Firmware-Schreiboperationen.

Aus dem Workspace:

```bash
ssh -F setup/n100/ssh_config uwa-n100-robot-lan \
  '~/uwa-camera/.venv/bin/python ~/uwa-camera/usb_oak_photo.py --focus 126 --output ~/uwa-camera/results/EINDEUTIGE-ID'
scp -r -F setup/n100/ssh_config \
  uwa-n100-robot-lan:uwa-camera/results/EINDEUTIGE-ID setup/n100/ros-camera/captures/
```

Der Ausgabeordner muss neu sein. Ohne `--focus` verwendet das Werkzeug die
ausgelesene Fokusposition der Werkskalibrierung (derzeit126). Optional
`--focus-values 96 112 128 144 160 176` für eine separate native Suchreihe;
höchstens12 Werte, Fokus-Readback jeweils bestätigt. Die Suche ist kein
Beleg einer jeweils passenden Intrinsics-Kalibrierung.

Dateien: `native.png` in voller4056×3040-Auflösung, `preview.jpg` als
verkleinerte Anzeige, `metadata.json` mit tatsächlichen Settings und SDK-K/D,
`factory-calibration.json` als Lesebackup. Suchreihe zusätzlich `focus-*.png`.
Factory-Hash vor/nach Aufnahme muss gleich sein. Kamera schließt nach dem
Auftrag; keine dauerhafte SDK-Sitzung. N100 macht nur Kamera-I/O; Bildanalyse
am Arbeitsplatz. Der erste heutige Link meldete USB`HIGH` (USB2); frühere
USB3/SUPER-Messungen sind historische Anschlussstände. Die native Bildgröße
ist trotzdem bestätigt, kein aktueller Durchsatz-Maximalnachweis.

## Orientierung und Kalibrierung

Erster Autofokusversuch23.11. meldete0 und war stark unscharf. Fest126 ist
deutlich schärfer, aber die kleinen Markermuster sind noch weich. Eine gute
Fokusstellung muss vor einer präzisen Poseberechnung gewählt und mit passenden
Intrinsics dokumentiert werden. SDK-/Factory-K/D nicht ungeprüft als unabhängig
validierte Optik bei beliebigem Fokus ausgeben.

Ausgangsbild zeigt viel Hintergrund oben und den nahen Tisch unten nur
angeschnitten. Vorschlag zur ersten physischen Korrektur: ungefähr15–20°
weiter nach unten auf die Mitte zwischen beiden Boards neigen, seitliche
Ausrichtung zunächst beibehalten. Winkel ist eine Bildbeurteilung, kein
vermessenes Montageziel. Nutzer richtet selbst aus; erst nach fester Montage
neu aufnehmen. Danach Sicht/Schärfe beider IDs prüfen, erst anschließend
Extrinsics zu den übernommenen festen Board-/Basisbezügen bestimmen.
Keine vorhandene OAK4-Registrierung durch diese zweite Kamera ersetzen.

Nutzer hat die Kamera anschließend steiler nach unten und dafür kopfüber
montiert. Das ist geometrisch zulässig: die neue Extrinsics-Schätzung muss
die tatsächliche Montage enthalten. Rohbilder bleiben in der Sensororientierung
für Detektion/Kalibrierung erhalten. Eine zusätzlich180° gedrehte Anzeige ist
als solche zu kennzeichnen und darf nicht mit den unveränderten Rohbild-K/D
als neue Messaufnahme verwechselt werden. Keine Stereo-Sockets vertauschen.

Erste Suchreihe der ummontierten Kamera:112 ist unter den geprüften Werten
deutlich besser als126; rechts17Marker/24Ecken, links13Marker/17Ecken.
Das nahe/linke Board ist unten noch angeschnitten; weitere ungefähr5° nach
unten wurden vorgeschlagen. Fokus112 ist eine Aufnahmeempfehlung, noch kein
eigenes Intrinsics-Profil. Dataset
`setup/n100/ros-camera/captures/20261123-remounted-inverted-focus-scan-01/`:
`focus-evaluation.json` dokumentiert die unveränderten Raw-Koordinaten,
`display-view.json` die180°-Anzeige. Vorher-/Nachher-Factoryhash unverändert.

Nach weiterer Neigung: `20261123-remounted-inverted-final-view-01` zeigt
beide festen Boards vollständig mit Rand, je17Marker/24Ecken bei112.
Diese Orientierung wurde als zunächst passend beurteilt. Das separate
Robotiq-Schachbrett erzeugte eine falsche doppelte Marker-ID außerhalb des
festen Boards; rechts wurde daher der tatsächlich beobachtete Boardausschnitt
ausgewertet. Raw-Koordinaten/ROI sind in `board-check.json` dokumentiert.

Erste Artefakte am Arbeitsplatz:
`setup/n100/ros-camera/captures/20261123-mounted-native-{01,focus126}/`.
