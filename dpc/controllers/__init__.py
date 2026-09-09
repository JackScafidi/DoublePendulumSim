"""Control laws.

One law per module. Each declares its tunable parameters and registers itself,
which is what lets the dashboard show it without any UI code knowing it exists.

This package is destined for the MCU, so it keeps the project's C-transcription
constraints: fixed-size arrays, explicit indexing, no Python-specific
constructs. It must never import from dpc.ui.
"""
