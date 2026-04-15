interface SettingsViewProps {
  apiBaseUrl: string;
  refreshIntervalSeconds: number | string;
}

export function SettingsView({ apiBaseUrl, refreshIntervalSeconds }: SettingsViewProps) {
  return (
    <div className="settings-grid">
      <section className="panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Settings</p>
            <h2>Operator access</h2>
            <p className="panel-copy">
              Dashboard access is handled by the local basic-auth proxy. The browser no longer
              stores the RelayMD API token.
            </p>
          </div>
        </div>
        <div className="empty-state">
          <h3>Auth flow</h3>
          <p>
            1. Open the dashboard through the proxy on port <code>36159</code>.
          </p>
          <p>2. Enter the proxy username and password in the browser prompt.</p>
          <p>
            3. The proxy injects the RelayMD API token upstream, so no dashboard token prompt is
            required.
          </p>
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
