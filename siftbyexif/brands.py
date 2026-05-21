# Copyright (c) 2026 FireSwordss. Free for non-commercial use.
"""Camera brand definitions: filename patterns, extensions, EXIF makes."""

BRANDS = {
    "Nikon": {
        "patterns": ["DSC_", "DSCN", "NIKON"],
        "extensions": [".nef", ".nrw"],
        "makes": ["NIKON"],
    },
    "Canon": {
        "patterns": ["IMG_", "CANON"],
        "extensions": [".cr2", ".cr3"],
        "makes": ["CANON"],
    },
    "Sony": {
        "patterns": ["DSC_", "SONY"],
        "extensions": [".arw"],
        "makes": ["SONY"],
    },
    "Fujifilm": {
        "patterns": ["FUJI"],
        "extensions": [".raf"],
        "makes": ["FUJIFILM"],
    },
    "Olympus": {
        "patterns": ["OLYMPUS"],
        "extensions": [".orf"],
        "makes": ["OLYMPUS"],
    },
    "Panasonic": {
        "patterns": ["DSC_", "PANASONIC"],
        "extensions": [".rw2"],
        "makes": ["PANASONIC"],
    },
    "Pentax": {
        "patterns": ["DSC_", "PENTAX"],
        "extensions": [".dng"],
        "makes": ["PENTAX"],
    },
    "Ricoh": {
        "patterns": [],
        "extensions": [],
        "makes": ["RICOH"],
    },
    "Leica": {
        "patterns": [],
        "extensions": [],
        "makes": ["LEICA"],
    },
    "Hasselblad": {
        "patterns": [],
        "extensions": [],
        "makes": ["HASSELBLAD"],
    },
    "Samsung": {
        "patterns": [],
        "extensions": [],
        "makes": ["SAMSUNG"],
    },
    "Apple": {
        "patterns": ["IMG_"],
        "extensions": [".heic", ".dng"],
        "makes": ["APPLE"],
    },
    "DJI": {
        "patterns": [],
        "extensions": [],
        "makes": ["DJI"],
    },
    "GoPro": {
        "patterns": [],
        "extensions": [],
        "makes": ["GOPRO"],
    },
}

# All unique camera makes (uppercase) for EXIF verification
ALL_MAKES = sorted(set(
    make.upper() for b in BRANDS.values() for make in b["makes"]
))

# All supported extensions (lowercase)
ALL_EXTENSIONS = sorted(set(
    ext.lower() for b in BRANDS.values() for ext in b["extensions"]
))
