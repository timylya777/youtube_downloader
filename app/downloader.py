import os
import sys
import re
import yt_dlp
import urllib.request
import zipfile
import io
from typing import Dict, Any, List, Callable

ffmpeg_download_active = False

def get_ffmpeg_path():
    # If application is compiled with PyInstaller
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        # If run as python file in D:\.code\youtube downloader\app\downloader.py
        base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    bin_path = os.path.join(base_path, 'bin')
    return bin_path

def download_ffmpeg() -> bool:
    global ffmpeg_download_active
    if ffmpeg_download_active:
        return False
        
    ffmpeg_download_active = True
    try:
        bin_dir = get_ffmpeg_path()
        os.makedirs(bin_dir, exist_ok=True)
        
        ffmpeg_exe = os.path.join(bin_dir, 'ffmpeg.exe')
        ffprobe_exe = os.path.join(bin_dir, 'ffprobe.exe')
        
        if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
            ffmpeg_download_active = False
            return True
            
        url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
        zip_path = os.path.join(bin_dir, 'ffmpeg.zip')
        
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        
        print("Starting download of FFmpeg Essentials...")
        sys.stdout.flush()
        
        with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
            meta = response.info()
            file_size_str = meta.get("Content-Length")
            file_size = int(file_size_str) if file_size_str else 0
            
            downloaded = 0
            block_size = 1024 * 1024 # 1MB
            
            while True:
                buffer = response.read(block_size)
                if not buffer:
                    break
                out_file.write(buffer)
                downloaded += len(buffer)
                if file_size > 0:
                    percent = (downloaded / file_size) * 100
                    print(f"Downloaded {downloaded / 1024 / 1024:.2f} MB / {file_size / 1024 / 1024:.2f} MB ({percent:.1f}%)")
                else:
                    print(f"Downloaded {downloaded / 1024 / 1024:.2f} MB")
                sys.stdout.flush()
                
        print("Download finished. Extracting...")
        sys.stdout.flush()
        
        with zipfile.ZipFile(zip_path) as z:
            for file_info in z.infolist():
                if file_info.filename.endswith('ffmpeg.exe') or file_info.filename.endswith('ffprobe.exe'):
                    filename = os.path.basename(file_info.filename)
                    target_path = os.path.join(bin_dir, filename)
                    with z.open(file_info) as source, open(target_path, 'wb') as target:
                        target.write(source.read())
                    print(f"Extracted: {filename}")
                    sys.stdout.flush()
                    
        # Remove temporary zip file
        try:
            os.remove(zip_path)
        except Exception:
            pass
            
        ffmpeg_download_active = False
        return os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe)
    except Exception as e:
        print(f"Error downloading FFmpeg: {e}")
        sys.stdout.flush()
        ffmpeg_download_active = False
        return False


def sanitize_filename(filename: str) -> str:
    # Remove chars that are illegal in Windows/macOS/Linux file names
    # Windows: \ / : * ? " < > |
    sanitized = re.sub(r'[\\/*?:"<>|]', '', filename)
    # Remove extra spaces
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    return sanitized

def parse_artist_title(title: str, uploader: str) -> (str, str):
    # Clean up common video suffixes like "(Official Video)", "[Official Audio]", etc.
    cleaned_title = re.sub(
        r'\s*[\(\[][Vv]ideo|[Oo]fficial|[Mm]usic|[Ll]yric[s]?|[Hh]D|[4kK]|[1080p]|[Aa]udio|[Vv]ideo|[Mm]/[Vv]|MV[\)\]]\s*',
        '', title
    )
    cleaned_title = re.sub(r'\s*\b(official|music|video|lyrics|mv|hd|audio)\b\s*', '', cleaned_title, flags=re.IGNORECASE)
    cleaned_title = cleaned_title.strip(" -()[]{}")
    
    artist = "Unknown Artist"
    track = cleaned_title
    
    # Split by standard separators
    if " - " in cleaned_title:
        parts = cleaned_title.split(" - ", 1)
        artist = parts[0].strip()
        track = parts[1].strip()
    elif " — " in cleaned_title:
        parts = cleaned_title.split(" — ", 1)
        artist = parts[0].strip()
        track = parts[1].strip()
    elif uploader:
        # If no clear separator, assume uploader (without " - Topic") is artist
        artist = uploader.replace(" - Topic", "").strip()
        track = cleaned_title
        
    return artist, track

def extract_playlist_info(playlist_url: str) -> Dict[str, Any]:
    # Extract playlist info in flat mode
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(playlist_url, download=False)
        except Exception as e:
            raise Exception(f"Не удалось загрузить плейлист: {str(e)}")
            
        if not info:
            raise Exception("Не удалось извлечь информацию о плейлисте.")
            
        playlist_title = info.get('title', 'Плейлист YouTube')
        entries = info.get('entries', [])
        
        parsed_entries = []
        for i, entry in enumerate(entries):
            if not entry:
                continue
            
            video_id = entry.get('id')
            title = entry.get('title')
            
            # Ignore private, deleted, blocked, or unavailable videos
            if not video_id or not title:
                continue
                
            title_lower = title.lower()
            if "[private video]" in title_lower or "[deleted video]" in title_lower or "deleted video" in title_lower or "private video" in title_lower:
                continue
                
            uploader = entry.get('uploader') or ''
            duration = entry.get('duration') # in seconds
            
            # Formatting duration
            duration_str = "00:00"
            if duration:
                mins = int(duration) // 60
                secs = int(duration) % 60
                duration_str = f"{mins:02d}:{secs:02d}"
                
            # Filter checks
            is_slowed = False
            slowed_warning = ""
            
            slowed_markers = ["slowed", "reverb", "slowed down", "slowed+reverb", "slowed & reverb"]
            for marker in slowed_markers:
                if marker in title_lower:
                    is_slowed = True
                    slowed_warning = f"Замедленная версия ({marker})"
                    break
                    
            is_long = False
            long_warning = ""
            if duration and duration > 600: # 10 minutes
                is_long = True
                long_warning = "Слишком длинное видео (> 10 мин)"
                
            artist, track = parse_artist_title(title, uploader)
            
            parsed_entries.append({
                'index': i + 1,
                'id': video_id,
                'title': title,
                'uploader': uploader,
                'artist': artist,
                'track': track,
                'duration': duration,
                'duration_str': duration_str,
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'is_slowed': is_slowed,
                'slowed_warning': slowed_warning,
                'is_long': is_long,
                'long_warning': long_warning,
                # Auto deselect if too long or slowed
                'selected': not (is_slowed or is_long)
            })
            
        return {
            'title': playlist_title,
            'tracks': parsed_entries
        }

def search_alternatives(original_title: str) -> List[Dict[str, Any]]:
    # Clean the title from slowed indicators
    clean_query = original_title
    slowed_patterns = [
        r'\(?\s*slowed\s*(?:&|\+)?\s*reverb\s*\)?',
        r'\[?\s*slowed\s*(?:&|\+)?\s*reverb\s*\]?',
        r'\b(?:slowed|reverb|slowed down|sped up|speed up)\b'
    ]
    for pattern in slowed_patterns:
        clean_query = re.sub(pattern, '', clean_query, flags=re.IGNORECASE)
    clean_query = re.sub(r'\s+', ' ', clean_query).strip(" -()[]{}")
    
    ydl_opts = {
        'extract_flat': True,
        'skip_download': True,
        'playlist_items': '1,2,3,4,5' # Top 5 results
    }
    
    search_url = f"ytsearch5:{clean_query}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(search_url, download=False)
            entries = info.get('entries', [])
            results = []
            for entry in entries:
                if not entry:
                    continue
                duration = entry.get('duration')
                duration_str = "00:00"
                if duration:
                    mins = int(duration) // 60
                    secs = int(duration) % 60
                    duration_str = f"{mins:02d}:{secs:02d}"
                    
                results.append({
                    'id': entry.get('id'),
                    'title': entry.get('title'),
                    'uploader': entry.get('uploader'),
                    'duration_str': duration_str,
                    'url': f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
            return results
        except Exception as e:
            print(f"Error searching alternatives: {e}")
            return []

def download_track(video_url: str, save_dir: str, artist: str, track: str, progress_fn: Callable[[Dict[str, Any]], None]) -> Dict[str, str]:
    ffmpeg_dir = get_ffmpeg_path()
    
    # Ensure save directory exists
    os.makedirs(save_dir, exist_ok=True)
    
    # We define a temporary template for the download first
    temp_template = os.path.join(save_dir, '%(id)s.%(ext)s')
    
    # We will build the final filepath AFTER extracting video info so we can resolve "Unknown Artist"
    context = {
        'filename': f"{artist} - {track}"
    }
            
    def ytdl_progress_hook(d):
        status_info = {
            'status': d['status'],
            'url': video_url,
            'filename': context['filename']
        }
        if d['status'] == 'downloading':
            # Extract percentage
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded_bytes = d.get('downloaded_bytes') or 0
            
            percent = 0.0
            if total_bytes > 0:
                percent = (downloaded_bytes / total_bytes) * 100.0
            else:
                # Parse percent string if available
                pct_str = d.get('_percent_str', '0%')
                pct_match = re.search(r'(\d+\.\d+|\d+)%', pct_str)
                if pct_match:
                    percent = float(pct_match.group(1))
            
            status_info.update({
                'percent': round(percent, 1),
                'speed': d.get('_speed_str', 'N/A').strip(),
                'eta': d.get('_eta_str', 'N/A').strip(),
                'downloaded_bytes': downloaded_bytes,
                'total_bytes': total_bytes
            })
        elif d['status'] == 'finished':
            status_info.update({
                'percent': 100.0,
                'msg': 'Конвертация в MP3...'
            })
        progress_fn(status_info)

    ydl_opts = {
        'format': 'bestaudio/best',
        'ffmpeg_location': ffmpeg_dir,
        'outtmpl': temp_template,
        'progress_hooks': [ytdl_progress_hook],
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320', # 320kbps as per requirements
        }],
        # Quiet output to not pollute console
        'quiet': True,
        'no_warnings': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        # Extract info (this downloads too)
        info = ydl.extract_info(video_url, download=True)
        video_id = info.get('id')
        
        # Resolve artist if "Unknown Artist"
        resolved_artist = artist
        if not artist or artist == "Unknown Artist":
            resolved_artist = info.get('artist') or info.get('uploader') or "Unknown Artist"
            resolved_artist = resolved_artist.replace(" - Topic", "").strip()
            
        resolved_track = track
        if not track or track == "Unknown Track" or track == "Без названия":
            resolved_track = info.get('track') or info.get('title') or "Unknown Track"
            # Clean up suffixes
            _, resolved_track = parse_artist_title(resolved_track, "")
            
        # Update filename in context for any late hook updates or logging
        context['filename'] = f"{resolved_artist} - {resolved_track}"
        
        # Build the final filepath
        final_filename = sanitize_filename(context['filename'])
        if not final_filename:
            final_filename = sanitize_filename(info.get('title') or video_id)
            
        final_filepath = os.path.join(save_dir, f"{final_filename}.mp3")
        
        # Remove existing file if any
        if os.path.exists(final_filepath):
            try:
                os.remove(final_filepath)
            except Exception:
                pass
        
        # After conversion, the file will be saved as {video_id}.mp3
        downloaded_mp3 = os.path.join(save_dir, f"{video_id}.mp3")
        
        # Rename it to our customized "Artist - Track.mp3"
        if os.path.exists(downloaded_mp3):
            os.replace(downloaded_mp3, final_filepath)
        else:
            # Sometimes it might not have been converted, check if the output exists or find it
            if not os.path.exists(final_filepath):
                potential_file = os.path.join(save_dir, f"{video_id}.mp3")
                if os.path.exists(potential_file):
                    os.replace(potential_file, final_filepath)
                else:
                    raise Exception("Файл MP3 не был создан конвертером.")
                    
        return {
            "filepath": final_filepath,
            "artist": resolved_artist,
            "track": resolved_track
        }
