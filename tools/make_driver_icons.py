"""Export the supplied artwork's SVG viewports to compact browser assets.

Requires Playwright and installed Chrome. Run build_brand.py first.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    exports = [
        ('logo', 704, 250, 'brand/logo.png'),
        ('car', 700, 165, 'brand/car.png'),
        ('app-icon', 192, 192, 'brand/app-icon.png'),
        ('app-icon', 64, 64, 'brand/favicon.png'),
        ('app-icon', 192, 192, 'driver/icon-192.png'),
        ('app-icon', 512, 512, 'driver/icon-512.png'),
    ]
    for source, width, height, output in exports:
        page = browser.new_page(viewport={'width': width, 'height': height}, device_scale_factor=1)
        page.goto((root / f'static/brand/{source}.svg').as_uri())
        page.evaluate('([w,h]) => { const svg=document.documentElement; svg.setAttribute("width",w); svg.setAttribute("height",h); }', [width, height])
        page.screenshot(path=str(root / 'static' / output))
        page.close()
    browser.close()
