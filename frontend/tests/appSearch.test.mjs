import assert from 'node:assert/strict'
import test from 'node:test'
import { appSearchDestination, appSearchFocusIndex, isAppSearchShortcut } from '../src/appSearch.ts'

const shortcut = {
  key: 'k',
  metaKey: true,
  ctrlKey: false,
  altKey: false,
  shiftKey: false,
  isComposing: false,
  repeat: false,
}

test('app search shortcut respects other dialogs, IME and modified browser commands', () => {
  assert.equal(isAppSearchShortcut(shortcut, false), true)
  assert.equal(isAppSearchShortcut({ ...shortcut, metaKey: false, ctrlKey: true, key: 'K' }, false), true)
  assert.equal(isAppSearchShortcut(shortcut, true), false)
  for (const overrides of [
    { isComposing: true },
    { keyCode: 229 },
    { repeat: true },
    { altKey: true },
    { shiftKey: true },
    { defaultPrevented: true },
    { key: 'p' },
    { metaKey: false },
  ])
    assert.equal(isAppSearchShortcut({ ...shortcut, ...overrides }, false), false)
})

test('Enter opens first suggestion and preserves catalog fallback while loading or empty', () => {
  assert.equal(
    appSearchDestination('Guardian', [{ items: [{ href: '#/rankings/7?group=published-rankings' }] }]),
    '#/rankings/7?group=published-rankings',
  )
  assert.equal(appSearchDestination('  Books & thought  ', []), '#/catalog?q=Books%20%26%20thought')
  assert.equal(appSearchDestination('x'.repeat(400), []).split('=')[1].length, 300)
})

test('arrow navigation connects search input to visible links with bounded indexes', () => {
  assert.equal(appSearchFocusIndex(-1, 1, 3), 0)
  assert.equal(appSearchFocusIndex(-1, -1, 3), 2)
  assert.equal(appSearchFocusIndex(0, -1, 3), -1)
  assert.equal(appSearchFocusIndex(1, 1, 3), 2)
  assert.equal(appSearchFocusIndex(2, 1, 3), 2)
  assert.equal(appSearchFocusIndex(-1, -1, 0), -1)
})
