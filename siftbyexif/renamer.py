# Copyright (c) 2026 FireSwordss. Free for non-commercial use.
"""Restore original filenames from camera MakerNote metadata.

Uses ExifTool to extract FileNumber (and DirectoryNumber for some brands).
Currently supports Nikon (NEF/NRW). Extensible for Canon/Sony/etc.
"""

import os, subprocess, sys

_SUBPROCESS_KW = {}
if sys.platform == 'win32':
    _SUBPROCESS_KW['creationflags'] = subprocess.CREATE_NO_WINDOW

EXIFTOOL = os.path.expandvars(
    r"%LOCALAPPDATA%\Programs\ExifTool\ExifTool.exe"
)


def rename_in_folder(folder_path, progress_cb=None):
    """Scan folder for NEF files and rename to DSC_XXXX.NEF.

    Returns (renamed_count, skipped_count, errors).
    errors = [(fname, error_msg), ...]
    """
    # Gather NEF files
    files = []
    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if os.path.isfile(fpath) and fname.upper().endswith('.NEF'):
            files.append((fname, fpath))

    if not files:
        return 0, 0, []

    # Batch extract FileNumber via ExifTool
    try:
        result = subprocess.run(
            [EXIFTOOL, "-T", "-n", "-filename", "-FileNumber", folder_path],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=120, **_SUBPROCESS_KW
        )
    except Exception as e:
        return 0, len(files), [(f, str(e)) for f, _ in files]

    # Parse
    fn_map = {}  # old_fname -> file_number
    for line in result.stdout.strip().split('\n'):
        line = line.strip()
        if not line or '\t' not in line:
            continue
        parts = line.split('\t')
        fname = parts[0].strip()
        fn_str = parts[1].strip() if len(parts) > 1 else '-'
        if fn_str not in ('', '-'):
            try:
                fn_map[fname] = int(float(fn_str))
            except ValueError:
                pass

    # Build rename plan
    rename_plan = []  # (old_path, new_path)
    collisions = {}   # new_path -> count
    skipped = 0
    errors = []

    for old_name, old_path in files:
        if old_name not in fn_map:
            skipped += 1
            continue
        fn = fn_map[old_name]
        new_name = f"DSC_{fn:04d}.NEF"
        new_path = os.path.join(folder_path, new_name)
        if old_path.lower() == new_path.lower():
            skipped += 1
            continue
        if new_path in collisions:
            collisions[new_path] += 1
            base, ext = os.path.splitext(new_name)
            new_name = f"{base}_{collisions[new_path]}{ext}"
            new_path = os.path.join(folder_path, new_name)
        collisions[new_path] = 0
        rename_plan.append((old_path, new_path))

    # Execute
    renamed = 0
    for i, (old, new) in enumerate(rename_plan):
        if progress_cb:
            progress_cb(i, len(rename_plan))
        try:
            if os.path.exists(new):
                errors.append((os.path.basename(old),
                               f"Target already exists: {os.path.basename(new)}"))
                continue
            os.rename(old, new)
            renamed += 1
        except Exception as e:
            errors.append((os.path.basename(old), str(e)))

    if progress_cb:
        progress_cb(len(rename_plan), len(rename_plan))

    return renamed, skipped, errors
