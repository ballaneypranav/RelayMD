import type { ClusterConfig } from "../types";

interface ClustersViewProps {
  clusters: ClusterConfig[];
}

export function ClustersView({ clusters }: ClustersViewProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <p className="eyebrow">Clusters</p>
          <h2>Provisioning targets</h2>
          <p className="panel-copy">Review scheduling strategy, pending limits, and wall-clock constraints.</p>
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
