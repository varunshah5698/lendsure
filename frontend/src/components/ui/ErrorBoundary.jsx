import { Component } from "react";

export default class ErrorBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch() {}
  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, textAlign: "center" }}>
          <h2 style={{ color: "var(--text)" }}>Something went wrong</h2>
          <p style={{ color: "var(--text-muted)", fontSize: 13 }}>{String(this.state.error.message || this.state.error)}</p>
          <button
            onClick={() => { this.setState({ error: null }); window.location.hash = ""; window.location.reload(); }}
            style={{ padding: "8px 18px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", cursor: "pointer" }}
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
