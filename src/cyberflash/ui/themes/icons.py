"""icons.py — Premium 3D-style SVG icon library for CyberFlash sidebar.

All icons use a 24x24 viewBox and are rendered at 32x32 pixels.
Each SVG uses {COLOR} as a runtime substitution placeholder.

3D effect technique:
  - Main shape filled with {COLOR}
  - Top-left white gradient overlay for lit-from-above depth
  - Bottom-right shadow layer (black, low opacity)
  - Where applicable: inner highlight for glass/metallic sheen
  - Drop-shadow filter for floating effect
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer

# ── Shared gradient/filter snippet ────────────────────────────────────────────
# Each icon embeds its own <defs> so gradients never collide across icons.

# ─────────────────────────────────────────────────────────────────────────────
# 1. DASHBOARD — Four 3D tiles, lit from top-left
# ─────────────────────────────────────────────────────────────────────────────
ICON_DASHBOARD = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="dg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="dh" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="df">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.55"/>
    </filter>
  </defs>
  <!-- Top-left tile (brightest) -->
  <rect x="1.5" y="1.5" width="9.5" height="9.5" rx="2.5" fill="url(#dg)" filter="url(#df)"/>
  <rect x="1.5" y="1.5" width="9.5" height="9.5" rx="2.5" fill="url(#dh)"/>
  <!-- Top-right tile -->
  <rect x="13" y="1.5" width="9.5" height="9.5" rx="2.5" fill="{COLOR}" opacity="0.75" filter="url(#df)"/>
  <rect x="13" y="1.5" width="9.5" height="9.5" rx="2.5" fill="url(#dh)" opacity="0.7"/>
  <!-- Bottom-left tile -->
  <rect x="1.5" y="13" width="9.5" height="9.5" rx="2.5" fill="{COLOR}" opacity="0.75" filter="url(#df)"/>
  <rect x="1.5" y="13" width="9.5" height="9.5" rx="2.5" fill="url(#dh)" opacity="0.7"/>
  <!-- Bottom-right tile (darkest) -->
  <rect x="13" y="13" width="9.5" height="9.5" rx="2.5" fill="{COLOR}" opacity="0.5" filter="url(#df)"/>
  <rect x="13" y="13" width="9.5" height="9.5" rx="2.5" fill="url(#dh)" opacity="0.5"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 2. DEVICE — 3D smartphone with screen glow and depth
# ─────────────────────────────────────────────────────────────────────────────
ICON_DEVICE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="body" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{COLOR}" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="screen" x1="0.2" y1="0" x2="0.8" y2="1">
      <stop offset="0%" stop-color="{COLOR}" stop-opacity="0.25"/>
      <stop offset="50%" stop-color="{COLOR}" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.22"/>
    </linearGradient>
    <linearGradient id="shine" x1="0" y1="0" x2="0.5" y2="0.7">
      <stop offset="0%" stop-color="white" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="devglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.5"
        flood-color="{COLOR}" flood-opacity="0.65"/>
    </filter>
  </defs>
  <!-- Phone body frame -->
  <rect x="5" y="1" width="14" height="22" rx="3" fill="url(#body)" filter="url(#devglow)"/>
  <!-- Right edge shadow for 3D depth -->
  <rect x="17" y="2.5" width="1.5" height="19" rx="0.5" fill="black" opacity="0.2"/>
  <!-- Bottom edge shadow -->
  <rect x="5.5" y="21" width="12" height="1.5" rx="0.5" fill="black" opacity="0.2"/>
  <!-- Screen area -->
  <rect x="7" y="4.5" width="10" height="14" rx="1.5" fill="url(#screen)"/>
  <rect x="7" y="4.5" width="10" height="14" rx="1.5"
    fill="none" stroke="{COLOR}" stroke-width="0.5" stroke-opacity="0.4"/>
  <!-- Camera + speaker bar at top -->
  <rect x="9.5" y="2.5" width="5" height="1" rx="0.5" fill="{COLOR}" opacity="0.5"/>
  <circle cx="15.5" cy="3" r="0.65" fill="{COLOR}" opacity="0.7"/>
  <!-- Home indicator bar -->
  <rect x="9.5" y="20.2" width="5" height="1.2" rx="0.6" fill="{COLOR}" opacity="0.65"/>
  <!-- Screen scan line highlight -->
  <rect x="7.5" y="5" width="5" height="13" rx="1"
    fill="url(#shine)" opacity="0.6"/>
  <!-- Screen active dot (glow) -->
  <circle cx="12" cy="11.5" r="2.5" fill="{COLOR}" opacity="0.12"/>
  <circle cx="12" cy="11.5" r="1.2" fill="{COLOR}" opacity="0.2"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 3. FLASH — 3D lightning bolt with metallic sheen
# ─────────────────────────────────────────────────────────────────────────────
ICON_FLASH = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="fg" x1="0.1" y1="0" x2="0.9" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.5"/>
    </linearGradient>
    <linearGradient id="fh" x1="0" y1="0" x2="0.4" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.55"/>
      <stop offset="40%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="fglow">
      <feDropShadow dx="0" dy="2" stdDeviation="2"
        flood-color="{COLOR}" flood-opacity="0.75"/>
    </filter>
  </defs>
  <!-- Shadow bolt (3D extrusion) -->
  <polygon points="13.5,1.5 5,13 11.5,13 10.5,22.5 19,11 12.5,11"
    fill="{COLOR}" opacity="0.3" transform="translate(1.5,1.5)"/>
  <!-- Main bolt -->
  <polygon points="13.5,1.5 5,13 11.5,13 10.5,22.5 19,11 12.5,11"
    fill="url(#fg)" filter="url(#fglow)"/>
  <!-- Highlight overlay -->
  <polygon points="13.5,1.5 5,13 11.5,13 10.5,22.5 19,11 12.5,11"
    fill="url(#fh)"/>
  <!-- Edge highlight line -->
  <line x1="13.5" y1="1.5" x2="5" y2="13"
    stroke="white" stroke-width="0.7" stroke-opacity="0.35" stroke-linecap="round"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 4. ROM LIBRARY — 3D stacked database disks
# ─────────────────────────────────────────────────────────────────────────────
ICON_ROM_LIBRARY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="rg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.5"/>
    </linearGradient>
    <linearGradient id="rh" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="rglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1"
        flood-color="{COLOR}" flood-opacity="0.5"/>
    </filter>
  </defs>
  <!-- Bottom disk (darkest/furthest) -->
  <rect x="2" y="17" width="20" height="5" rx="2.5" fill="{COLOR}" opacity="0.45" filter="url(#rglow)"/>
  <rect x="2" y="17" width="20" height="2" rx="2.5" fill="url(#rh)" opacity="0.5"/>
  <!-- Disk detail line -->
  <line x1="18" y1="19.5" x2="20" y2="19.5" stroke="white" stroke-width="1" stroke-opacity="0.3" stroke-linecap="round"/>
  <!-- Middle disk -->
  <rect x="2" y="10.5" width="20" height="5" rx="2.5" fill="{COLOR}" opacity="0.7" filter="url(#rglow)"/>
  <rect x="2" y="10.5" width="20" height="2" rx="2.5" fill="url(#rh)"/>
  <line x1="18" y1="13" x2="20" y2="13" stroke="white" stroke-width="1" stroke-opacity="0.35" stroke-linecap="round"/>
  <!-- Top disk (brightest/closest) -->
  <rect x="2" y="4" width="20" height="5" rx="2.5" fill="url(#rg)" filter="url(#rglow)"/>
  <rect x="2" y="4" width="20" height="2.2" rx="2.5" fill="url(#rh)"/>
  <line x1="18" y1="6.5" x2="20" y2="6.5" stroke="white" stroke-width="1" stroke-opacity="0.45" stroke-linecap="round"/>
  <circle cx="5.5" cy="6.5" r="0.8" fill="white" opacity="0.5"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 5. BACKUP — 3D download to hard drive
# ─────────────────────────────────────────────────────────────────────────────
ICON_BACKUP = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.5"/>
    </linearGradient>
    <linearGradient id="bh" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="bglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.5"
        flood-color="{COLOR}" flood-opacity="0.6"/>
    </filter>
  </defs>
  <!-- Drive body (3D bottom edge) -->
  <rect x="3" y="15.5" width="18" height="7" rx="2.5" fill="{COLOR}" opacity="0.5" filter="url(#bglow)"/>
  <!-- Drive top face -->
  <rect x="3" y="14" width="18" height="7" rx="2.5" fill="url(#bg)"/>
  <rect x="3" y="14" width="18" height="3" rx="2.5" fill="url(#bh)"/>
  <!-- Drive LED dot -->
  <circle cx="6.5" cy="17.5" r="1" fill="white" opacity="0.6"/>
  <!-- Download arrow shaft -->
  <line x1="12" y1="2" x2="12" y2="11"
    stroke="{COLOR}" stroke-width="2.5" stroke-linecap="round" filter="url(#bglow)"/>
  <!-- Arrow head -->
  <polygon points="12,13 7.5,8.5 16.5,8.5" fill="{COLOR}" filter="url(#bglow)"/>
  <!-- Arrow head highlight -->
  <line x1="7.5" y1="8.5" x2="12" y2="13"
    stroke="white" stroke-width="0.7" stroke-opacity="0.4" stroke-linecap="round"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 6. ROOT — 3D shield with crown/key emblem
# ─────────────────────────────────────────────────────────────────────────────
ICON_ROOT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="shg" x1="0" y1="0" x2="0.7" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="shh" x1="0" y1="0" x2="0.5" y2="0.8">
      <stop offset="0%" stop-color="white" stop-opacity="0.5"/>
      <stop offset="60%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="shglow">
      <feDropShadow dx="0" dy="2.5" stdDeviation="2"
        flood-color="{COLOR}" flood-opacity="0.7"/>
    </filter>
  </defs>
  <!-- Shield silhouette (3D shadow) -->
  <path d="M12 2.5 L21 6 L21 13 Q21 19 12 22.5 Q3 19 3 13 L3 6 Z"
    fill="{COLOR}" opacity="0.25" transform="translate(0.8,1)"/>
  <!-- Shield body -->
  <path d="M12 2.5 L21 6 L21 13 Q21 19 12 22.5 Q3 19 3 13 L3 6 Z"
    fill="url(#shg)" filter="url(#shglow)"/>
  <!-- Shield highlight overlay -->
  <path d="M12 2.5 L21 6 L21 13 Q21 19 12 22.5 Q3 19 3 13 L3 6 Z"
    fill="url(#shh)"/>
  <!-- Crown emblem -->
  <path d="M8 15 L8 11 L10 13 L12 9 L14 13 L16 11 L16 15 Z"
    fill="black" opacity="0.35"/>
  <path d="M8 15 L8 11 L10 13 L12 9 L14 13 L16 11 L16 15 Z"
    fill="white" opacity="0.8"/>
  <!-- Shield edge highlight (left edge lit) -->
  <line x1="3" y1="6" x2="3" y2="13"
    stroke="white" stroke-width="1" stroke-opacity="0.4" stroke-linecap="round"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 7. NETHUNTER — Kali dragon claw / cyber target
# ─────────────────────────────────────────────────────────────────────────────
ICON_NETHUNTER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="nhg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="nhh" x1="0" y1="0" x2="0.4" y2="0.6">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="nhglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.8"
        flood-color="{COLOR}" flood-opacity="0.75"/>
    </filter>
  </defs>
  <!-- Outer target ring -->
  <circle cx="12" cy="12" r="10" fill="none"
    stroke="{COLOR}" stroke-width="1.5" stroke-opacity="0.6" filter="url(#nhglow)"/>
  <!-- Crosshair lines -->
  <line x1="12" y1="2" x2="12" y2="6.5"
    stroke="{COLOR}" stroke-width="1.5" stroke-linecap="round" filter="url(#nhglow)"/>
  <line x1="12" y1="17.5" x2="12" y2="22"
    stroke="{COLOR}" stroke-width="1.5" stroke-linecap="round" filter="url(#nhglow)"/>
  <line x1="2" y1="12" x2="6.5" y2="12"
    stroke="{COLOR}" stroke-width="1.5" stroke-linecap="round" filter="url(#nhglow)"/>
  <line x1="17.5" y1="12" x2="22" y2="12"
    stroke="{COLOR}" stroke-width="1.5" stroke-linecap="round" filter="url(#nhglow)"/>
  <!-- Inner ring -->
  <circle cx="12" cy="12" r="5.5" fill="none"
    stroke="{COLOR}" stroke-width="1.2" stroke-opacity="0.8" filter="url(#nhglow)"/>
  <!-- Center target dot (3D sphere) -->
  <circle cx="12" cy="12" r="2.8" fill="url(#nhg)" filter="url(#nhglow)"/>
  <circle cx="12" cy="12" r="2.8" fill="url(#nhh)"/>
  <!-- Top-left highlight on center dot -->
  <circle cx="11.1" cy="11.1" r="0.8" fill="white" opacity="0.55"/>
  <!-- Corner tick marks -->
  <path d="M4.5 6.5 L6.5 6.5 L6.5 4.5" fill="none"
    stroke="{COLOR}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.7"/>
  <path d="M19.5 6.5 L17.5 6.5 L17.5 4.5" fill="none"
    stroke="{COLOR}" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" stroke-opacity="0.7"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 8. PARTITION — 3D storage blocks / partition table
# ─────────────────────────────────────────────────────────────────────────────
ICON_PARTITION = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="pg" x1="0" y1="0" x2="0.5" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="ph" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.4"/>
      <stop offset="50%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="pglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.5"/>
    </filter>
  </defs>
  <!-- Drive body frame (3D depth - right and bottom edge) -->
  <rect x="3.5" y="3.5" width="17" height="17" rx="2.5"
    fill="{COLOR}" opacity="0.3" transform="translate(1,1.2)"/>
  <!-- Main drive body -->
  <rect x="3.5" y="3.5" width="17" height="17" rx="2.5"
    fill="url(#pg)" filter="url(#pglow)"/>
  <rect x="3.5" y="3.5" width="17" height="8" rx="2.5"
    fill="url(#ph)"/>
  <!-- Vertical dividers -->
  <line x1="10" y1="5" x2="10" y2="19"
    stroke="black" stroke-width="0.5" stroke-opacity="0.25"/>
  <line x1="10" y1="5" x2="10" y2="19"
    stroke="white" stroke-width="0.5" stroke-opacity="0.2"/>
  <line x1="15.5" y1="5" x2="15.5" y2="19"
    stroke="black" stroke-width="0.5" stroke-opacity="0.25"/>
  <line x1="15.5" y1="5" x2="15.5" y2="19"
    stroke="white" stroke-width="0.5" stroke-opacity="0.2"/>
  <!-- Horizontal dividers -->
  <line x1="5" y1="12" x2="19" y2="12"
    stroke="black" stroke-width="0.5" stroke-opacity="0.25"/>
  <line x1="5" y1="12" x2="19" y2="12"
    stroke="white" stroke-width="0.5" stroke-opacity="0.2"/>
  <!-- Partition color patches -->
  <rect x="4.5" y="4.5" width="4.5" height="6.5" rx="1"
    fill="white" opacity="0.18"/>
  <rect x="11" y="4.5" width="3.5" height="6.5" rx="1"
    fill="white" opacity="0.1"/>
  <rect x="4.5" y="13" width="9.5" height="6.5" rx="1"
    fill="white" opacity="0.12"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 9. TERMINAL — 3D monitor with command prompt
# ─────────────────────────────────────────────────────────────────────────────
ICON_TERMINAL = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="tg" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="tscreen" x1="0.2" y1="0" x2="0.8" y2="1">
      <stop offset="0%" stop-color="{COLOR}" stop-opacity="0.15"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.05"/>
    </linearGradient>
    <linearGradient id="th" x1="0" y1="0" x2="0.5" y2="0.7">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="tglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.5"
        flood-color="{COLOR}" flood-opacity="0.65"/>
    </filter>
  </defs>
  <!-- Monitor shadow (3D depth) -->
  <rect x="2.5" y="3.5" width="19" height="14" rx="2.5"
    fill="{COLOR}" opacity="0.3" transform="translate(0.8,1.2)"/>
  <!-- Monitor bezel -->
  <rect x="2.5" y="3.5" width="19" height="14" rx="2.5"
    fill="url(#tg)" filter="url(#tglow)"/>
  <!-- Monitor bezel highlight -->
  <rect x="2.5" y="3.5" width="19" height="6" rx="2.5"
    fill="url(#th)"/>
  <!-- Screen area (dark, recessed) -->
  <rect x="4.5" y="5.5" width="15" height="10" rx="1.5"
    fill="url(#tscreen)"/>
  <rect x="4.5" y="5.5" width="15" height="10" rx="1.5"
    fill="none" stroke="{COLOR}" stroke-width="0.4" stroke-opacity="0.5"/>
  <!-- Terminal caret symbol -->
  <polyline points="6.5,9 9.5,11.5 6.5,14"
    fill="none" stroke="{COLOR}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
    filter="url(#tglow)"/>
  <!-- Cursor underline -->
  <rect x="11" y="13.5" width="5" height="1.2" rx="0.6"
    fill="{COLOR}" opacity="0.9" filter="url(#tglow)"/>
  <!-- Stand base -->
  <path d="M10 17.5 L14 17.5 L15 20 L9 20 Z"
    fill="url(#tg)" opacity="0.8"/>
  <rect x="8" y="20" width="8" height="1.5" rx="0.75"
    fill="url(#tg)"/>
  <rect x="8" y="20" width="8" height="0.8" rx="0.75"
    fill="url(#th)"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 10. DIAGNOSTICS — 3D ECG / heartbeat monitor
# ─────────────────────────────────────────────────────────────────────────────
ICON_DIAGNOSTICS = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="diag" x1="0" y1="0" x2="0.5" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.5"/>
    </linearGradient>
    <linearGradient id="diah" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.4"/>
      <stop offset="60%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="diagglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.5"
        flood-color="{COLOR}" flood-opacity="0.65"/>
    </filter>
  </defs>
  <!-- Monitor body shadow (3D) -->
  <rect x="2" y="3" width="20" height="15" rx="2.5"
    fill="{COLOR}" opacity="0.25" transform="translate(0.8,1.2)"/>
  <!-- Monitor body -->
  <rect x="2" y="3" width="20" height="15" rx="2.5"
    fill="url(#diag)" filter="url(#diagglow)"/>
  <rect x="2" y="3" width="20" height="6" rx="2.5"
    fill="url(#diah)"/>
  <!-- Screen inner -->
  <rect x="3.5" y="4.5" width="17" height="12" rx="1.5"
    fill="black" opacity="0.45"/>
  <!-- ECG / waveform line -->
  <polyline
    points="4,12 6.5,12 8,7.5 9.5,16.5 11,10.5 12.5,10.5 13.5,12 16,12 17,9 18.5,12 20,12"
    fill="none" stroke="{COLOR}" stroke-width="1.8"
    stroke-linecap="round" stroke-linejoin="round"
    filter="url(#diagglow)"/>
  <!-- Scan line (animated feel) -->
  <line x1="12.5" y1="4.5" x2="12.5" y2="16.5"
    stroke="{COLOR}" stroke-width="0.5" stroke-opacity="0.25"
    stroke-dasharray="2,2"/>
  <!-- Stand -->
  <rect x="9.5" y="18" width="5" height="1.5" rx="0.75"
    fill="url(#diag)" opacity="0.8"/>
  <rect x="7.5" y="19.5" width="9" height="1.5" rx="0.75"
    fill="url(#diag)"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 11. SETTINGS — 3D metallic gear / cog
# ─────────────────────────────────────────────────────────────────────────────
ICON_SETTINGS = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <radialGradient id="gearRadial" cx="40%" cy="35%" r="65%">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </radialGradient>
    <linearGradient id="gearHi" x1="0" y1="0" x2="0.5" y2="0.5">
      <stop offset="0%" stop-color="white" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="gearglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.8"
        flood-color="{COLOR}" flood-opacity="0.65"/>
    </filter>
  </defs>
  <!-- Gear shadow (3D depth) -->
  <path d="M12 2 L13.5 4.2 L16 3.5 L16.5 5.8 L19 6 L18.5 8.5 L21 9.5 L19.8 12 L21 14.5 L18.5 15.5 L19 18 L16.5 18.2 L16 20.5 L13.5 19.8 L12 22 L10.5 19.8 L8 20.5 L7.5 18.2 L5 18 L5.5 15.5 L3 14.5 L4.2 12 L3 9.5 L5.5 8.5 L5 6 L7.5 5.8 L8 3.5 L10.5 4.2 Z"
    fill="{COLOR}" opacity="0.3" transform="translate(0.7,1)"/>
  <!-- Gear body -->
  <path d="M12 2 L13.5 4.2 L16 3.5 L16.5 5.8 L19 6 L18.5 8.5 L21 9.5 L19.8 12 L21 14.5 L18.5 15.5 L19 18 L16.5 18.2 L16 20.5 L13.5 19.8 L12 22 L10.5 19.8 L8 20.5 L7.5 18.2 L5 18 L5.5 15.5 L3 14.5 L4.2 12 L3 9.5 L5.5 8.5 L5 6 L7.5 5.8 L8 3.5 L10.5 4.2 Z"
    fill="url(#gearRadial)" filter="url(#gearglow)"/>
  <!-- Highlight overlay -->
  <path d="M12 2 L13.5 4.2 L16 3.5 L16.5 5.8 L19 6 L18.5 8.5 L21 9.5 L19.8 12 L21 14.5 L18.5 15.5 L19 18 L16.5 18.2 L16 20.5 L13.5 19.8 L12 22 L10.5 19.8 L8 20.5 L7.5 18.2 L5 18 L5.5 15.5 L3 14.5 L4.2 12 L3 9.5 L5.5 8.5 L5 6 L7.5 5.8 L8 3.5 L10.5 4.2 Z"
    fill="url(#gearHi)"/>
  <!-- Center hole with 3D concave effect -->
  <circle cx="12" cy="12" r="4.2"
    fill="black" opacity="0.5" filter="url(#gearglow)"/>
  <circle cx="12" cy="12" r="3.5"
    fill="{COLOR}" opacity="0.6"/>
  <!-- Inner rim highlight -->
  <circle cx="12" cy="12" r="3.5"
    fill="none" stroke="white" stroke-width="0.7" stroke-opacity="0.35"/>
  <!-- Top-left shine dot -->
  <circle cx="10.5" cy="10.5" r="1.2"
    fill="white" opacity="0.3"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 12. RESCUE — 3D lifebuoy / emergency cross
# ─────────────────────────────────────────────────────────────────────────────
ICON_RESCUE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <radialGradient id="rsg" cx="40%" cy="35%" r="65%">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </radialGradient>
    <linearGradient id="rsh" x1="0" y1="0" x2="0.5" y2="0.7">
      <stop offset="0%" stop-color="white" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="rsglow">
      <feDropShadow dx="0" dy="2.5" stdDeviation="2"
        flood-color="{COLOR}" flood-opacity="0.75"/>
    </filter>
  </defs>
  <!-- Outer ring shadow -->
  <circle cx="12" cy="12" r="10" fill="{COLOR}" opacity="0.2"
    transform="translate(0.6,1)"/>
  <!-- Outer ring -->
  <circle cx="12" cy="12" r="10" fill="url(#rsg)" filter="url(#rsglow)"/>
  <circle cx="12" cy="12" r="10" fill="url(#rsh)"/>
  <!-- Inner cutout -->
  <circle cx="12" cy="12" r="6.5" fill="black" opacity="0.55"/>
  <!-- Inner ring (accent) -->
  <circle cx="12" cy="12" r="6.5" fill="none"
    stroke="{COLOR}" stroke-width="0.6" stroke-opacity="0.4"/>
  <!-- Cross arms (plus symbol) -->
  <rect x="10.2" y="3.5" width="3.6" height="17" rx="1.8"
    fill="white" opacity="0.9" filter="url(#rsglow)"/>
  <rect x="3.5" y="10.2" width="17" height="3.6" rx="1.8"
    fill="white" opacity="0.9" filter="url(#rsglow)"/>
  <!-- Cross inner shadow cutout to restore ring look -->
  <circle cx="12" cy="12" r="5.8" fill="black" opacity="0.5"/>
  <!-- Final inner ring hint -->
  <circle cx="12" cy="12" r="5.8" fill="none"
    stroke="white" stroke-width="0.5" stroke-opacity="0.2"/>
  <!-- Top-left lens highlight -->
  <circle cx="9.5" cy="9.5" r="2" fill="white" opacity="0.2"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 13. APP MANAGER — 3D grid of 4 app tiles with badge dots
# ─────────────────────────────────────────────────────────────────────────────
ICON_APP_MANAGER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="amg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="amh" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="amglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.55"/>
    </filter>
  </defs>
  <!-- Top-left tile -->
  <rect x="1.5" y="1.5" width="9.5" height="9.5" rx="2.5" fill="url(#amg)" filter="url(#amglow)"/>
  <rect x="1.5" y="1.5" width="9.5" height="9.5" rx="2.5" fill="url(#amh)"/>
  <!-- Top-right tile -->
  <rect x="13" y="1.5" width="9.5" height="9.5" rx="2.5" fill="{COLOR}" opacity="0.75" filter="url(#amglow)"/>
  <rect x="13" y="1.5" width="9.5" height="9.5" rx="2.5" fill="url(#amh)" opacity="0.7"/>
  <!-- Bottom-left tile -->
  <rect x="1.5" y="13" width="9.5" height="9.5" rx="2.5" fill="{COLOR}" opacity="0.75" filter="url(#amglow)"/>
  <rect x="1.5" y="13" width="9.5" height="9.5" rx="2.5" fill="url(#amh)" opacity="0.7"/>
  <!-- Bottom-right tile -->
  <rect x="13" y="13" width="9.5" height="9.5" rx="2.5" fill="{COLOR}" opacity="0.5" filter="url(#amglow)"/>
  <rect x="13" y="13" width="9.5" height="9.5" rx="2.5" fill="url(#amh)" opacity="0.5"/>
  <!-- Badge dots (top-right corner of each tile) -->
  <circle cx="10" cy="3" r="1.8" fill="white" opacity="0.9"/>
  <circle cx="21.5" cy="3" r="1.8" fill="white" opacity="0.75"/>
  <circle cx="10" cy="14.5" r="1.8" fill="white" opacity="0.75"/>
  <circle cx="21.5" cy="14.5" r="1.8" fill="white" opacity="0.55"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 14. FILE MANAGER — 3D folder with document stack inside
# ─────────────────────────────────────────────────────────────────────────────
ICON_FILE_MANAGER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="fmg" x1="0" y1="0" x2="0.7" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="fmh" x1="0" y1="0" x2="0.5" y2="0.7">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="fmglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.55"/>
    </filter>
  </defs>
  <!-- Folder shadow (3D depth) -->
  <path d="M2 8 Q2 6 4 6 L9.5 6 L11 8 L21 8 Q22 8 22 9.5 L22 19 Q22 20 21 20 L3 20 Q2 20 2 19 Z"
    fill="{COLOR}" opacity="0.25" transform="translate(0.6,1)"/>
  <!-- Folder body -->
  <path d="M2 8 Q2 6 4 6 L9.5 6 L11 8 L21 8 Q22 8 22 9.5 L22 19 Q22 20 21 20 L3 20 Q2 20 2 19 Z"
    fill="url(#fmg)" filter="url(#fmglow)"/>
  <!-- Folder tab (top-left) -->
  <path d="M2 8 L2 6.5 Q2 5 3.5 5 L9 5 L10.5 8 Z"
    fill="{COLOR}" opacity="0.85"/>
  <!-- Folder highlight overlay -->
  <path d="M2 8 Q2 6 4 6 L9.5 6 L11 8 L21 8 Q22 8 22 9.5 L22 19 Q22 20 21 20 L3 20 Q2 20 2 19 Z"
    fill="url(#fmh)"/>
  <!-- Document stack inside folder -->
  <rect x="7" y="11" width="10" height="7" rx="1" fill="white" opacity="0.3"/>
  <rect x="8" y="10" width="8" height="6.5" rx="1" fill="white" opacity="0.5"/>
  <!-- Document lines -->
  <line x1="9.5" y1="12" x2="14.5" y2="12" stroke="{COLOR}" stroke-width="0.8" stroke-opacity="0.7" stroke-linecap="round"/>
  <line x1="9.5" y1="13.5" x2="14.5" y2="13.5" stroke="{COLOR}" stroke-width="0.8" stroke-opacity="0.7" stroke-linecap="round"/>
  <line x1="9.5" y1="15" x2="12.5" y2="15" stroke="{COLOR}" stroke-width="0.8" stroke-opacity="0.7" stroke-linecap="round"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 15. MAGISK — 3D delta/triangle shield (Magisk logo)
# ─────────────────────────────────────────────────────────────────────────────
ICON_MAGISK = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="mgg" x1="0.1" y1="0" x2="0.9" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="mgh" x1="0" y1="0" x2="0.4" y2="0.7">
      <stop offset="0%" stop-color="white" stop-opacity="0.5"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="mgglow">
      <feDropShadow dx="0" dy="2" stdDeviation="1.8"
        flood-color="{COLOR}" flood-opacity="0.7"/>
    </filter>
  </defs>
  <!-- Triangle shadow (3D depth) -->
  <polygon points="12,2 22,20 2,20"
    fill="{COLOR}" opacity="0.25" transform="translate(0.7,1.2)"/>
  <!-- Main triangle body -->
  <polygon points="12,2 22,20 2,20"
    fill="url(#mgg)" filter="url(#mgglow)"/>
  <!-- Highlight overlay -->
  <polygon points="12,2 22,20 2,20"
    fill="url(#mgh)"/>
  <!-- Left edge highlight -->
  <line x1="2" y1="20" x2="12" y2="2"
    stroke="white" stroke-width="0.8" stroke-opacity="0.4" stroke-linecap="round"/>
  <!-- Inner triangle cutout for Magisk M shape -->
  <polygon points="12,7 18.5,18.5 5.5,18.5"
    fill="black" opacity="0.35"/>
  <!-- Inner M hint: two smaller triangles -->
  <polygon points="9,18.5 12,13 15,18.5"
    fill="white" opacity="0.55"/>
  <line x1="9" y1="18.5" x2="12" y2="13"
    stroke="white" stroke-width="0.6" stroke-opacity="0.3" stroke-linecap="round"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 16. PROP EDITOR — 3D document with gear overlay
# ─────────────────────────────────────────────────────────────────────────────
ICON_PROP_EDITOR = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="peg" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="peh" x1="0" y1="0" x2="0.5" y2="0.8">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="peglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.55"/>
    </filter>
  </defs>
  <!-- Document shadow (3D depth) -->
  <path d="M5 2 L15 2 L19 6 L19 22 L5 22 Z"
    fill="{COLOR}" opacity="0.25" transform="translate(0.6,0.8)"/>
  <!-- Document body -->
  <path d="M5 2 L15 2 L19 6 L19 22 L5 22 Z"
    fill="url(#peg)" filter="url(#peglow)"/>
  <!-- Folded corner -->
  <path d="M15 2 L15 6 L19 6 Z"
    fill="black" opacity="0.25"/>
  <path d="M15 2 L15 6 L19 6 Z"
    fill="white" opacity="0.15"/>
  <!-- Document highlight overlay -->
  <path d="M5 2 L15 2 L19 6 L19 22 L5 22 Z"
    fill="url(#peh)"/>
  <!-- Text lines on document -->
  <line x1="7.5" y1="9" x2="14.5" y2="9" stroke="white" stroke-width="0.9" stroke-opacity="0.55" stroke-linecap="round"/>
  <line x1="7.5" y1="11.5" x2="16" y2="11.5" stroke="white" stroke-width="0.9" stroke-opacity="0.55" stroke-linecap="round"/>
  <line x1="7.5" y1="14" x2="13" y2="14" stroke="white" stroke-width="0.9" stroke-opacity="0.55" stroke-linecap="round"/>
  <!-- Gear overlay (bottom-right, 6-point star simplified) -->
  <g transform="translate(15.5,17.5)">
    <circle r="3.5" fill="{COLOR}" opacity="0.9" filter="url(#peglow)"/>
    <circle r="3.5" fill="url(#peh)" opacity="0.7"/>
    <!-- Gear teeth (6 points) -->
    <polygon points="0,-3.5 0.7,-2 -0.7,-2" fill="{COLOR}" opacity="0.9"/>
    <polygon points="0,3.5 0.7,2 -0.7,2" fill="{COLOR}" opacity="0.9"/>
    <polygon points="-3.5,0 -2,0.7 -2,-0.7" fill="{COLOR}" opacity="0.9"/>
    <polygon points="3.5,0 2,0.7 2,-0.7" fill="{COLOR}" opacity="0.9"/>
    <polygon points="-2.5,-2.5 -1.2,-1.2 -2.2,-0.2" fill="{COLOR}" opacity="0.9"/>
    <polygon points="2.5,2.5 1.2,1.2 2.2,0.2" fill="{COLOR}" opacity="0.9"/>
    <!-- Center hole -->
    <circle r="1.4" fill="black" opacity="0.4"/>
    <circle r="1.1" fill="{COLOR}" opacity="0.6"/>
  </g>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 17. PRIVACY — 3D eye with shield/lock overlay
# ─────────────────────────────────────────────────────────────────────────────
ICON_PRIVACY = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="pvg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="pvh" x1="0" y1="0" x2="0.5" y2="0.7">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="pvglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.55"/>
    </filter>
  </defs>
  <!-- Eye shadow (3D depth) -->
  <path d="M2 12 Q12 3 22 12 Q12 21 2 12 Z"
    fill="{COLOR}" opacity="0.22" transform="translate(0.4,0.8)"/>
  <!-- Eye white / outer shape -->
  <path d="M2 12 Q12 3 22 12 Q12 21 2 12 Z"
    fill="url(#pvg)" filter="url(#pvglow)"/>
  <!-- Eye highlight overlay -->
  <path d="M2 12 Q12 3 22 12 Q12 21 2 12 Z"
    fill="url(#pvh)"/>
  <!-- Iris (dark circle) -->
  <circle cx="12" cy="12" r="4.2" fill="black" opacity="0.5"/>
  <!-- Iris fill with color -->
  <circle cx="12" cy="12" r="3.5" fill="{COLOR}" opacity="0.75" filter="url(#pvglow)"/>
  <!-- Pupil -->
  <circle cx="12" cy="12" r="1.8" fill="black" opacity="0.65"/>
  <!-- Eye highlight dot -->
  <circle cx="10.8" cy="10.8" r="0.9" fill="white" opacity="0.7"/>
  <!-- Shield overlay (bottom-right) -->
  <path d="M17.5 14.5 L21 15.8 L21 19 Q21 21.5 17.5 22.5 Q14 21.5 14 19 L14 15.8 Z"
    fill="{COLOR}" opacity="0.25" transform="translate(0.5,0.5)"/>
  <path d="M17.5 14.5 L21 15.8 L21 19 Q21 21.5 17.5 22.5 Q14 21.5 14 19 L14 15.8 Z"
    fill="url(#pvg)" filter="url(#pvglow)"/>
  <path d="M17.5 14.5 L21 15.8 L21 19 Q21 21.5 17.5 22.5 Q14 21.5 14 19 L14 15.8 Z"
    fill="url(#pvh)"/>
  <!-- Lock icon inside shield -->
  <rect x="16.2" y="18" width="2.6" height="2" rx="0.5" fill="white" opacity="0.85"/>
  <path d="M16.5 18 L16.5 17 Q16.5 15.5 17.5 15.5 Q18.5 15.5 18.5 17 L18.5 18"
    fill="none" stroke="white" stroke-width="0.9" stroke-opacity="0.85" stroke-linecap="round"/>
</svg>"""

# ─────────────────────────────────────────────────────────────────────────────
# 18. BATCH — 3D grid of 3 device rectangles with checkmarks
# ─────────────────────────────────────────────────────────────────────────────
ICON_BATCH = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <defs>
    <linearGradient id="btg" x1="0" y1="0" x2="0.6" y2="1">
      <stop offset="0%" stop-color="{COLOR}"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.45"/>
    </linearGradient>
    <linearGradient id="bth" x1="0" y1="0" x2="0.5" y2="0.8">
      <stop offset="0%" stop-color="white" stop-opacity="0.45"/>
      <stop offset="55%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <filter id="btglow">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.2"
        flood-color="{COLOR}" flood-opacity="0.55"/>
    </filter>
  </defs>
  <!-- Left device shadow -->
  <rect x="1.5" y="3.5" width="6" height="17" rx="1.5"
    fill="{COLOR}" opacity="0.2" transform="translate(0.5,0.8)"/>
  <!-- Left device body -->
  <rect x="1.5" y="3.5" width="6" height="17" rx="1.5"
    fill="url(#btg)" filter="url(#btglow)"/>
  <rect x="1.5" y="3.5" width="6" height="7" rx="1.5"
    fill="url(#bth)"/>
  <!-- Left device checkmark -->
  <polyline points="3,12.5 4.2,14 6.5,11"
    fill="none" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>
  <!-- Center device shadow -->
  <rect x="9" y="3.5" width="6" height="17" rx="1.5"
    fill="{COLOR}" opacity="0.2" transform="translate(0.5,0.8)"/>
  <!-- Center device body -->
  <rect x="9" y="3.5" width="6" height="17" rx="1.5"
    fill="{COLOR}" opacity="0.7" filter="url(#btglow)"/>
  <rect x="9" y="3.5" width="6" height="7" rx="1.5"
    fill="url(#bth)" opacity="0.7"/>
  <!-- Center device checkmark -->
  <polyline points="10.5,12.5 11.7,14 14,11"
    fill="none" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.85"/>
  <!-- Right device shadow -->
  <rect x="16.5" y="3.5" width="6" height="17" rx="1.5"
    fill="{COLOR}" opacity="0.2" transform="translate(0.5,0.8)"/>
  <!-- Right device body -->
  <rect x="16.5" y="3.5" width="6" height="17" rx="1.5"
    fill="{COLOR}" opacity="0.5" filter="url(#btglow)"/>
  <rect x="16.5" y="3.5" width="6" height="7" rx="1.5"
    fill="url(#bth)" opacity="0.5"/>
  <!-- Right device checkmark -->
  <polyline points="18,12.5 19.2,14 21.5,11"
    fill="none" stroke="white" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.75"/>
</svg>"""


ICON_WORKFLOW = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <rect x="1" y="2" width="7" height="4" rx="1" fill="{COLOR}" opacity="0.9"/>
  <rect x="8.5" y="10" width="7" height="4" rx="1" fill="{COLOR}" opacity="0.75"/>
  <rect x="16" y="18" width="7" height="4" rx="1" fill="{COLOR}" opacity="0.6"/>
  <polyline points="4.5,6 4.5,8 12,8 12,10" stroke="{COLOR}" stroke-width="1.2"
    fill="none" opacity="0.8"/>
  <polyline points="15.5,14 15.5,16 19.5,16 19.5,18" stroke="{COLOR}" stroke-width="1.2"
    fill="none" opacity="0.8"/>
</svg>"""

ICON_SCRIPTING = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <rect x="2" y="3" width="20" height="18" rx="2" fill="{COLOR}" opacity="0.15"/>
  <rect x="2" y="3" width="20" height="4" rx="2" fill="{COLOR}" opacity="0.5"/>
  <polyline points="7,13 4,15 7,17" stroke="{COLOR}" stroke-width="1.8" fill="none"
    stroke-linecap="round"/>
  <polyline points="17,13 20,15 17,17" stroke="{COLOR}" stroke-width="1.8" fill="none"
    stroke-linecap="round"/>
  <line x1="11" y1="13" x2="13" y2="17" stroke="{COLOR}" stroke-width="1.4"
    stroke-linecap="round"/>
</svg>"""

ICON_SERVICE_MANAGER = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="3" fill="{COLOR}" opacity="0.9"/>
  <path d="M12 2 L13.5 5.5 L17 4 L17 7.5 L20.5 8 L19 12 L20.5 16 L17 16.5 L17 20
           L13.5 18.5 L12 22 L10.5 18.5 L7 20 L7 16.5 L3.5 16 L5 12 L3.5 8
           L7 7.5 L7 4 L10.5 5.5 Z"
    fill="{COLOR}" opacity="0.6"/>
</svg>"""

ICON_FLEET = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <rect x="1" y="5" width="7" height="12" rx="1.5" fill="{COLOR}" opacity="0.45"/>
  <rect x="5" y="3" width="7" height="14" rx="1.5" fill="{COLOR}" opacity="0.7"/>
  <rect x="9" y="5" width="7" height="12" rx="1.5" fill="{COLOR}" opacity="0.45"/>
  <circle cx="8.5" cy="15.5" r="0.8" fill="{COLOR}" opacity="0.9"/>
</svg>"""

ICON_THEME_STUDIO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <ellipse cx="12" cy="13" rx="9" ry="8" fill="{COLOR}" opacity="0.5"/>
  <circle cx="8"  cy="10" r="2"  fill="{COLOR}" opacity="0.9"/>
  <circle cx="12" cy="8"  r="2"  fill="{COLOR}" opacity="0.75"/>
  <circle cx="16" cy="10" r="2"  fill="{COLOR}" opacity="0.6"/>
  <circle cx="15" cy="15" r="2"  fill="{COLOR}" opacity="0.45"/>
  <circle cx="9" cy="17" r="2.5" fill="none" stroke="{COLOR}" stroke-width="1.2"/>
</svg>"""


# ── Icon map ──────────────────────────────────────────────────────────────────

_ICON_MAP: dict[str, str] = {
    "dashboard":        ICON_DASHBOARD,
    "device":           ICON_DEVICE,
    "flash":            ICON_FLASH,
    "rom_library":      ICON_ROM_LIBRARY,
    "backup":           ICON_BACKUP,
    "root":             ICON_ROOT,
    "nethunter":        ICON_NETHUNTER,
    "partition":        ICON_PARTITION,
    "terminal":         ICON_TERMINAL,
    "diagnostics":      ICON_DIAGNOSTICS,
    "rescue":           ICON_RESCUE,
    "settings":         ICON_SETTINGS,
    "app_manager":      ICON_APP_MANAGER,
    "file_manager":     ICON_FILE_MANAGER,
    "magisk":           ICON_MAGISK,
    "prop_editor":      ICON_PROP_EDITOR,
    "privacy":          ICON_PRIVACY,
    "batch":            ICON_BATCH,
    "workflow":         ICON_WORKFLOW,
    "scripting":        ICON_SCRIPTING,
    "service_manager":  ICON_SERVICE_MANAGER,
    "fleet":            ICON_FLEET,
    "theme_studio":     ICON_THEME_STUDIO,
}


def get_icon(name: str, color: str = "#00d4ff", size: int = 32) -> QIcon:
    """Return a QIcon for the given sidebar icon name at *size* x *size* pixels.

    Args:
        name:  Icon key from ``_ICON_MAP``.
        color: Hex color string substituted for the ``{COLOR}`` placeholder.
        size:  Output pixel size (default 32).

    Returns:
      QIcon rendered at *size* x *size* with transparent background.
    """
    svg_template = _ICON_MAP.get(name, ICON_DASHBOARD)
    svg_data = svg_template.replace("{COLOR}", color)

    renderer = QSvgRenderer(QByteArray(svg_data.encode()))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    from PySide6.QtGui import QPainter

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


# ── Hero device illustration ───────────────────────────────────────────────────

_HERO_PHONE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 200">
  <defs>
    <!-- Phone body gradient: top highlight to deep bottom -->
    <linearGradient id="phoneBody" x1="0.15" y1="0" x2="0.85" y2="1">
      <stop offset="0%" stop-color="{COLOR}" stop-opacity="0.9"/>
      <stop offset="45%" stop-color="{COLOR}" stop-opacity="0.65"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.28"/>
    </linearGradient>
    <!-- Screen gradient: deep dark with glow -->
    <radialGradient id="screenGlow" cx="50%" cy="50%" r="55%">
      <stop offset="0%" stop-color="{COLOR}" stop-opacity="0.22"/>
      <stop offset="60%" stop-color="{COLOR}" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.0"/>
    </radialGradient>
    <linearGradient id="screenBase" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0a0f1a"/>
      <stop offset="100%" stop-color="#050810"/>
    </linearGradient>
    <!-- Top face gloss (bevel) -->
    <linearGradient id="topEdge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="white" stop-opacity="0.6"/>
      <stop offset="100%" stop-color="white" stop-opacity="0.05"/>
    </linearGradient>
    <!-- Left edge gloss -->
    <linearGradient id="leftEdge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="white" stop-opacity="0.5"/>
      <stop offset="100%" stop-color="white" stop-opacity="0.0"/>
    </linearGradient>
    <!-- Screen reflection diagonal -->
    <linearGradient id="screenReflect" x1="0" y1="0" x2="0.6" y2="0.8">
      <stop offset="0%" stop-color="white" stop-opacity="0.12"/>
      <stop offset="100%" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <!-- Outer glow -->
    <filter id="phoneGlow" x="-20%" y="-10%" width="140%" height="120%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
    <!-- Soft drop shadow -->
    <filter id="phoneShadow" x="-15%" y="-5%" width="130%" height="120%">
      <feDropShadow dx="0" dy="8" stdDeviation="10"
        flood-color="{COLOR}" flood-opacity="0.45"/>
    </filter>
    <!-- Camera lens gradient -->
    <radialGradient id="cameraLens" cx="35%" cy="35%" r="65%">
      <stop offset="0%" stop-color="white" stop-opacity="0.8"/>
      <stop offset="40%" stop-color="{COLOR}" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.6"/>
    </radialGradient>
    <!-- Side edge for 3D perspective -->
    <linearGradient id="rightEdge3D" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="{COLOR}" stop-opacity="0.55"/>
      <stop offset="100%" stop-color="{COLOR}" stop-opacity="0.15"/>
    </linearGradient>
  </defs>

  <!-- ─── Ambient glow behind phone ─────────────────────────── -->
  <ellipse cx="80" cy="185" rx="52" ry="10"
    fill="{COLOR}" opacity="0.25">
    <animate attributeName="opacity" values="0.2;0.35;0.2" dur="3s" repeatCount="indefinite"/>
  </ellipse>

  <!-- ─── 3D right-side edge (thickness illusion) ───────────── -->
  <path d="M130 18 L135 22 L135 182 L130 186"
    fill="url(#rightEdge3D)" opacity="0.7"/>

  <!-- ─── Phone body ────────────────────────────────────────── -->
  <rect x="26" y="14" width="104" height="172" rx="18"
    fill="url(#phoneBody)" filter="url(#phoneShadow)"/>

  <!-- Inner body shadow for depth -->
  <rect x="27" y="15" width="102" height="170" rx="17"
    fill="none" stroke="black" stroke-width="2" stroke-opacity="0.25"/>

  <!-- ─── Left bevel highlight ─────────────────────────────── -->
  <rect x="26" y="14" width="8" height="172" rx="4"
    fill="url(#leftEdge)" opacity="0.6"/>

  <!-- ─── Top bevel highlight ──────────────────────────────── -->
  <rect x="26" y="14" width="104" height="8" rx="4"
    fill="url(#topEdge)" opacity="0.7"/>

  <!-- ─── Screen bezel (outer) ─────────────────────────────── -->
  <rect x="32" y="32" width="96" height="136" rx="12"
    fill="#050810"/>

  <!-- ─── Screen (active display area) ────────────────────── -->
  <rect x="34" y="34" width="92" height="132" rx="11"
    fill="url(#screenBase)"/>
  <rect x="34" y="34" width="92" height="132" rx="11"
    fill="url(#screenGlow)"/>

  <!-- Screen border glow -->
  <rect x="34" y="34" width="92" height="132" rx="11"
    fill="none" stroke="{COLOR}" stroke-width="0.8" stroke-opacity="0.4"/>

  <!-- ─── Screen reflection ─────────────────────────────────── -->
  <rect x="34" y="34" width="46" height="132" rx="11"
    fill="url(#screenReflect)"/>

  <!-- ─── Screen interface elements ─────────────────────────── -->
  <!-- Status bar -->
  <rect x="40" y="42" width="30" height="2.5" rx="1.25"
    fill="{COLOR}" opacity="0.35"/>
  <rect x="106" y="42" width="14" height="2.5" rx="1.25"
    fill="{COLOR}" opacity="0.25"/>

  <!-- Center icon placeholder — CyberFlash bolt -->
  <g opacity="0.9" filter="url(#phoneGlow)">
    <polygon points="83,72 67,100 77,100 75,128 97,100 87,100"
      fill="{COLOR}" opacity="0.8"/>
    <!-- Bolt highlight -->
    <polygon points="83,72 67,100 77,100 75,128 97,100 87,100"
      fill="white" opacity="0.15"/>
    <line x1="67" y1="100" x2="83" y2="72"
      stroke="white" stroke-width="1.2" stroke-opacity="0.4" stroke-linecap="round"/>
  </g>

  <!-- Bottom app bar lines -->
  <rect x="55" y="148" width="14" height="2.5" rx="1.25"
    fill="{COLOR}" opacity="0.3"/>
  <rect x="73" y="148" width="14" height="2.5" rx="1.25"
    fill="{COLOR}" opacity="0.2"/>
  <rect x="91" y="148" width="14" height="2.5" rx="1.25"
    fill="{COLOR}" opacity="0.3"/>

  <!-- ─── Dynamic island / camera notch ────────────────────── -->
  <rect x="62" y="20" width="36" height="10" rx="5"
    fill="#080d14"/>
  <rect x="63" y="21" width="34" height="8" rx="4"
    fill="black" opacity="0.9"/>
  <!-- Camera lens -->
  <circle cx="89" cy="25" r="3.5" fill="url(#cameraLens)"/>
  <circle cx="89" cy="25" r="2" fill="#000810" opacity="0.7"/>
  <circle cx="88" cy="24" r="0.7" fill="white" opacity="0.6"/>
  <!-- Face ID sensor dots -->
  <circle cx="82" cy="25" r="1" fill="{COLOR}" opacity="0.4"/>
  <circle cx="77" cy="25" r="0.6" fill="{COLOR}" opacity="0.3"/>

  <!-- ─── Home bar ──────────────────────────────────────────── -->
  <rect x="60" y="169" width="40" height="4" rx="2"
    fill="{COLOR}" opacity="0.55"/>
  <rect x="62" y="169.5" width="36" height="2" rx="1"
    fill="white" opacity="0.2"/>

  <!-- ─── Side buttons ─────────────────────────────────────── -->
  <!-- Volume up -->
  <rect x="22" y="55" width="5" height="18" rx="2.5"
    fill="{COLOR}" opacity="0.6"/>
  <rect x="22" y="55" width="5" height="8" rx="2.5"
    fill="white" opacity="0.25"/>
  <!-- Volume down -->
  <rect x="22" y="80" width="5" height="14" rx="2.5"
    fill="{COLOR}" opacity="0.6"/>
  <rect x="22" y="80" width="5" height="6" rx="2.5"
    fill="white" opacity="0.25"/>
  <!-- Power button (right) -->
  <rect x="133" y="60" width="5" height="22" rx="2.5"
    fill="{COLOR}" opacity="0.65"/>
  <rect x="133" y="60" width="5" height="10" rx="2.5"
    fill="white" opacity="0.3"/>
</svg>"""


def get_hero_phone_pixmap(color: str = "#00d4ff", size: int = 160) -> QPixmap:
    """Return a large 3D smartphone illustration as a QPixmap.

    Args:
        color: Primary theme color (hex) for the phone frame and glow.
        size:  Width in pixels (height = size x 1.25 for 160:200 ratio).

    Returns:
        QPixmap with transparent background.
    """
    svg_data = _HERO_PHONE_SVG.replace("{COLOR}", color)
    height = int(size * 1.25)

    renderer = QSvgRenderer(QByteArray(svg_data.encode()))
    pixmap = QPixmap(size, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    from PySide6.QtGui import QPainter

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter)
    painter.end()

    return pixmap
