#!/data/data/com.termux/files/usr/bin/python3
# -*- coding: utf-8 -*-

"""
Termux Video Downloader Pro v3 – Interactive & Advanced Media Extractor
Downloads videos from ANY website with smart fallback, format selection, and more.

INSTALLATION (Termux):
----------------------------------------------------------------------
pkg update && pkg upgrade -y
pkg install python ffmpeg -y
pip install yt-dlp
termux-setup-storage   # Grant storage access (optional)
----------------------------------------------------------------------

Usage: Simply run `python vid.py` and follow the interactive prompts.
"""

import os
import sys
import re
import time
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote, urljoin

# ANSI colors
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'

# ----------------------------------------------------------------------
# Utility functions
# ----------------------------------------------------------------------
def is_termux():
    return os.path.isdir('/data/data/com.termux') or 'PREFIX' in os.environ and '/com.termux' in os.environ['PREFIX']

def check_ffmpeg():
    return shutil.which('ffmpeg') is not None

def human_size(num_bytes):
    if num_bytes is None:
        return '?'
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TiB"

def extract_nested_url(url):
    """Recursively extract media URL from query parameters."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ['url', 'src', 'video', 'source', 'file']:
        if key in query:
            candidate = unquote(query[key][0])
            if any(ext in candidate.lower() for ext in ['.m3u8', '.mp4', '.ts', '.mkv', '.webm', '.mpd']):
                # Check if candidate itself contains nested URL
                deeper = extract_nested_url(candidate)
                return deeper if deeper else candidate
    return None

def fetch_page_html(url, headers=None, timeout=10):
    import urllib.request
    if headers is None:
        headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36'}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except:
        return None

def extract_media_from_html(html, base_url):
    patterns = [
        r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.ts[^\s"\'<>]*)',
        r'(https?://[^\s"\'<>]+\.mkv[^\s"\'<>]*)',
        r'https?://[^\s"\'<>]+\.cloudfront\.net[^\s"\'<>]*',
        r'src\s*=\s*["\']([^"\']+\.(?:m3u8|mp4|ts|mkv)[^"\']*)',
    ]
    found = set()
    for pat in patterns:
        for match in re.findall(pat, html, re.I):
            if not match.startswith('http'):
                match = urljoin(base_url, match)
            found.add(match)
    return list(found)

def download_with_ffmpeg(url, output_path, headers=None):
    cmd = ['ffmpeg', '-y']
    if headers:
        for k, v in headers.items():
            cmd.extend(['-headers', f'{k}: {v}'])
    cmd.extend(['-i', url, '-c', 'copy', str(output_path)])
    try:
        subprocess.run(cmd, check=True, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

# ----------------------------------------------------------------------
# Main interactive downloader
# ----------------------------------------------------------------------
class InteractiveDownloader:
    def __init__(self):
        self.output_dir = self._get_output_dir()
        self.custom_headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36',
            'Referer': ''
        }
        self.ydl_opts_base = {
            'outtmpl': str(self.output_dir / '%(title)s.%(ext)s'),
            'progress_hooks': [self._progress_hook],
            'quiet': False,
            'no_warnings': False,
            'continuedl': True,
            'retries': 10,
            'fragment_retries': 10,
            'merge_output_format': 'mp4',
            'geo_bypass': True,
            'throttledratelimit': None,
            'user_agent': self.custom_headers['User-Agent'],
        }
        self.last_downloaded_file = None

    def _get_output_dir(self):
        if is_termux():
            storage = Path.home() / 'storage' / 'downloads'
            return storage if storage.exists() else Path.home() / 'Downloads'
        return Path.cwd() / 'downloads'

    def _progress_hook(self, d):
        if d['status'] == 'downloading':
            pct = d.get('_percent_str', '?').strip()
            speed = d.get('_speed_str', '?').strip()
            eta = d.get('_eta_str', '?').strip()
            name = Path(d.get('filename', '')).name
            print(f"\r⬇️  {Colors.CYAN}{pct}{Colors.RESET} @ {Colors.YELLOW}{speed}{Colors.RESET} ETA {eta}  {name}", end='')
            sys.stdout.flush()
        elif d['status'] == 'finished':
            print()
            self.last_downloaded_file = d.get('filename')
            print(f"{Colors.GREEN}✅ Downloaded: {self.last_downloaded_file}{Colors.RESET}")

    def _print(self, msg, color=Colors.RESET, bold=False):
        prefix = Colors.BOLD if bold else ''
        print(f"{prefix}{color}{msg}{Colors.RESET}")

    def _input(self, prompt):
        return input(f"{Colors.YELLOW}{prompt}{Colors.RESET}").strip()

    def _display_formats(self, info):
        formats = info.get('formats', [])
        if not formats:
            self._print("No formats found.", Colors.YELLOW)
            return
        print(f"\n{Colors.BOLD}{Colors.MAGENTA}📋 Available formats:{Colors.RESET}")
        print(f"{'ID':<6} {'Ext':<6} {'Resolution':<12} {'Codec':<10} {'Size':<10} {'Audio':<5} {'Note'}")
        print("-" * 80)
        for f in formats:
            fid = f.get('format_id', 'N/A')
            ext = f.get('ext', 'N/A')
            res = f.get('resolution', 'audio only' if f.get('vcodec')=='none' else f'{f.get("height","?")}p')
            vcodec = (f.get('vcodec','none') or 'none')[:8]
            acodec = f.get('acodec','none')
            size = human_size(f.get('filesize') or f.get('filesize_approx'))
            audio = '✔' if acodec != 'none' else '✘'
            note = f.get('format_note', '')
            color = Colors.YELLOW if f.get('vcodec')=='none' else (Colors.BLUE if f.get('acodec')=='none' else Colors.GREEN)
            line = f"{fid:<6} {ext:<6} {res:<12} {vcodec:<10} {size:<10} {audio:<5} {note}"
            print(f"{color}{line}{Colors.RESET}")

    def _choose_format_interactive(self, info):
        self._display_formats(info)
        default = 'bestvideo+bestaudio/best'
        choice = self._input(f"Enter format ID (or press Enter for '{default}'): ")
        return choice if choice else default

    def _extract_info_safe(self, url, ydl_opts):
        import yt_dlp
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            self._print(f"⚠️  yt-dlp extraction failed: {e}", Colors.YELLOW)
            return None

    def _download_with_ytdlp(self, url, ydl_opts):
        import yt_dlp
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            return True
        except Exception as e:
            self._print(f"❌ Download failed: {e}", Colors.RED)
            return False

    def process_url(self, url):
        original_url = url
        self.custom_headers['Referer'] = original_url

        # Step 1: Extract nested URL if any
        nested = extract_nested_url(url)
        target_url = nested if nested else url
        if nested:
            self._print(f"🔀 Extracted media URL: {nested}", Colors.CYAN)

        # Step 2: Try yt-dlp extraction
        self._print(f"\n🔍 Analyzing: {target_url}", Colors.CYAN)
        ydl_opts = self.ydl_opts_base.copy()
        ydl_opts['http_headers'] = self.custom_headers

        info = self._extract_info_safe(target_url, ydl_opts)
        if info is None and target_url != original_url:
            self._print("🔄 Retrying with original URL...", Colors.YELLOW)
            info = self._extract_info_safe(original_url, ydl_opts)

        # Step 3: If extraction failed, try fallback scraping
        if info is None:
            self._print("🔎 Attempting fallback page scraping...", Colors.BLUE)
            html = fetch_page_html(original_url, headers=self.custom_headers)
            if html:
                media_urls = extract_media_from_html(html, original_url)
                if media_urls:
                    self._print(f"Found {len(media_urls)} potential media URL(s)", Colors.CYAN)
                    for idx, mu in enumerate(media_urls, 1):
                        self._print(f"   • {mu}", Colors.WHITE)
                        # Try each
                        if mu.endswith('.m3u8'):
                            out_file = self.output_dir / f"stream_{int(time.time())}.mp4"
                            if download_with_ffmpeg(mu, out_file, headers=self.custom_headers):
                                self._print(f"✅ Downloaded via FFmpeg: {out_file}", Colors.GREEN)
                                return
                        else:
                            if self._download_with_ytdlp(mu, ydl_opts):
                                return
            self._print("❌ All methods failed.", Colors.RED)
            return

        # Step 4: Show info and choose format
        title = info.get('title', 'Unknown')
        duration = info.get('duration', 0)
        dur_str = f"{duration//60}:{duration%60:02d}" if duration else '?'
        self._print(f"🎬 Title   : {title}", Colors.BOLD)
        self._print(f"⏱️  Duration: {dur_str}", Colors.WHITE)

        # Interactive options
        print()
        self._print("Choose download mode:", Colors.MAGENTA)
        print("  1. Best video+audio (default)")
        print("  2. Audio only")
        print("  3. Select specific format")
        mode = self._input("Enter choice (1/2/3) [1]: ") or '1'

        if mode == '2':
            ydl_opts['format'] = 'bestaudio/best'
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        elif mode == '3':
            fmt = self._choose_format_interactive(info)
            ydl_opts['format'] = fmt
        else:
            ydl_opts['format'] = 'bestvideo+bestaudio/best'

        # Step 5: Download
        self._print("⬇️  Starting download...", Colors.GREEN)
        if self._download_with_ytdlp(target_url, ydl_opts):
            # Try to show direct URL
            final_info = self._extract_info_safe(target_url, ydl_opts)
            if final_info:
                direct = final_info.get('url') or final_info.get('webpage_url')
                if direct:
                    self._print(f"🔗 Direct URL: {direct}", Colors.BLUE)

    def batch_download(self, file_path):
        path = Path(file_path).expanduser()
        if not path.exists():
            self._print(f"File not found: {path}", Colors.RED)
            return
        with open(path) as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        self._print(f"📄 Batch: {len(urls)} URLs", Colors.CYAN)
        for idx, url in enumerate(urls, 1):
            self._print(f"\n[{idx}/{len(urls)}] Processing...", Colors.BOLD+Colors.MAGENTA)
            self.process_url(url)

def main():
    os.system('clear')
    print(f"{Colors.BOLD}{Colors.CYAN}========================================")
    print("   Termux Video Downloader Pro v3")
    print("   (Interactive • All Formats • Smart Fallback)")
    print(f"========================================{Colors.RESET}\n")

    if not check_ffmpeg():
        print(f"{Colors.RED}❌ ffmpeg not found! Install with: pkg install ffmpeg{Colors.RESET}")
        sys.exit(1)

    downloader = InteractiveDownloader()
    print(f"📁 Download folder: {downloader.output_dir}\n")

    # Main menu
    print("Select mode:")
    print("  1. Single URL download")
    print("  2. Batch download (from file)")
    choice = downloader._input("Enter choice (1/2) [1]: ") or '1'

    if choice == '2':
        file_path = downloader._input("Enter path to file containing URLs: ")
        downloader.batch_download(file_path)
    else:
        url = downloader._input("Enter the webpage/video URL: ")
        if not url.startswith(('http://', 'https://')):
            print(f"{Colors.RED}Invalid URL.{Colors.RESET}")
            return
        downloader.process_url(url)

    print(f"\n{Colors.GREEN}Done!{Colors.RESET}")

if __name__ == "__main__":
    main()
