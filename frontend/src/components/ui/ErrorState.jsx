import Button from "./Button";
import Icon from "./Icon";
import "./ErrorState.css";

export default function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state">
      <div className="error-icon"><Icon name="alert" size={30} /></div>
      <h3 className="error-title">Something went wrong</h3>
      <p className="error-msg">{message || "An unexpected error occurred."}</p>
      {onRetry && (
        <Button variant="secondary" onClick={onRetry}>Try again</Button>
      )}
    </div>
  );
}
