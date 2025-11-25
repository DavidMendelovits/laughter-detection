"""Core laughter detection functionality."""

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
from moviepy.editor import VideoFileClip


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


class LaughterDetector:
    """Detects laughter in audio/video files using acoustic feature analysis."""

    def __init__(
        self,
        threshold: float = 0.5,
        min_duration: float = 0.3,
        hop_length: int = 512,
        frame_length: int = 2048,
    ):
        """
        Initialize the laughter detector.

        Args:
            threshold: Minimum score to consider as laughter (0-1)
            min_duration: Minimum duration in seconds for a laughter segment
            hop_length: Hop length for audio analysis
            frame_length: Frame length for audio analysis
        """
        self.threshold = threshold
        self.min_duration = min_duration
        self.hop_length = hop_length
        self.frame_length = frame_length

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
        video.audio.write_audiofile(output_path, verbose=False, logger=None)
        video.close()

        return output_path

    def compute_laughter_features(self, y: np.ndarray, sr: int) -> np.ndarray:
        """
        Compute acoustic features indicative of laughter.

        Laughter typically has:
        - High spectral flux (rapid changes)
        - Irregular rhythm patterns
        - Specific frequency characteristics
        - High zero-crossing rate variations

        Args:
            y: Audio time series
            sr: Sample rate

        Returns:
            Frame-level laughter scores
        """
        # Compute various features
        # Spectral centroid - laughter tends to have higher frequencies
        spectral_centroid = librosa.feature.spectral_centroid(
            y=y, sr=sr, hop_length=self.hop_length
        )[0]

        # Spectral flux - laughter has rapid spectral changes
        onset_env = librosa.onset.onset_strength(
            y=y, sr=sr, hop_length=self.hop_length
        )

        # Zero crossing rate - indicates noisiness/breathiness
        zcr = librosa.feature.zero_crossing_rate(
            y, hop_length=self.hop_length
        )[0]

        # RMS energy - laughter has characteristic energy patterns
        rms = librosa.feature.rms(
            y=y, hop_length=self.hop_length
        )[0]

        # MFCC variance - laughter has high timbral variation
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=self.hop_length)
        mfcc_var = np.var(mfccs, axis=0)

        # Normalize features to 0-1 range
        def normalize(x):
            if x.max() - x.min() == 0:
                return np.zeros_like(x)
            return (x - x.min()) / (x.max() - x.min())

        # Ensure all features have the same length
        min_len = min(len(spectral_centroid), len(onset_env), len(zcr), len(rms), len(mfcc_var))

        spectral_centroid = normalize(spectral_centroid[:min_len])
        onset_env = normalize(onset_env[:min_len])
        zcr = normalize(zcr[:min_len])
        rms = normalize(rms[:min_len])
        mfcc_var = normalize(mfcc_var[:min_len])

        # Combine features with weights tuned for laughter detection
        # These weights emphasize features most characteristic of laughter
        laughter_score = (
            0.25 * onset_env +      # Rapid bursts
            0.20 * zcr +            # Breathiness
            0.20 * mfcc_var +       # Timbral variation
            0.20 * spectral_centroid +  # Higher frequencies
            0.15 * rms              # Energy
        )

        return laughter_score

    def detect(self, audio_path: str) -> list[LaughterSegment]:
        """
        Detect laughter segments in an audio file.

        Args:
            audio_path: Path to the audio file

        Returns:
            List of detected laughter segments
        """
        # Load audio
        y, sr = librosa.load(audio_path, sr=22050)

        # Compute laughter scores
        scores = self.compute_laughter_features(y, sr)

        # Convert frame indices to time
        times = librosa.frames_to_time(
            np.arange(len(scores)),
            sr=sr,
            hop_length=self.hop_length
        )

        # Find segments above threshold
        segments = []
        in_segment = False
        segment_start = 0
        segment_scores = []

        for i, (time, score) in enumerate(zip(times, scores)):
            if score >= self.threshold:
                if not in_segment:
                    in_segment = True
                    segment_start = time
                    segment_scores = [score]
                else:
                    segment_scores.append(score)
            else:
                if in_segment:
                    segment_end = times[i - 1] if i > 0 else time
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
            segment_end = times[-1]
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
                    "min_duration": self.min_duration
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
    threshold: float = 0.5,
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
