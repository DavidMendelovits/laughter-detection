"""Laughter Detection - Detect laughter in video/audio files."""

from .detector import LaughterDetector, detect_laughter

__version__ = "0.1.0"
__all__ = ["LaughterDetector", "detect_laughter"]
