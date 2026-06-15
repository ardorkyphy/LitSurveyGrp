import { Activity, Files, PlayCircle } from "lucide-react";
import type { PropsWithChildren } from "react";

type AppShellProps = PropsWithChildren<{
  view: string;
  onViewChange: (view: string) => void;
}>;

export function AppShell({ view, onViewChange, children }: AppShellProps) {
  const items = [
    { key: "runs", label: "Runs", icon: Activity },
    { key: "new", label: "New Run", icon: PlayCircle },
    { key: "files", label: "Results", icon: Files }
  ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">LitSurveyGrp</div>
        <nav>
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.key}
                className={view === item.key ? "nav-item active" : "nav-item"}
                onClick={() => onViewChange(item.key)}
              >
                <Icon size={18} />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}

