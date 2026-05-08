#!/usr/bin/env python3
"""
vidge - Universal Video Downloader for Termux
Author: Termux Video Tool
Description: Extracts and downloads video from any webpage using
             yt-dlp + custom fallback extractors.
Usage: python vidge.py [URL] [options]
"""

import argparse
import os
import re
import sys
import time
import subprocess
from urllib.parse import urlparse, parse_qs, unquote
from pathlib import Path

# External libraries
try:
    import requests
    from bs4 import BeautifulSoup
    import yt_dlp
    from rich.console import Console
    from rich.table import Table
    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
    from rich.prompt import Prompt, Confirm
    from rich.panel import Panel
    from rich import print as rprint
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install requests beautifulsoup4 yt-dlp rich")
    sys.exit(1)

# ------------------ Configuration ------------------
USER_AGENT = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
M3U8_PATTERN = re.compile(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)')
MP4_PATTERN  = re.compile(r'(https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*)')
console = Console()
# ---------------------------------------------------

class VideoDownloader:
    def __init__(self, url, output_path=None, format_choice='best', verbose=False):
        self.url = url
        self.output_path = output_path or os.getcwd()
        self.format_choice = format_choice
        self.verbose = verbose
        self._sanitize_output_path()

    def _sanitize_output_path(self):
        """Ensure output directory exists."""
        Path(self.output_path).mkdir(parents=True, exist_ok=True)

    def _progress_hook(self, d):
        """Rich progress display for yt-dlp downloads."""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            speed = d.get('_speed_str', 'N/A').strip()
            eta = d.get('_eta_str', 'N/A').strip()
            console.print(f"\r[bold cyan]⬇ Downloading:[/] {percent} | [green]{speed}[/] | ETA: [yellow]{eta}[/]", end='')
        elif d['status'] == 'finished':
            console.print("\n[bold green]✅ Download finished. Processing...[/]")

    def _is_valid_url(self):
        """Basic URL validation."""
        parsed = urlparse(self.url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)

    def fetch_page(self):
        """Download page HTML."""
        try:
            resp = requests.get(self.url, headers={'User-Agent': USER_AGENT}, timeout=15)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            console.print(f"[red]❌ Failed to fetch page: {e}[/]")
            return None

    def extract_from_html(self, html):
        """Extract video URLs from HTML using BeautifulSoup."""
        soup = BeautifulSoup(html, 'html.parser')
        video_urls = []

        # <video> tags
        for video in soup.find_all('video'):
            src = video.get('src')
            if src:
                video_urls.append(src)
            for source in video.find_all('source'):
                src = source.get('src')
                if src:
                    video_urls.append(src)

        # Regex search for m3u8/mp4 in scripts
        text = html
        video_urls.extend(M3U8_PATTERN.findall(text))
        video_urls.extend(MP4_PATTERN.findall(text))

        # Also check URL query parameters for encoded video links
        parsed = urlparse(self.url)
        query_params = parse_qs(parsed.query)
        for values in query_params.values():
            for val in values:
                decoded = unquote(val)
                if '.m3u8' in decoded or '.mp4' in decoded:
                    video_urls.append(decoded)

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for u in video_urls:
            if u not in seen:
                seen.add(u)
                unique_urls.append(u)
        return unique_urls

    def download_with_ytdlp(self, url=None):
        """Primary method: use yt-dlp."""
        target = url or self.url
        ydl_opts = {
            'outtmpl': os.path.join(self.output_path, '%(title)s.%(ext)s'),
            'format': self.format_choice,
            'merge_output_format': 'mp4',
            'user_agent': USER_AGENT,
            'progress_hooks': [self._progress_hook],
            'quiet': not self.verbose,
            'no_warnings': not self.verbose,
            'noplaylist': True,
            'continuedl': True,          # resume partial downloads
            'retries': 10,
            'fragment_retries': 10,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                console.print("[bold blue]🔍 Analyzing with yt-dlp...[/]")
                info = ydl.extract_info(target, download=False)
                if not info:
                    return False
                console.print(f"[green]✅ Recognized: {info.get('title', 'Unknown')}[/]")
                ydl.download([target])
                return True
        except yt_dlp.utils.DownloadError as e:
            console.print(f"[yellow]⚠️ yt-dlp failed: {e}[/]")
            return False
        except Exception as e:
            console.print(f"[red]❌ Unexpected error: {e}[/]")
            return False

    def download_m3u8_with_ffmpeg(self, m3u8_url):
        """Fallback: direct HLS download with ffmpeg."""
        output_file = os.path.join(self.output_path, f"video_{int(time.time())}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-user_agent", USER_AGENT,
            "-i", m3u8_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            output_file
        ]
        console.print("[bold blue]🎬 Converting HLS stream with ffmpeg...[/]")
        try:
            # Use subprocess with real-time output (optional)
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
            for line in proc.stdout:
                if self.verbose:
                    console.print(line.strip())
                # Simple progress indicator
                if "time=" in line:
                    console.print(".", end="")
            proc.wait()
            if proc.returncode == 0:
                console.print(f"\n[bold green]✅ HLS download complete! Saved as: {output_file}[/]")
                return True
            else:
                console.print(f"[red]❌ ffmpeg failed with code {proc.returncode}[/]")
                return False
        except Exception as e:
            console.print(f"[red]❌ ffmpeg error: {e}[/]")
            return False

    def list_formats(self, url=None):
        """Display available formats using yt-dlp."""
        target = url or self.url
        ydl_opts = {
            'listformats': True,
            'quiet': True,
            'no_warnings': True,
            'user_agent': USER_AGENT,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(target, download=False)
                formats = info.get('formats', [])
                if not formats:
                    console.print("[yellow]No formats found via yt-dlp.[/]")
                    return None

                table = Table(title="Available Formats", show_header=True, header_style="bold magenta")
                table.add_column("ID", style="cyan")
                table.add_column("Extension", style="green")
                table.add_column("Resolution", style="yellow")
                table.add_column("Filesize", style="blue")
                table.add_column("Note", style="white")

                for f in formats:
                    format_id = f.get('format_id', 'N/A')
                    ext = f.get('ext', 'N/A')
                    resolution = f.get('resolution', 'audio only' if f.get('acodec') != 'none' and f.get('vcodec') == 'none' else 'unknown')
                    filesize = f.get('filesize')
                    if filesize:
                        filesize = f"{filesize / 1024 / 1024:.1f} MB"
                    else:
                        filesize = "unknown"
                    note = f.get('format_note', '')
                    table.add_row(format_id, ext, resolution, filesize, note)

                console.print(table)
                return formats
        except Exception as e:
            console.print(f"[red]Failed to list formats: {e}[/]")
            return None

    def run(self):
        """Main orchestration."""
        if not self._is_valid_url():
            console.print("[red]❌ Invalid URL. Must start with http:// or https://[/]")
            return False

        console.print(Panel.fit(f"[bold]📥 Processing: {self.url}[/]", border_style="blue"))

        # 1. Try yt-dlp first
        if self.download_with_ytdlp():
            return True

        # 2. Fallback to custom extraction
        console.print("[bold yellow]🔄 yt-dlp failed, trying custom extraction...[/]")
        html = self.fetch_page()
        if not html:
            return False

        video_urls = self.extract_from_html(html)
        if not video_urls:
            console.print("[red]❌ No video links found in page.[/]")
            return False

        console.print(f"[green]🔗 Found {len(video_urls)} potential video source(s).[/]")
        for idx, vurl in enumerate(video_urls):
            console.print(f"  {idx+1}. {vurl[:100]}...")

        # If multiple, let user choose
        chosen_url = video_urls[0]
        if len(video_urls) > 1:
            choice = Prompt.ask("Select URL number (or 'q' to quit)", default="1")
            if choice.lower() == 'q':
                return False
            try:
                chosen_url = video_urls[int(choice)-1]
            except:
                console.print("[red]Invalid selection, using first.[/]")

        # If m3u8, use ffmpeg; else try yt-dlp again with direct URL
        if '.m3u8' in chosen_url:
            return self.download_m3u8_with_ffmpeg(chosen_url)
        else:
            return self.download_with_ytdlp(chosen_url)

def main():
    parser = argparse.ArgumentParser(
        description="vidge - Universal Video Downloader for Termux",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vidge.py https://example.com/video
  python vidge.py -f bestvideo+bestaudio https://youtube.com/...
  python vidge.py -o ~/storage/downloads -f 22 https://youtu.be/...
        """
    )
    parser.add_argument('url', nargs='?', help='Webpage URL containing video')
    parser.add_argument('-o', '--output', default='.', help='Output directory (default: current)')
    parser.add_argument('-f', '--format', default='best', help='Format selection (yt-dlp format string)')
    parser.add_argument('-l', '--list-formats', action='store_true', help='List available formats and exit')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    args = parser.parse_args()

    # If no URL provided, prompt interactively
    url = args.url
    if not url:
        url = Prompt.ask("[bold cyan]🔗 Enter webpage URL[/]")

    downloader = VideoDownloader(url, output_path=args.output, format_choice=args.format, verbose=args.verbose)

    if args.list_formats:
        downloader.list_formats()
        sys.exit(0)

    success = downloader.run()
    if success:
        console.print(Panel.fit("[bold green]🎉 All done! Video saved.[/]", border_style="green"))
    else:
        console.print(Panel.fit("[bold red]❌ Download failed. Check your URL or try manual extraction.[/]", border_style="red"))
        sys.exit(1)

if __name__ == "__main__":
    main()
