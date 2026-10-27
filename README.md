# Marketing dashboard for Hermes

A read-only **Marketing** page for the [Hermes Agent](https://github.com/NousResearch/hermes-agent)
desktop app. Point it at a marketing package folder and it shows:

- **Overview:** campaign spend against its lifetime cap, pacing, days left, and
  the funnel from link clicks to your conversion events, with problems and
  data gaps called out
- **Daily:** delivery per day, with gap days marked as missing rather than zero
- **Breakdown:** spend and clicks by placement, age and gender
- **Approvals:** packets waiting for the owner, and the owner's recorded decisions
- **Budget:** monthly contribution, ad spend and the allowance settings
- **Activity:** recent runs from the package's run logs

It never changes anything. It reads files and draws them.

## How it works

```
marketing package/                    this plugin
├── policy.yaml                        marketing_snapshot.py ── reads the package,
├── runs/meta-daily/*.json   ───────▶                           writes runs/dashboard/snapshot.json
├── runs/*/log.md                      dashboard/plugin_api.py ─ serves the snapshot to the app
├── packets/*/manifest.json            desktop/plugin.js ─────── the Marketing page
├── decisions.json
└── economics/YYYY-MM.yaml
```

Whatever runs your marketing (an agent's scheduled jobs, a script, you) calls
`marketing_snapshot.py <package> --write` after each run, and the page picks
up the new snapshot within a minute. **Rebuild now** on the page does the same
on demand. The file format is in [SNAPSHOT.md](SNAPSHOT.md), so anything that
writes it works with the page.

The layout matches the **Marketer** specialist agent from
[Agent Wikis](https://agentwikis.com/specialists), which ships this plugin and
refreshes the snapshot from every one of its scheduled workflows. The plugin
works on its own with any package in this layout.

## Install

Needs Hermes 0.22.5 or later.

1. Put this folder in your Hermes plugins folder as `marketing-dashboard`:

   ```bash
   git clone <this repo> ~/.hermes/plugins/marketing-dashboard
   ```

   (Or a profile's own `plugins/` folder to scope it to that profile.)
2. Allow its read-only backend in that home's `config.yaml`, then restart the
   gateway (`hermes gateway restart`):

   ```yaml
   plugins:
     enabled:
       - marketing-dashboard
   ```

3. Tell it where your package is, in `$HERMES_HOME/local/marketing-dashboard.yaml`:

   ```yaml
   packages:
     - ~/marketing/my-business
   ```

   It also reads `package:` from `local/marketer.yaml`, or the
   `MARKETING_DASHBOARD_PACKAGES` environment variable (folders separated by
   `:` on Linux and macOS, `;` on Windows). Several packages give a switcher.
4. In the desktop app: **Capabilities → Plugins → Marketing**, switch it on.
   Open **Marketing** in the sidebar, or ⌘K → *Open Marketing dashboard*.

**Desktop on another machine.** If the app connects to a Hermes running
elsewhere, also copy `desktop/plugin.js` to
`desktop-plugins/marketing-dashboard/plugin.js` in the Hermes home on the
machine with the app, then ⌘K → *Reload desktop plugins*. The data still comes
from the server.

## Try it with the example

```bash
python3 examples/make_example.py                  # writes examples/northwind-candles/
python3 marketing_snapshot.py examples/northwind-candles --write
```

Then list `examples/northwind-candles` under `packages:` as in step 3.
Northwind Candles is made up; its numbers are invented.

## Security

- The page sends no paths: it picks a business by an id the backend issued, and
  the backend only reads packages named in configuration.
- The backend reads files and writes one derived file,
  `runs/dashboard/snapshot.json`. It never contacts an ad platform or a store.
- The builder keeps decisions' text short and copies no credentials. Don't put
  secrets in a marketing package anyway.

## Development

```bash
python3 -m unittest discover -s tests             # builder and backend
npm install --prefix /tmp/react react@19 react-dom@19
node tests/render_test.mjs /tmp/react <snapshot.json>   # renders every tab
```

The desktop page is plain ESM loaded uncompiled by Hermes: no JSX, and only
`@hermes/plugin-sdk`, `react` and `react/jsx-runtime` can be imported. Colors
come from the app's theme variables.

## License

MIT
