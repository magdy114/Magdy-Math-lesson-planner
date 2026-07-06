"""Intentionally lightweight.

All production hooks are installed explicitly from expert_entry.py. Keeping this
module empty prevents Python from importing heavy validation libraries before
Gunicorn starts and avoids memory spikes on small Render instances.
"""
