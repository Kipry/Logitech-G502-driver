#!/bin/zsh
# Doppelklick startet die Belegungs-Oberfläche im Browser. Fenster offen lassen, solange sie läuft.
cd "$(dirname "$0")"
exec .venv/bin/python server.py
