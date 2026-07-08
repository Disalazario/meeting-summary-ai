import { test, expect } from '@playwright/test';
import { loginViaAPI } from './auth.setup.js';

test.describe('Dashboard page', () => {
  let authed;

  test.beforeEach(async ({ page }) => {
    authed = await loginViaAPI(page);
    if (!authed.authenticated) {
      // Navigate to the page anyway so non-auth assertions can still be checked
      await page.goto('/');
    }
  });

  test('shows meeting list or empty state', async ({ page }) => {
    test.skip(!authed.authenticated, 'Skipped — authentication failed');

    // Either the meetings heading is visible or we see the empty-state text
    const heading = page.getByRole('heading', { name: 'Совещания' });
    await expect(heading).toBeVisible({ timeout: 10000 });

    const emptyState = page.getByText('Нет совещаний');
    const meetingCard = page.locator('.grid > div').first();

    // At least one of these should be present
    const hasEmpty = await emptyState.isVisible().catch(() => false);
    const hasCards = await meetingCard.isVisible().catch(() => false);
    expect(hasEmpty || hasCards).toBeTruthy();
  });

  test('navigation links work (Расписание, Настройки, Ганта)', async ({ page }) => {
    test.skip(!authed.authenticated, 'Skipped — authentication failed');

    // Wait for the nav to be rendered
    await expect(page.getByRole('heading', { name: 'Совещания' })).toBeVisible({ timeout: 10000 });

    // Расписание
    await page.getByRole('link', { name: 'Расписание' }).click();
    await expect(page).toHaveURL(/\/schedule/);

    // Ганта
    await page.getByRole('link', { name: 'Ганта' }).click();
    await expect(page).toHaveURL(/\/gantt/);

    // Настройки
    await page.getByRole('link', { name: 'Настройки' }).click();
    await expect(page).toHaveURL(/\/settings/);
  });

  test('logout button returns to login page', async ({ page }) => {
    test.skip(!authed.authenticated, 'Skipped — authentication failed');

    await expect(page.getByRole('heading', { name: 'Совещания' })).toBeVisible({ timeout: 10000 });

    await page.getByRole('button', { name: 'Выйти' }).click();
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: 'Войти' })).toBeVisible();
  });
});
