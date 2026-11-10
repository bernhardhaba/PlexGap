<p align="center"><img src="logo.webp" alt="PlexGap" width="480"></p>

# PlexGap

Findet fehlende Serienfolgen in deiner Plex-Bibliothek. Die App meldet sich per Plex-PIN an,
liest die vorhandenen Folgen aus Plex und vergleicht sie mit den Episodenlisten von
[TVmaze](https://www.tvmaze.com/api) (kein API-Key nötig). Nur Python 3, keine Zusatzpakete.

## Starten (lokal)

```bash
python server.py
```

Dann http://localhost:8765 öffnen, bei Plex anmelden, Serveradresse (z. B. `http://192.168.2.20:32400`)
eintragen und auf „Prüfen“ klicken.

- Specials (Staffel 0) und noch nicht ausgestrahlte Folgen zählen nicht als fehlend.
- Das letzte Ergebnis wird in `last_result.json` gespeichert; „Fortsetzen“ macht nach einem Stopp weiter.
- Ergebnis löschen: komplett oder pro Serie (✕).

## Als LXC (Proxmox)

1. Container anlegen (Debian 12) und `server.py`, `index.html`, `install-lxc.sh` hineinkopieren.
2. Im Container als root: `bash install-lxc.sh`
3. Erreichbar unter `http://<Container-IP>:8765`

`proxmox-template.sh` enthält ein Setup-Skript für den Proxmox-Host (legt den Container an, startet
die Installation). Daraus erzeugt man ein Einzel-Skript, indem man die Platzhalter `@@SERVER_PY@@`,
`@@INDEX_HTML@@` und `@@INSTALL_SH@@` durch die Base64-Inhalte der jeweiligen Dateien ersetzt.

## Docker / Synology

Mit der mitgelieferten `docker-compose.yml` läuft PlexGap ohne weitere Installation:

```bash
docker compose up -d
```

Auf einer Synology (DSM 7.2 oder neuer): In **Container Manager → Projekt → Erstellen** einen Ordner
wählen (z. B. `/volume1/docker/plexgap`), die `docker-compose.yml` dort ablegen bzw. einfügen und das
Projekt starten. Beim ersten Start lädt der Container die App selbst von GitHub in den Unterordner `data`;
Ergebnisse, Ausgeblendete und Verlauf liegen ebenfalls dort und bleiben bei Neustarts erhalten.
Erreichbar unter `http://<Synology-IP>:8765`.

Ohne Docker: im Paket-Zentrum „Python 3“ installieren und im Aufgabenplaner eine Aufgabe „Beim Hochfahren“
anlegen: `cd /volume1/plexgap && HOST=0.0.0.0 HEADLESS=1 python3 server.py`.

## Automatisches Update

Im LXC läuft PlexGap mit `PLEXGAP_AUTOUPDATE=1`: Beim Start und danach alle 6 Stunden prüft die App den
Branch `main` dieses Repos und lädt `server.py` und `index.html` bei Änderungen selbst nach (mit
Plausibilitätsprüfung, Sicherung als `*.bak`, anschließendem Neustart; laufende Prüfungen werden nicht
unterbrochen). Lokal ist das Auto-Update aus; unten auf der Seite gibt es „Nach Update suchen“.
Das Repo muss dafür öffentlich sein. Wer in `main` pushen darf, bestimmt damit, was im Container läuft.

## Datenschutz

PlexGap läuft komplett bei dir und sendet keine Daten an den Entwickler. Es gibt kein Tracking und keine Statistik.

- **Plex:** Die Anmeldung läuft über `plex.tv` (PIN-Login), die Bibliothek liest die App von deinem Plex-Server.
- **TVmaze:** Zum Abgleich werden Serientitel bzw. IDs (TVDB/IMDb) an `api.tvmaze.com` gesendet.
- **GitHub:** Das Auto-Update fragt `github.com` ab (dabei sieht GitHub die IP-Adresse deiner Installation). Ohne `PLEXGAP_AUTOUPDATE=1` passiert das nur auf Knopfdruck.
- **Speicherung:** Der Plex-Token liegt im Browser (`localStorage`), Ergebnisse, Ausgeblendete und Verlauf als Dateien im App-Ordner auf deinem Server.

## Hinweis

Die Seite hat keinen eigenen Passwortschutz. Nicht ungeschützt aus dem Internet erreichbar machen.
