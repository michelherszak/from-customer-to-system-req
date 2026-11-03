import { test, expect } from '@playwright/test'

test('US_30_AC_03 critical browser journey login and project workflow is reachable', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('max.mustermann')
  await page.getByLabel('Passwort').fill('KuSys-Demo-2026')
  await page.getByRole('button', { name: 'Anmelden' }).click()
  await expect(page.getByRole('heading', { name: 'Projekte' })).toBeVisible()
  await page.getByRole('button', { name: /Öffnen/ }).first().click()
  await expect(page.getByText('Kundendokument → Prüfschritt')).toBeVisible()
  await expect(page.getByRole('tab', { name: /Dokumente/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: /Prüfschritt/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: /Anforderungen/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: /Planung/ })).toBeVisible()
  await expect(page.getByRole('tab', { name: /Angebote/ })).toBeVisible()
})

test('US_07_AC_04 customer sees only portal surface', async ({ page }) => {
  await page.goto('/')
  await page.getByLabel('Benutzername').fill('kunde.nordstern')
  await page.getByLabel('Passwort').fill('KuSys-Demo-2026')
  await page.getByRole('button', { name: 'Anmelden' }).click()
  await expect(page.getByText('KuSys Kundenportal')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Veröffentlichte Projekte' })).toBeVisible()
  await expect(page.getByText('Vorlagen')).toHaveCount(0)
})
