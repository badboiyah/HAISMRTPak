"""Package unmodified supplied artwork in SVG viewports for the site and app.

No redrawing: the embedded PNG is identical to static/brand/reference.png.
Coordinates refer to the user's 1448 x 1086 brand board.
"""
from pathlib import Path
import base64

ROOT = Path(__file__).resolve().parents[1]
target = ROOT / 'static' / 'brand'
encoded = base64.b64encode((target / 'reference.png').read_bytes()).decode('ascii')
for name, box in {
    'logo': (76, 98, 704, 250),
    'app-icon': (913, 51, 192, 192),
}.items():
    x, y, width, height = box
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {width} {height}" '
           f'width="{width}" height="{height}"><image width="1448" height="1086" '
           f'href="data:image/png;base64,{encoded}"/></svg>')
    (target / f'{name}.svg').write_text(svg, encoding='utf-8')

# The favicon uses the square app mark from the reference.
# car.svg is a standalone parking illustration, maintained separately.
(ROOT / 'static' / 'favicon.svg').write_text((target / 'app-icon.svg').read_text(encoding='utf-8'), encoding='utf-8')
