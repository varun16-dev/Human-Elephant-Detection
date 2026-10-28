"""
Trilingual Message Builder for Elephant Detection Early Warning System
Department of AI & ML, Sri Sairam College of Engineering

Generates a unified, plain-text trilingual elephant detection alert:
1. English
2. Kannada (ಕನ್ನಡ)
3. Tamil (தமிழ்)

Designed for 100% cross-platform compatibility across WhatsApp (PyWhatKit)
and Telegram (Telegram Bot API) without HTML tags or formatting discrepancies.
"""

import re
from datetime import datetime
from typing import Optional, Tuple, Union

# Heavy horizontal divider (18 characters)
DIVIDER = "━" * 18

MONTHS_KN = {
    1: "ಜನವರಿ", 2: "ಫೆಬ್ರವರಿ", 3: "ಮಾರ್ಚ್", 4: "ಏಪ್ರಿಲ್",
    5: "ಮೇ", 6: "ಜೂನ್", 7: "ಜುಲೈ", 8: "ಆಗಸ್ಟ್",
    9: "ಸೆಪ್ಟೆಂಬರ್", 10: "ಅಕ್ಟೋಬರ್", 11: "ನವೆಂಬರ್", 12: "ಡಿಸೆಂಬರ್"
}

MONTHS_TA = {
    1: "ஜனவரி", 2: "பிப்ரவரி", 3: "மார்ச்", 4: "ஏப்ரல்",
    5: "மே", 6: "ஜூன்", 7: "ஜூலை", 8: "ஆகஸ்ட்",
    9: "செப்டம்பர்", 10: "அக்டோபர்", 11: "நவம்பர்", 12: "டிசம்பர்"
}


def format_multilingual_timestamps(dt_or_str: Optional[Union[datetime, str]] = None) -> Tuple[str, str, str]:
    """
    Formats the alert timestamp for English, Kannada, and Tamil using local timezone.
    Returns: (time_en, time_kn, time_ta)
    """
    if dt_or_str is None:
        dt = datetime.now().astimezone()
    elif isinstance(dt_or_str, datetime):
        dt = dt_or_str.astimezone() if dt_or_str.tzinfo else dt_or_str
    elif isinstance(dt_or_str, str):
        dt = None
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%d %B %Y, %I:%M %p",
            "%d %b %Y, %I:%M %p",
            "%d/%m/%Y, %H:%M:%S",
            "%Y-%m-%d %H:%M:%S"
        ):
            try:
                dt = datetime.strptime(dt_or_str.strip(), fmt)
                break
            except Exception:
                pass
        if dt is None:
            dt = datetime.now().astimezone()
    else:
        dt = datetime.now().astimezone()

    day = dt.day
    year = dt.year
    hour_12 = int(dt.strftime("%I"))
    minute = dt.strftime("%M")
    am_pm = dt.strftime("%p")
    hour_24 = dt.hour

    month_en = dt.strftime("%B")
    month_kn = MONTHS_KN.get(dt.month, month_en)
    month_ta = MONTHS_TA.get(dt.month, month_en)

    if 0 <= hour_24 < 12:
        period_kn = "ಬೆಳಿಗ್ಗೆ"
        period_ta = "காலை"
    elif 12 <= hour_24 < 16:
        period_kn = "ಮಧ್ಯಾಹ್ನ"
        period_ta = "மதியம்"
    elif 16 <= hour_24 < 20:
        period_kn = "ಸಂಜೆ"
        period_ta = "மாலை"
    else:
        period_kn = "ರಾತ್ರಿ"
        period_ta = "இரவு"

    time_en = f"{day} {month_en} {year}, {hour_12}:{minute} {am_pm}"
    time_kn = f"{day} {month_kn} {year}, {period_kn} {hour_12}:{minute}"
    time_ta = f"{day} {month_ta} {year}, {period_ta} {hour_12}:{minute}"

    return time_en, time_kn, time_ta


def translate_locations(location: Optional[str] = "Monitoring Zone 1") -> Tuple[str, str, str]:
    """
    Translates known monitoring zone patterns to Kannada and Tamil while preserving
    actual location names. Never invents GPS coordinates.
    Returns: (loc_en, loc_kn, loc_ta)
    """
    loc_str = str(location or "Monitoring Zone 1").strip()
    if not loc_str:
        loc_str = "Monitoring Zone 1"

    # Kannada translation
    loc_kn = loc_str
    loc_kn = re.sub(r'Monitoring\s*Zone\s*(\d+)', r'ನಿಗಾ ವಲಯ \1', loc_kn, flags=re.I)
    loc_kn = re.sub(r'Zone\s*(\d+)', r'ವಲಯ \1', loc_kn, flags=re.I)
    loc_kn = re.sub(r'Corridor\s*(\d+)', r'ಕಾರಿಡಾರ್ \1', loc_kn, flags=re.I)
    if loc_kn == loc_str and loc_str.lower() == "monitoring zone":
        loc_kn = "ನಿಗಾ ವಲಯ"

    # Tamil translation
    loc_ta = loc_str
    loc_ta = re.sub(r'Monitoring\s*Zone\s*(\d+)', r'கண்காணிப்பு பகுதி \1', loc_ta, flags=re.I)
    loc_ta = re.sub(r'Zone\s*(\d+)', r'பகுதி \1', loc_ta, flags=re.I)
    loc_ta = re.sub(r'Corridor\s*(\d+)', r'பாதை \1', loc_ta, flags=re.I)
    if loc_ta == loc_str and loc_str.lower() == "monitoring zone":
        loc_ta = "கண்காணிப்பு பகுதி"

    return loc_str, loc_kn, loc_ta


def build_trilingual_alert(elephant_count: Union[int, float, str] = 1,
                           location: Optional[str] = "Monitoring Zone 1",
                           timestamp: Optional[Union[datetime, str]] = None) -> str:
    """
    Builds the standardized trilingual elephant detection alert.
    Language Order strictly: English -> Kannada -> Tamil.
    Plain-text format compatible with both WhatsApp and Telegram.
    """
    try:
        count_int = max(1, int(float(elephant_count)))
    except (ValueError, TypeError):
        count_int = 1

    time_en, time_kn, time_ta = format_multilingual_timestamps(timestamp)
    loc_en, loc_kn, loc_ta = translate_locations(location)

    # English grammar
    approach_en = "the elephant" if count_int == 1 else "the elephants"

    # Kannada grammar
    approach_kn = "ಆನೆಯ ಹತ್ತಿರ ಹೋಗಬೇಡಿ" if count_int == 1 else "ಆನೆಗಳ ಹತ್ತಿರ ಹೋಗಬೇಡಿ"

    # Tamil grammar
    approach_ta = "யானையின் அருகில் செல்ல வேண்டாம்" if count_int == 1 else "யானைகளின் அருகில் செல்ல வேண்டாம்"
    count_label_ta = "யானையின் எண்ணிக்கை" if count_int == 1 else "யானைகளின் எண்ணிக்கை"

    return (
        "🚨 ELEPHANT ALERT | ಆನೆ ಎಚ್ಚರಿಕೆ | யானை எச்சரிக்கை 🚨\n\n"
        f"{DIVIDER}\n"
        "1. ENGLISH\n"
        f"{DIVIDER}\n\n"
        f"🐘 Elephant Count: {count_int}\n"
        f"📍 Location: {loc_en}\n"
        f"🕒 Time: {time_en}\n\n"
        "⚠️ SAFETY ADVISORY:\n"
        f"Maintain a safe distance. Do not approach {approach_en}. Follow forest department instructions.\n\n"
        f"{DIVIDER}\n"
        "2. ಕನ್ನಡ\n"
        f"{DIVIDER}\n\n"
        f"🐘 ಆನೆಗಳ ಸಂಖ್ಯೆ: {count_int}\n"
        f"📍 ಸ್ಥಳ: {loc_kn}\n"
        f"🕒 ಸಮಯ: {time_kn}\n\n"
        "⚠️ ಸುರಕ್ಷತಾ ಸೂಚನೆ:\n"
        f"ಸುರಕ್ಷಿತ ಅಂತರವನ್ನು ಕಾಯ್ದುಕೊಳ್ಳಿ. {approach_kn}. ಅರಣ್ಯ ಇಲಾಖೆಯ ಸೂಚನೆಗಳನ್ನು ಪಾಲಿಸಿ.\n\n"
        f"{DIVIDER}\n"
        "3. தமிழ்\n"
        f"{DIVIDER}\n\n"
        f"🐘 {count_label_ta}: {count_int}\n"
        f"📍 இடம்: {loc_ta}\n"
        f"🕒 நேரம்: {time_ta}\n\n"
        "⚠️ பாதுகாப்பு அறிவுரை:\n"
        f"பாதுகாப்பான தூரத்தில் இருங்கள். {approach_ta}. வனத்துறையின் அறிவுறுத்தல்களைப் பின்பற்றுங்கள்.\n\n"
        "— Elephant Early Warning System"
    )
