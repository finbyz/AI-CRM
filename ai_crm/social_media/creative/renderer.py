# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt
#
# Turns validated creative content into on-brand PNGs and a PDF.
# The AI only ever supplies text: layout, colours, fonts and logos come from the
# templates here, so every creative matches the FinByz design system.

import os
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ai_crm.social_media.creative.brand import A4, BRAND, BRAND_DIR, ICONS, SIZES, TEMPLATE_DIR
from ai_crm.social_media.creative.schema import validate_document, validate_slides

# Browsers are installed inside the bench virtualenv so every bench user
# (web, workers, console) finds the same Chromium build.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", os.path.join(sys.prefix, "playwright-browsers"))

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass
class RenderResult:
    images: list = field(default_factory=list)  # PNG bytes, one per slide/page
    pdf: bytes = b""
    warnings: list = field(default_factory=list)
    html: str = ""


THEME_TONES = {"Navy": "dark", "Light": "light"}


def render_slides(data, size="portrait", strict=False, theme="Mixed"):
    """Render a carousel (or a single image when there is one slide).

    theme "Navy" or "Light" forces every slide onto one background; "Mixed"
    keeps each layout's default (or the tone the content asked for).
    """
    if size not in SIZES:
        raise ValueError(f"size must be one of {', '.join(SIZES)}")
    clean = validate_slides(data, strict=strict)
    if theme in THEME_TONES:
        for slide in clean["slides"]:
            slide["tone"] = THEME_TONES[theme]
    width, height = SIZES[size]
    html = _env.get_template("slides.html").render(
        slides=clean["slides"], width=width, height=height, size=size, **_context()
    )
    result = _render(html, ".slide", width, height)
    result.warnings[:0] = clean["warnings"]
    return result


def render_document(data, strict=False):
    """Render a single A4 one-pager."""
    clean = validate_document(data, strict=strict)
    width, height = A4
    html = _env.get_template("document.html").render(doc=clean, width=width, height=height, **_context())
    result = _render(html, ".page", width, height)
    result.warnings[:0] = clean["warnings"]
    return result


def _context():
    return {"brand": BRAND, "icons": ICONS, "asset": BRAND_DIR.as_uri()}


def _render(html, selector, width, height):
    from playwright.sync_api import sync_playwright

    result = RenderResult(html=html)
    with tempfile.TemporaryDirectory(prefix="ai_crm_creative_") as tmp:
        page_file = Path(tmp) / "creative.html"
        page_file.write_text(html, encoding="utf-8")
        allowed = (BRAND_DIR.as_uri(), page_file.as_uri())

        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                # Content is AI-written: only the page itself and brand assets may load.
                page.route(
                    "**/*",
                    lambda route: route.continue_()
                    if route.request.url.startswith(allowed)
                    else route.abort(),
                )
                page.goto(page_file.as_uri(), wait_until="load")
                page.evaluate("document.fonts.ready.then(() => true)")
                overflow = page.evaluate("window.fitAll()")
                for index in overflow:
                    result.warnings.append(f"page {index + 1}: text still overflows after shrinking")

                for element in page.query_selector_all(selector):
                    result.images.append(element.screenshot(type="png"))
                result.pdf = page.pdf(
                    width=f"{width}px",
                    height=f"{height}px",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
            finally:
                browser.close()
    return result
