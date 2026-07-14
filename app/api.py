import os
import sys
import asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import tkinter as tk
from tkinter import filedialog
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.downloader import (
    extract_playlist_info,
    search_alternatives,
    download_track,
    get_ffmpeg_path
)
from app.history import init_db, add_to_history, get_history, clear_history

# Initialize database
init_db()

app = FastAPI(title="YouTube Playlist Downloader API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global download state
class DownloadState:
    def __init__(self):
        self.is_running = False
        self.total_tracks = 0
        self.completed_tracks = 0
        self.failed_tracks = 0
        self.current_index = 0
        self.tracks_status: Dict[str, Dict[str, Any]] = {}
        self.errors: List[str] = []

download_state = DownloadState()

# Request schemas
class PlaylistRequest(BaseModel):
    url: str

class SearchRequest(BaseModel):
    title: str

class TrackItem(BaseModel):
    id: str
    url: str
    artist: str
    track: str
    title: str

class DownloadRequest(BaseModel):
    tracks: List[TrackItem]
    save_dir: str
    format_type: str = "mp3"
    quality: str = "320"
    playlist_title: str = "YouTube Downloads"
    archive: bool = False

# Helper to open folder dialog in background thread
def ask_directory_dialog(initial_dir: str = "") -> str:
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        # Determine initial directory
        init_path = initial_dir if initial_dir and os.path.exists(initial_dir) else os.path.expanduser("~")
        
        folder = filedialog.askdirectory(initialdir=init_path, title="Выберите папку для сохранения MP3")
        root.destroy()
        return folder
    except Exception as e:
        print(f"Error opening folder dialog: {e}")
        return ""

# Helper to package downloaded files into a zip archive
def create_zip_archive(save_dir: str, playlist_title: str, file_paths: List[str]) -> str:
    import zipfile
    from app.downloader import sanitize_filename
    safe_title = sanitize_filename(playlist_title) or "playlist_downloads"
    zip_filename = f"{safe_title}.zip"
    zip_path = os.path.join(save_dir, zip_filename)
    
    # Remove existing zip if any
    if os.path.exists(zip_path):
        try:
            os.remove(zip_path)
        except Exception:
            pass
            
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            if os.path.exists(file_path):
                zipf.write(file_path, os.path.basename(file_path))
                
    # Delete individual files after successful zipping
    for file_path in file_paths:
        if os.path.exists(file_path) and file_path != zip_path:
            try:
                os.remove(file_path)
            except Exception:
                pass
                
    return zip_path

# Background downloader queue runner
async def run_download_queue(tracks: List[TrackItem], save_dir: str, format_type: str, quality: str, playlist_title: str, archive: bool):
    global download_state
    download_state.is_running = True
    download_state.total_tracks = len(tracks)
    download_state.completed_tracks = 0
    download_state.failed_tracks = 0
    download_state.current_index = 0
    download_state.errors = []
    
    # Initialize track statuses
    for t in tracks:
        download_state.tracks_status[t.id] = {
            'id': t.id,
            'title': t.title,
            'artist': t.artist,
            'track': t.track,
            'status': 'pending', # pending, downloading, converting, completed, failed
            'percent': 0.0,
            'speed': 'N/A',
            'eta': 'N/A',
            'error': None
        }
        
    loop = asyncio.get_event_loop()
    
    downloaded_filepaths = []
    resolved_metadata = {} # map of track_id -> (resolved_artist, resolved_track, final_path)
    
    for idx, track in enumerate(tracks):
        download_state.current_index = idx + 1
        track_id = track.id
        download_state.tracks_status[track_id]['status'] = 'downloading'
        
        def progress_callback(info: Dict[str, Any]):
            status = info.get('status')
            if status == 'downloading':
                download_state.tracks_status[track_id].update({
                    'percent': info.get('percent', 0.0),
                    'speed': info.get('speed', 'N/A'),
                    'eta': info.get('eta', 'N/A')
                })
            elif status == 'finished':
                download_state.tracks_status[track_id].update({
                    'status': 'converting',
                    'percent': 100.0,
                    'speed': '0 B/s',
                    'eta': 'Готово'
                })

        try:
            # Run blocking download_track in executor
            result = await loop.run_in_executor(
                None,
                download_track,
                track.url,
                save_dir,
                track.artist,
                track.track,
                format_type,
                quality,
                progress_callback
            )
            
            final_path = result["filepath"]
            resolved_artist = result["artist"]
            resolved_track = result["track"]
            
            downloaded_filepaths.append(final_path)
            resolved_metadata[track_id] = (resolved_artist, resolved_track, final_path)
            
            # Update status with resolved metadata
            download_state.tracks_status[track_id].update({
                'status': 'completed',
                'percent': 100.0,
                'artist': resolved_artist,
                'track': resolved_track
            })
            download_state.completed_tracks += 1
            
        except Exception as e:
            error_msg = str(e)
            download_state.tracks_status[track_id].update({
                'status': 'failed',
                'error': error_msg
            })
            download_state.failed_tracks += 1
            download_state.errors.append(f"Ошибка {track.title}: {error_msg}")
            
    # Post-processing: Package into ZIP archive if requested
    final_save_path_map = {}
    if archive and downloaded_filepaths:
        try:
            # Update state messages
            for track_id in download_state.tracks_status:
                if download_state.tracks_status[track_id]['status'] == 'completed':
                    download_state.tracks_status[track_id].update({
                        'status': 'converting',
                        'eta': 'Упаковка в ZIP...'
                    })
                    
            zip_path = await loop.run_in_executor(
                None,
                create_zip_archive,
                save_dir,
                playlist_title,
                downloaded_filepaths
            )
            
            # Map all completed tracks to the zip path
            for track_id in download_state.tracks_status:
                if download_state.tracks_status[track_id]['status'] == 'completed':
                    final_save_path_map[track_id] = zip_path
                    download_state.tracks_status[track_id].update({
                        'status': 'completed',
                        'eta': 'В архиве'
                    })
        except Exception as e:
            download_state.errors.append(f"Не удалось создать архив: {str(e)}")
            # Fallback to individual file paths
            for track_id, info in resolved_metadata.items():
                final_save_path_map[track_id] = info[2] # final_path
    else:
        # Map to individual file paths
        for track_id, info in resolved_metadata.items():
            final_save_path_map[track_id] = info[2] # final_path
            
    # Add to history
    for track in tracks:
        track_id = track.id
        if track_id in resolved_metadata and download_state.tracks_status[track_id]['status'] == 'completed':
            resolved_artist, resolved_track, _ = resolved_metadata[track_id]
            final_path = final_save_path_map.get(track_id)
            await loop.run_in_executor(
                None,
                add_to_history,
                resolved_track,
                resolved_artist,
                track.url,
                final_path,
                format_type,
                quality
            )
            
    download_state.is_running = False

# API Routes

@app.post("/api/playlist-info")
async def get_playlist(request: PlaylistRequest):
    loop = asyncio.get_event_loop()
    try:
        info = await loop.run_in_executor(None, extract_playlist_info, request.url)
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/search-alternatives")
async def get_alternatives(request: SearchRequest):
    loop = asyncio.get_event_loop()
    try:
        results = await loop.run_in_executor(None, search_alternatives, request.title)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/select-folder")
async def select_folder(request: Dict[str, str] = None):
    initial_dir = request.get("current_path", "") if request else ""
    loop = asyncio.get_event_loop()
    selected = await loop.run_in_executor(None, ask_directory_dialog, initial_dir)
    return {"folder": selected}

@app.get("/api/default-save-dir")
def get_default_save_dir():
    # Return user Downloads directory
    downloads = os.path.join(os.path.expanduser("~"), "Downloads")
    if os.path.exists(downloads):
        return {"folder": downloads}
    return {"folder": os.getcwd()}

@app.post("/api/start-download")
def start_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    if download_state.is_running:
        raise HTTPException(status_code=400, detail="Загрузка уже запущена.")
    
    background_tasks.add_task(
        run_download_queue,
        request.tracks,
        request.save_dir,
        request.format_type,
        request.quality,
        request.playlist_title,
        request.archive
    )
    return {"status": "started"}

@app.get("/api/download-status")
def get_download_status():
    return {
        "is_running": download_state.is_running,
        "total_tracks": download_state.total_tracks,
        "completed_tracks": download_state.completed_tracks,
        "failed_tracks": download_state.failed_tracks,
        "current_index": download_state.current_index,
        "tracks_status": list(download_state.tracks_status.values()),
        "errors": download_state.errors
    }

@app.get("/api/history")
def fetch_history():
    return get_history()

@app.post("/api/history/clear")
def clear_db_history():
    clear_history()
    return {"status": "cleared"}

@app.get("/api/ffmpeg-status")
def check_ffmpeg_availability():
    ffmpeg_dir = get_ffmpeg_path()
    ffmpeg_exe = os.path.join(ffmpeg_dir, 'ffmpeg.exe')
    ffprobe_exe = os.path.join(ffmpeg_dir, 'ffprobe.exe')
    
    # Also check if it exists in path (for other OS, or if user installed it globally)
    import shutil
    has_system_ffmpeg = shutil.which("ffmpeg") is not None
    
    has_local_ffmpeg = os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe)
    
    from app.downloader import ffmpeg_download_active
    
    return {
        "available": has_system_ffmpeg or has_local_ffmpeg,
        "local_found": has_local_ffmpeg,
        "system_found": has_system_ffmpeg,
        "ffmpeg_dir": ffmpeg_dir,
        "download_active": ffmpeg_download_active
    }

@app.post("/api/download-ffmpeg")
def trigger_ffmpeg_download(background_tasks: BackgroundTasks):
    from app.downloader import download_ffmpeg, ffmpeg_download_active
    if ffmpeg_download_active:
        return {"status": "already_downloading"}
    
    background_tasks.add_task(download_ffmpeg)
    return {"status": "started"}

# Serve static files
# Make sure the static directory exists before mounting
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

