"""Walidacja i rozwiązywanie względnej ścieżki wyjściowej."""
import os
import re

_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def normalize_out_dir(raw, default="default"):
    """Zwraca znormalizowaną ścieżkę względną (z "/") albo rzuca ValueError."""
    path = (raw or "").strip().replace("\\", "/")
    if path.startswith("/") or _DRIVE_RE.match(path):
        raise ValueError("Ścieżka musi być względna (bez / na początku i bez litery dysku).")
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise ValueError("Ścieżka nie może zawierać „..”.")
    if any(ord(c) < 32 for c in path):
        raise ValueError("Ścieżka zawiera niedozwolone znaki.")
    return "/".join(parts) or default


def resolve_out_dir(output_root, rel):
    """Zwraca ścieżkę absolutną dla `rel`; rzuca ValueError, jeśli wychodzi poza output_root."""
    root = os.path.realpath(output_root)
    target = os.path.realpath(os.path.join(root, *rel.split("/")))
    if os.path.commonpath([root, target]) != root:
        raise ValueError("Ścieżka wychodzi poza katalog wyjściowy.")
    return target
