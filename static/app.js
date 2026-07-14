// State variables
let playlistTracks = [];
let selectedTrackIds = new Set();
let currentPlaylistTitle = "";
let downloadPollingInterval = null;
let currentSearchTrackId = null;

// On Page Load
document.addEventListener("DOMContentLoaded", () => {
    // 1. Fetch default save directory
    fetchDefaultSaveDir();
    // 2. Check FFmpeg status
    checkFFmpegStatus();
    // 3. Load download history
    loadHistory();
    // 4. Check if download is already running in background
    checkActiveDownload();
});

// Tab Switching
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.getElementById(`tab-btn-${tabName}`).classList.add('active');
    
    if (tabName === 'history') {
        loadHistory();
    }
}

// Fetch default save folder
async function fetchDefaultSaveDir() {
    try {
        const res = await fetch('/api/default-save-dir');
        const data = await res.json();
        if (data.folder) {
            document.getElementById('save-dir').value = data.folder;
        }
    } catch (e) {
        console.error("Failed to load default save directory", e);
    }
}

// Check FFmpeg installation status
async function checkFFmpegStatus() {
    const badge = document.getElementById('ffmpeg-badge');
    const desc = document.getElementById('ffmpeg-desc');
    const dlBtn = document.getElementById('ffmpeg-download-btn');
    
    try {
        const res = await fetch('/api/ffmpeg-status');
        const data = await res.json();
        
        badge.className = 'status-badge';
        
        if (data.available) {
            badge.classList.add('installed');
            badge.innerHTML = '<i class="fa-solid fa-check"></i> Установлен';
            desc.innerHTML = data.local_found 
                ? 'FFmpeg найден в локальной папке приложения (bin/).' 
                : 'FFmpeg обнаружен в системных переменных (PATH).';
            dlBtn.classList.add('hidden');
        } else {
            badge.classList.add('missing');
            badge.innerHTML = '<i class="fa-solid fa-xmark"></i> Отсутствует';
            desc.innerHTML = 'Для конвертации аудио в MP3 необходим FFmpeg. Нажмите кнопку ниже для автоматической загрузки.';
            dlBtn.classList.remove('hidden');
        }
    } catch (e) {
        console.error("FFmpeg check failed", e);
        badge.className = 'status-badge missing';
        badge.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> Оффлайн';
        desc.innerHTML = 'Не удалось подключиться к локальному серверу. Пожалуйста, убедитесь, что сервер запущен.';
    }
}

// Download FFmpeg programmatically
async function startFFmpegDownload() {
    const badge = document.getElementById('ffmpeg-badge');
    const desc = document.getElementById('ffmpeg-desc');
    const dlBtn = document.getElementById('ffmpeg-download-btn');
    
    badge.className = 'status-badge checking';
    badge.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Загрузка';
    desc.innerHTML = 'Началось скачивание статической сборки FFmpeg (~100 MB). Это может занять пару минут...';
    dlBtn.classList.add('hidden');
    
    try {
        // Trigger server background task to download ffmpeg
        // In our current setup, we also have the background downloader script running.
        // Let's create an endpoint in api.py if we need it. Our checkFFmpegStatus polls this.
        const res = await fetch('/api/download-ffmpeg', { method: 'POST' });
        
        // Let's check status every 5 seconds
        const pollFFmpeg = setInterval(async () => {
            const checkRes = await fetch('/api/ffmpeg-status');
            const checkData = await checkRes.json();
            if (checkData.available) {
                clearInterval(pollFFmpeg);
                checkFFmpegStatus();
            }
        }, 5000);
    } catch (e) {
        console.error("Failed to start FFmpeg download", e);
        // Fallback: search-based script might already be running.
        // Let's poll anyway:
        const pollFFmpeg = setInterval(async () => {
            const checkRes = await fetch('/api/ffmpeg-status');
            const checkData = await checkRes.json();
            if (checkData.available) {
                clearInterval(pollFFmpeg);
                checkFFmpegStatus();
            }
        }, 5000);
    }
}

// Browse folder using native dialog
async function browseFolder() {
    const currentPath = document.getElementById('save-dir').value;
    try {
        const res = await fetch('/api/select-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ current_path: currentPath })
        });
        const data = await res.json();
        if (data.folder) {
            document.getElementById('save-dir').value = data.folder;
        }
    } catch (e) {
        console.error("Browse folder error", e);
        alert("Не удалось открыть диалог. Вы можете прописать путь вручную.");
    }
}

// Load Playlist details
async function loadPlaylist() {
    const url = document.getElementById('playlist-url').value.trim();
    if (!url) {
        alert("Пожалуйста, введите ссылку на плейлист YouTube");
        return;
    }
    
    const loadBtn = document.getElementById('load-playlist-btn');
    const originalHTML = loadBtn.innerHTML;
    
    loadBtn.disabled = true;
    loadBtn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i> Загрузка...';
    
    try {
        const res = await fetch('/api/playlist-info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: url })
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Не удалось загрузить плейлист");
        }
        
        const data = await res.json();
        currentPlaylistTitle = data.title;
        playlistTracks = data.tracks;
        
        // Reset selections
        selectedTrackIds.clear();
        playlistTracks.forEach(t => {
            if (t.selected) {
                selectedTrackIds.add(t.id);
            }
        });
        
        renderPlaylist();
        
        // Show section
        document.getElementById('playlist-section').classList.remove('hidden');
        document.getElementById('progress-section').classList.add('hidden');
        
    } catch (e) {
        alert(`Ошибка: ${e.message}`);
    } finally {
        loadBtn.disabled = false;
        loadBtn.innerHTML = originalHTML;
    }
}

// Render Playlist tracks
function renderPlaylist() {
    document.getElementById('playlist-title-display').innerText = currentPlaylistTitle;
    const trackListContainer = document.getElementById('track-list');
    trackListContainer.innerHTML = '';
    
    playlistTracks.forEach((track) => {
        const isChecked = selectedTrackIds.has(track.id);
        const card = document.createElement('div');
        card.className = 'track-card';
        
        let warningBadge = '';
        let cardClassModifier = '';
        if (track.is_slowed) {
            warningBadge += `<span class="track-warning slowed"><i class="fa-solid fa-triangle-exclamation"></i> Замедленная</span>`;
            cardClassModifier = 'warning-state';
        }
        if (track.is_long) {
            warningBadge += `<span class="track-warning long"><i class="fa-solid fa-clock"></i> > 10 мин</span>`;
            cardClassModifier = 'danger-state';
        }
        
        if (cardClassModifier) {
            card.classList.add(cardClassModifier);
        }
        
        card.innerHTML = `
            <div class="track-check">
                <input type="checkbox" id="check-${track.id}" ${isChecked ? 'checked' : ''} onchange="toggleTrack('${track.id}')">
            </div>
            <div class="track-index">${track.index}</div>
            <div class="track-details">
                <span class="track-title" id="title-text-${track.id}">${track.title}</span>
                <div class="track-info-row">
                    <span class="track-uploader"><i class="fa-solid fa-user"></i> ${track.uploader || 'YouTube'}</span>
                    ${warningBadge}
                </div>
                <div class="track-edit-inputs">
                    <input type="text" class="artist-input" id="artist-${track.id}" placeholder="Исполнитель" value="${track.artist || ''}" onchange="updateTrackMetadata('${track.id}')">
                    <span style="color: var(--text-muted); align-self: center;">—</span>
                    <input type="text" class="track-input" id="track-name-${track.id}" placeholder="Название" value="${track.track || ''}" onchange="updateTrackMetadata('${track.id}')">
                </div>
            </div>
            <div class="track-duration">${track.duration_str}</div>
            <div class="track-actions">
                ${track.is_slowed ? `
                <button class="btn btn-sm btn-outline-primary" onclick="findOriginal('${track.id}', '${track.title}')">
                    <i class="fa-solid fa-magnifying-glass"></i> Найти оригинал
                </button>
                ` : ''}
            </div>
        `;
        
        trackListContainer.appendChild(card);
    });
    
    updateSelectionCounter();
}

// Track selection toggle
function toggleTrack(trackId) {
    if (selectedTrackIds.has(trackId)) {
        selectedTrackIds.delete(trackId);
    } else {
        selectedTrackIds.add(trackId);
    }
    updateSelectionCounter();
}

// Update local track metadata state when user edits fields manually
function updateTrackMetadata(trackId) {
    const artistVal = document.getElementById(`artist-${trackId}`).value.trim();
    const trackVal = document.getElementById(`track-name-${trackId}`).value.trim();
    
    const track = playlistTracks.find(t => t.id === trackId);
    if (track) {
        track.artist = artistVal;
        track.track = trackVal;
    }
}

// Select All / Deselect All
function selectAll(val) {
    selectedTrackIds.clear();
    playlistTracks.forEach(t => {
        if (val) {
            selectedTrackIds.add(t.id);
        }
        const checkbox = document.getElementById(`check-${t.id}`);
        if (checkbox) {
            checkbox.checked = val;
        }
    });
    updateSelectionCounter();
}

// Update selection counter display
function updateSelectionCounter() {
    const count = selectedTrackIds.size;
    const total = playlistTracks.length;
    document.getElementById('selection-counter').innerText = `Выбрано: ${count} из ${total}`;
}

// Search for original version modal
async function findOriginal(trackId, title) {
    currentSearchTrackId = trackId;
    document.getElementById('modal-track-title').innerText = title;
    document.getElementById('search-modal').classList.remove('hidden');
    document.getElementById('modal-loader').classList.remove('hidden');
    document.getElementById('search-results').innerHTML = '';
    
    try {
        const res = await fetch('/api/search-alternatives', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: title })
        });
        const data = await res.json();
        
        document.getElementById('modal-loader').classList.add('hidden');
        const resultsContainer = document.getElementById('search-results');
        
        if (data.results && data.results.length > 0) {
            data.results.forEach(result => {
                const card = document.createElement('div');
                card.className = 'result-card';
                card.innerHTML = `
                    <div class="result-info">
                        <span class="result-title" title="${result.title}">${result.title}</span>
                        <span class="result-uploader">${result.uploader}</span>
                    </div>
                    <div class="result-duration">${result.duration_str}</div>
                    <button class="btn btn-sm btn-primary" onclick="selectAlternative('${result.id}', '${result.title.replace(/'/g, "\\'")}', '${result.uploader.replace(/'/g, "\\'")}')">
                        Выбрать
                    </button>
                `;
                resultsContainer.appendChild(card);
            });
        } else {
            resultsContainer.innerHTML = '<p class="text-center">Альтернативные треки не найдены.</p>';
        }
    } catch (e) {
        document.getElementById('modal-loader').classList.add('hidden');
        document.getElementById('search-results').innerHTML = `<p class="text-danger">Ошибка: ${e.message}</p>`;
    }
}

// Select alternative video to replace slowed one
function selectAlternative(newVideoId, newTitle, uploader) {
    const trackId = currentSearchTrackId;
    const track = playlistTracks.find(t => t.id === trackId);
    
    if (track) {
        // Update track details
        track.id = newVideoId;
        track.url = `https://www.youtube.com/watch?v=${newVideoId}`;
        track.title = newTitle;
        track.uploader = uploader;
        track.is_slowed = false; // Resolved slowed
        track.slowed_warning = "";
        
        // Auto parse artist and track for new title
        // We can do it on client or let server re-parse. Let's do simple dash parse:
        let artist = uploader.replace(" - Topic", "").strip || uploader;
        let name = newTitle;
        if (newTitle.includes(" - ")) {
            const parts = newTitle.split(" - ");
            artist = parts[0].trim();
            name = parts[1].replace(/\(.*?\)|\[.*?\]/g, '').trim();
        }
        
        track.artist = artist;
        track.track = name;
        
        // Add to selected list
        selectedTrackIds.delete(trackId); // remove old ID
        selectedTrackIds.add(newVideoId); // add new ID
        
        // Re-render
        renderPlaylist();
    }
    
    closeModal();
}

function closeModal() {
    document.getElementById('search-modal').classList.add('hidden');
    currentSearchTrackId = null;
}

// Start download queue
async function startDownload() {
    const saveDir = document.getElementById('save-dir').value.trim();
    if (!saveDir) {
        alert("Пожалуйста, укажите папку для сохранения файлов.");
        return;
    }
    
    if (selectedTrackIds.size === 0) {
        alert("Выберите хотя бы один трек для скачивания.");
        return;
    }
    
    // Prepare selected tracks data
    const tracksToDownload = playlistTracks
        .filter(t => selectedTrackIds.has(t.id))
        .map(t => ({
            id: t.id,
            url: t.url,
            artist: t.artist,
            track: t.track,
            title: t.title
        }));
        
    try {
        const formatVal = document.getElementById('format-select').value;
        const qualityVal = document.getElementById('quality-select').value;
        
        const res = await fetch('/api/start-download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                tracks: tracksToDownload,
                save_dir: saveDir,
                format_type: formatVal,
                quality: qualityVal
            })
        });
        
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || "Не удалось запустить скачивание");
        }
        
        // Show progress UI
        document.getElementById('playlist-section').classList.add('hidden');
        document.getElementById('progress-section').classList.remove('hidden');
        
        // Start status polling
        startProgressPolling();
        
    } catch (e) {
        alert(`Ошибка: ${e.message}`);
    }
}

// Check if download is running in background (e.g. page refreshed)
async function checkActiveDownload() {
    try {
        const res = await fetch('/api/download-status');
        const data = await res.json();
        
        if (data.is_running) {
            document.getElementById('playlist-section').classList.add('hidden');
            document.getElementById('progress-section').classList.remove('hidden');
            startProgressPolling();
        }
    } catch (e) {
        console.error("Error checking active download", e);
    }
}

// Start polling API for download progress
function startProgressPolling() {
    if (downloadPollingInterval) clearInterval(downloadPollingInterval);
    
    // Call once immediately
    pollDownloadStatus();
    
    downloadPollingInterval = setInterval(pollDownloadStatus, 1500);
}

// Poll download progress API
async function pollDownloadStatus() {
    try {
        const res = await fetch('/api/download-status');
        const data = await res.json();
        
        // Update global progress bar
        const total = data.total_tracks;
        const currentIdx = data.current_index;
        const completed = data.completed_tracks;
        const failed = data.failed_tracks;
        
        document.getElementById('progress-ratio').innerText = `${completed + failed} / ${total}`;
        
        let percent = 0;
        if (total > 0) {
            percent = Math.round(((completed + failed) / total) * 100);
        }
        
        document.getElementById('global-progress-bar').style.width = `${percent}%`;
        
        // Update list of queue statuses
        const queueContainer = document.getElementById('queue-list');
        queueContainer.innerHTML = '';
        
        let currentlyDownloadingName = 'Подготовка...';
        let currentSpeed = '0 B/s';
        
        data.tracks_status.forEach(t => {
            const card = document.createElement('div');
            card.className = 'queue-card';
            
            let statusText = 'Ожидание';
            let badgeClass = 'pending';
            
            if (t.status === 'downloading') {
                statusText = `Скачивание: ${t.percent}%`;
                badgeClass = 'downloading';
                currentlyDownloadingName = `${t.artist} - ${t.track}`;
                currentSpeed = `${t.speed} (Осталось: ${t.eta})`;
            } else if (t.status === 'converting') {
                statusText = 'Конвертация в MP3';
                badgeClass = 'converting';
                currentlyDownloadingName = `${t.artist} - ${t.track}`;
                currentSpeed = 'Обработка FFmpeg...';
            } else if (t.status === 'completed') {
                statusText = 'Готово';
                badgeClass = 'completed';
            } else if (t.status === 'failed') {
                statusText = 'Ошибка';
                badgeClass = 'failed';
            }
            
            card.innerHTML = `
                <div class="queue-info">
                    <span class="queue-title">${t.artist} - ${t.track}</span>
                    <span class="queue-meta">${t.status === 'failed' ? `<span class="text-danger">${t.error || 'Ошибка скачивания'}</span>` : t.status}</span>
                </div>
                <div class="queue-status-box">
                    <span class="queue-status-badge ${badgeClass}">${statusText}</span>
                </div>
            `;
            queueContainer.appendChild(card);
        });
        
        document.getElementById('current-track-name').innerText = currentlyDownloadingName;
        document.getElementById('download-speed').innerText = currentSpeed;
        
        // If finished
        if (!data.is_running && (completed + failed >= total) && total > 0) {
            clearInterval(downloadPollingInterval);
            downloadPollingInterval = null;
            document.getElementById('progress-title').innerText = 'Загрузка завершена!';
            document.getElementById('current-track-name').innerText = `Успешно скачано: ${completed}, Ошибок: ${failed}`;
            document.getElementById('download-speed').innerText = '';
            
            // Auto reload history
            loadHistory();
            
            // Show alert or let user go back
            setTimeout(() => {
                alert(`Скачивание успешно завершено!\nУспешно: ${completed}\nОшибок: ${failed}`);
            }, 500);
        }
        
    } catch (e) {
        console.error("Polling progress status failed", e);
    }
}

// Fetch and load history list
async function loadHistory() {
    const listContainer = document.getElementById('history-list');
    const emptyContainer = document.getElementById('history-empty');
    
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        
        if (data && data.length > 0) {
            emptyContainer.classList.add('hidden');
            listContainer.classList.remove('hidden');
            listContainer.innerHTML = '';
            
            data.forEach(item => {
                const card = document.createElement('div');
                card.className = 'history-card';
                const formatDisplay = (item.format || 'mp3').toUpperCase();
                const qualityDisplay = item.format === 'mp4' ? item.quality : `${item.quality} kbps`;
                
                card.innerHTML = `
                    <div class="history-details">
                        <h4>${item.artist} - ${item.title}</h4>
                        <div class="history-meta">
                            <span><i class="${item.format === 'mp4' ? 'fa-solid fa-file-video' : 'fa-solid fa-file-audio'}"></i> ${formatDisplay} (${qualityDisplay})</span>
                            <span><i class="fa-solid fa-calendar-day"></i> ${item.download_date}</span>
                            <span><i class="fa-solid fa-folder"></i> ${item.save_path}</span>
                            <span><a href="${item.url}" target="_blank" style="color: var(--primary); text-decoration: none;"><i class="fa-brands fa-youtube"></i> Ссылка</a></span>
                        </div>
                    </div>
                    <div class="history-actions">
                        <button class="btn btn-sm btn-secondary" onclick="copyPath('${item.save_path.replace(/\\/g, '\\\\')}')">
                            <i class="fa-regular fa-copy"></i> Копировать путь
                        </button>
                    </div>
                `;
                listContainer.appendChild(card);
            });
        } else {
            emptyContainer.classList.remove('hidden');
            listContainer.classList.add('hidden');
        }
    } catch (e) {
        console.error("Failed to load history", e);
    }
}

// Copy file save path to clipboard
function copyPath(path) {
    navigator.clipboard.writeText(path).then(() => {
        alert("Путь скопирован в буфер обмена!");
    }).catch(err => {
        console.error('Copy failed', err);
        // Fallback alert
        prompt("Скопируйте путь вручную:", path);
    });
}

// Clear history database
async function clearAllHistory() {
    if (confirm("Вы уверены, что хотите очистить всю историю загрузок?")) {
        try {
            await fetch('/api/history/clear', { method: 'POST' });
            loadHistory();
        } catch (e) {
            console.error("Failed to clear history", e);
        }
    }
}

// Format switch handler
function onFormatChange() {
    const formatSelect = document.getElementById('format-select');
    const qualitySelect = document.getElementById('quality-select');
    const format = formatSelect.value;
    
    // Clear old options
    qualitySelect.innerHTML = '';
    
    if (format === 'mp3') {
        qualitySelect.innerHTML = `
            <option value="320">320 kbps (Наилучшее)</option>
            <option value="256">256 kbps (Высокое)</option>
            <option value="192">192 kbps (Среднее)</option>
            <option value="128">128 kbps (Стандартное)</option>
        `;
    } else if (format === 'mp4') {
        qualitySelect.innerHTML = `
            <option value="1080p">1080p (Full HD)</option>
            <option value="720p">720p (HD)</option>
            <option value="480p">480p (Среднее)</option>
            <option value="360p">360p (Низкое)</option>
        `;
    }
}
