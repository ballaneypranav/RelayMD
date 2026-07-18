import { describe, expect, it } from "vitest";

import { displayWorkerImage } from "./workerImages";

describe("displayWorkerImage", () => {
  it("uses configured names and keeps unknown keys literal", () => {
    expect(displayWorkerImage("atom-openmm", { "atom-openmm": "AToM-OpenMM" })).toBe(
      "AToM-OpenMM",
    );
    expect(displayWorkerImage("unknown", {})).toBe("unknown");
    expect(displayWorkerImage(undefined, {})).toBe("-");
  });
});
