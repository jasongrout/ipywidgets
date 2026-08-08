// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import { test } from '@jupyterlab/galata';

import { expect } from '@playwright/test';

test.describe('Widget extension smoke test', () => {
  test('registers and activates the manager plugin', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const app = (window as any).jupyterapp;
      const id = '@jupyter-widgets/jupyterlab-manager:plugin';
      if (!app.hasPlugin(id)) {
        return { hasPlugin: false, activated: false, error: '' };
      }
      try {
        await app.activatePlugin(id);
        return { hasPlugin: true, activated: true, error: '' };
      } catch (e) {
        return { hasPlugin: true, activated: false, error: `${e}` };
      }
    });
    expect(result.error).toBe('');
    expect(result.hasPlugin).toBe(true);
    expect(result.activated).toBe(true);
  });
});
