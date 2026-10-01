"""Compile and render the dashboard's embedded React UI without a browser.

dashboard.py ships its UI as JSX inside a Python string, compiled by
Babel in the player's browser. A syntax slip there means a blank page
for every player, and nothing in the Python toolchain would notice. This
script extracts the JSX, compiles it with Babel under node, and renders
each tab to HTML with react-dom/server using canned state, asserting a
few expected strings per tab.

Requires node (any recent version) and network access to cdnjs (same
files the page itself loads). Usage:

    python scripts/check_dashboard_ui.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CDN = {
    "babel.min.js": "https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.9/babel.min.js",
    "react.js": "https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.development.js",
    "react-dom-server.js": "https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom-server-legacy.browser.development.js",
}

# useState(...) initialisers replaced so tabs can be rendered in a
# non-initial state without effects or fetch.
STATE_HOOKS = [
    ('const [tab, setTab] = useState("setup");',
     'const [tab, setTab] = useState(globalThis.__T.tab || "setup");'),
    ('const [status, setStatus] = useState(null);',
     'const [status, setStatus] = useState(globalThis.__T.status || null);'),
    ('const [bridgeStatus, setBridgeStatus] = useState(null);',
     'const [bridgeStatus, setBridgeStatus] = useState(globalThis.__T.bridge || null);'),
    ('const [techCatalog, setTechCatalog] = useState(null);',
     'const [techCatalog, setTechCatalog] = useState(globalThis.__T.catalog || null);'),
    ('const [yamlGroups, setYamlGroups] = useState(null);',
     'const [yamlGroups, setYamlGroups] = useState(globalThis.__T.yaml || null);'),
    ('const [errors, setErrors] = useState(null);',
     'const [errors, setErrors] = useState(globalThis.__T.errors || null);'),
]

CHECK_JS = r"""
const Babel = require('./babel.min.js');
const fs = require('fs');
const code = fs.readFileSync('./app.jsx', 'utf8');
let compiled;
try {
  compiled = Babel.transform(code, {presets: ['react'], filename: 'app.jsx'}).code;
  console.log('JSX syntax OK (' + compiled.length + ' chars)');
} catch (e) { console.log('JSX ERROR: ' + e.message.split('\n').slice(0, 8).join('\n')); process.exit(1); }

globalThis.window = globalThis;
globalThis.document = { getElementById: () => ({ hasChildNodes: () => true, innerHTML: '' }) };
globalThis.navigator = { clipboard: { writeText: () => Promise.resolve() } };
globalThis.fetch = () => new Promise(() => {});
globalThis.React = require('react');
const Server = require('./react-dom-server.js');
globalThis.ReactDOM = { render: () => {} };
globalThis.__T = {};
new Function(compiled)();
const App = globalThis.__App;

const fakeStatus = (overrides) => Object.assign({
  user_dir: 'C:/u', game_dir: 'C:/g', mod_installed: true, mod_files: 16, dll_installed: true, dll_built: false,
  dll_available: true, config_exists: false, config_randomized: 0, config_total: 0, dynamic_techs: 3, ap_errors: 0,
  websocket_lib: true, pywin32: true, python_deps_missing: [],
  launch_options: { supported: true, steam_found: true, steam_running: false, configured: true, options: '-logall', manual: 'M1' },
  launcher: { db_found: true, launcher_running: false, registered: true, enabled: true, playset: 'nomod', manual: 'M2' },
  bridge_settings: { server: 's', slot: 'x', password: '' },
}, overrides || {});

const cases = [
  ['setup/loading', {}, 'Loading'],
  ['setup/ready', { tab: 'setup', status: fakeStatus() }, 'READY TO PLAY'],
  ['setup/not-ready', { tab: 'setup', status: fakeStatus({ mod_installed: false, dll_installed: false, python_deps_missing: ['pywin32'],
      launch_options: { supported: true, steam_found: true, steam_running: true, configured: false, options: '', manual: 'M1' },
      launcher: { db_found: false, launcher_running: true, registered: false, enabled: false, playset: null, manual: 'M2' } }) }, 'Set up everything'],
  ['setup/no-dirs', { tab: 'setup', status: fakeStatus({ user_dir: null, game_dir: null, mod_installed: false, dll_installed: false,
      launch_options: { supported: true, steam_found: false, configured: null, options: '', manual: 'M1' },
      launcher: { db_found: false, registered: false, enabled: false, manual: 'M2' } }) }, 'Steam not found'],
  ['bridge/idle', { tab: 'bridge', status: fakeStatus() }, 'Start Bridge'],
  ['bridge/generated', { tab: 'bridge', status: fakeStatus(), bridge: { bridge: { running: true, pid: 1, log: ['DYNAMIC TECHS GENERATED!', 'waiting for Stellaris to report in'] }, mock: { running: false, log: [] } } }, 'AP techs generated'],
  ['bridge/ingame', { tab: 'bridge', status: fakeStatus(), bridge: { bridge: { running: true, pid: 1, log: ['DYNAMIC TECHS GENERATED!', '[log] Stellaris is in-game (mod reported in)'] }, mock: { running: true, pid: 2, log: ['CHECK RECEIVED'] } } }, 'Connected and in-game'],
  ['bridge/refused', { tab: 'bridge', status: fakeStatus(), bridge: { bridge: { running: false, pid: null, log: ['SERVER REFUSED CONNECTION: InvalidSlot'] }, mock: { running: false, log: [] } } }, 'refused the connection'],
  ['techs/loaded', { tab: 'techs', status: fakeStatus(), catalog: [{ key: 'tech_a', display: 'A', tier: 1, area: 'physics', prereqs: [], dlc: null, offset: 0 }, { key: 'tech_b', display: 'B', tier: 2, area: 'society', prereqs: ['tech_a'], dlc: 'utopia', offset: 1 }] }, 'CATALOG TECHS'],
  ['yaml/loaded', { tab: 'yaml', status: fakeStatus(), yaml: [{ label: 'G', options: [
      { attr: 'goal', display_name: 'Goal', doc: 'd', kind: 'choice', choices: [{ name: 'victory', value: 0 }], default: 'victory' },
      { attr: 'trap_percentage', display_name: 'T', doc: 'd', kind: 'range', range_start: 0, range_end: 30, default: 0 },
      { attr: 'traps_enabled', display_name: 'E', doc: 'd', kind: 'toggle', default: false },
      { attr: 'randomized_techs', display_name: 'R', doc: 'd', kind: 'set', valid_keys: ['a'], default: [] } ] }] }, 'Generated YAML'],
  ['errors', { tab: 'errors', status: fakeStatus(), errors: ['e1'] }, 'e1'],
  ['log', { tab: 'log', status: fakeStatus() }, 'Activity Log'],
];
let failed = 0;
for (const [name, t, want] of cases) {
  globalThis.__T = t;
  try {
    const html = Server.renderToString(React.createElement(App));
    const text = html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
    const ok = text.includes(want);
    if (!ok) failed++;
    console.log((ok ? 'ok   ' : 'FAIL ') + name + (ok ? '' : ' -- missing "' + want + '": ' + text.slice(0, 300)));
  } catch (e) { failed++; console.log('FAIL ' + name + ': ' + e.message.split('\n')[0]); }
}
process.exit(failed ? 1 : 0);
"""


def main() -> int:
    node = shutil.which("node")
    if not node:
        print("node not found — skipping dashboard UI check")
        return 0

    work = Path(tempfile.mkdtemp(prefix="ap_dash_ui_"))
    for name, url in CDN.items():
        urllib.request.urlretrieve(url, work / name)
    shim = work / "node_modules" / "react"
    shim.mkdir(parents=True)
    (shim / "package.json").write_text(json.dumps({"name": "react", "main": "index.js"}), encoding="utf-8")
    (shim / "index.js").write_text("module.exports = require('../../react.js');\n", encoding="utf-8")

    src = (REPO / "dashboard.py").read_text(encoding="utf-8")
    start = src.index('<script type="text/babel">') + len('<script type="text/babel">')
    end = src.index("</script>", start)
    jsx = src[start:end]
    for old, new in STATE_HOOKS:
        if jsx.count(old) != 1:
            print(f"FAIL dashboard.py no longer contains the expected hook line: {old}")
            return 1
        jsx = jsx.replace(old, new)
    (work / "app.jsx").write_text(jsx + "\n;globalThis.__App = App;\n", encoding="utf-8")
    (work / "check.js").write_text(CHECK_JS, encoding="utf-8")

    r = subprocess.run([node, "check.js"], cwd=work, capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith(("ok ", "FAIL", "JSX")):
            print("  " + line)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        print("\nDashboard UI check FAILED")
        return 1
    shutil.rmtree(work, ignore_errors=True)
    print("\nDashboard UI renders.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
