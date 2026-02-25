"""Known-good and known-bad domain reputation lists for ROM sources.

These curated lists power the first heuristic layer of the
:class:`SourceScorer` trust engine.  Domains can also be loaded from
user-supplied JSON files at runtime.

This module lives in ``core/`` and contains no Qt imports.
"""

from __future__ import annotations

from typing import Final

# ── Verified / Trusted ROM Sources ────────────────────────────────────────────
# Official project domains and well-known mirrors.

TRUSTED_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        # LineageOS
        "download.lineageos.org",
        "lineageos.org",
        "mirror.math.princeton.edu",
        # Pixel Experience
        "download.pixelexperience.org",
        "pixelexperience.org",
        # crDroid
        "crdroid.net",
        "sourceforge.net",
        # /e/OS
        "e.foundation",
        "images.ecloud.global",
        # CalyxOS
        "calyxos.org",
        "release.calyxinstitute.org",
        # GrapheneOS
        "grapheneos.org",
        "releases.grapheneos.org",
        # DivestOS
        "divestos.org",
        # Paranoid Android
        "paranoidandroid.co",
        "aospa.co",
        # ArrowOS
        "arrowos.net",
        # Evolution X
        "evolution-x.org",
        # DerpFest
        "derpfest.org",
        # AOSP mirrors
        "android.googlesource.com",
        "dl.google.com",
        # Trusted hosting
        "github.com",
        "github.io",
        "gitlab.com",
        "androidfilehost.com",
        "mega.nz",
        # TWRP
        "dl.twrp.me",
        "twrp.me",
        # Magisk
        "github.com/topjohnwu",
        # NetHunter
        "kali.org",
        "nethunter.com",
        # XDA
        "xdaforums.com",
        "xda-developers.com",
    }
)

# ── Suspicious / Dangerous Domains ────────────────────────────────────────────
# Known malware distributors, phishing sites, and ad-farm mirrors.

BLOCKED_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "firmwarefile.com",
        "romsfirmware.com",
        "androidresult.com",
        "androidsage.com",
        "flashfilebd.com",
        "needrom.com",
        "romshillzz.net",
        "mfrtech.com",
        "stockromfiles.com",
        "flashfile25.com",
        "firmwaretoday.com",
        "gsmfirmware.net",
        "firmware-file.com",
        "gsmmafia.com",
        "phonefirmware.com",
        "updateboss.com",
    }
)

# ── Suspicious TLD Patterns ──────────────────────────────────────────────────
# Top-level domains frequently used by ad-farm and malware domains.

SUSPICIOUS_TLDS: Final[frozenset[str]] = frozenset(
    {
        ".xyz",
        ".top",
        ".club",
        ".buzz",
        ".icu",
        ".pw",
        ".tk",
        ".ml",
        ".ga",
        ".cf",
        ".gq",
        ".work",
        ".click",
        ".loan",
        ".download",
    }
)

# ── Suspicious URL Patterns ──────────────────────────────────────────────────
# Fragments commonly found in deceptive ROM download URLs.

SUSPICIOUS_URL_FRAGMENTS: Final[frozenset[str]] = frozenset(
    {
        "adf.ly",
        "bit.ly/",
        "linkvertise.com",
        "ouo.io",
        "shrinkme.io",
        "exe.io",
        "bc.vc",
        "cutt.ly",
        "short.am",
        "za.gl",
        "link-center.net",
        "/download?token=",
        "/getfile.php?",
        "mediafire.com/folder/",  # folders, not direct links
        "?password=",
    }
)


def is_trusted_domain(domain: str) -> bool:
    """Return True if *domain* matches a known trusted source."""
    domain = domain.lower().strip()
    return any(domain == trusted or domain.endswith("." + trusted) for trusted in TRUSTED_DOMAINS)


def is_blocked_domain(domain: str) -> bool:
    """Return True if *domain* matches a known dangerous source."""
    domain = domain.lower().strip()
    return any(domain == blocked or domain.endswith("." + blocked) for blocked in BLOCKED_DOMAINS)


def has_suspicious_tld(domain: str) -> bool:
    """Return True if the domain uses a suspicious TLD."""
    domain = domain.lower().strip()
    return any(domain.endswith(tld) for tld in SUSPICIOUS_TLDS)


def has_suspicious_url_fragment(url: str) -> bool:
    """Return True if the URL contains known suspicious fragments."""
    url_lower = url.lower()
    return any(frag in url_lower for frag in SUSPICIOUS_URL_FRAGMENTS)
