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

## Hinweis

Die Seite hat keinen eigenen Passwortschutz. Nicht ungeschützt aus dem Internet erreichbar machen.
