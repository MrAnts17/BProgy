BProgy Projekt WZ5.py

1. Wasserzeichen hinzufügen 

    Textbasierte Wasserzeichen  mit:
        Frei wählbarem Text  (z. B. Copyright-Hinweise)
        Schriftartauswahl  (Systemfonts oder Fallback auf Standard)
        Größenanpassung  (Slider von 8–200px)
        Deckkraftregelung  (0–100%)
        Farbauswahl  (via Colorpicker)
        
    

2. Interaktive Vorschau 

    Echtzeit-Vorschau  des ersten Videos mit positionierbarem Wasserzeichen
    Drag-and-Drop-Positionierung  des Wasserzeichens auf dem Canvas
    Skalierung  des Vorschaubildes zur besseren Platzierung
    

3. Batch-Verarbeitung 

    Mehrere Videos gleichzeitig  verarbeiten (Dateiauswahl via Dialog)
    Hintergrundverarbeitung  via Threading (GUI bleibt responsiv)
    Fortschrittsanzeige  (Progressbar + Statusupdates)
    

4. Technische Features 

    FFmpeg-Integration  für Video-Processing (H.264/x264 Encoding)
    GPU-Beschleunigung  (optional via h264_nvenc für NVIDIA-GPUs)
    Plattformübergreifend  (Windows/Linux/macOS)
    DPI-Awareness  für hochauflösende Displays (Windows)
    Speicheroptimierung  (explizites Schließen von Video-Clips + Garbage Collection)
    

5. Fehlerbehandlung 

    Klare Fehlermeldungen  bei:
        Fehlendem FFmpeg
        Schlechten Video-Dateien
        Schreibschutz im Ausgabeordner
        Nicht unterstützten Schriftarten
        
    Automatische Fehlerprotokollierung  in der Konsole
    

6. Systemvoraussetzungen 

    Python 3.10+  mit Paketen:
        moviepy
        imageio-ffmpeg
        numpy
        Pillow
        
    FFmpeg-Installation  (optional manueller Pfad)
    GPU-Treiber  (falls NVIDIA-Encoding genutzt wird)
    

7. Besonderheiten 

    Positionierungsgenauigkeit :
        Das Wasserzeichen behält seine relative Position bei unterschiedlichen Videoauflösungen
        Automatische Begrenzung innerhalb des Video-Bereichs
        
    Kompatibilität :
        Ausgabe im MP4-Format mit yuv420p-Farbraum (läuft auf allen Geräten)
        -movflags +faststart für Web-Streaming
        
    

Ablauf 

    Videos auswählen  → 2. Wasserzeichen konfigurieren  → 3. Ausgabeordner festlegen  → 4. Vorschau anpassen  → 5. Batch-Verarbeitung starten
    

Zielgruppe : Content-Ersteller, die schnell und einfach visuelle Markierungen  (z. B. Logos/Branding) auf mehreren Videos gleichzeitig anbringen möchten.
