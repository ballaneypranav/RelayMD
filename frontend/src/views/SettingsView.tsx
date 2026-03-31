interface SettingsViewProps {
  tokenInput: string;
  tokenStored: boolean;
  apiBaseUrl: string;
  refreshIntervalSeconds: number | string;
  onTokenChange: (value: string) => void;
  onSaveToken: () => void;
  onClearToken: () => void;
}

export function SettingsView({
  tokenInput,
  tokenStored,
  apiBaseUrl,
  refreshIntervalSeconds,
  onTokenChange,
  onSaveToken,
  onClearToken,
}: SettingsViewProps) {
  return (
    <div className="settings-grid">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Settings</p>
            <h2>Operator access</h2>
            <p className="panel-copy">
              Store the API token in this browser and review the current orchestrator connection.
            </p>
          </div>
        </div>

        <label className="field-label" htmlFor="relaymd-token">
          API token
        </label>
        <input
          id="relaymd-token"
          type="password"
          value={tokenInput}
          onChange={(event) => onTokenChange(event.target.value)}
          placeholder="Enter RELAYMD_API_TOKEN"
        />
        <p className="panel-copy">
          Token is stored in localStorage for this browser only. Current state:{" "}
          {tokenStored ? "configured" : "missing"}.
        </p>
        <div className="toolbar">
          <button onClick={onSaveToken}>Save token</button>
          <button className="secondary" onClick={onClearToken}>
            Clear token
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Connection</p>
            <h2>Runtime config</h2>
          </div>
        </div>
        <dl className="detail-list">
          <div>
            <dt>API base URL</dt>
            <dd>{apiBaseUrl}</dd>
          </div>
          <div>
            <dt>Refresh interval</dt>
            <dd>{refreshIntervalSeconds}s</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
