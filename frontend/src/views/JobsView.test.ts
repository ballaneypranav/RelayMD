import { describe, expect, it } from "vitest";

import {
  JOB_EXPANDED_PANEL_COLUMN_KEYS,
  JOB_EXPORT_COLUMN_KEYS,
} from "./JobsView";

describe("JobsView export columns", () => {
  it("includes every expanded-panel field in export columns", () => {
    const exportSet = new Set(JOB_EXPORT_COLUMN_KEYS);
    for (const key of JOB_EXPANDED_PANEL_COLUMN_KEYS) {
      expect(exportSet.has(key)).toBe(true);
    }
  });

  it("has no duplicate export columns", () => {
    expect(new Set(JOB_EXPORT_COLUMN_KEYS).size).toBe(JOB_EXPORT_COLUMN_KEYS.length);
  });
});
