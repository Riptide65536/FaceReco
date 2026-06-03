interface StateBlockProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void | Promise<void>;
}

export function StateBlock({
  title,
  description,
  actionLabel,
  onAction,
}: StateBlockProps) {
  return (
    <div className="state-block">
      <div>
        <p className="state-block__title">{title}</p>
        <p className="state-block__description">{description}</p>
      </div>
      {actionLabel && onAction ? (
        <button className="ghost-button" onClick={() => void onAction()}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
