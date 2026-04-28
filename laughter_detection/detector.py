"""Core laughter detection functionality using YAMNet."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import resampy
import tensorflow as tf
import tensorflow_hub as hub
from moviepy import VideoFileClip
from scipy.io import wavfile


@dataclass
class LaughterSegment:
    """Represents a detected laughter segment."""
    start_time: float
    end_time: float
    score: float

    def to_dict(self) -> dict:
        return {
            "start_time": round(self.start_time, 3),
            "end_time": round(self.end_time, 3),
            "duration": round(self.end_time - self.start_time, 3),
            "score": round(self.score, 4)
        }


# YAMNet class indices for laughter-related sounds
# From yamnet_class_map.csv
LAUGHTER_CLASS_IDS = [
    17,   # Laughter
    18,   # Baby laughter
    19,   # Giggle
    20,   # Snicker
    21,   # Belly laugh
    22,   # Chuckle, chortle
]


class LaughterDetector:
    """Detects laughter in audio/video files using YAMNet neural network."""

    def __init__(
        self,
        threshold: float = 0.3,
        min_duration: float = 0.3,
    ):
        """
        Initialize the laughter detector with YAMNet model.

        Args:
            threshold: Minimum score to consider as laughter (0-1)
            min_duration: Minimum duration in seconds for a laughter segment
        """
        self.threshold = threshold
        self.min_duration = min_duration
        self._model = None

    @property
    def model(self):
        """Lazy-load the YAMNet model."""
        if self._model is None:
            self._model = hub.load('https://tfhub.dev/google/yamnet/1')
        return self._model

    def extract_audio_from_video(self, video_path: str, output_path: Optional[str] = None) -> str:
        """
        Extract audio from a video file.

        Args:
            video_path: Path to the video file
            output_path: Optional path for the extracted audio file

        Returns:
            Path to the extracted audio file
        """
        if output_path is None:
            output_path = tempfile.mktemp(suffix=".wav")

        video = VideoFileClip(video_path)
        video.audio.write_audiofile(output_path, logger=None)
        video.close()

        return output_path

    def load_audio(self, audio_path: str) -> tuple[np.ndarray, int]:
        """
        Load audio file and convert to mono 16kHz as required by YAMNet.

        Args:
            audio_path: Path to the audio file

        Returns:
            Tuple of (waveform as float32, sample_rate)
        """
        sample_rate, wav_data = wavfile.read(audio_path)

        # Convert to mono if stereo
        if len(wav_data.shape) > 1:
            wav_data = np.mean(wav_data, axis=1)

        # Convert to float32 in [-1, 1] range
        if wav_data.dtype == np.int16:
            wav_data = wav_data.astype(np.float32) / 32768.0
        elif wav_data.dtype == np.int32:
            wav_data = wav_data.astype(np.float32) / 2147483648.0
        elif wav_data.dtype == np.uint8:
            wav_data = (wav_data.astype(np.float32) - 128) / 128.0
        else:
            wav_data = wav_data.astype(np.float32)

        # Resample to 16kHz if needed (YAMNet requirement)
        if sample_rate != 16000:
            wav_data = resampy.resample(wav_data, sample_rate, 16000)
            sample_rate = 16000

        return wav_data, sample_rate

    def detect(self, audio_path: str) -> list[LaughterSegment]:
        """
        Detect laughter segments in an audio file using YAMNet.

        Args:
            audio_path: Path to the audio file

        Returns:
            List of detected laughter segments
        """
        # Load and preprocess audio
        waveform, sample_rate = self.load_audio(audio_path)

        # Run YAMNet inference
        scores, embeddings, spectrogram = self.model(waveform)
        scores = scores.numpy()

        # YAMNet outputs scores every 0.48 seconds (with 0.96s window, 50% overlap)
        frame_duration = 0.48

        # Extract laughter scores (sum of all laughter-related classes)
        laughter_scores = np.zeros(len(scores))
        for class_id in LAUGHTER_CLASS_IDS:
            laughter_scores += scores[:, class_id]

        # Find segments above threshold
        segments = []
        in_segment = False
        segment_start = 0.0
        segment_scores = []

        for i, score in enumerate(laughter_scores):
            time = i * frame_duration

            if score >= self.threshold:
                if not in_segment:
                    in_segment = True
                    segment_start = time
                    segment_scores = [score]
                else:
                    segment_scores.append(score)
            else:
                if in_segment:
                    segment_end = time
                    duration = segment_end - segment_start

                    if duration >= self.min_duration:
                        avg_score = float(np.mean(segment_scores))
                        segments.append(LaughterSegment(
                            start_time=segment_start,
                            end_time=segment_end,
                            score=avg_score
                        ))

                    in_segment = False
                    segment_scores = []

        # Handle segment at end of file
        if in_segment:
            segment_end = len(laughter_scores) * frame_duration
            duration = segment_end - segment_start

            if duration >= self.min_duration:
                avg_score = float(np.mean(segment_scores))
                segments.append(LaughterSegment(
                    start_time=segment_start,
                    end_time=segment_end,
                    score=avg_score
                ))

        return segments

    def process_video(self, video_path: str, output_path: Optional[str] = None) -> dict:
        """
        Process a video file and detect laughter.

        Args:
            video_path: Path to the video file
            output_path: Optional path for the output JSON file

        Returns:
            Dictionary with detection results
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        # Extract audio
        temp_audio = None
        try:
            temp_audio = self.extract_audio_from_video(str(video_path))

            # Detect laughter
            segments = self.detect(temp_audio)

            # Prepare results
            results = {
                "source_file": str(video_path.absolute()),
                "total_segments": len(segments),
                "segments": [seg.to_dict() for seg in segments],
                "settings": {
                    "threshold": self.threshold,
                    "min_duration": self.min_duration,
                    "model": "YAMNet"
                }
            }

            # Save to JSON if output path specified
            if output_path:
                with open(output_path, 'w') as f:
                    json.dump(results, f, indent=2)

            return results

        finally:
            # Clean up temp audio file
            if temp_audio and os.path.exists(temp_audio):
                os.remove(temp_audio)


def detect_laughter(
    video_path: str,
    output_path: Optional[str] = None,
    threshold: float = 0.3,
    min_duration: float = 0.3
) -> dict:
    """
    Convenience function to detect laughter in a video file.

    Args:
        video_path: Path to the video file
        output_path: Optional path for the output JSON file
        threshold: Minimum score to consider as laughter (0-1)
        min_duration: Minimum duration in seconds for a laughter segment

    Returns:
        Dictionary with detection results
    """
    detector = LaughterDetector(threshold=threshold, min_duration=min_duration)
    return detector.process_video(video_path, output_path)
