import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("Uncaught error in UI:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0a0a0f', color: '#e5e7eb', fontFamily: 'monospace', padding: '2rem', textAlign: 'center' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#f59e0b', marginBottom: '1rem' }}>An Unexpected Chrono-Anomaly Occurred</h2>
          <p style={{ fontSize: '0.875rem', color: '#9ca3af', maxWidth: '600px', marginBottom: '1.5rem', wordBreak: 'break-word' }}>
            {this.state.error?.message || 'Something went wrong rendering the console interface.'}
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{ padding: '0.5rem 1.25rem', background: '#f59e0b', color: '#000', fontWeight: 'bold', borderRadius: '4px', border: 'none', cursor: 'pointer' }}
          >
            Reload Console
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
