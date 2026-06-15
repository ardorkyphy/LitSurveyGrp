import { describe, expect, it } from "vitest";
import pkg from "../package.json";

describe("desktop shell", () => {
  it("has a packaged app name", async () => {
    expect(pkg.productName).toBe("LitSurveyGrp");
  });
});
