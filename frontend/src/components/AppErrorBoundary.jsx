import React from 'react'

class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('MolGenix frontend render error:', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app-error-boundary">
          <h1>Frontend error</h1>
          <p>{this.state.error.message || 'Unknown render failure.'}</p>
          <pre>{this.state.error.stack}</pre>
        </div>
      )
    }

    return this.props.children
  }
}

export default AppErrorBoundary
