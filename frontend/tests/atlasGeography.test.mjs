import assert from 'node:assert/strict'
import test from 'node:test'
import { countryCoordinates, isMappedCountry, projectCountry } from '../src/atlasGeography.ts'

test('UK constituent countries keep their own published label coordinates', () => {
  const labels = ['United Kingdom', 'England', 'Scotland', 'Wales', 'Northern Ireland']
  const points = labels.map((label) => countryCoordinates(label))
  assert.equal(new Set(points.map(JSON.stringify)).size, labels.length)
  assert.deepEqual(countryCoordinates('England'), [-1.402032, 52.60981])
  assert.deepEqual(countryCoordinates('Scotland'), [-4.045025, 56.792374])
})

test('whole-label aliases locate without interpreting contextual or historical labels', () => {
  assert.deepEqual(countryCoordinates('USA'), countryCoordinates('United States'))
  assert.deepEqual(countryCoordinates('US'), countryCoordinates('UnitedStates'))
  assert.deepEqual(countryCoordinates('Türkiye'), countryCoordinates('Turkey'))
  assert.deepEqual(countryCoordinates('Côte d’Ivoire'), countryCoordinates("Côte d'Ivoire"))
  for (const label of ['Global', 'Ancient world', 'United Kingdom and Ireland', 'Japan context', 'France / USA', 'Scotland / United Kingdom', '__unknown__', 'Korea']) {
    assert.equal(isMappedCountry(label), false, label)
  }
})

test('small territories have source coordinates and the same map projection', () => {
  for (const label of ['Cook Islands', 'Niue', 'Kosovo', 'Western Sahara', 'Hong Kong', 'São Tomé and Príncipe', 'Holy See / Vatican City', 'Antigua and Barbuda', 'Tuvalu']) {
    assert.equal(isMappedCountry(label), true, label)
    const [longitude, latitude] = countryCoordinates(label)
    const [x, y] = projectCountry(label)
    assert.equal(x, (longitude + 180) * 2)
    assert.equal(y, (90 - latitude) * 2)
    assert.ok(x >= 0 && x <= 720)
    assert.ok(y >= 0 && y <= 360)
  }
})
