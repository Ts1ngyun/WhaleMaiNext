"""Fail closed before recording if Windows cannot select VB-CABLE input."""
import subprocess
from pathlib import Path

import json
CONFIG = Path(__file__).resolve().parent.parent/'data/maibot-link.json'

def script_path():
    config=json.loads(CONFIG.read_text(encoding='utf-8-sig'))
    return Path(config['bridgeRoot'])/'audio/Ensure-Microphone.ps1'

def ensure():
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(script_path())],
        capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode or b'CABLE Output verified' not in result.stdout:
        raise RuntimeError('Cannot verify CABLE Output default microphone; voice cancelled')
