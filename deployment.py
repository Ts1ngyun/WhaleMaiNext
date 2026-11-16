"""Paths belong to each installation, never to the published repository."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent
WHALE_ROOT=ROOT/'WhaleGirl'
MAIBOT_ROOT=ROOT/'MaiBot'
INSTANCE_ROOT=ROOT/'instance'
MAIBOT_PYTHON=MAIBOT_ROOT/'.venv/Scripts/python.exe'
