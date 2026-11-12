import { Component, type ReactNode } from "react";

/** Keeps one broken part (like the chart) from blanking the whole page. */
export default class ErrorBoundary extends Component<{ children: ReactNode; label: string }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error(`${this.props.label} failed:`, error);
  }

  render() {
    if (this.state.failed) return <div className="chart skeleton">{this.props.label} couldn't load. Try reloading the page.</div>;
    return this.props.children;
  }
}
