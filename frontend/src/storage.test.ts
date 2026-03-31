import { clearApiToken, loadApiToken, saveApiToken } from "./storage";

describe("token storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("stores and clears the api token", () => {
    saveApiToken("secret-token");
    expect(loadApiToken()).toBe("secret-token");
    clearApiToken();
    expect(loadApiToken()).toBe("");
  });
});
