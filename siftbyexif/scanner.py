# Copyright (c) 2026 FireSwordss. Free for non-commercial use.
"""Camera photo detection and corruption scanning."""

import os, struct, subprocess, sys
from PIL import Image, ImageFile
from .brands import BRANDS, ALL_MAKES

# Suppress console windows from ExifTool subprocess in PyInstaller --windowed
_SUBPROCESS_KW = {}
if sys.platform == 'win32':
    _SUBPROCESS_KW['creationflags'] = subprocess.CREATE_NO_WINDOW

ImageFile.LOAD_TRUNCATED_IMAGES = True

EXIFTOOL = os.path.expandvars(
    r"%LOCALAPPDATA%\Programs\ExifTool\ExifTool.exe"
)


# ============================================================
# Camera photo detection
# ============================================================

def detect_fast(filepath, selected_brands=None):
    """Mode 1: filename match first, then EXIF verify."""
    fname = os.path.basename(filepath).upper()
    brands = _resolve_brands(selected_brands)

    # Step 1: filename pattern match
    matched_brand = None
    for brand_name, brand_def in brands.items():
        for pat in brand_def["patterns"]:
            if pat.upper() in fname:
                matched_brand = brand_name
                break
        if not matched_brand:
            ext = os.path.splitext(fname)[1].lower()
            if ext in [e.lower() for e in brand_def["extensions"]]:
                matched_brand = brand_name
    if not matched_brand:
        return None  # No filename match, skip

    # Step 2: EXIF verify
    if _exif_is_camera(filepath, brands):
        return matched_brand
    return None


def detect_recovery(filepath, selected_brands=None):
    """Mode 2: full EXIF scan, filename ignored."""
    brands = _resolve_brands(selected_brands)
    exif_brand = _exif_detect_brand(filepath, brands)
    return exif_brand


def _resolve_brands(selected_brands):
    """Return dict of selected brands, or all if none selected."""
    if not selected_brands:
        return BRANDS
    return {k: v for k, v in BRANDS.items() if k in selected_brands}


def _exif_is_camera(filepath, brands):
    """Check if file has camera EXIF markers from any known brand."""
    make, model, has_mk = _read_exif_basic(filepath)
    make_u = make.upper()
    model_u = model.upper()
    if has_mk:
        return True
    for brand_def in brands.values():
        for m in brand_def["makes"]:
            if m in make_u or m in model_u:
                return True
    return False


def _exif_detect_brand(filepath, brands):
    """Return brand name if EXIF matches, else None."""
    make, model, has_mk = _read_exif_basic(filepath)
    make_u = make.upper()
    model_u = model.upper()
    if has_mk:
        # With MakerNote, try to match brand
        for brand_name, brand_def in brands.items():
            for m in brand_def["makes"]:
                if m in make_u or m in model_u:
                    return brand_name
        return "UnknownCamera"
    for brand_name, brand_def in brands.items():
        for m in brand_def["makes"]:
            if m in make_u or m in model_u:
                return brand_name
    return None


def _read_exif_basic(filepath):
    """Return (make, model, has_makernote) from a file."""
    try:
        img = Image.open(filepath)
        exif = img.getexif()
        make = str(exif.get(271, ""))
        model = str(exif.get(272, ""))
        mk = exif.get(0x927C) is not None
        img.close()
        return make, model, mk
    except Exception:
        return "", "", False


# ============================================================
# Corruption scan
# ============================================================

def median_iqr(values):
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0, 0, 0, 0
    return s[n // 2], s[n // 4], s[3 * n // 4], s[3 * n // 4] - s[n // 4]


def scan_folder(folder_path, progress_cb=None):
    """Scan a folder for NEF corruption. Returns list of (fname, issues).

    issues = [(check_name, severity, message), ...]
    """
    from PIL import Image

    # Gather NEF files
    files = []
    for fname in sorted(os.listdir(folder_path)):
        fpath = os.path.join(folder_path, fname)
        if os.path.isfile(fpath) and fname.upper().endswith('.NEF'):
            files.append((fname, fpath))

    if not files:
        return []

    # Batch stats: file sizes
    sizes = [os.path.getsize(f[1]) for f in files]
    sz_med, _, _, sz_iqr = median_iqr(sizes)

    # Batch stats: MakerNote sizes
    mk_sizes = []
    for _, fp in files:
        try:
            img = Image.open(fp)
            exif = img.getexif()
            ef = exif.get_ifd(0x8769)
            if ef:
                mk = ef.get(37500)
                if mk and isinstance(mk, bytes):
                    mk_sizes.append(len(mk))
            img.close()
        except Exception:
            pass
    mk_med, _, _, mk_iqr = median_iqr(mk_sizes) if mk_sizes else (0, 0, 0, 0)

    results = []
    for i, (fname, fpath) in enumerate(files):
        if progress_cb:
            progress_cb(i, len(files))

        issues = []

        # FILE_OPEN
        try:
            with open(fpath, 'rb') as f:
                f.read(1024)
        except Exception as e:
            issues.append(("FILE_OPEN", "HIGH", str(e)))
            results.append((fname, issues))
            continue

        # FILE_SIZE
        if sz_iqr > 0:
            dev = abs(os.path.getsize(fpath) - sz_med)
            if dev > 3 * sz_iqr:
                issues.append(("FILE_SIZE", "MEDIUM",
                    f"{os.path.getsize(fpath):,} bytes (dev={dev:,})"))

        # NEF_STRUCTURE
        ok, msg = _check_nef_structure(fpath)
        if not ok:
            issues.append(("NEF_STRUCTURE", "HIGH", msg))

        # MAKERNOTE_SIZE
        ms = _get_makernote_size(fpath)
        if ms > 0 and mk_iqr > 0:
            dev = abs(ms - mk_med)
            if dev > 3 * mk_iqr:
                issues.append(("MAKERNOTE_SIZE", "MEDIUM",
                    f"{ms:,} bytes (dev={dev:,})"))
        elif ms == 0:
            issues.append(("MAKERNOTE_SIZE", "MEDIUM", "No MakerNote"))

        # EXIF_PARSE via ExifTool
        ok, msg = _check_exif_parse(fpath)
        if not ok:
            issues.append(("EXIF_PARSE", "MEDIUM", msg))

        # NEF_EMBEDDED
        ok, msg = _check_nef_embedded(fpath)
        if not ok:
            issues.append(("NEF_EMBEDDED", "HIGH", msg))

        results.append((fname, issues))

    if progress_cb:
        progress_cb(len(files), len(files))

    return results


def _check_nef_structure(path):
    issues = []
    try:
        with open(path, 'rb') as f:
            header = f.read(8)
            if header[:2] not in (b'II', b'MM'):
                return False, "Not valid TIFF header"
            be = header[:2] == b'MM'
            tiff_magic = struct.unpack('>H' if be else '<H', header[2:4])[0]
            if tiff_magic != 0x002A:
                return False, f"Bad TIFF magic: {tiff_magic:#06x}"
            ifd_offset = struct.unpack('>I' if be else '<I', header[4:8])[0]
            f.seek(0, 2)
            file_size = f.tell()
            for chain_idx in range(10):
                if ifd_offset == 0 or ifd_offset >= file_size:
                    break
                f.seek(ifd_offset)
                ec = struct.unpack('>H' if be else '<H', f.read(2))[0]
                if ec > 1000:
                    issues.append(f"IFD{chain_idx} excessive entries:{ec}")
                    break
                for _ in range(ec):
                    entry = f.read(12)
                    if len(entry) < 12:
                        issues.append("IFD entry truncated")
                        break
                    tag, typ = struct.unpack('>HH' if be else '<HH', entry[:4])
                    count, vo = struct.unpack('>II' if be else '<II', entry[4:])
                    if tag in (273, 279) and typ == 4:
                        vals = []
                        if count == 1:
                            vals = [vo]
                        elif count > 1 and vo < file_size:
                            f.seek(vo)
                            raw = f.read(count * 4)
                            fmt = f">{count}I" if be else f"<{count}I"
                            vals = struct.unpack(fmt, raw)
                        for v in vals:
                            if v >= file_size:
                                issues.append(f"Tag{tag} offset {v} beyond EOF")
                next_off = f.read(4)
                if len(next_off) < 4:
                    break
                ifd_offset = struct.unpack('>I' if be else '<I', next_off)[0]
        if issues:
            return False, "; ".join(issues)
        return True, ""
    except Exception as e:
        return False, str(e)


def _get_makernote_size(path):
    try:
        img = Image.open(path)
        exif = img.getexif()
        ef = exif.get_ifd(0x8769)
        if ef:
            mk = ef.get(37500)
            if mk and isinstance(mk, bytes):
                return len(mk)
        img.close()
    except Exception:
        pass
    return 0


def _check_exif_parse(path):
    try:
        result = subprocess.run(
            [EXIFTOOL, "-T", "-n", "-ShutterCount", "-FileNumber", path],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            timeout=30, **_SUBPROCESS_KW
        )
        se = (result.stderr or "").lower()
        for kw in ["filename encoding", "file name encoding"]:
            se = se.replace(kw, "")
        if se.strip():
            return False, se.strip()[:200]
        parts = result.stdout.strip().split('\t')
        sc = parts[0].strip() if len(parts) > 0 else '-'
        fn = parts[1].strip() if len(parts) > 1 else '-'
        if sc in ('', '-'):
            return False, "Missing ShutterCount"
        if fn in ('', '-'):
            return False, "Missing FileNumber"
        return True, f"SC={sc}, FN={fn}"
    except Exception as e:
        return False, str(e)


def _check_nef_embedded(path):
    import tempfile
    try:
        result = subprocess.run(
            [EXIFTOOL, "-b", "-JpgFromRaw", path],
            capture_output=True, timeout=30, **_SUBPROCESS_KW
        )
        if not result.stdout or len(result.stdout) < 1000:
            return False, "Embedded JPEG too small or empty"
        tmp = os.path.join(tempfile.gettempdir(),
                           f"_nscan_{os.path.basename(path)}.jpg")
        with open(tmp, 'wb') as f:
            f.write(result.stdout)
        try:
            # Disable LOAD_TRUNCATED for integrity check -
            # must fail on corrupt data, not silently accept
            ImageFile.LOAD_TRUNCATED_IMAGES = False
            img = Image.open(tmp)
            img.load()
            return True, f"{img.size[0]}x{img.size[1]}"
        except Exception as e:
            return False, str(e)[:150]
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            if os.path.exists(tmp):
                os.remove(tmp)
    except Exception as e:
        return False, str(e)
