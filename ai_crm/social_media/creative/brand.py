# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt
#
# FinByz brand constants for rendered creatives. Colours, fonts and logos live in
# the templates and public/brand; this module holds the text identity and the
# icon library the AI is allowed to pick from.

from pathlib import Path

BRAND_DIR = Path(__file__).resolve().parents[2] / "public" / "brand"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

BRAND = {
    "company": "FinByz Tech Pvt. Ltd.",
    "short_name": "FinByz Tech",
    "website": "finbyz.tech",
    "email": "info@finbyz.com",
    "tagline": "Steer Your Vision",
}

# Canvas sizes in CSS px. Slides are rendered at 1x, which is LinkedIn's native size.
SIZES = {
    "portrait": (1080, 1350),
    "square": (1080, 1080),
    "landscape": (1200, 627),
}
A4 = (794, 1123)

# 24x24 single-stroke icons (FinByz design system section 7, plus a few extras
# in the same weight). The AI may only reference these names.
ICONS = {
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "building": '<path d="M3 21h18M5 21V7l7-4 7 4v14"/><path d="M9 21v-5h6v5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3.2-5.5 7-5.5s7 2 7 5.5"/><path d="M16 4.6a3.5 3.5 0 0 1 0 6.8M18 14.8c2.4.6 4 2.4 4 5.2"/>',
    "rupee": '<circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4"/>',
    "map_pin": '<path d="M12 21s7-5.5 7-11a7 7 0 0 0-14 0c0 5.5 7 11 7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L16 13l5 2v0a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
    "chip": '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M10 2v3M14 2v3M10 19v3M14 19v3M2 10h3M2 14h3M19 10h3M19 14h3"/>',
    "document": '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4M9 13h6M9 16h4"/>',
    "megaphone": '<path d="M3 11l16-6v14L3 13z"/><path d="M8 12v5a2 2 0 0 0 4 0"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M16 16l5 5"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M9 12l2 2 4-4"/>',
    "cross": '<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>',
    "truck": '<path d="M3 6h11v9H3z"/><path d="M14 9h4l3 3v3h-7z"/><circle cx="7" cy="18" r="1.8"/><circle cx="17" cy="18" r="1.8"/>',
    "shield": '<path d="M12 3l7 3v6c0 4-3 7-7 9-4-2-7-5-7-9V6z"/>',
    "chart": '<path d="M3 21h18"/><path d="M6 17v-5M11 17V8M16 17v-8M21 17V5"/>',
    "trend": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "bolt": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>',
    "cog": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    "layers": '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    "rocket": '<path d="M12 15l-3-3c1-5 4.5-8.5 11-9-.5 6.5-4 10-9 11z"/><path d="M9 12H5l2-4h4M12 15v4l4-2v-4"/><path d="M6 17c-1.5 1-2 3-2 3s2-.5 3-2"/>',
    "bulb": '<path d="M9 18h6M10 21h4"/><path d="M12 3a6 6 0 0 0-3.5 10.9c.7.5 1 1.2 1 2.1h5c0-.9.3-1.6 1-2.1A6 6 0 0 0 12 3z"/>',
    "database": '<ellipse cx="12" cy="5.5" rx="7.5" ry="2.5"/><path d="M4.5 5.5v13c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5v-13"/><path d="M4.5 12c0 1.4 3.4 2.5 7.5 2.5s7.5-1.1 7.5-2.5"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    "cloud": '<path d="M7 18a4.5 4.5 0 0 1-.6-9A6 6 0 0 1 18 9.5a4.3 4.3 0 0 1-.5 8.5z"/>',
    "cart": '<path d="M3 4h2l2.5 11h11L21 7H6.2"/><circle cx="9" cy="19.5" r="1.5"/><circle cx="17" cy="19.5" r="1.5"/>',
    "invoice": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9 8h6M9 12h6M9 16h3"/>',
    "factory": '<path d="M3 21V10l5 3V10l5 3V10l5 3V4h3v17z"/><path d="M7 17h2M12 17h2"/>',
    "sparkle": '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 16l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
    "arrow_right": '<path d="M4 12h16M14 6l6 6-6 6"/>',
    "handshake": '<path d="M2 11l4-4 4 2 3-2 4 1 5 3"/><path d="M6 7v6l5 5a1.5 1.5 0 0 0 2-2M10 15l3 3a1.5 1.5 0 0 0 2-2l-3-3M13 13l3 3a1.5 1.5 0 0 0 2-2l-4-4"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
}
DEFAULT_ICON = "sparkle"
