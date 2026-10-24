import { useEffect, useState } from 'react'

const POLL_INTERVAL_MS = 2000

export default function useModelReadiness(model, enabled = true, refresh = 0) {
  const [state, setState] = useState({
    model: null,
    status: 'unknown',
    error: null,
  })

  useEffect(() => {
    if (!enabled || !model) {
      setState({ model, status: 'unknown', error: null })
      return
    }

    let cancelled = false
    let timer = null
    let controller = null

    async function poll() {
      controller = new AbortController()

      try {
        const response = await fetch('/api/router/models', {
          credentials: 'include',
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`Router status request failed: ${response.status}`)
        }

        const data = await response.json()
        const entry = data.models?.find(item => item.model === model)

        if (!cancelled) {
          setState({
            model,
            status: entry?.status ?? 'unavailable',
            error: null,
          })
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            model,
            status: 'unavailable',
            error: error.message,
          })
        }
      } finally {
        if (!cancelled) {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      }
    }

    setState({ model, status: 'checking', error: null })
    poll()

    return () => {
      cancelled = true
      clearTimeout(timer)
      controller?.abort()
    }
  }, [model, enabled, refresh])

  return {
    status: state.model === model ? state.status : 'checking',
    error: state.model === model ? state.error : null,
    ready: enabled && state.model === model && state.status === 'loaded',
  }
}
