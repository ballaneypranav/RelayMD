const TOKEN_KEY = "relaymd_api_token";

export function loadApiToken(): string {
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

export function saveApiToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token.trim());
}

export function clearApiToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}
