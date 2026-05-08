import yt_dlp
import sys
import os
import re
from urllib.parse import urlparse, parse_qs, unquote

def extract_nested_url(url):
    """
    Scans the provided URL for nested video links in query parameters.
    Example: site.com/play?file=https://source.com/video.m3u8
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    
    for key, values in query_params.items():
        for val in values:
            # Decode the URL (e.g., %3A to :)
            decoded_val = unquote(val)
            # Check if the parameter contains a common video extension
            if any(ext in decoded_val.lower() for ext in ['.m3u8', '.mp4', '.ts', '.mpd']):
                return decoded_val
    return None

def download_video(url):
    # Try to find a hidden link first
    hidden_url = extract_nested_url(url)
    target_url = hidden_url if hidden_url else url

    if hidden_url:
        print(f"[*] Detected nested video source: {hidden_url}")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': './%(title)s.%(ext)s',
        'noplaylist': True,
        # Added headers to mimic a real browser to bypass some blocks
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'referer': url, 
        'quiet': False,
        'no_warnings': False,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }

    print(f"\n[!] Analyzing URL: {target_url}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info
            info = ydl.extract_info(target_url, download=True)
            print(f"\n[SUCCESS] Saved: {info.get('title', 'video')}.mp4")

    except Exception as e:
        # If the specific extracted URL fails, try one last generic attempt
        print(f"\n[ERROR] Primary download failed.")
        print(f"[DEBUG] Error details: {str(e)[:200]}...")
        
        if not hidden_url:
            print("\n[TIP] This site might be using a protected player. Try finding the .m3u8 link in 'Network' tab of a browser and paste that directly.")

def main():
    os.system('clear')
    print("========================================")
    print("      Termux Video Downloader Pro v2    ")
    print("      (Nested URL & m3u8 Support)       ")
    print("========================================\n")

    user_input = input("Enter the webpage URL: ").strip()

    if not user_input.startswith(("http://", "https://")):
        print("[!] Error: Invalid URL.")
        return

    download_video(user_input)

if __name__ == "__main__":
    main()
