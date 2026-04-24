import { useCallback, useEffect, useState } from 'react'
import { getTarget } from '../services/api'

export function useTarget(targetId) {
  const [target, setTarget] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    if (!targetId) {
      setTarget(null)
      setLoading(false)
      setError('')
      return null
    }

    setLoading(true)
    setError('')

    try {
      const nextTarget = await getTarget(targetId)
      setTarget(nextTarget)
      return nextTarget
    } catch (requestError) {
      setTarget(null)
      setError(requestError.message)
      throw requestError
    } finally {
      setLoading(false)
    }
  }, [targetId])

  useEffect(() => {
    let cancelled = false

    if (!targetId) {
      return undefined
    }

    getTarget(targetId)
      .then((nextTarget) => {
        if (!cancelled) {
          setTarget(nextTarget)
          setError('')
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          setTarget(null)
          setError(requestError.message)
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [targetId])

  return {
    target,
    loading,
    error,
    refetch,
  }
}
