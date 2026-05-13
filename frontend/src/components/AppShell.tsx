import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";

export interface NavigationItem<TView extends string> {
  id: TView;
  label: string;
  description: string;
  icon: LucideIcon;
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
      <aside className="console-rail">
        <div className="rail-brand" aria-label="RelayMD Operator Console">
          <span>R</span>
        </div>
        <nav className="rail-nav" aria-label="Primary">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={activeView === item.id ? "rail-nav-link active" : "rail-nav-link"}
              onClick={() => onNavigate(item.id)}
              title={item.description}
            >
              <item.icon aria-hidden="true" size={20} strokeWidth={2} />
              <span>{item.label}</span>
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
