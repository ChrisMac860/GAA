import { test, expect } from '@playwright/test';

test('landing loads and fixtures page lists items', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'GAA Fixtures & Results' })).toBeVisible();
  await page.getByRole('link', { name: 'Fixtures' }).click();
  await expect(page.getByRole('heading', { name: 'Fixtures' })).toBeVisible();
  // At least one article in the list
  const articles = page.locator('article');
  await expect(articles.first()).toBeVisible();
});
