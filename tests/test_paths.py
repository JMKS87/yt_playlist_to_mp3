import os

import pytest

from app.paths import normalize_out_dir, resolve_out_dir


@pytest.mark.parametrize("raw, expected", [
    ("", "default"),
    ("   ", "default"),
    (None, "default"),
    (".", "default"),
    ("muzyka", "muzyka"),
    ("test/sub", "test/sub"),
    (" test/sub/ ", "test/sub"),
    ("test//sub", "test/sub"),
    ("./test/./sub", "test/sub"),
    ("test\\sub", "test/sub"),
    ("Muzyka 2026/Rock", "Muzyka 2026/Rock"),
    ("a..b", "a..b"),
])
def test_normalize_ok(raw, expected):
    assert normalize_out_dir(raw) == expected


def test_normalize_custom_default():
    assert normalize_out_dir("", default="inne") == "inne"


@pytest.mark.parametrize("raw", [
    "..",
    "../x",
    "a/../../b",
    "a/..",
    "a\\..\\b",
    "/data/output",
    "/etc",
    "\\server\\share",
    "C:\\muzyka",
    "c:muzyka",
    "D:/x",
    "a\x00b",
    "a\nb",
])
def test_normalize_rejects(raw):
    with pytest.raises(ValueError):
        normalize_out_dir(raw)


def test_resolve_inside_root(tmp_path):
    root = tmp_path / "output"
    root.mkdir()
    assert resolve_out_dir(str(root), "test/sub") == os.path.join(os.path.realpath(root), "test", "sub")
    assert resolve_out_dir(str(root), "default") == os.path.join(os.path.realpath(root), "default")


@pytest.mark.skipif(os.name == "nt", reason="symlinki na Windows wymagają uprawnień")
def test_resolve_rejects_symlink_escape(tmp_path):
    root = tmp_path / "output"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        resolve_out_dir(str(root), "link/x")
