import type { ReactNode } from "react";

export interface NavigationItem<TView extends string> {
  id: TView;
  label: string;
  description: string;
}

interface AppShellProps<TView extends string> {
  activeView: TView;
  navigation: NavigationItem<TView>[];
  onNavigate: (view: TView) => void;
  header: ReactNode;
  overview: ReactNode;
  children: ReactNode;
}

export function AppShell<TView extends string>({
  activeView,
  navigation,
  onNavigate,
  header,
  overview,
  children,
}: AppShellProps<TView>) {
  return (
    <div className="console-shell">
      <aside className="console-sidebar">
        <div className="brand-block">
          <p className="eyebrow">RelayMD</p>
          <h1>Operator Console</h1>
          <p className="sidebar-copy">
            Cluster-aware orchestration view for jobs, workers, and control-plane status.
          </p>
        </div>
        <nav className="console-nav" aria-label="Primary">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={activeView === item.id ? "nav-link active" : "nav-link"}
              onClick={() => onNavigate(item.id)}
            >
              <span>{item.label}</span>
              <small>{item.description}</small>
            </button>
          ))}
        </nav>
      </aside>

      <div className="console-main">
        {header}
        {overview}
        <div className="view-frame">{children}</div>
      </div>
    </div>
  );
}
