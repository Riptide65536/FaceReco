import type { PropsWithChildren, ReactNode } from "react";

interface PanelProps extends PropsWithChildren {
  eyebrow?: string;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  className?: string;
}

export function Panel({
  eyebrow,
  title,
  subtitle,
  actions,
  className,
  children,
}: PanelProps) {
  return (
    <section className={`panel ${className ?? ""}`.trim()}>
      <header className="panel__header">
        <div>
          {eyebrow ? <p className="panel__eyebrow">{eyebrow}</p> : null}
          <h2 className="panel__title">{title}</h2>
          {subtitle ? <p className="panel__subtitle">{subtitle}</p> : null}
        </div>
        {actions ? <div className="panel__actions">{actions}</div> : null}
      </header>
      <div className="panel__body">{children}</div>
    </section>
  );
}
