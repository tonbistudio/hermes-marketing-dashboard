// Marketing dashboard: a Hermes Desktop page over a marketing package's snapshot.
//
// Data comes from this package's backend (dashboard/plugin_api.py), which reads
// runs/dashboard/snapshot.json in the configured marketing package. The agent's
// scheduled jobs rewrite that file after every run; this page polls it. Read-only:
// nothing here changes a campaign, a packet or a decision.
import { Button, SegmentedControl, host, atom, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA, PALETTE_AREA, STATUSBAR_AREAS } from '@hermes/plugin-sdk'
import { useState, Children, createElement } from 'react'

const ID = 'marketing-dashboard'
const ROUTE = '/marketing-dashboard'
const POLL_MS = 60000

// --- shared state: one poll loop feeds the page and the status bar --------------------------
const $state = atom({ loading: true, error: null, businesses: [], business: null, snap: null })
let CTX = null

async function load(businessId) {
  const ctx = CTX
  if (!ctx) return
  try {
    const { businesses } = await ctx.rest('/businesses')
    const id = businessId || ctx.storage.get('business', null)
    const pick = businesses.find(b => b.id === id) || businesses[0] || null
    if (!pick) { $state.set({ loading: false, error: null, businesses, business: null, snap: null }); return }
    const snap = await ctx.rest('/snapshot?business=' + encodeURIComponent(pick.id))
    $state.set({ loading: false, error: null, businesses, business: pick.id, snap })
  } catch (e) {
    $state.set({ ...$state.get(), loading: false, error: String((e && e.message) || e) })
  }
}

async function refresh() {
  const ctx = CTX, s = $state.get()
  if (!ctx || !s.business) return load()
  try {
    const snap = await ctx.rest('/refresh?business=' + encodeURIComponent(s.business), { method: 'POST' })
    $state.set({ ...s, error: null, snap })
    host.notify({ kind: 'info', message: 'Marketing snapshot rebuilt' })
  } catch (e) {
    host.notifyError ? host.notifyError(e) : host.notify({ kind: 'error', message: String(e) })
  }
}

function choose(id) {
  CTX && CTX.storage.set('business', id)
  $state.set({ ...$state.get(), loading: true })
  load(id)
}

// --- formatting -------------------------------------------------------------------------------
function el(tag, props, ...children) {
  const kids = Children.toArray(children.flat().filter(c => c !== null && c !== undefined && c !== false))
  return createElement(tag, props || {}, ...kids)
}
const isNum = v => typeof v === 'number' && Number.isFinite(v)
const dash = '—'
function money(v, cur) {
  if (!isNum(v)) return dash
  try { return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur || 'USD' }).format(v) } catch { return v.toFixed(2) }
}
const count = v => isNum(v) ? Math.round(v).toLocaleString() : dash
const pct = v => isNum(v) ? (v * 100).toFixed(2) + '%' : dash
const days = v => isNum(v) ? (v < 10 ? v.toFixed(1) : Math.round(v)) + ' d' : dash
function ago(t) {
  if (!t) return dash
  const s = (Date.now() - Date.parse(t)) / 1000
  if (!isFinite(s)) return t
  if (s < 90) return 'just now'
  if (s < 5400) return Math.round(s / 60) + ' min ago'
  if (s < 129600) return Math.round(s / 3600) + ' h ago'
  return Math.round(s / 86400) + ' days ago'
}
const date = t => t ? String(t).slice(0, 10) : dash
const humanize = s => String(s || '').replace(/_/g, ' ').toLowerCase()
// Meta action types read like 'offsite_conversion.fb_pixel_add_to_cart'; show 'add to cart'.
const actionLabel = s => humanize(String(s || '').replace(/^(offsite|onsite)_conversion\./, '').replace(/^fb_pixel_/, '')
  .replace(/^custom$/, 'custom events'))

// --- building blocks --------------------------------------------------------------------------
const muted = { color: 'var(--ui-text-tertiary)', fontSize: 12 }
const box = { border: '1px solid var(--ui-stroke-secondary)', borderRadius: 10, padding: 16 }
const LEVEL = { ok: 'var(--ui-green)', attention: 'var(--ui-orange)', problem: 'var(--ui-red)', unknown: 'var(--ui-text-tertiary)' }

function Panel({ title, sub, children }) {
  return el('section', { style: { ...box, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 } },
    el('div', null, el('h2', { style: { fontSize: 15, fontWeight: 650 } }, title), sub ? el('p', { style: muted }, sub) : null),
    children)
}
function Stat({ label, value, detail }) {
  return el('div', { style: box },
    el('div', { style: muted }, label),
    el('div', { style: { fontSize: 22, fontWeight: 650, fontVariantNumeric: 'tabular-nums', margin: '4px 0' } }, value),
    detail ? el('div', { style: muted }, detail) : null)
}
function Grid({ min = 170, children }) {
  return el('div', { style: { display: 'grid', gridTemplateColumns: `repeat(auto-fit,minmax(${min}px,1fr))`, gap: 12 } }, children)
}
function Notice({ tone = 'attention', children }) {
  return el('div', { style: { borderLeft: `3px solid ${LEVEL[tone]}`, padding: '8px 12px', fontSize: 13,
    background: `color-mix(in srgb, ${LEVEL[tone]} 8%, transparent)` } }, children)
}
function Table({ headers, rows, empty = 'Nothing yet.' }) {
  if (!rows.length) return el('p', { style: muted }, empty)
  const cell = (i, head) => ({ textAlign: i ? 'right' : 'left', padding: '8px 10px', whiteSpace: i ? 'nowrap' : 'normal',
    borderBottom: `1px solid var(${head ? '--ui-stroke-secondary' : '--ui-stroke-tertiary'})`,
    color: head ? 'var(--ui-text-tertiary)' : undefined, fontVariantNumeric: 'tabular-nums' })
  return el('div', { style: { overflowX: 'auto' } },
    el('table', { style: { width: '100%', borderCollapse: 'collapse', fontSize: 12 } },
      el('thead', null, el('tr', null, headers.map((h, i) => el('th', { key: i, style: cell(i, true) }, h)))),
      el('tbody', null, rows.map((r, i) => el('tr', { key: i }, r.map((c, j) => el('td', { key: j, style: cell(j, false) }, c)))))))
}
function Bar({ value, max, tone = 'var(--ui-accent)' }) {
  const w = isNum(value) && isNum(max) && max > 0 ? Math.min(100, value / max * 100) : 0
  return el('div', { style: { height: 8, borderRadius: 4, background: 'var(--ui-stroke-tertiary)', overflow: 'hidden' } },
    el('div', { style: { width: w + '%', height: '100%', background: tone } }))
}

// --- tabs -------------------------------------------------------------------------------------
function topAction(totals) {
  const a = (totals && totals.actions) || {}
  const skip = new Set(['link_click', 'landing_page_view', 'page_engagement', 'post_engagement', 'video_view', 'post_reaction', 'comment'])
  return Object.entries(a).filter(([k, v]) => !skip.has(k) && isNum(v)).sort((x, y) => y[1] - x[1])[0] || null
}

function Campaign({ c, cur }) {
  const t = c.totals || {}
  const p = c.pacing || {}
  const action = topAction(t)
  // Impressions dwarf every later step, so the bars start at link clicks.
  const steps = [['Link clicks', t.link_clicks], ['Landing views', t.landing_views]]
  if (action) steps.push([actionLabel(action[0]), action[1]])
  const live = c.effective_status === 'ACTIVE'
  return Panel({
    title: c.name || c.id || 'Campaign',
    sub: [c.objective && humanize(c.objective), date(c.start) + ' → ' + date(c.end)].filter(Boolean).join(' · '),
    children: [
      el('div', { key: 's', style: { fontSize: 12, fontWeight: 650, color: live ? 'var(--ui-green)' : 'var(--ui-text-secondary)' } },
        '● ' + (c.effective_status ? humanize(c.effective_status).toUpperCase() : 'STATUS UNKNOWN')),
      el('div', { key: 'b', style: { display: 'grid', gap: 6 } },
        el('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 13 } },
          el('span', null, money(c.spend, cur) + ' of ' + money(c.cap, cur)),
          el('span', { style: muted }, money(c.remaining, cur) + ' left')),
        Bar({ value: c.spend, max: c.cap }),
        isNum(p.even_spend_to_date) ? el('div', { style: muted }, 'Even pacing would be ' + money(p.even_spend_to_date, cur) + ' by now') : null),
      Grid({ key: 'g', min: 130, children: [
        Stat({ key: 1, label: 'Days left', value: days(p.days_left), detail: isNum(p.per_day_to_finish) ? money(p.per_day_to_finish, cur) + '/day to spend the rest' : null }),
        Stat({ key: 2, label: 'Link CTR', value: pct(t.ctr), detail: count(t.link_clicks) + ' link clicks' }),
        Stat({ key: 3, label: 'Cost per link click', value: money(t.cpc, cur), detail: 'CPM ' + money(t.cpm, cur) }),
        Stat({ key: 4, label: 'Reach', value: count(t.reach), detail: 'frequency ' + (isNum(t.frequency) ? t.frequency.toFixed(2) : dash) })
      ] }),
      el('div', { key: 'f', style: { display: 'grid', gap: 8 } },
        el('div', { style: muted }, 'Funnel from ' + count(t.impressions) + ' impressions: where people stop'),
        steps.map(([label, v], i) => el('div', { key: i, style: { display: 'grid', gridTemplateColumns: '130px 1fr 130px', gap: 10, alignItems: 'center', fontSize: 12 } },
          el('span', null, label), Bar({ value: v, max: steps[0][1] }),
          el('span', { style: { textAlign: 'right', fontVariantNumeric: 'tabular-nums' } },
            count(v) + (i && isNum(steps[i - 1][1]) && steps[i - 1][1] > 0 && isNum(v) ? '  (' + pct(v / steps[i - 1][1]) + ')' : ''))))),
      c.problems.length ? Notice({ key: 'p', tone: 'problem', children: c.problems.map((x, i) => el('div', { key: i }, x)) }) : null,
      c.data_gaps.length ? Notice({ key: 'd', children: 'Data gaps (Meta returned 0 cost for these days; not real zeros): ' + c.data_gaps.join(', ') }) : null,
      c.complete === false ? Notice({ key: 'c', children: 'The last report was incomplete (pagination stopped early).' }) : null
    ]
  })
}

function Overview({ snap }) {
  const cur = snap.business.currency
  const waiting = snap.packets.filter(p => p.needs_owner)
  return el('div', { style: { display: 'grid', gap: 16 } },
    snap.campaigns.length ? snap.campaigns.map(c => el(Campaign, { key: c.id, c, cur }))
      : Panel({ title: 'No campaign report yet', sub: 'The daily report job writes one once reporting is set up (access level 1 or 2 and a live campaign).' }),
    waiting.length ? Panel({ title: 'Waiting for you', children: Table({ headers: ['Packet', 'Status', 'Updated'],
      rows: waiting.map(p => [p.id, humanize(p.status), ago(p.updated)]) }) }) : null,
    snap.warnings.length ? Notice({ children: [el('strong', { key: 'h' }, 'Some files could not be read: '), snap.warnings.join(' · ')] }) : null)
}

function Daily({ snap }) {
  const [metric, setMetric] = useState('spend')
  const [ci, setCi] = useState(0)
  const c = snap.campaigns[ci]
  if (!c) return Panel({ title: 'No daily data yet' })
  const cur = snap.business.currency
  const rows = c.daily
  const max = Math.max(0, ...rows.map(r => r[metric] || 0))
  const show = v => metric === 'spend' ? money(v, cur) : count(v)
  return el('div', { style: { display: 'grid', gap: 16 } },
    snap.campaigns.length > 1 ? el(SegmentedControl, { value: String(ci), onChange: v => setCi(Number(v)),
      options: snap.campaigns.map((x, i) => ({ id: String(i), label: x.name || x.id })) }) : null,
    Panel({ title: 'Daily delivery', sub: 'Days in the ad account timezone. A marked day had a data gap: missing, not zero.', children: [
      el(SegmentedControl, { key: 'm', value: metric, onChange: setMetric,
        options: [['spend', 'Spend'], ['impressions', 'Impressions'], ['link_clicks', 'Link clicks'], ['landing_views', 'Landing views']].map(([id, label]) => ({ id, label })) }),
      el('div', { key: 'c', style: { display: 'flex', alignItems: 'flex-end', gap: 6, height: 190, overflowX: 'auto' } },
        rows.map(r => el('div', { key: r.date, title: r.date + ': ' + show(r[metric]), style: { flex: '1 0 18px', textAlign: 'center', minWidth: 18 } },
          r.gap && !isNum(r[metric])
            ? el('div', { style: { ...muted, fontSize: 10, color: 'var(--ui-orange)', borderBottom: '3px dashed var(--ui-orange)' } }, 'gap')
            : el('div', { style: { height: 150 * ((r[metric] || 0) / (max || 1)), background: r.gap ? 'var(--ui-orange)' : 'var(--ui-accent)', borderRadius: '4px 4px 0 0' } }),
          el('div', { style: { ...muted, fontSize: 10, marginTop: 4 } }, String(r.date || '').slice(5)))))
    ] }),
    Panel({ title: 'Daily values', children: Table({ headers: ['Date', 'Spend', 'Impr.', 'Reach*', 'Link clicks', 'CTR', 'Cost/click', 'Landing views'],
      rows: rows.map(r => [r.date + (r.gap ? ' (gap)' : ''), money(r.spend, cur), count(r.impressions), count(r.reach), count(r.link_clicks), pct(r.ctr), money(r.cpc, cur), count(r.landing_views)]) }) }),
    el('p', { style: muted }, '* Reach is deduplicated: daily reach never adds up to the total.'))
}

function Breakdown({ snap }) {
  const [view, setView] = useState('placement')
  const cur = snap.business.currency
  const rows = []
  for (const c of snap.campaigns) {
    if (view === 'placement') for (const p of c.placements) rows.push([p.label, money(p.spend, cur), count(p.impressions), count(p.link_clicks), pct(p.ctr), money(p.cpc, cur), count(p.landing_views)])
    else {
      const groups = new Map()
      for (const a of c.audience) {
        const key = view === 'age' ? a.age : view === 'gender' ? a.gender : a.age + ' · ' + a.gender
        const g = groups.get(key) || { spend: 0, impressions: 0, link_clicks: 0, landing_views: 0 }
        for (const k of Object.keys(g)) g[k] += a[k] || 0
        groups.set(key, g)
      }
      for (const [k, g] of groups) rows.push([k, money(g.spend, cur), count(g.impressions), count(g.link_clicks),
        pct(g.impressions ? g.link_clicks / g.impressions : null), money(g.link_clicks ? g.spend / g.link_clicks : null, cur), count(g.landing_views)])
    }
  }
  return Panel({ title: 'Where the money went', sub: 'Delivered breakdowns from the latest report. Small samples don\'t make a winner.', children: [
    el(SegmentedControl, { key: 'v', value: view, onChange: setView,
      options: [['placement', 'Placement'], ['age', 'Age'], ['gender', 'Gender'], ['both', 'Age × gender']].map(([id, label]) => ({ id, label })) }),
    Table({ key: 't', headers: ['Segment', 'Spend', 'Impr.', 'Link clicks', 'CTR', 'Cost/click', 'Landing views'], rows, empty: 'No breakdown in the latest report.' })
  ] })
}

function Approvals({ snap }) {
  return el('div', { style: { display: 'grid', gap: 16 } },
    Panel({ title: 'Packets', sub: 'Drafts packaged for approval, newest first.', children: Table({ headers: ['Packet', 'Status', 'Updated', 'Review page'],
      rows: snap.packets.map(p => [p.id, (p.needs_owner ? '● ' : '') + humanize(p.status), ago(p.updated), p.review_page || dash]), empty: 'No packets yet.' }) }),
    Panel({ title: 'Owner decisions', sub: 'Recorded in decisions.json, in the owner\'s words. Newest first.', children: snap.decisions.length
      ? snap.decisions.map(d => el('div', { key: d.id, style: { ...box, display: 'grid', gap: 6 } },
          el('div', { style: { display: 'flex', justifyContent: 'space-between', gap: 8 } }, el('strong', { style: { fontSize: 13 } }, d.id), el('span', { style: muted }, date(d.at))),
          d.owner_words ? el('div', { style: { fontSize: 13 } }, '“' + d.owner_words + '”') : null,
          el('div', { style: muted }, (d.approves_files ? d.approves_files + ' files bound by hash' : 'binds no files') +
            (d.not_authorized.length ? ' · not authorized: ' + d.not_authorized.join(', ') : ''))))
      : el('p', { style: muted }, 'No decisions recorded yet.') }))
}

function Economics({ snap }) {
  const cur = snap.business.currency, b = snap.budget || {}, le = b.launch_exception || {}
  return el('div', { style: { display: 'grid', gap: 16 } },
    Grid({ children: [
      Stat({ key: 1, label: 'Owner monthly cap', value: money(b.owner_monthly_cap, cur) }),
      Stat({ key: 2, label: 'Share of contribution', value: isNum(b.contribution_share) ? Math.round(b.contribution_share * 100) + '%' : dash, detail: 'allowance = min(cap, share × contribution)' }),
      Stat({ key: 3, label: 'Launch exception', value: le.approved ? money(Number(le.total), cur) : 'none', detail: le.approved ? 'until ' + (le.end || dash) : null })
    ] }),
    Panel({ title: 'Monthly economics', sub: 'From economics/YYYY-MM.yaml. A missing cost makes contribution unknown, never zero.', children: Table({
      headers: ['Month', 'Net revenue', 'Costs', 'Contribution', 'Ad spend', 'After ads', 'Missing'],
      rows: snap.economics.map(m => [m.month, money(m.net_revenue, cur), money(m.costs, cur), money(m.contribution, cur), money(m.ad_spend, cur), money(m.net_after_ads, cur), m.missing.join(', ') || dash]),
      empty: 'No monthly figures yet.' }) }),
    snap.weekly.length ? Panel({ title: 'Weekly windows', children: Table({ headers: ['Window', 'Verdict', 'File'],
      rows: snap.weekly.map(w => [(w.since || '?') + ' → ' + (w.until || '?'), w.verdict || dash, w.file]) }) }) : null)
}

function Activity({ snap }) {
  return Panel({ title: 'Recent activity', sub: 'From the run logs and run records in runs/, newest first.', children: Table({ headers: ['When', 'Job', 'Result', 'What happened'],
    rows: snap.activity.map(a => [a.at ? a.at.replace('T', ' ').slice(0, 16) : dash, a.job, a.verdict ? humanize(a.verdict) : dash, a.text]), empty: 'No run logs yet.' }) })
}

const TABS = [['overview', 'Overview', Overview], ['daily', 'Daily', Daily], ['breakdown', 'Breakdown', Breakdown],
  ['approvals', 'Approvals', Approvals], ['economics', 'Budget', Economics], ['activity', 'Activity', Activity]]

function Setup({ error }) {
  return Panel({ title: error ? 'The dashboard backend isn\'t answering' : 'No marketing package configured', children: [
    error ? el('p', { key: 'e', style: muted }, error) : null,
    el('ol', { key: 'l', style: { fontSize: 13, lineHeight: 1.8, paddingLeft: 18 } },
      el('li', null, 'Add marketing-dashboard to plugins.enabled in this profile\'s config.yaml, then restart the gateway.'),
      el('li', null, 'Point it at a package: package: in local/marketer.yaml, or packages: [...] in local/marketing-dashboard.yaml.'),
      el('li', null, 'Switch to the profile that holds the package in the profile selector.'))
  ] })
}

function Dashboard() {
  const s = useValue($state)
  const [tab, setTab] = useState(() => (CTX && CTX.storage.get('tab', 'overview')) || 'overview')
  const pick = id => { setTab(id); CTX && CTX.storage.set('tab', id) }
  const snap = s.snap
  const Page = (TABS.find(t => t[0] === tab) || TABS[0])[2]
  const level = snap ? snap.status.level : 'unknown'
  return el('div', { style: { height: '100%', overflowY: 'auto', color: 'var(--ui-text-primary)', padding: 24 } },
    el('div', { style: { display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1400 } },
      el('header', { style: { display: 'flex', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' } },
        el('div', null,
          el('div', { style: { ...muted, letterSpacing: 2, textTransform: 'uppercase' } }, 'Marketing'),
          el('h1', { style: { fontSize: 24, fontWeight: 700, margin: '4px 0' } }, snap ? snap.business.name : 'Marketing dashboard'),
          snap ? el('div', { style: muted }, [snap.business.mode, 'access level ' + (snap.business.access_level ?? dash), snap.business.timezone].filter(Boolean).join(' · ')) : null),
        el('div', { style: { display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' } },
          s.businesses.length > 1 ? el(SegmentedControl, { value: s.business, onChange: choose, options: s.businesses.map(b => ({ id: b.id, label: b.name })) }) : null,
          el(Button, { variant: 'outline', onClick: () => refresh() }, 'Rebuild now'))),
      s.loading && !snap ? el('p', { style: muted }, 'Loading…') : null,
      !s.loading && !snap ? el(Setup, { error: s.error }) : null,
      snap ? el('div', { style: { display: 'grid', gap: 6 } },
        Notice({ tone: level, children: [el('strong', { key: 's' }, snap.status.headline)] }),
        el('div', { style: muted }, 'Snapshot ' + ago(snap.generated_at) + ' by ' + snap.generated_by +
          (snap.report ? ' · last campaign report ' + ago(snap.report.checked_at) : '') +
          (snap.source === 'live' ? ' · built now, no saved snapshot yet' : '') +
          (s.error ? ' · last refresh failed: ' + s.error : ''))) : null,
      snap ? el(SegmentedControl, { value: tab, onChange: pick, options: TABS.map(([id, label]) => ({ id, label })) }) : null,
      snap ? el(Page, { snap }) : null))
}

function StatusChip() {
  const s = useValue($state)
  const snap = s.snap
  if (!snap) return null
  const c = snap.campaigns[0]
  const cur = snap.business.currency
  const label = c ? (c.effective_status ? humanize(c.effective_status) : 'unknown') + ' · ' + money(c.spend, cur) + ' / ' + money(c.cap, cur) : snap.status.headline
  return el('button', { type: 'button', onClick: () => host.navigate(ROUTE), title: snap.status.headline,
    style: { fontSize: 11, color: LEVEL[snap.status.level] || 'var(--ui-text-tertiary)', padding: '0 6px' } },
    snap.business.name + ' · ' + label)
}

export default {
  id: ID,
  name: 'Marketing',
  register(ctx) {
    CTX = ctx
    ctx.onDispose(() => { CTX = null })
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: ROUTE }, render: () => el(Dashboard) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, order: 86, data: { path: ROUTE, label: 'Marketing', codicon: 'megaphone' } },
      { id: 'open', area: PALETTE_AREA, data: { id: ID + '.open', label: 'Open Marketing dashboard', keywords: ['marketing', 'ads', 'campaign', 'email'], run: () => host.navigate(ROUTE) } },
      { id: 'rebuild', area: PALETTE_AREA, data: { id: ID + '.rebuild', label: 'Marketing: rebuild snapshot', keywords: ['marketing', 'refresh'], run: () => refresh() } },
      { id: 'status', area: STATUSBAR_AREAS.right, order: 140, render: () => el(StatusChip) }
    ])
    load()
    ctx.setInterval(() => load($state.get().business), POLL_MS)
  }
}
