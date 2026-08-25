'use client'

import { Component } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import Button from '@/components/ui/Button'
import { logger } from '@/lib/logger'

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    logger.error(`[ErrorBoundary] ${this.props.name || 'Component'} crashed`, {
      message: error?.message,
      code: error?.code,
      request_id: error?.request_id,
      trace_id: error?.trace_id,
      origin: error?.origin,
      errorInfo,
    })
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null })
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="max-w-md text-center space-y-4">
            <div className="inline-flex p-3 rounded-full bg-danger-soft">
              <AlertTriangle size={28} className="text-danger" />
            </div>
            <h3 className="text-xl font-semibold text-text-primary">
              Something went wrong
            </h3>
            <p className="text-[15px] text-text-secondary">
              {this.props.name
                ? `The ${this.props.name} tab encountered an error.`
                : 'This component encountered an unexpected error.'}
            </p>
            {this.state.error?.message && (
              <pre className="text-[13px] text-text-muted bg-bg-tertiary rounded-lg p-3 text-left overflow-auto max-h-32">
                {this.state.error.message}
                {this.state.error.code ? `\ncode: ${this.state.error.code}` : ''}
                {/* Surface the correlation ids the boundary already logs, so a
                    user can quote them in a bug report and they can be matched
                    against the gateway logs. */}
                {this.state.error.request_id ? `\nrequest: ${this.state.error.request_id}` : ''}
                {this.state.error.trace_id ? `\ntrace: ${this.state.error.trace_id}` : ''}
              </pre>
            )}
            <Button variant="primary" size="sm" onClick={this.handleRetry} className="gap-1.5">
              <RefreshCw size={14} />
              Try Again
            </Button>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
