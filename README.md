# Laufdaten

Kleine Webanwendung, um GPS-Laufdaten aus der StatSports-App von Hand zu erfassen und grafisch auszuwerten: Höchstgeschwindigkeit, Laufleistung, HSR-, Sprint- und High-Intensity-Distanz, Sprints, Beschleunigungen, Heatmaps je Halbzeit – pro Spielerin und Spiel.

## Aufbau

- **`docs/index.html`** – die Webanwendung. Läuft in zwei Modi:
  - **Team-Seite** (GitHub Pages): liest die verschlüsselten Daten aus `docs/data/` und entschlüsselt sie im Browser mit dem Team-Passwort (AES-GCM, Schlüssel per PBKDF2-SHA256).
  - **Eingabe** (lokal über `admin.py`): Daten erfassen, bearbeiten und veröffentlichen.
- **`admin.py`** – lokaler Server (nur `127.0.0.1`, nur Python-Standardbibliothek). Speichert die Daten unverschlüsselt im Ordner `daten/` und schreibt beim Veröffentlichen die verschlüsselte Kopie nach `docs/data/`, committet und pusht.
- **`Eingabe starten.bat`** – startet `admin.py` unter Windows.
- **Sicherung:** `daten/` ist ein eigenes Git-Repository mit einem separaten, privaten Remote. `admin.py` committet und pusht dorthin automatisch (alle 5 Minuten bei Änderungen, bei jedem Veröffentlichen und per Knopf).

## Datenschutz

Unverschlüsselte Daten (`daten/`, Sicherungen, Exporte) sind per `.gitignore` ausgeschlossen. Im Repository liegen nur verschlüsselte Dateien; ohne Team-Passwort sind sie nicht lesbar.

Bedienung: siehe `Anleitung.txt`.
