import type { ClusterConfig } from "../types";

interface ClustersViewProps {
  clusters: ClusterConfig[];
  clusterEdits: Record<string, boolean>;
  unsavedCount: number;
  saveInFlight: boolean;
  onToggle: (clusterName: string, enabled: boolean) => void;
  onSave: () => void;
}

export function ClustersView({
  clusters,
  clusterEdits,
  unsavedCount,
  saveInFlight,
  onToggle,
  onSave,
}: ClustersViewProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Clusters</p>
          <h2>Provisioning targets</h2>
          <p className="panel-copy">Review scheduling strategy, pending limits, and wall-clock constraints.</p>
        </div>
        <div className="toolbar">
          <span className="muted">{unsavedCount} unsaved changes</span>
          <button onClick={onSave} disabled={saveInFlight || unsavedCount === 0}>
            {saveInFlight ? "Saving..." : "Save changes"}
          </button>
        </div>
      </div>

      {clusters.length === 0 ? (
        <div className="empty-state">
          <h3>No cluster configs available</h3>
          <p>Configured SLURM clusters will appear here when the orchestrator exposes them.</p>
        </div>
      ) : (
        <div className="cluster-grid">
          {clusters.map((cluster) => (
            <article className="cluster-card" key={cluster.name}>
              <div className="cluster-head">
                <div>
                  <p className="eyebrow">Cluster</p>
                  <h3>{cluster.name}</h3>
                </div>
                <span className="cluster-badge">{cluster.strategy}</span>
              </div>
              <dl className="detail-list compact">
                <div>
                  <dt>Provisioning</dt>
                  <dd>
                    <label className="toggle-label">
                      <input
                        type="checkbox"
                        checked={clusterEdits[cluster.name] ?? cluster.enabled}
                        onChange={(event) => onToggle(cluster.name, event.target.checked)}
                      />
                      <span>{(clusterEdits[cluster.name] ?? cluster.enabled) ? "Enabled" : "Disabled"}</span>
                    </label>
                  </dd>
                </div>
                <div>
                  <dt>Partition</dt>
                  <dd>{cluster.partition}</dd>
                </div>
                <div>
                  <dt>Max Pending Jobs</dt>
                  <dd>{cluster.max_pending_jobs}</dd>
                </div>
                <div>
                  <dt>Wall Time</dt>
                  <dd>{cluster.wall_time}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
