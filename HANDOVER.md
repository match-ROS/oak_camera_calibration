# OAK4-Einrichtung und Live-/Grenztests

## Optionaler HDR-Fotomodus, 2026-11-17

- Nutzerfeedback nach Realvergleich: HDR gefällt; Nutzer fragt nach Ursache der
  langen Laufzeit. Keine zusätzliche Geschwindigkeitsanforderung/Zielzeit oder
  Freigabe für Auflösungsreduktion daraus ableiten. Analyse des vorhandenen
  ISO400-/6Frame-Auftrags:41,07s Gesamtzeit, tatsächliche summierte Belichtungs-
  zeit nur0,190312s. Regulärer Erfolgsweg enthält11,3s feste Sleeps (5s Einlauf,
  1,5s Optiksperre, dreimal1,5s Belichtungswechsel,0,3s Abschluss).
  Zwischen erstem/letztem HDR-Frame13,00058s Gerätezeit, darin auch Übertragung,
  Mittelung, PNG-Speicherung und Wartezeiten zwischen Stufen; diese Zeiten
  nicht additiv doppelt zählen. Drei Stufen-PNGs werden vor der Fusion auf
  Platte geschrieben und danach erneut dekodiert; Kamera-/Pipelineaufbau,
  48MP-Verarbeitung, Mertens und finales PNG kommen hinzu. Einzelphasen nicht
  separat gemessen. Beschleunigungspotenzial: Readback-basiertes Warten und
  weniger serielle PNG-Zwischenschritte, bei gleicher Auflösung/Originalerhalt.

- Reale Fortsetzung auf ausdrückliche Nutzerfreigabe für kurze Aufnahmen und
  anschließende Freigabe der Kamera: alte Fünfkamera-Vorschau hielt die Lease.
  Über ihren regulären `Pause live view`-Knopf pausiert (Atspi-Bedienung);
  tatsächliches Schließen/Sperrfreigabe abgewartet. GUI bleibt geöffnet und
  pausiert, keine Roboterbewegung ausgelöst.
- Drei reale Aufträge erfolgreich: `20261117-173451-hdr-a4552d0c` mit ISO100/
  drei Frames/5625–22500–90000µs (37,66s); `20261117-173538-compare-c45d8cc8`
  mit Standard plus acht HQ-Frames bei ISO100/72500µs (23,46s);
  `20261117-173652-hdr-d0c5805e` mit ISO400/zwei Frames je Stufe/
  4531–18125–72500µs (41,07s). Fokus107 in allen Frames; WB je Auftrag fest.
  ISO400-EV-Abstände −2,00008/0/+2, eindeutige steigende Sequenzen/Gerätezeiten.
  Alle elf gespeicherten PNGs erneut vollständig als8000×6000 dekodiert.
- ISO100-Reihe liegt wegen Zeitgrenze mit Basis−1,708EV unter der Automatik,
  daher sichtbar dunkel. ISO400-Reihe vollständig um die Automatik zentriert,
  `exposure_limited=false`. Visuell weniger helle Tischreflexe, Schatten weiter
  sichtbar verrauscht; HQ wirkt dort sauberer. Kein pauschaler Bildgewinn,
  keine Messung kalibrierten Dynamikumfangs/Geometrie-/Rauschgenauigkeit.
  Einzelaufträge sind zeitlich getrennt, kein synchroner Vergleich.
- Reale Nachweise und Vergleichsbilder imWorkspace:
  `setup/oak4/hdr_validation_20261117/{real-validation.json,real-comparison.jpg,
  real-crops-native.jpg,validate_real.py}`. Deskriptiv: Anteil Luma≥250
  HQ0,330% / HDR4000,046%; schwarze Pixel können echte dunkle Objekte sein.
  `camera-release.json`: Sperre am17.11.17:38:11+08:00 unabhängig erworben;
  GUI meldet PAUSED/OAK released. Eigene Worker beendet, Kamera freigegeben.
  Frühere Aussagen unten „noch ungeprüft“ sind durch diese Fortsetzung überholt.

- Nutzer fragt nach Erweiterung des guten HQ-Fotodienstes um unterschiedliche
  Belichtungen statt ausschließlich identischer Mittelungsframes.
- Implementiert als zusätzlicher Modus `capture --mode hdr`; bisheriger
  HQ-Default bleibt. Drei native 8000×6000-Stufen −2/0/+2 EV, standardmäßig
  ISO100 und ein Frame je Stufe; optional 1–8 Frames je Stufe mitteln.
  Fokus/WB fest, tatsächliche Einstellungen prüfen. Basis 400–22500µs,
  damit die gesamte Reihe im Bereich 100–90000µs bleibt. Referenzabweichung
  und tatsächliche EV-Abstände dokumentiert.
- Originalstufen/Metadaten erhalten, danach Kamera schließen und mit OpenCV
  Mertens zu `hdr.png` fusionieren. ISP8Bit, kein RAW-/radiometrisches HDR,
  keine Ausrichtung/Geisterbildkorrektur. Keine Roboteraktion oder Firmware-/
  Kalibrieränderung.
- 45 Tests/17 Subtests unter System-Python/pytest PASS. Native synthetische
  48MP-Fusion PASS: 11,80s, 5169064KiB Spitzen-RSS, Strukturkontrast dunkel5/
  hell27 Graustufen. Beleg `setup/oak4/hdr_validation_20261117/native-fusion.json`,
  keine Realbilder. Gesamt-unittest-Aufruf im SDK-Venv zunächst wegen fehlender
  pytest/yaml gescheitert; korrekte System-Python-Tests anschließend vollständig
  bestanden. Keine Pakete geändert.
- Erster Versuch mit Fokus107 vor der obigen Fortsetzung an bestehender
  `.capture.lock` korrekt abgewiesen; andere Kameranutzer damals erhalten.
  Fokus107 bleibt vorläufiger Montagewert, keine Intrinsics-Freigabe.
- CLI sofort verfügbar. Untätigen ROS-Fotodienst nach bestätigtem Status IDLE
  neu geladen; `/oak4/photo/capture_hdr` in der Dienstliste bestätigt.
  Anleitung OAK4_PHOTOS.md. Dienst nicht während eines Auftrags neu starten;
  keine fremde Vorschau für HDR unterbrechen.

## Neumontage bestätigt, Sicht und Fokus geprüft, 2026-11-17

- Nutzer bestätigt neue Montage. Der zuletzt stärker nach unten gerichtete
  Ausschnitt zeigt beide Tische und den zentralen Arbeitsbereich mit mehr Rand
  unten; diese Montage vorerst beibehalten. Keine Höhe vermessen.
- Native8K-Standardbilder:151025/Fokus116 rechts13/links0Ecken;
 151245/Autofokusreadback107 rechts24/links15;151413/fest100 rechts19/links8.
  Zusätzlich geänderter Ausschnitt zwischen116/107 verhindert reine
  Ursachenzuordnung zum Fokus.107 vorläufig brauchbarer als100, kein Optimumbeweis.
- Zell-GUI nutzt nun fest107 im datensatzlokalen Aufnahmeprofil; globale
  Optikprofile bleiben erhalten. Factory-K/D bei116 nicht ungeprüft auf107
  übertragen. Neue Sitzung kennzeichnet Registrierung als historisch und
  Intrinsics bei107 als unvalidiert. Keine Kalibrieraktivierung/Armfahrt.
- Artefakte setup/calibration/oak_recalibration_20261117/remounted/ imWorkspace;
  Quellen unter photos/20261117-{151025-standard-6bc0b63c,
  151245-standard-15690ce1,151413-standard-f8e7dbe9}/.

## Aktuelle Montage-/Sichtprüfung und Fünfkamera-GUI,2026-11-17

- ErneuterNutzerauftrag: vermuteteStativbewegung, zuerstaktuellePosebeurteilen,
  dannZell-Aufnahmestellungen/Fünfkamera-GUI. AktuellesStandardfoto14:04:
  photos/20261117-140400-standard-f9d95b9e/,8000×6000, tatsächlicherFokus116,
  ISO257/25000µs. Rechts24/24Ecken, links0/24; Übersichtgut, fernesBoardunscharf.
- Empfehlung höher(max2mStativ), steilerzurMittebeiderTische, Fokusdanachprüfen.
  PhysischeÄnderung/Rückmeldungausstehend, keine6D-NeukalibrierungoderAktivierung.
- ZelleöffnetverbesserteKamera-only-GUI mit5Feeds undeigenerOAK-Lease:
  uwa-oak-recalibration-view-20261117.service. KeinekonkurrierendenSDK-Aufnahmen
  starten; fürweitereNativechecksVorschaugeordnetpausieren. BewährteEinstellungen
  via keep-camera-settings erhalten. UI-/Detektionsbelege imWorkspace unter
  setup/calibration/oak_recalibration_20261117/. KeineUR-Bewegung in diesemSchritt.

## OAK-Zellbezug neu prüfen / mobiles Board,2026-11-17

- Kartonrealtest imZellprojekt: ersteunbeladeneRF-Anfahrt erreichtGelenkziel,
  FotoabgleichzeigtVersatz. Nutzer: OAK/Stativseit12.11.möglicherweisebewegt,
  Boards/Tischeeherunverändert; bietetNeukalibrierungan. KeinbestätigterUmbau.
- FrischesHQ13:33/Fokus116/8Frames unterphotos/20261117-133312-hq-e718fc74/;
  rechts24Ecken, Prüf-RMS2,098px, links0Ecken. Kamera danachgeschlossen.
  DreiAufträge11:40/13:02/13:33 ergeben0,599mm/0,0271°maxAbweichungzumMittel,
  nurstatischeWiederholbarkeit.1px-Kriteriumnichtbestanden, keineKalibrierung
  aktiviert. KandidatimWorkspace setup/tasks/carton_oak_reregistration_20261117_01/.
- Mobiles38mm-Brettverfügbar; unabhängigeOAK/RF-Bildreihevorbereitet. Eigene
  Kamera-only-App läuftmitOAK-Livepreview/Lease, Dienst
  uwa-carton-oak-registration-view-20261117; fürneueAufnahmendieseAnsichtnutzen
  oderPreviewgeordnetpausieren. KeineparallelkonkurrierendeSDK-Sitzungstarten.
- Nutzerwunsch:GuteKameraeinstellungendürfenbestehenbleiben, keinroutinemäßiges
  vollständigesZurückstellen. Fokus/IntrinsicsbindungundLeaseweiterbeachten.
  Zell-Appbietet `--keep-camera-settings`; nativeFormat-/Dienstfunktionerhalten.

## Karton wieder am Platz,2026-11-17

- Nutzer erlaubt imKartontest selbständigeOAK-Szenenchecks undbestätigtKarton
  wiederanvorigemPlatz. BestehenderFotodienst/Lease, nativeStandardaufnahme
  8000×6000/Fokus116 um10:31:25+08:00, photos/20261117-103125-standard-abdf393d/.
  Kartonvisuellbestätigt; Kameraanschließendgeschlossen, keineSDK-/Firmware-
  oderKalibrieränderung undkeineUR-BewegungdurchdiesenCheck.
- Zell-TexturePoseoffline:69Inlier/2,458pxRMS; kamerabezogeneEinzelbildpose,
  keineabsoluteGenauigkeit/Manipulationsfreigabe. VorläufigerZelltransform
  ergibt1,43degNeigung, keinneuer6D-Kalibriernachweis. ArtefakteimWorkspace
  setup/tasks/carton_hardware_preparation_20261117_01/oak-localization/.

## Neuer Tischboardversuch und expliziter Abstands-Fallback, 2026-11-17

- Nutzer hatKistezurSeitegestellt undbeauftragtneuesFoto; fallsnichtauswertbar,
 99,1cmBasisabstandausdrücklichverwenden. NativeStandardaufnahmeFokus116 unter
  photos/20261117-101007-standard-37a99717/erfolgreich, Kameradanachgeschlossen.
  Rechts24Ecken/2,050pxPrüf-RMS, links0Ecken/0Marker. KeineaktuelleZweiboardpose.
- ZellprojektübernimmtNutzer-Fallback99,1cmalsvorläufigenskalarenAbstand,
  keine6D-OAK-/Basiskalibrierung. Dort anschließendseparatautorisierteArme/
  Greifergetestet; FotoauftragalleinalserteiltkeineArmfreigabe. Nachweis
  Zellrepo docs/hardware_commissioning_2026-11-17.md.

## Tischboard-/Basisabgleich, 2026-11-16

- Nutzerauftrag im Zellprojekt: hintere Montagezentren laut Zollstock100cm,
  offeneGreifer ungefähr20cmSpalt; beideTischboards zur relativenVermessung
  verwenden. Keine Roboter-/Dienst-/Firmware-/Kalibrieraktion durch diesen Check.
- Bestehende Foto-Lease: Standard154654 undHQ154841/8Frames/Fokus116,
  native8000×6000, Kamera nachher geschlossen. LinkesfernesBoard visuellunscharf,
  nur1Marker/0Ecken; rechts24Ecken,8ausgeschlossenePrüfecken1,835/1,924pxRMS.
  Keine heutigeZweiboardpose/Genauigkeitsfreigabe. FactoryK/Rational14 erhalten.
- Historische12.11.-Boardposen plus akzeptierteRear-Basis-Board-Fits ergeben
 99,115cm, nurPlausibilitätscheck (alterFokusnichtprotokolliert). Keine Welt-
  oderBasisanker übernommen. Nachweis Zellrepo
  docs/rear_base_spacing_review_2026-11-16.md undWorkspace
  setup/research/four-arm-model-distance-review/board-base-review.json.

## Mobile Referenzserie und realer Karton-GPU-Test, 2026-11-16

- Nutzer bestätigt mobiles38mm-Brett und Bereitschaft je Aufnahme. Fünf
  Aufträge à8Paaren; drei mobile Ansichten auswertbar, zwei wegen Blick/
  Bildrand unzureichend erhalten. Kein UR-/Dienst-/Firmwareeingriff.
- Z-Zentren ausRGB0,922/1,152/1,330m; maxPrüf-RMS0,452px. Nominale SDK-Z-
  Abweichungen+13,15/+16,08/+2,51mm. Benutzermaß5Felder191 statt190mm getrennt
  als isotrope Sensitivitätsannahme gerechnet, keine Definition geändert.
- Rechenbeispiel+8,10/+10,10/−4,44mm zeigt keine belastbare Pauschalkorrektur.
  Ursachen aus gekoppelten Ansichts-/Abstands-/Ortsänderungen nicht isoliert;
  Nahansicht nur42,6% gültig im Muster. Vergleich und Quellenhashes unter
  setup/oak4/rgbd/validation_20261116/, Details OAK4_RGBD.md.
-38Tests/9Subtests PASS, mobileIDs75–91/38mm von TischIDs50–66/40mm getrennt.
- Nutzer stellt danach bekannten Karton bereit; Aufnahme111619-rgbd-5a8d0ae9.
  Erster statischer GPU-Replay mit manuellem Umriss und vorhandenem Mesh visuell
  plausibel,1,62s/18,8ms Kernzeiten. Arbeitsbilder640×480 aus1280×960 mit
  Faktor0,5 und passender Pixelzentrum-K, Originaldaten unverändert.
  Quelle/Nachweise im Zellrepo docs/foundationpose_titanpc.md; keine Messfreigabe.
- Eigene Kamera-/GPU-Jobs beendet, Kamera-Lease frei; keine globale Aktivierung.

## RGB-D-Boardprüfung: gute Bildkonsistenz, Tiefenabweichung offen, 2026-11-16

- Nutzer erlaubt Fortsetzung/bietet Karton neben aktuellem Roboter an. Zuerst
  acht gespeicherte RGB-D-Paare offline geprüft, keine neue Aufnahme/UR-Aktion.
- Neuer wiederverwendbarer Offlineprüfer oak4_rgbd_board_check.py: fixes SDK-K,
 40mm-Board IDs50–66,16Fit-/8ausgeschlossene Prüfecken. Alle8Bilder24Ecken,
  maximales Prüf-RMS0,3222px,1px-Kriterium bestanden; keine Vollkalibrierung.
- Boardinneres median95,27% gültige Tiefe. SDK-Z gegenüber RGB-Boardebene
  median+11,05mm; Tiefenebenenwinkel median1,11°. Keine unabhängige absolute
  Genauigkeit und keine Blindkorrektur der Tiefenwerte oder Werkskalibrierung.
- Nutzer-Linealmessung: fünf Felder200mm, Genauigkeit nur nach Lineal,
  nicht kalibriert. Gesondert im Datensatz als operator-reference.json erhalten.
- Nachweise unter rgbd/20261116-102913-rgbd-fa320e7a/board-check-v1/;
 36Tests/9Subtests PASS. Vorgehen/Interpretation in OAK4_RGBD.md ergänzt.
- Für Ursache/Genauigkeit weitere Entfernungen/Neigungen eines separaten
  mobilen38mm-Boards vorgeschlagen, dessen Verfügbarkeit beim Nutzer gefragt.
  Tischboards/OAK nicht verschieben; noch keine neue Kalibrierung freigegeben.

## Erste gemeinsame RGB-D-Aufnahme, 2026-11-16

- Nutzer beauftragt ersten FoundationPose-Eingabeschritt; aktuell studentischer
  Roboter statt Karton am Aufnahmeort. Aufnahme benötigt noch kein Objektmesh.
- Neuer Modus `oak4_photo.sh capture --mode rgbd` im bestehenden Transaktions-
  pfad: isolierter SDK-Worker, vorhandene Lease, RVC4 ImageAlign+Sync, entzerrtes
  RGB und RGB-ausgerichtete Tiefe. Keine fremden Kamera-/UR-Dienste gesteuert.
- NativeStereo1280×800, gemeinsames Ausgabe-Gitter1280×960/10fps, Fokus116,
  maximale Zeitdifferenz25ms geprüft; keine Zeitfusion/HQ-Mittelung.
- Real erfolgreich: setup/oak4/rgbd/20261116-102913-rgbd-fa320e7a/,8Paare,
  maxZeitdifferenz1,727ms/maxSDK-RGB-Alter144,567ms. K beider Ausgaben identisch.
  Gespeicherte PNGs/Masken/Zeiten erneut geprüft, Kamera-Lease danach frei.
- Vorschau geprüft: Roboter/Board sichtbar, Überlagerung grob plausibel,
  Tiefenlücken erhalten; Gesamtbild42,01–42,72% gültig. Keine unabhängige
  Genauigkeitsprüfung oder FoundationPose-Erkennung dieses Roboters behauptet.
-31Offline-Tests/9Subtests PASS. Bedienung/Daten/Quellenbezug OAK4_RGBD.md;
  nächste Prüfung Board/K und Tiefenkanten, spätere Pose mit passendem Mesh/Maske.

## Opt-in-RGB-Stream für CPU-Objekttracking, 2026-11-13

- Nutzer möchte statische und schnelle dynamische6D-Objektpose auf dem Mini-PC.
  Zellpaket uwa_cell_tracking besitzt einen expliziten OAK-Provider auf Domain65;
  kein Kamera-/Roboterstart allein aus Modellerstellung oder normalem Zellstart.
- Bestehender oak4_board_preview.py erhält optionalefps/width/height und
  --tracking-metadata: tatsächlichesOutput-K, Factory-D, manuellerFokus116,
  SDK-synchronesBildalter/Sequenz. Default2000×1500/2fps und bisherige
  GUI-Aufrufe bleiben erhalten; fürTracking explizit unentzerrtes1600×1200/10fps.
  Gemeinsame photos/.capture.lock beibehalten, keine fremdePipeline beendet.
- Begrenzter Livetest:188Frames bei10,012HostFPS; statischePose und116Online-
  Poseupdates bei ruhendemKarton. MaxSDK-Bildalter128ms,24Boardecken/0,256pxRMS
  als separateOptikprüfung. Keine absolutePosengenauigkeit oder echteObjekt-
  Bewegung geprüft. Pipeline geschlossen undLeasefrei bestätigt, keinReset/OTA.
- Anleitung imZellrepo docs/object_tracking.md; Ergebnisse unter
  setup/tracking/carton_cpu_20261113/live/. NurKamera, keineUR-Anbindung.

## Autorisiertes OS1.47-Update und Scanergänzung abgeschlossen, 2026-11-13

- Nutzer bestätigte das angebotene Update ausdrücklich mit „ja bitte“. Offizielles
  Herstellerpaket vor Installation erneut SHA256-geprüft; gleiche OAK4-D R9 mit
  ID1479883285/192.168.8.238. Updater Exit0, danach **OS1.47.0/Agent0.28.0**.
- Frische Werkskalibrierung vor/nach OTA exakt identisch: SHA256
  a07141cce771738c713df4ef62f3719ed2ede411c556bc920089270cc4689eae.
  Produktiver SDK3.12.0 unverändert, keine neuen globalen Kalibrierprofile/TFs.
-15direkt aufeinanderfolgende native8K-Start-/Fotozyklen PASS, Fokus116,
  gleicheIdentität, steigendeGerätezeit, vollständig dekodierte unterschiedliche
  Bilder. Danach vollständiger letzter Fünfkamera-Satz mit unabhängigem
  Stillstandsaudit PASS. Insgesamt16OAK-Aufnahmen seit Update erfolgreich.
- Statisches Board vor/nach Update:24gemeinsameEcken,0,52nativePixelRMS
  Bildverschiebung. Enthält Detektions-/Licht-/Montageeinflüsse, keine neue
  geometrische Genauigkeitsfreigabe. Factory-K/D blieb unverändert.
- Jetzt25/25Scanbilder bestätigt. Index/Übersichten im Zell-Workspace:
  setup/digitization/four_arm_scan_20261113/scan_dataset.json,
  scan_overview.jpg undscan_all_rounds.jpg. Gruppen1–4 OAK-OS1.32.1, Gruppe5
  OS1.47.0 ist ausdrücklich dokumentiert; Fehlversuche/Teilindex bleiben erhalten.
- Während OTA/Nachprüfung keine Arm-, Power-, Brake- oder Programmaktion.
  AlleArmeRUNNING/NORMAL/Stillstand, Fahrcontrollerinaktiv. LinkeProgramme
  STOPPEDbelassen, keine automatische Rückfahrt. Wrist-Konfigurationen restauriert.
- Paket, Updateplan, Rohlogs und Abschlussbericht:
  setup/oak4/stability_20261113/ota/update_validation.json. Wiederholungsprüfung
  ist ein begrenzter Nachweis, keine dauerhafte Stabilitätsgarantie; RGBStandard
  wurde geprüft, HQ-/Tiefenverfahren nach diesem OTA nicht erneut vermessen.
- FolgendeAbschnitte sind historische Zwischenstände vor diesem Abschluss.


## Erneuter OAK-Serienfehler; OS-Update vorbereitet, 2026-11-13

- Nutzer erlaubte Scanfortsetzung nach zunächst neun erfolgreichen nativen Fotos.
  Alle Roboterstellungen erreicht; 20 Wrist-Ansichten und vier OAK-Fotos bestätigt.
  Letzte OAK-Aufnahme wieder Pipeline-Startfehler. Kurze erfolgreiche Testreihe
  deshalb nicht als dauerhafte Behebung ausgeben. Keine weiteren Armziele nötig.
- Die während der Fotos störbare Stillstandsaufzeichnung läuft jetzt separat
  von der Bildarbeit. Echter Audit-PASS für letzte vier Wrist-Fotos; OAK bleibt
  das fehlende25.Bild. Fehlerflags und ursprüngliche Datensätze unverändert.
- SDK3.11 isoliert verglichen, kein Gerätekontakt/kein Bild. Keine Umstellung.
- Offizielles OS1.47-Paket lokal vorbereitet, 2.615.716.662Byte, Hersteller-MD5
  korrekt; SHA256 c0de519ab273a8dac1a327cc639316b5dcf22f4b38972d069bd973b579989639.
  Factorybackup gesichert und unverändert. Kein eigener Reset/OS-Flash.
- Updateplan unter setup/oak4/stability_20261113/ota/update_plan.json. Freigabe
  für dauerhafte Kamera-OS-Änderung1.32.1→1.47.0 mit Neustart noch ausstehend.
- 87 gemeinsame Scan-/Audit-/Kamera-Regressionen bestanden. Voller Datenstand im
  Zell-HANDOVER und scan_dataset_partial.json. Aktuelle Diagnose/Quellen in
  OAK4_STABILITY_2026-11-13.md; frühere Abschnitte sind Zwischenstände.


## OAK wieder funktionsfähig nach Nutzerneustart, 2026-11-13

- Nutzer bestätigt eigenenNeustart/Neuanschluss kurzvorDiagnose; Gerätezeitzu
  Beginnca79s passtdazu. Danach9native8K-FotosPASS:4Baseline,2stationäre
  Fünfkamera-Sätze,3neuerCLI-Prüflauf. KeinSDK-/OS-Wechsel oder eigenerReset.
- BeidevollständigenFünfersets mitStillstandaudit, unabhängigemROS-/GUI-Wächter
  undOriginalsettings-Restaurierung bestanden; maximaleParent-Spinpause17,5ms.
- Neuer CLI: `bash src/oak_camera_calibration/tools/oak4_photo.sh check --count 3 --focus 116`.
  Größen-/Fokus-/ID-/Zeit-/Dekodier-/Payloadprüfung, ersterFehlerbeendetReihe.
 17TestsPASS, echterCheckPASS unter setup/oak4/checks/20261113-124214-72ddab27/.
- FrischeWerkskalibrierung exaktgleichzurSicherungvom12.11. Rohdaten unter
  setup/oak4/stability_20261113/. SDK3.11 lediglichisoliert heruntergeladen,
  nichtverwendet/aktiviert; produktive3.12 unverändert.
- FrühererCrashdump: Discovery-Bindfehler undSensorHw0belegt. Zurückgebliebene
  SDK-Sitzung plausibel, genaueUrsache unbewiesen. Hersteller dokumentiertneuere
  Sensor-/FSYNC-/Sitzungsfixes; keinUpdatefürdieseDiagnoseausgeführt.
- Neuer Nutzerauftrag erlaubtScanfortsetzungnachOAK-PASS; Ausführung liegtim
  Zellrepo work/four-arm-object-scan-run.md. Diagnose selbst bewegtekeinenArm.
- Bedienung/Quellen/Grenzen: OAK4_STABILITY_2026-11-13.md, OAK4_PHOTOS.md.


## OAK im realen Vierarm-Scan, 2026-11-13

- Native Standardfotos mit Fokus116 funktionieren heute intermittierend, Erfolg
  11:12 und11:45. Spätere Pipeline-Starts wiederholt SDK-Pingverlust/FW-crash
  bzw. Device-not-found, auch bei separater Aufnahme nach allen Wristtransaktionen.
  Ursache nicht belegt; kein manueller Reset oder Firmwareflash vorgenommen.
- Vierarm-Scan nach erster erreichter Stellung angehalten, keine vier weiteren
  Runden. Kameraarbeit prozessisoliert: realer stationärer Retest alle4Wrist-HD-
  Fotos und StillstandsauditPASS, ROS-Parent-Spinmax18,2ms; OAK wieder gescheitert.
- Fehlerdaten setup/oak4/photos/20261113-114831-standard-f75b6347/ und
  20261113-115524-standard-6fe31b81/. Erfolgreiche separate Referenz
  20261113-114509-standard-022dd3ee/. SDK-/Kameradienste nicht pauschal beendet.
- Zellstand/Entscheidungsfrage im Zell-Repo docs/parallel_object_scan.md und
  work/four-arm-object-scan-run.md. Vorerst keine automatische neue Armfahrt.


## Neuer Prüfversuch nach Ethernet-Rückkehr, 2026-11-13

- Für den beauftragten Vierarm-Objektscan ein Standard-RGB-Einzelfoto mit
  unverändertem8K/Fokus116 versucht. Gerät1479883285 zunächst erkannt, dann
  missed ping/device gone/MessageQueue closed und FW crash im SDK protokolliert.
  Kein gültiges Foto und keine bestätigte abschließende Rückstellung.
- Fehlerdaten setup/oak4/photos/20261113-110935-standard-2810009d/ erhalten;
  SDK-Crashdump zusätzlich unter ~/.cache/depthai/crashdumps/. Ursache offen,
  nicht als bewiesener Firmwarefehler oder als Nutzereingriff ausgeben.
- Begrenzter zweiter Versuch danach erfolgreich: ein natives8000×6000-PNG,
  tatsächlicher Fokus116,16666µs/ISO255. Sitzung
  setup/oak4/photos/20261113-111253-standard-5b8d982b/. Bild zur Aufbauprüfung
  durchgesehen. Erste Fehleraufnahme unverändert ungültig, Ursache bleibt offen.
- Kein Flash, kein expliziter Geräte-Reset, keine fremden Pipelines/Dienste
  beendet und keine Armkommandos. Ein begrenzter Wiederholungsversuch durchgeführt;
  erste Fehlaufnahme bleibt ungültig. Zell-Arbeitsstand work/four-arm-object-scan-run.md.

Stand: 2026-11-12, Australia/Perth. Status: **Host eingerichtet, LAN-Extremtests
vom 09.11. und spätere Erreichbarkeits-/Bildtests erfolgreich; Roboternetz wieder Ethernet**.

## Gemeinsame mobile Board-Aufnahme,2026-11-12

- Zell-App **UWA Camera Capture** zeigtbeide rechtenWristkameras undOAK4,
  erkenntnur mobilesA4 IDs75–91 undspeichert nativeDreierfotos. KeineArmfahrt.
  Zell-Dokumentation docs/three_camera_capture.md, Skript scripts/camera_capture.sh.
- VorhandenerFotodienst erhielt optional `--focus 0..255` fürRGB; ohneOption
  Verhaltenunverändert. Tatsächlicher8K-Framefokus mussWunschwertentsprechen.
  GUI: standard-Einzelbild mit116manual stattHQ-MittelungdesHandheldBoards.
- Neue tools/oak4_board_preview.py: eigenesSDKKind,voller4:3-8KSensor,
  Ausgabe2000×1500/2fps,NV12→JPEG,AE5sEinlauf,festerFokus116. Teilt
  setup/oak4/photos/.capture.lock mitRGB/Tiefe. VorFotoeigenePipelinebeenden
  UNDfreigegebeneDateisperreabwarten; oakctl-Wrapperendet teilsfrüher.
- EchterGUI-Lauf mitVorschau→nativemDreierfoto→Vorschau→Pause/Sperrfreigabe
  PASS: setup/calibration/three_camera_20261112/gui_check/20261112_154921_20ecc2ad/.
  OAK24/24 mobileEcken inPreviewund8KFoto,RF8/RR24native. KeinGeräteflash,
  Firmware-/Factorykalibrierwechsel oderfremderDienststopp. Pausieren derGUI
  nötig,wennderTiefendienst dieselbephysischeOAK benötigt.

## HQ-Tiefenaufnahme als RViz-Punktwolke,2026-11-12

- Nutzer bittet nach HQ-Tiefenmodus um sichtbare RViz-Anzeige. Vorhandene
  Domain70-Designvorschau erhalten; eigene Domain65-Snapshotansicht geöffnet.
- CLI `bash src/oak_camera_calibration/tools/oak4_photo.sh view-depth`, optional
  --capture DIR. OAK-Tools oak4_depth_rviz.py/geometry.py, keine ROS-Neubaupflicht.
  HQ standardmäßig aktiv, Standardwolke optional, klarer STATIC-/Datumshinweis.
- Frische nativeHQ-Aufnahme: setup/oak4/depth/20261112-145646-depth_hq-437c09ec/.
  Worker speichert jetzt tatsächliche rektifizierte Frame-K/Größe und Referenz-
  extrinsics in Metern. K fx=fy800.60913,cx637.89282,cy398.7670 für1280×800.
  Keine unrektifizierteFactory-K als Ausgabe-K verwendet; alte Aufnahmen ohne
  projection für3D abgewiesen. SDK-Metadatenquelle im JSON protokolliert.
- Kamera-lokale PointCloud2,273323HQ-/429717Standardpunkte, EinheitenMeter;
  TF nur oak4_snapshot_view→oak4_snapshot_rectified_right_optical. Kein world-
  TF/kein global aktiviertes Kalibrierprofil, keine angenommene Weltregistrierung.
- Geöffnet per temporäremBenutzerdienst uwa-oak4-depth-rviz; Config/Quelle/Counts
  unter setup/oak4/rviz/. ROS-Empfang mit endlichen Punkten/korrektemPayload/TF,
  RViz-Abonnent und GUI GlobalStatusOk nachgewiesen.17TestsPASS, neue bekannte
  Pixelprojektion/mm→m/Nullwert-/Kalibrierfehlerprüfungen enthalten.
- Rendererbilder perDesktop-/RViz-Qt-Grab unterWayland nicht zuverlässig prüfbar
  (schwarz); deshalb kein visueller Screenshot-Nachweis behauptet. Punkte-
  empfang/GUIstatus sind unabhängig geprüft. Keine fremdenDienste/Roboter geändert.


## Statischer HQ-Tiefendienst ergänzt,2026-11-12

- Nutzer fragt nach ähnlichem HQ-Verfahren für Tiefe. Bestehenden Fotodienst
  erweitert, keine separate permanente Kamera-Pipeline. Neue Trigger-Services
  `/oak4/depth/capture_{hq,standard,compare}` und `/oak4/depth/status`, Domain65.
  CLI über oak4_photo.sh capture --mode depth_hq (Standard16Frames).
- Native1280×800-Stereo/FAST_ACCURACY/SoftwareLR,10fps; Mono-AE nach Einlauf
  sperren. Keine räumlichen/historischen Softwarefilter, stattdessen zeitlicher
  Median gültiger Werte, mindestens75% Support/Inlier und MAD-Grenze
  max10mm/1%Tiefe. Instabile Werte0, keine Lochfüllung. Keine ISO100-Behauptung.
- Worker/Fusion im OAK-Repo tools/oak4_depth_{capture,fusion}.py, Anleitung
  OAK4_DEPTH.md. Rohframes/Count-/Inlier-/MAD-/Maskenkarten,16bit-mm-PNGs und
  Factorybackup unter setup/oak4/depth/. Gleiche Thread-/Dateisperre wie RGB.
- Installierten Vergleichsservice real PASS geprüft, native1280×800,uint16,
 16Frames57–72/1,500s: setup/oak4/depth/20261112-144815-depth_compare-97e070f4/.
  Standard41,67% gültig, HQ26,87% nach konservativer Aussonderung. Akzeptierter
  medianer zeitlicherMAD3mm; kein absoluterGenauigkeitsnachweis. AndereArm-
  arbeit parallel; kein garantierterStillstand/Kamera-Roboter-Zeitsync.
- Regulärer HQ-Endpunkt ebenfalls real PASS: setup/oak4/depth/20261112-145220-depth_hq-29c6117c/.
  Status CAPTURING währendAufnahme, parallelesRGB abgewiesen,danachREADY.
  14automatisierteTestsPASS; intakte16bit-PNGs/NPZ und Supportmasken geprüft.
- Mono links3000µs/ISO188,rechts3135µs/ISO200 währendBurst konstant. Kein
  Firmware-/Flash-/Kalibrierprofil-/Roboterkommando. Foto-/Tiefenaufträge exklusiv.
  Neue Tests für Fusion/ungültigeDaten/Bewegungskanten; bestehende Foto-Sperr-
  Fehler-/Timeouttests erhalten. Agentenhinweise/README in beiden Repos ergänzt.


## Wiederverwendbarer OAK4-Fotodienst,2026-11-12

- Nutzer beauftragt nach erfolgreichem Standard/HQ-Vergleich dauerhafte Ablage
  als Service und sichtbare Dokumentation für spätere Agenten.
- Implementierung im OAK-Repo `tools/oak4_photo{.sh,_service.py,_capture.py}`,
  Anleitung `OAK4_PHOTOS.md`. CLI ohne ROS, Trigger-Services unter `/oak4/photo/`
  (capture_hq/capture_standard/capture_compare/status), Domain65/LOCALHOST.
- Installiert/aktiviert: systemd-user `uwa-oak4-photo.service`; idle ohne Kamera.
  Bestehende isolierte Laufzeit `.venvs/oak4` (DepthAI3.12) und oakctl verwendet;
  Inventar-IP/Geräte-ID zentral aus Zellrepo, keine temporären Chatabhängigkeiten.
- HQ ISO100, max90ms, acht echte48MP-Frames mit konstantemFokus/WB, nativePNG.
  Sensor10fps, nur angeforderte Vollbilder übertragen. Keine Rohsensor-/HDR-
  Aufnahme, keine Bewegungskompensation oder automatische Roboterfahrt.
  Exklusiver SDK-Zugriff, kein automatisches Stoppen fremder Kameradienste.
- Reale Serviceprobe PASS: setup/oak4/photos/20261112-135950-compare-cf3a4ee9/,
  drei intakte8000×6000-PNGs, StandardISO309/16,666ms, HQISO100/51,498ms,
  Fokus107/WB4138K, achtverschiedeneFrames. Status währenddessen erreichbar,
  zweiteAufnahme abgewiesen, danachREADY. Sechs Fehler-/Sperr-/TimeouttestsPASS.
- Finale reguläre HQ-Serviceprobe nach dem letzten Dienstupdate ebenfalls PASS:
  setup/oak4/photos/20261112-140403-hq-f3cec77a/, ISO100, acht unterschiedliche
  native48MP-Frames, exposure_limited=false. Benutzerdienst aktiv und enabled.
- Agentenhinweise/README in beiden Repos und Workspace-Einstieg ergänzt.
  Ergebnisse dauerhaft in setup/oak4/photos/; keine Bilddateien im Git.


## Grobe OAK-Extrinsics aus vorhandenemFoto,2026-11-12

- Folgeauftrag: Pose zunächst relativ rechtemTisch schätzen und passendeUR-
  Sichtstellungenentwerfen. Nur EEPROM-K/D gelesen, keineKalibrierunggeschrieben,
  keine Kameraparameter-/UR-Befehle. Gerät wieder geschlossen.
- Standard4000×3000-K auf8000×6000 skaliert,alle14Distortionwerte; Factory-
  Linsenstellung116,Foto-AF unbekannt. Tischboard-PnP getrennt: rechts1,708px,
  links0,460px. RechteTischmitte→Optik grob[.806,.025,.958]m/33,54°nachunten,
  Boardposition/-yaw alsModellannahme. Kein finalesOAK-Extrinsicsprofil.
- Rohbackup/Schätzmatrizen/Sensitivität lokal setup/calibration/oak_pose_20261112/.
  UmfangreicherArm-/SichtentwurfimZellrepo docs/oak_pose_and_shared_views_2026-11-12.md;
  nurDesign/RViz-Domain70, keineechtenArmebewegt.

## Drei UWA-ChArUco-Boards im nativen8K-Foto,2026-11-12

- Nutzerauftrag: Vorbereitung externerOAK-Kalibrierung, dreiBoards gleichzeitig
  im echtenFoto prüfen. OAK238 überDepthAI3.12 exklusiv geöffnet, Live-Dienst
  war inaktiv; keine anderen Dienste/Roboter gesteuert. Danach Gerät geschlossen.
- Vorhandenes rgb_full-Profil/IMX5868000×6000,NV12,Ausgabe1fps und5sWarmup.
  OriginalPNG tatsächlich8000×6000; kein Hochskalieren. Schnappschuss und JSON
  unter `$UWA_WS/setup/oak4/captures/boards_20261112/`, keine Fotos insGit.
- OpenCV5-ID-getrennteChArUco-Detektion aufOriginalauflösung: linkesTischboard
 0–16,rechtes50–66,mobilesA4 75–91; **je17Marker und24Ecken** erkannt.
  `detection.json` enthält Ecken/IDs/Pixelkoordinaten undOriginalSHA256;
  `boards-annotated-8k.jpg`/`boards-overview.jpg` zeigen getrennterBoard-Beschriftung.
- Keine Pose geschätzt/keine OAK-Extrinsics aktiviert. Board-Sichtbarkeit ist
  Voraussetzung, keine fertige metrische Kalibrierung. Globale gültigeWrist-
  Kalibrierung imZellrepo separat als hardware_20261112_v1 aktiviert.

## Aktueller Netzwerkstand nach Kabeltausch, 2026-11-10

Nutzer meldet Kabel ersetzt. Roboter-/Kameranetz wieder über Ethernet;
PC192.168.8.209 auf enp87s0, keine temporären Funk-Annahmen weiter anwenden.
Keine Kameraprofile oder Internetverbindungen durch diese Dokumentationspflege
geändert. Die nachfolgenden Erreichbarkeits-/5-fps-Werte sind frühere Messdaten.

## Historisch: Erreichbarkeit vor Kabeltausch, 2026-11-10

- PC laut Nutzer vorübergehend per WLAN wegen defektem PC-Router-LAN-Kabel;
  OAK und URs bleiben kabelgebunden am Router. Bestätigt PC192.168.8.209/24
  aufwlp88s0f0, Route zur OAK192.168.8.238 über WLAN; enp87s0 DOWN.
- OAK viaoakctl alsOAK4-D R9, ID1479883285, OS1.32.1/Agent0.20.0 erreicht.
  Je40 Pings ohne Verlust, OAK-RTT Mittel6,52ms, Maximum14,52ms.
- Kurzer SDK-Test640×480,NV12,5fps nach3s Einlauf:52 Frames über10,21s,
  **4,997fps**, ca18,9Mbit/s Bildnutzdaten. Danach geschlossen. Der alte
  Livedienst war vorher inaktiv und wurde nicht dauerhaft gestartet.
- UR-Zuordnung: `right_rear`=192.168.8.170, `right_front`=192.168.8.103;
  beide Dashboard-Server lesend erreicht, keine Bewegungs-/Zustandsbefehle.
- WLAN-Linkraten sind kein Nutzdatendurchsatz. Die folgenden48MP/HFR-/Tiefen-
  Messungen wurden am09.11. über2,5-Gbit-Ethernet gemacht und gelten dafür
  unverändert als historische LAN-Ergebnisse, nicht als WLAN-Nachweis.
- Bericht im Zellrepo `docs/hardware_network_2026-11-10.md`, Inventar dort
  `config/hardware_inventory.yaml`; lokale Artefakte unter
  `~/UWA_ws/setup/logs/hardware-wifi-2026-11-10/`.

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
  korrigiert. Damals blieb die RGB-Vorschau geöffnet; beim Netzwerkcheck
  am10.11. war der Dienst bereits inaktiv. ROS-Testprozesse damals beendet.
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

## Echte Leistungsmessungen vom 2026-11-09 über LAN

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

### Identifikation der unbeschrifteten USB-Zusatzkamera, 2026-11-09

- Nutzer korrigiert die bisherige Vermutung OAK-D-S2-FF und schließt ein
  unbeschriftetes Gerät per USB-C an. Genau dieses USB-Gerät geöffnet;
  Ethernet-OAK4 und Simulation nicht gestoppt/geändert.
- Ausgelesen: EEPROM-Produktname **OAK-D Pro AF**, SDK **OAK-D-PRO-AF**,
  Plattform **RVC2**, Board **DM9098**, Revision **R6M2E6**,
  Geräte-ID **18443010314F3B1300**. Damit ist diese Kamera als Pro-Autofokus-
  Variante identifiziert; die zweite Zusatzkamera ist noch nicht geprüft.
- Sensoren: CAM_A **IMX378**,4056×3040, Autofokus=true; CAM_B/C je **OV9282**,
  1280×800, Autofokus=false. Sensor-Shutter laut Luxonis: IMX378 Rolling,
  OV9282 Global. USB bei geöffnetem Gerät **SUPER** (USB3).
  Reine Sensor-Modustabellen ausgelesen, keine FPS-/Bildqualitätsmessung.
- Fehlende USB-Zugriffsrechte behoben: `/etc/udev/rules.d/60-luxonis-oak.rules`,
  beschränkt auf Vendor03e7, MODE0660, Gruppeplugdev, TAGuaccess. Benutzer ist
  Mitglied inplugdev. Quelle im Repo `tools/60-luxonis-oak.rules`; Regeln geladen
  und nur passende USB-Geräte getriggert. SDK-Zugriff danach ohne sudo erfolgreich.
- Nur normale flüchtige SDK-Verbindung/RAM-Start und Lesezugriff auf Kalibrierung;
  keine Flash-/Factory-Reset-/Kalibrierschreiboperationen, keine IR-Aktivierung.
  Gerät nach Auslesen wieder geschlossen.
- Diagnose und Factory-Kalibrierungsbackup lokal unter
  `~/UWA_ws/setup/oak4/usb-identification/{device,factory-calibration}.json`.
  Inventar im Zellrepo entsprechend korrigieren; historischen S2-FF-Vermutungen
  nicht als bestätigte Geräteidentität folgen.

### Weitere Bedienung

- Folgeauftrag: OAK4-D als statische Übersichtskamera auf Stativ rechts in die
  Gazebo-Zelle aufgenommen. Umsetzung/Designparameter im Schwesterrepo
  `multi_arm_manipulation_UWA`, siehe dessen `docs/oak_overview.md` und
  `HANDOVER.md`. Die echte Kamera steht laut Nutzer rechts und schaut auf die
  Tischplatten; genaue Montage ist offen. Stativ laut Nutzer höchstens2m;
  jetzt virtuelle Pose[1.8,-0.8,2]m, Ziel[0,-0.1,.95]m. Frühere3m-/2,6m-Posen
  sind historisch, keine gemessenen Hardware-Extrinsics. Zwei zusätzliche OAKs
  sind für mögliche tote Winkel verfügbar; erste als OAK-D Pro AF identifiziert,
  zweite noch ungeprüft. Keine Anbindung als Zell-Zusatzkameras erfolgt.
  Echte OAK-/SDK-Einstellungen dabei nicht geändert.

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
