import { test, expect } from '@playwright/test';
import { loginViaAPI } from './auth.setup.js';

test.describe('Gantt page', () => {
  let authed;

  test.beforeEach(async ({ page }) => {
    authed = await loginViaAPI(page);
    if (authed.authenticated) {
      await page.goto('/gantt');
    }
  });

  test('page loads without crashing (no blank screen)', async ({ page }) => {
    test.skip(!authed.authenticated, 'Skipped — authentication failed');

    // The page should show *something* — either the configured state with
    // a project selector or the unconfigured message. Either way, the body
    // should not be empty.
    await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {});

    const body = page.locator('body');
    await expect(body).not.toBeEmpty();

    // Specifically: either the heading or the "not configured" message
    const heading = page.getByRole('heading', { name: 'Диаграмма Ганта' });
    const notConfigured = page.getByText('PlanFix не настроен');
    const loadingText = page.getByText('Загрузка');

    const headingVisible = await heading.isVisible().catch(() => false);
    const notConfiguredVisible = await notConfigured.isVisible().catch(() => false);
    const loadingVisible = await loadingText.isVisible().catch(() => false);

    expect(headingVisible || notConfiguredVisible || loadingVisible).toBeTruthy();
  });

  test('shows "PlanFix не настроен" or project dropdown', async ({ page }) => {
    test.skip(!authed.authenticated, 'Skipped — authentication failed');

    // Wait for initial loading to finish
    await page.waitForTimeout(2000);

    const notConfigured = page.getByText('PlanFix не настроен');
    const projectSelect = page.locator('select');

    const showsNotConfigured = await notConfigured.isVisible().catch(() => false);
    const showsSelect = await projectSelect.isVisible().catch(() => false);

    expect(showsNotConfigured || showsSelect).toBeTruthy();
  });

  test('project selector contains "Выберите проект" placeholder', async ({ page }) => {
    test.skip(!authed.authenticated, 'Skipped — authentication failed');

    // Wait for loading
    await page.waitForTimeout(2000);

    const projectSelect = page.locator('select');
    const selectVisible = await projectSelect.isVisible().catch(() => false);

    if (selectVisible) {
      // The default option should be the placeholder
      const placeholder = page.locator('option', { hasText: 'Выберите проект' });
      await expect(placeholder).toBeAttached();
    } else {
      // PlanFix is not configured — that is a valid state
      const notConfigured = page.getByText('PlanFix не настроен');
      await expect(notConfigured).toBeVisible();
    }
  });
});
