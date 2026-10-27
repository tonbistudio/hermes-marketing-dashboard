// Render test for desktop/plugin.js: real React server rendering with a stand-in SDK.
//
//   node tests/render_test.mjs <react-dir> <snapshot.json>
//
// <react-dir> holds node_modules/react and react-dom. The test rewrites the
// plugin's SDK import to the stub below, registers the plugin against a fake
// context, and renders every tab, the status chip and the empty and error states.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

const [reactDir, snapPath] = process.argv.slice(2)
if (!reactDir || !snapPath) { console.error('usage: node tests/render_test.mjs <react-dir> <snapshot.json>'); process.exit(2) }
const here = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(path.join(path.resolve(reactDir), 'package.json'))
const React = require('react')
const { renderToString } = require('react-dom/server')

const work = fs.mkdtempSync(path.join(os.tmpdir(), 'mdash-'))
fs.writeFileSync(path.join(work, 'react.cjs'), `module.exports = require(${JSON.stringify(require.resolve('react'))})`)
fs.writeFileSync(path.join(work, 'sdk.mjs'), `
import React from './react.cjs'
const h = React.createElement
export const Button = ({ children, onClick }) => h('button', { onClick }, children)
export const SegmentedControl = ({ options, value }) => h('div', { 'data-seg': value }, options.map(o => h('span', { key: o.id }, o.label)))
export const host = { navigate() {}, notify() {}, notifyError() {} }
export function atom(v) { const subs = new Set(); return { get: () => v, set(n) { v = n; subs.forEach(f => f()) }, subscribe(f) { subs.add(f); return () => subs.delete(f) } } }
export function useValue(a) { return React.useSyncExternalStore(a.subscribe, a.get, a.get) }
export const ROUTES_AREA = 'routes', SIDEBAR_NAV_AREA = 'nav', PALETTE_AREA = 'palette', STATUSBAR_AREAS = { right: 'status.right' }
`)
const source = fs.readFileSync(path.join(here, '..', 'desktop', 'plugin.js'), 'utf8')
const imports = [...source.matchAll(/^import .* from '([^']+)'/gm)].map(m => m[1])
const bad = imports.filter(s => !['@hermes/plugin-sdk', 'react', 'react/jsx-runtime'].includes(s))
if (bad.length) throw new Error('unsupported imports: ' + bad.join(', '))
if (/#[0-9a-f]{3,8}\b|rgb\(|\b(black|white)\b/i.test(source.replace(/\/\/.*$/gm, ''))) throw new Error('hardcoded color in plugin.js')
fs.writeFileSync(path.join(work, 'plugin.mjs'), source
  .replace("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
  .replace("from 'react'", "from './react.cjs'"))
const plugin = (await import(pathToFileURL(path.join(work, 'plugin.mjs')).href)).default

const snap = JSON.parse(fs.readFileSync(snapPath, 'utf8'))
let mode = 'ok'
const store = new Map()
const contributions = []
const ctx = {
  storage: { get: (k, d) => store.has(k) ? store.get(k) : d, set: (k, v) => store.set(k, v) },
  rest: async (p) => {
    if (mode === 'error') throw new Error('HTTP 404')
    if (p.startsWith('/businesses')) return { businesses: mode === 'empty' ? [] : [{ id: 'b1', name: snap.business.name }] }
    return { ...snap, business_id: 'b1', source: 'saved' }
  },
  registerMany: cs => { contributions.push(...cs); return () => {} },
  register: c => { contributions.push(c); return () => {} },
  onDispose() {}, setInterval() { return () => {} }, setTimeout() { return () => {} }
}
plugin.register(ctx)
await new Promise(r => setTimeout(r, 50))
const byId = id => contributions.find(c => c.id === id)
const page = byId('page')
let checks = 0
const expect = (cond, msg) => { if (!cond) throw new Error('FAIL ' + msg); checks++ }

for (const tab of ['overview', 'daily', 'breakdown', 'approvals', 'economics', 'activity']) {
  store.set('tab', tab)
  const html = renderToString(page.render())
  expect(html.includes(snap.business.name), `${tab}: business name`)
  expect(html.length > 2000, `${tab}: rendered content (${html.length} bytes)`)
  if (tab === 'overview') {
    expect(html.includes(snap.status.headline.replace(/&/g, '&amp;')), 'overview: status headline')
    expect(html.includes('Funnel'), 'overview: funnel')
  }
  if (tab === 'daily') expect(html.includes('(gap)') === snap.campaigns.some(c => c.data_gaps.length), 'daily: gap days marked')
  if (tab === 'approvals') expect(snap.decisions.every(d => html.includes(d.id)), 'approvals: every decision listed')
  if (tab === 'economics') expect(html.includes('unknown') || html.includes('Missing'), 'economics: missing figures shown')
}
const chip = renderToString(byId('status').render())
expect(chip.includes(snap.business.name), 'status chip')
expect(['page', 'nav', 'open', 'rebuild', 'status'].every(byId), 'all five contributions registered')

for (const m of ['empty', 'error']) {
  mode = m
  plugin.register(ctx)
  await new Promise(r => setTimeout(r, 50))
  const html = renderToString(byId('page').render())
  expect(html.includes(m === 'empty' ? 'No marketing package configured' : 'isn'), `${m} state`)
}
fs.rmSync(work, { recursive: true, force: true })
console.log(`PASS render: ${checks} checks`)
