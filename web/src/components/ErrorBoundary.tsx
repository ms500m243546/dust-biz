import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props { children: ReactNode; label?: string }
interface State { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };
  static getDerivedStateFromError(error: Error): State { return { error }; }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught', this.props.label, error, info);
  }
  render() {
    if (this.state.error) {
      return (
        <div className="card card-error">
          <h2>{this.props.label ?? 'Card'} unavailable</h2>
          <p className="muted">{this.state.error.message}</p>
          <button onClick={() => this.setState({ error: null })}>Retry</button>
        </div>
      );
    }
    return this.props.children;
  }
}
