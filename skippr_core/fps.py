import fractions
import math

# Common frame rates to fractional representation (numerator, denominator)
FPS_FRACTIONS = {
    24: (1, 24),
    25: (1, 25),
    30: (1, 30),
    50: (1, 50),
    60: (1, 60),
    23.976: (1001, 24000),
    23.98: (1001, 24000),
    29.97: (1001, 30000),
    59.94: (1001, 60000),
}


def get_frame_duration(fps: float) -> fractions.Fraction:
    """Returns the duration of 1 frame as an exact fraction in seconds."""
    rounded_fps = round(fps, 3)
    for known_fps, (num, den) in FPS_FRACTIONS.items():
        if abs(fps - known_fps) < 0.005:
            return fractions.Fraction(num, den)
    # Generic fallback
    f = fractions.Fraction(1 / fps).limit_denominator(120000)
    return f


def sec_to_frames(sec: float, fps: float) -> int:
    """Converts seconds to integer frames using standard round()."""
    if sec is None or math.isnan(sec):
        return 0
    return int(round(sec * fps))


def frames_to_sec(frames: int, fps: float) -> float:
    """Converts integer frames to float seconds."""
    return float(frames / fps)


def format_fcpxml_time(frames: int, fps: float) -> str:
    """
    Formats a frame count into FCPXML rational time string, e.g. '125/25s' or '0s'.
    For 25 fps: 10 frames -> '10/25s'.
    """
    if frames == 0:
        return "0s"
    dur_frac = get_frame_duration(fps)
    # total duration = frames * (dur_frac.numerator / dur_frac.denominator)
    total_frac = fractions.Fraction(frames * dur_frac.numerator, dur_frac.denominator)
    return f"{total_frac.numerator}/{total_frac.denominator}s"


def format_fcpxml_frame_duration(fps: float) -> str:
    """Formats frame duration for FCPXML <format> tag, e.g. '1/25s' or '1001/24000s'."""
    dur_frac = get_frame_duration(fps)
    return f"{dur_frac.numerator}/{dur_frac.denominator}s"


def frames_to_timecode(frames: int, fps: float) -> str:
    """
    Converts integer frame count to non-drop frame SMPTE timecode HH:MM:SS:FF.
    """
    int_fps = int(round(fps))
    if int_fps <= 0:
        int_fps = 25
    if frames < 0:
        frames = 0
    ff = frames % int_fps
    total_seconds = frames // int_fps
    ss = total_seconds % 60
    total_minutes = total_seconds // 60
    mm = total_minutes % 60
    hh = total_minutes // 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"

