# Laughter Detection

A Python module for detecting laughter in video and audio files. Extracts audio from video, analyzes acoustic features, and outputs timestamped laughter segments with confidence scores as JSON.

## Installation

```bash
pip install laughter-detection
```

Or install from source:

```bash
git clone https://github.com/jrgillick/laughter-detection.git
cd laughter-detection
pip install -e .
```

## Usage

### Command Line

```bash
# Basic usage - outputs to video_laughter.json
laughter-detect video.mp4

# Specify output file
laughter-detect video.mp4 -o results.json

# Adjust detection sensitivity
laughter-detect video.mp4 --threshold 0.6 --min-duration 0.5

# Print JSON to stdout
laughter-detect video.mp4 --print-json
```

### Python API

```python
from laughter_detection import detect_laughter, LaughterDetector

# Simple usage
results = detect_laughter("video.mp4", output_path="results.json")

# With custom settings
detector = LaughterDetector(
    threshold=0.5,      # Detection threshold (0-1)
    min_duration=0.3    # Minimum segment duration in seconds
)
results = detector.process_video("video.mp4", "output.json")

# Access results
print(f"Found {results['total_segments']} laughter segments")
for segment in results['segments']:
    print(f"  {segment['start_time']}s - {segment['end_time']}s (score: {segment['score']})")
```

## Output Format

The JSON output contains:

```json
{
  "source_file": "/path/to/video.mp4",
  "total_segments": 3,
  "segments": [
    {
      "start_time": 12.5,
      "end_time": 14.2,
      "duration": 1.7,
      "score": 0.72
    },
    {
      "start_time": 45.1,
      "end_time": 47.8,
      "duration": 2.7,
      "score": 0.85
    }
  ],
  "settings": {
    "threshold": 0.5,
    "min_duration": 0.3
  }
}
```

## How It Works

The detector analyzes audio using acoustic features characteristic of laughter:

- **Spectral flux**: Laughter has rapid spectral changes
- **Zero-crossing rate**: Indicates breathiness/noisiness
- **MFCC variance**: Laughter has high timbral variation
- **Spectral centroid**: Laughter tends toward higher frequencies
- **RMS energy**: Characteristic energy patterns

These features are combined with empirically-tuned weights to produce a frame-level laughter score.

## Requirements

- Python 3.9+
- librosa
- moviepy
- numpy

## License

MIT
