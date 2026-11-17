"""Crop profiles: starting values for the advice rules.
IMPORTANT: these are typical textbook ranges, to be confirmed with an agronomist or your mentor.
Soil moisture % depends on how the soil sensor is calibrated, so tune moist_low / moist_high on the real sensor.
The N, P and K limits are placeholders until the NPK sensor's units are confirmed."""

EDITABLE = ["moist_low", "moist_high", "ph_low", "ph_high", "temp_high", "n_low", "p_low", "k_low"]
RANGES = {"moist_low": (0, 100), "moist_high": (0, 100), "ph_low": (0, 14), "ph_high": (0, 14),
          "temp_high": (0, 70), "n_low": (0, 100000), "p_low": (0, 100000), "k_low": (0, 100000)}

CROPS = {
    "general": {"name": "General (default)", "moist_low": 40, "moist_high": 80, "ph_low": 5.5, "ph_high": 7.5, "temp_high": 38},
    "rice":    {"name": "Rice (paddy)",      "moist_low": 60, "moist_high": 95, "ph_low": 5.5, "ph_high": 7.0, "temp_high": 35},
    "wheat":   {"name": "Wheat",             "moist_low": 40, "moist_high": 70, "ph_low": 6.0, "ph_high": 7.5, "temp_high": 32},
    "potato":  {"name": "Potato",            "moist_low": 50, "moist_high": 75, "ph_low": 5.0, "ph_high": 6.5, "temp_high": 30},
    "maize":   {"name": "Maize",             "moist_low": 40, "moist_high": 70, "ph_low": 5.8, "ph_high": 7.0, "temp_high": 35},
    "tomato":  {"name": "Tomato",            "moist_low": 50, "moist_high": 75, "ph_low": 6.0, "ph_high": 6.8, "temp_high": 35},
    "tea":     {"name": "Tea",               "moist_low": 50, "moist_high": 80, "ph_low": 4.5, "ph_high": 5.5, "temp_high": 35},
    "jute":    {"name": "Jute",              "moist_low": 50, "moist_high": 80, "ph_low": 6.0, "ph_high": 7.5, "temp_high": 38},
}


def effective_thresholds(base, settings):
    """base config < crop profile < the user's own overrides."""
    settings = settings or {}
    th = dict(base)
    crop = CROPS.get(settings.get("crop", "general"), CROPS["general"])
    th.update({k: v for k, v in crop.items() if k != "name"})
    for k, v in (settings.get("overrides") or {}).items():
        if k in EDITABLE:
            th[k] = v
    return th


def validate_overrides(o):
    """Returns clean {name: float}. Raises ValueError with a message the user can read."""
    if not isinstance(o, dict):
        raise ValueError("overrides must be an object")
    clean = {}
    for k, v in o.items():
        if k not in EDITABLE:
            raise ValueError(f"unknown setting: {k}")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
            raise ValueError(f"{k} must be a number")
        lo, hi = RANGES[k]
        if not lo <= v <= hi:
            raise ValueError(f"{k} must be between {lo} and {hi}")
        clean[k] = float(v)
    return clean
