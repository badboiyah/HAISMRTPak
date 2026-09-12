import {cpSync, mkdirSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const out = resolve(root, 'dist/cloudflare');
mkdirSync(resolve(out, 'driver'), {recursive: true});
cpSync(resolve(root, 'static'), resolve(out, 'static'), {recursive: true});
cpSync(resolve(root, 'static/index.html'), resolve(out, 'index.html'));
cpSync(resolve(root, 'static/driver/index.html'), resolve(out, 'driver/index.html'));
cpSync(resolve(root, 'static/driver/sw.js'), resolve(out, 'driver/sw.js'));
cpSync(resolve(root, 'static/kiosk'), resolve(out, 'qr'), {recursive: true});
console.log('Built Cloudflare public assets in dist/cloudflare');
