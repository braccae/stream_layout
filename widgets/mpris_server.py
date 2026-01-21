#!/usr/bin/env python3
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import threading
import subprocess

class MPRISHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urlparse(self.path)

        if parsed_path.path == '/':
            # Serve the HTML file
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            html_content = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Now Playing</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
        href="https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap"
        rel="stylesheet"
    />
    <style>
        body {
            background: transparent;
            font-family: 'Press Start 2P', sans-serif; /* Change this to any font you prefer */
            margin: 0;
            padding: 20px;
            text-shadow:
                2px 2px 4px rgba(30, 32, 48, 0.8),
                1px 1px 2px rgba(24, 25, 38, 0.9);
        }

        .now-playing {
            max-width: 400px;
        }

        .track-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 8px;
            color: #c6a0f6;
        }

        .track-artist {
            font-size: 16px;
            opacity: 0.9;
            margin-bottom: 4px;
            color: #b7bdf8;
        }

        .track-album {
            font-size: 12px;
            opacity: 0.7;
            color: #8aadf4;
        }

        .no-player {
            font-size: 12px;
            opacity: 0.6;
            color: #a5adcb;
        }

        .header-title {
            font-size: 10px;
            opacity: 0.6;
            color: #f4dbd6;
        }

        /* You can easily change the font by modifying the CSS custom property */
        :root {
            --main-font: 'Press Start 2P', sans-serif;
            --title-font: 'Press Start 2P', sans-serif;
        }

        .track-title {
            font-family: var(--title-font);
        }

        .track-artist, .track-album {
            font-family: var(--main-font);
        }
    </style>
</head>
<body>
    <h3 class="header-title">Now Playing:</h3>
    <div class="now-playing" id="nowPlaying">
        <div class="no-player">No music playing</div>
    </div>

    <script>
        function updateNowPlaying() {
            fetch('/api/nowplaying')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('nowPlaying');

                    if (data.playing && data.title) {
                        container.innerHTML = `
                            <div class="track-title">${data.title}</div>
                            <div class="track-artist">${data.artist || 'Unknown Artist'}</div>
                            <div class="track-album">${data.album || ''}</div>
                        `;
                    } else {
                        container.innerHTML = '<div class="no-player">No music playing</div>';
                    }
                })
                .catch(error => {
                    console.error('Error fetching now playing data:', error);
                    document.getElementById('nowPlaying').innerHTML = '<div class="no-player">Error loading data</div>';
                });
        }

        // Update every 2 seconds
        setInterval(updateNowPlaying, 2000);
        // Initial load
        updateNowPlaying();
    </script>
</body>
</html>
            '''

            self.wfile.write(html_content.encode())

        elif parsed_path.path == '/api/nowplaying':
            # Serve the MPRIS data as JSON
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            mpris_data = get_mpris_data()
            self.wfile.write(json.dumps(mpris_data).encode())

        else:
            self.send_response(404)
            self.end_headers()

def get_mpris_data():
    """Get MPRIS data using dbus commands"""
    try:
        # Get list of MPRIS players
        result = subprocess.run([
            'dbus-send', '--session', '--dest=org.freedesktop.DBus',
            '--type=method_call', '--print-reply',
            '/org/freedesktop/DBus', 'org.freedesktop.DBus.ListNames'
        ], capture_output=True, text=True)

        # Find MPRIS players
        players = []
        for line in result.stdout.split('\n'):
            if 'org.mpris.MediaPlayer2.' in line:
                player = line.strip().split('"')[1]
                players.append(player)

        if not players:
            return {'playing': False, 'title': None, 'artist': None, 'album': None}

        # Use the first available player
        player = players[0]

        # Get playback status
        try:
            status_result = subprocess.run([
                'dbus-send', '--session', '--print-reply',
                f'--dest={player}',
                '/org/mpris/MediaPlayer2',
                'org.freedesktop.DBus.Properties.Get',
                'string:org.mpris.MediaPlayer2.Player',
                'string:PlaybackStatus'
            ], capture_output=True, text=True)

            is_playing = 'Playing' in status_result.stdout
        except:
            is_playing = False

        if not is_playing:
            return {'playing': False, 'title': None, 'artist': None, 'album': None}

        # Get metadata
        metadata_result = subprocess.run([
            'dbus-send', '--session', '--print-reply',
            f'--dest={player}',
            '/org/mpris/MediaPlayer2',
            'org.freedesktop.DBus.Properties.Get',
            'string:org.mpris.MediaPlayer2.Player',
            'string:Metadata'
        ], capture_output=True, text=True)

        # Parse the metadata (simplified parsing)
        title = extract_metadata_value(metadata_result.stdout, 'xesam:title')
        artist = extract_metadata_value(metadata_result.stdout, 'xesam:artist')
        album = extract_metadata_value(metadata_result.stdout, 'xesam:album')

        return {
            'playing': True,
            'title': title,
            'artist': artist,
            'album': album
        }

    except Exception as e:
        print(f"Error getting MPRIS data: {e}")
        return {'playing': False, 'title': None, 'artist': None, 'album': None}

def extract_metadata_value(text, key):
    """Extract metadata value from dbus output"""
    try:
        lines = text.split('\n')
        for i, line in enumerate(lines):
            if key in line:
                # Look for the value in subsequent lines
                for j in range(i+1, min(i+5, len(lines))):
                    if 'variant' in lines[j] and 'string' in lines[j]:
                        # Extract string value
                        parts = lines[j].split('"')
                        if len(parts) >= 2:
                            return parts[1]
                    elif 'array [' in lines[j]:
                        # Handle array (like artist)
                        for k in range(j+1, min(j+5, len(lines))):
                            if 'string' in lines[k] and '"' in lines[k]:
                                parts = lines[k].split('"')
                                if len(parts) >= 2:
                                    return parts[1]
        return None
    except:
        return None

def run_server(port=8888):
    """Run the HTTP server"""
    server = HTTPServer(('localhost', port), MPRISHandler)
    print(f"Server running on http://localhost:{port}")
    print("Open this URL in your browser to see the now playing display")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()

if __name__ == "__main__":
    run_server()
