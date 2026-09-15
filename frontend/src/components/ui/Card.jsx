import "./Card.css";

export default function Card({ children, className = "", hover = false, padding = "md", ...props }) {
  return (
    <div className={`card card-${padding} ${hover ? "card-hover" : ""} ${className}`} {...props}>
      {children}
    </div>
  );
}

export function CardHeader({ children, className = "" }) {
  return <div className={`card-header ${className}`}>{children}</div>;
}

export function CardTitle({ children, className = "" }) {
  return <h3 className={`card-title ${className}`}>{children}</h3>;
}

export function CardDescription({ children }) {
  return <p className="card-desc">{children}</p>;
}

export function CardContent({ children, className = "" }) {
  return <div className={`card-content ${className}`}>{children}</div>;
}
