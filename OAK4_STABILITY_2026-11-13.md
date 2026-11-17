# OAK-Verbindung: Diagnose und Wiederholungsprüfung am13.11.2026

## Ergebnis: autorisiertes Update installiert und nachgeprüft

Der Nutzer hat das angebotene Kamera-OS-Update ausdrücklich mit „ja bitte“
freigegeben. Das offizielle OTA wurde nach erneuter Identitäts-/SHA256-Prüfung
unter exklusivem Kamerazugriff installiert. Dieselbe OAK4-D R9/1479883285 meldet
jetzt **LuxonisOS1.47.0/Agent0.28.0**. Der produktive SDK bleibt3.12.0.

- Frische Werkskalibrierung vor/nach OTA exakt identisch, SHA256
  `a07141cce771738c713df4ef62f3719ed2ede411c556bc920089270cc4689eae`.
-15aufeinanderfolgende nativeStart-/Fotozyklen bestanden:8000×6000, Fokus116,
  dieselbeGeräte-ID, steigendeGerätezeit und unterschiedliche dekodierte Bilder.
- Danach kompletter abschließender Fünfkamera-Satz mit unabhängigem Stillstands-
  audit bestanden. Insgesamt16nativeOAK-Aufnahmen nach dem Update erfolgreich.
- Statisches Board:24gemeinsameEcken,0,52nativePixelRMS Verschiebung vor/nach
  OTA. Das enthält Detektions-/Licht-/Montageeinflüsse, keine neue Kalibrierung.
-25/25Bilder im Scanindex `setup/digitization/four_arm_scan_20261113/scan_dataset.json`.
  Die bereits erreichten Endstellungen wurden nur fotografiert. Keine Arm-,
  Power-, Brake- oder Programmaktion während OTA/Nachprüfung; alleFahrcontroller
  inaktiv, alleArme im tatsächlichen Stillstand. Wrist-Originalsettings restauriert.

Der Datenindex nennt OAK-OS1.32.1 für Gruppen1–4 und1.47.0 für Gruppe5.
Frühere Fehlversuche/Flags und der partielle Index wurden nicht verändert.
RGB-Standard wurde wiederholt geprüft; HQ-/Tiefenverfahren wurden nach OTA
nicht erneut vermessen. Die Wiederholungsreihe beweist keine dauerhafte
Fehlerfreiheit und keine metrische Rekonstruktionsgenauigkeit.

Paket und Update-/Factory-/Testnachweise:
`setup/oak4/stability_20261113/ota/`, insbesondere update_validation.json.
Das Paket ist2.615.716.662Byte groß, Hersteller-MD5 stimmte überein; SHA256
`c0de519ab273a8dac1a327cc639316b5dcf22f4b38972d069bd973b579989639`.

## Zwischenstand nach Nutzerneustart


Nutzer bestätigt einen eigenen OAK-Neustart unmittelbar vor dieser Diagnose.
Danach waren vier nativeStandardaufnahmen mit dem unveränderten produktiven
SDK3.12.0 erfolgreich. Anschließend bestanden zwei kompletteFünfkamera-Sätze
an unveränderten Roboterstellungen, jeweils mit nativer8K-OAK, vier nativen
2592×1944-Wrists, Stillstandsaudit und unabhängigem ROS-/GUI-Wächter.
Größte gemessene Pause im ROS-Parent während des Fototests17,5ms.
Alle vier ursprünglichen Wrist-Konfigurationen danach vollständig bestätigt.
Keine neuen Scanstellungen, Arm-/Power-/Brake-/Programmaktionen in dieser Arbeit.

## Was nachgewiesen ist

- Kamera1479883285, OAK4-D R9, LuxonisOS1.32.1/Agent0.20.0/DepthAI3.12.0.
- Route über enp87s0/192.168.8.209, PC-Link2500Mb/s FullDuplex. LesenderPingtest
  ohne Paketverlust, keine konkurrierende OAK-App oder offeneSDK-Verbindung.
- Vorherige Fehler bereits bei `pipeline.start()`. Crashdump vom11:55 enthält
  `Failure binding. Couldn't start device discovery service` und CamX
  `SensorHw : 0 ... AvailableResource = 0`. Das spricht für einen belegten
  Geräte-/Sitzungskontext; welcher frühere Vorgang ihn zurückließ, ist nicht bewiesen.
- Zu Diagnosebeginn Gerätezeit seitBoot ca79s; Nutzer bestätigt den Neustart.
  Die Erholung deshalb nicht als bereits wirksamen Softwarefix ausgeben.
- Frische Werkskalibrierung lesend gesichert und exakt gleich zurHQ-Tiefensicherung
  vom12.11.; kein Kamera-OS-/EEPROM-/Kalibrierflash und kein eigener Geräte-Reset.
- Neuere oakctl-Statistik-/Diagnoseendpunkte sind auf OS1.32.1 nicht verfügbar.
  SSH mit vorhandenem Schlüssel abgewiesen; kein Passwort geraten/gespeichert.

## Wiederholbarer Prüfaufruf

```bash
bash src/oak_camera_calibration/tools/oak4_photo.sh check --count 3 --focus 116
```

EigenerCLI-Prüfpfad `tools/oak4_photo_check.py`, nutzt bestehenden `PhotoCapture`.
Nimmt1–10 nativeStandardfotos auf, prüft tatsächliche Größe/Fokus/Geräte-ID,
steigendeGerätezeit, vollständigeBilddekodierung und unterschiedlicheSHA256.
Beim ersten Fehler Ende ohne weitere SDK-Startversuche. Exitcode0 nur für
vollständigenPASS; alle Prüf-/Fehlberichte unter setup/oak4/checks/ erhalten.
Keine automatische Roboterscan-Freigabe, kein Geräte-Reset und kein Update.

Der produktive SDK-/OS-Stand blieb unverändert. SDK3.11 wurde zunächst nur in einem
separaten Testordner heruntergeladen; der spätere erfolglose Vergleich ist oben
dokumentiert. Zum hier beschriebenen Zwischenstand war es noch nicht verwendet: Die aktuelle SDK-Reihe bestand bereits nach Nutzerneustart.

## Herstellerhinweise und Grenzen

Die [offiziellen Luxonis-OS-Release-Notes](https://docs.luxonis.com/software-v3/sw-stack/luxonis-os)
führen unter1.40 Verbesserungen beiSensor-Recovery, unter1.44 dieFSYNC-Freigabe
beimSchließen und unter1.47 zuverlässigereSitzungsneustarts auf. Das ist ein
sinnvoller Ansatz bei erneutem Auftreten, kein Beweis der konkreten lokalenUrsache.
Laut [DepthAI3.12-Release-Notes](https://github.com/luxonis/depthai-core-v3-release/blob/debian/jazzy/bookworm/depthai_v3/CHANGELOG.rst)
wurde3.12 mitOS1.35/1.41/1.45/1.46 getestet; unsere1.32.1 liegt außerhalb dieser
aufgeführtenTestmatrix. Daraus allein folgt keine bewieseneInkompatibilität.

Nach dem späteren erneuten Fehler wurde das oben dokumentierte OS-Update
ausdrücklich freigegeben und ausgeführt. Ein kurzer bestandenerTest nach
Neustart beweist keine dauerhafteFehlerbehebung; bei erneutemSDK-Ausfall den
Scanangehaltenlassen und aktuelleFehlerdaten prüfen, nicht blind neu starten.

## Artefakte

`setup/oak4/stability_20261113/`: device_info*, apps.json, Netzwerklogs,
crash_1155/, factory-calibration-before.json, factory_comparison.json,
current312_series/, five_camera_retest/result.json, Tests und neuerCLI-Prüflauf.
Fehlgeschlagene frühere Bildsätze und SDK-Crashdumps unverändert erhalten.
