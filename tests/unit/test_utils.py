from cyberflash.utils.ansi_utils import ansi_to_html, strip_ansi
from cyberflash.utils.size_utils import format_size


def test_format_size_bytes():
    assert format_size(0) == "0 B"
    assert format_size(512) == "512.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 ** 3) == "1.0 GB"
    assert format_size(-1) == "Unknown"


def test_strip_ansi():
    colored = "\x1b[32mHello\x1b[0m World"
    assert strip_ansi(colored) == "Hello World"


def test_strip_ansi_no_codes():
    plain = "Hello World"
    assert strip_ansi(plain) == plain


def test_ansi_to_html_removes_codes():
    colored = "\x1b[32mHello\x1b[0m"
    html = ansi_to_html(colored)
    assert "\x1b" not in html
    assert "Hello" in html
