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
        # Force stdout/stderr streams to write UTF-8 encoded text
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    except Exception:
        pass

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
