import Icon from "./Icon";
import "./EmptyState.css";

export default function EmptyState({ icon = "clipboard", title, description, action }) {
  return (
    <div className="empty-state">
      <div className="empty-icon"><Icon name={icon} size={30} /></div>
      <h3 className="empty-title">{title}</h3>
      {description && <p className="empty-desc">{description}</p>}
      {action && <div className="empty-action">{action}</div>}
    </div>
  );
}
