import os
import sys
import webbrowser
import threading
import time
import uvicorn
import subprocess
import io

# Configure console encoding for Russian language support on Windows
if sys.platform.startswith('win'):
    try:
        # Switch command prompt active code page to UTF-8 (65001)
        subprocess.run('chcp 65001', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
        
    try:
        # Force stdout/stderr streams to write UTF-8 encoded text if they exist
        if sys.stdout is not None:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        if sys.stderr is not None:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

# Safe stream wrapper for windowed/noconsole mode where stdout/stderr are None
class SafeStream:
    def __init__(self, original):
        self.original = original
        self.encoding = getattr(original, 'encoding', 'utf-8') or 'utf-8'
        
    def write(self, data):
        if self.original:
            try:
                self.original.write(data)
            except Exception:
                pass
                
    def flush(self):
        if self.original and hasattr(self.original, 'flush'):
            try:
                self.original.flush()
            except Exception:
                pass
                
    def isatty(self):
        if self.original and hasattr(self.original, 'isatty'):
            try:
                return self.original.isatty()
            except Exception:
                pass
        return False

# Wrap streams to prevent crashes in libraries (like uvicorn/logging) that expect isatty()
sys.stdout = SafeStream(sys.stdout)
sys.stderr = SafeStream(sys.stderr)

def open_browser():
    # Wait for the server to start up
    time.sleep(1.2)
    url = "http://127.0.0.1:8088"
    print(f"Opening web interface: {url}")
    webbrowser.open(url)

if __name__ == '__main__':
    # Add project root to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Start browser thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Start server
    uvicorn.run("app.api:app", host="127.0.0.1", port=8088, log_level="info")
