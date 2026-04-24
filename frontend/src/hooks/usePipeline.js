import { useCallback, useEffect, useRef, useState } from 'react'
import { getTarget, runPipeline } from '../services/api'

const sessionCompletedTargets = new Set()
const sessionPipelineResults = new Map()

const STEP_NAMES = [
  'Target Analysis',
  'Molecule Generation',
  'ADMET Screening',
  'Molecular Docking',
  'Report Generation',
]

const STEP_DETAILS = {
  'Target Analysis': 'Parsing target context...',
  'Molecule Generation': 'Generating candidates...',
  'ADMET Screening': 'Scoring...',
  'Molecular Docking': 'Docking...',
  'Report Generation': 'Assembling report...',
}

const POLL_INTERVAL_MS = 3000
const PIPELINE_TIMEOUT_MS = 5 * 60 * 1000

function makeSteps() {
  return STEP_NAMES.map((name, index) => ({
    name,
    status: index === 0 ? 'running' : 'pending',
    detail: index === 0 ? STEP_DETAILS[name] : null,
    duration: null,
  }))
}

export function resetPipelineSession(targetId) {
  if (!targetId) {
    return
  }

  sessionCompletedTargets.delete(targetId)
  sessionPipelineResults.delete(targetId)
}

export function markPipelineSessionComplete(targetId) {
  if (!targetId) {
    return
  }

  sessionCompletedTargets.add(targetId)
}

export function wasPipelineCompletedThisSession(targetId) {
  return Boolean(targetId) && sessionCompletedTargets.has(targetId)
}

export function setPipelineSessionResult(targetId, result) {
  if (!targetId || !result) {
    return
  }

  sessionPipelineResults.set(targetId, result)
}

export function getPipelineSessionResult(targetId) {
  return targetId ? sessionPipelineResults.get(targetId) || null : null
}

function createCompletedSteps(target, result, runStartedAt) {
  const now = Date.now()
  const totalSeconds = Math.max(1, (now - runStartedAt) / 1000)
  const weights = [0.14, 0.26, 0.18, 0.28, 0.14]
  const durations = weights.map((weight) => Number((totalSeconds * weight).toFixed(1)))
  const bestDocking = result?.docking_results?.length
    ? Math.min(...result.docking_results.map((entry) => entry.docking_score))
    : null

  return [
    {
      name: 'Target Analysis',
      status: 'complete',
      detail: `${target?.name || result?.target?.name || 'Target'} identified`,
      duration: durations[0],
    },
    {
      name: 'Molecule Generation',
      status: 'complete',
      detail: `${result?.molecules?.length || 0} molecules`,
      duration: durations[1],
    },
    {
      name: 'ADMET Screening',
      status: 'complete',
      detail: `${result?.admet_results?.length || 0} compounds scored`,
      duration: durations[2],
    },
    {
      name: 'Molecular Docking',
      status: 'complete',
      detail: bestDocking !== null ? `Best score ${bestDocking} kcal/mol` : 'Docking complete',
      duration: durations[3],
    },
    {
      name: 'Report Generation',
      status: 'complete',
      detail: result?.report_url ? 'PDF generated' : 'Report complete',
      duration: durations[4],
    },
  ]
}

export function usePipeline(targetId, options = {}) {
  const { skipCache = false } = options
  const initialResult = null
  const [steps, setSteps] = useState(() =>
    initialResult ? createCompletedSteps(initialResult.target, initialResult, Date.now() - 7000) : makeSteps(),
  )
  const [isRunning, setIsRunning] = useState(false)
  const [isComplete, setIsComplete] = useState(Boolean(initialResult))
  const [error, setError] = useState('')
  const [result, setResult] = useState(initialResult)
  const [status, setStatus] = useState(initialResult ? 'complete' : 'idle')
  const progressIntervalRef = useRef(null)
  const progressStartedAtRef = useRef(0)
  const activeStepRef = useRef(0)
  const pollCleanupRef = useRef(null)

  // Change: dedicated backend status polling for /api/targets/{target_id}/status
  const fetchPipelineStatus = useCallback(async (resolvedTargetId) => {
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const response = await fetch(`${baseUrl}/api/targets/${resolvedTargetId}/status`)

    if (!response.ok) {
      throw new Error('Could not fetch pipeline status.')
    }

    return response.json()
  }, [])

  useEffect(() => {
    const nextResult = null
    setResult(nextResult)
    setIsComplete(Boolean(nextResult))
    setError('')
    setStatus(nextResult ? 'complete' : 'idle')
    setSteps(nextResult ? createCompletedSteps(nextResult.target, nextResult, Date.now() - 7000) : makeSteps())
  }, [skipCache, targetId])

  const stopProgressSimulation = useCallback(() => {
    if (progressIntervalRef.current) {
      window.clearInterval(progressIntervalRef.current)
      progressIntervalRef.current = null
    }
  }, [])

  const stopPolling = useCallback(() => {
    if (pollCleanupRef.current) {
      pollCleanupRef.current()
      pollCleanupRef.current = null
    }
  }, [])

  const updateSteps = useCallback((target, pipelineResult = result) => {
    if (!pipelineResult) {
      return
    }

    setSteps(createCompletedSteps(target, pipelineResult, progressStartedAtRef.current || Date.now()))
  }, [result])

  // Change: poll every 3 seconds until complete, failed, or timed out at 5 minutes
  const startPolling = useCallback((resolvedTargetId, pipelineResult) => {
    const startedAt = Date.now()
    let intervalId = null
    let cancelled = false

    const cleanup = () => {
      cancelled = true
      if (intervalId) {
        window.clearInterval(intervalId)
        intervalId = null
      }
    }

    const checkStatus = async () => {
      if (cancelled) {
        return
      }

      if (Date.now() - startedAt >= PIPELINE_TIMEOUT_MS) {
        cleanup()
        stopProgressSimulation()
        setIsRunning(false)
        setIsComplete(false)
        setStatus('failed')
        setError('Pipeline timed out after 5 minutes.')
        return
      }

      try {
        const statusPayload = await fetchPipelineStatus(resolvedTargetId)

        if (statusPayload?.pipeline_error) {
          cleanup()
          stopProgressSimulation()
          setIsRunning(false)
          setIsComplete(false)
          setStatus('failed')
          setError(statusPayload.pipeline_error)
          return
        }

        if (statusPayload?.pipeline_complete === true) {
          const latestTarget = await getTarget(resolvedTargetId)
          updateSteps(latestTarget, pipelineResult)
          cleanup()
          stopProgressSimulation()
          setIsRunning(false)
          setIsComplete(true)
          setStatus('complete')
        }
      } catch (pollError) {
        console.warn('Pipeline status poll failed:', pollError.message)
      }
    }

    void checkStatus()
    intervalId = window.setInterval(() => {
      void checkStatus()
    }, POLL_INTERVAL_MS)

    return cleanup
  }, [fetchPipelineStatus, stopProgressSimulation, updateSteps])

  useEffect(() => {
    return () => {
      stopProgressSimulation()
      stopPolling()
    }
  }, [stopPolling, stopProgressSimulation])

  const simulateProgress = useCallback(() => {
    activeStepRef.current = 0
    progressStartedAtRef.current = Date.now()
    setSteps(makeSteps())

    progressIntervalRef.current = window.setInterval(() => {
      setSteps((current) => {
        if (activeStepRef.current >= STEP_NAMES.length - 1) {
          return current
        }

        const now = Date.now()
        const nextSteps = current.map((step, index) => {
          if (index < activeStepRef.current) {
            return step
          }

          if (index === activeStepRef.current) {
            return {
              ...step,
              status: 'complete',
              detail: step.detail || STEP_DETAILS[step.name],
              duration: Number(((now - progressStartedAtRef.current) / 1000).toFixed(1)),
            }
          }

          if (index === activeStepRef.current + 1) {
            return {
              ...step,
              status: 'running',
              detail: STEP_DETAILS[step.name],
            }
          }

          return step
        })

        activeStepRef.current += 1
        return nextSteps
      })
    }, 1600)
  }, [])

  const run = useCallback(async (query, seedSmiles, nMolecules) => {
    setError('')
    setIsComplete(false)
    setIsRunning(true)
    setStatus('running')
    stopPolling()
    stopProgressSimulation()
    simulateProgress()

    try {
      const pipelineResult = await runPipeline(query, seedSmiles, nMolecules)
      const resolvedTargetId = pipelineResult.target?.id || targetId
      markPipelineSessionComplete(resolvedTargetId)
      setPipelineSessionResult(resolvedTargetId, pipelineResult)
      setResult(pipelineResult)
      stopProgressSimulation()
      updateSteps(pipelineResult.target, pipelineResult)

      // Change: rely on dedicated backend status polling instead of manual clear hacks
      pollCleanupRef.current = startPolling(resolvedTargetId, pipelineResult)
      return pipelineResult
    } catch (requestError) {
      stopPolling()
      stopProgressSimulation()
      setIsRunning(false)
      setIsComplete(false)
      setError(requestError.message)
      setStatus('failed')
      setResult(null)
      setSteps(makeSteps())
      throw requestError
    }
  }, [simulateProgress, startPolling, stopPolling, stopProgressSimulation, targetId, updateSteps])

  const reset = useCallback(() => {
    stopPolling()
    stopProgressSimulation()
    setResult(null)
    setError('')
    setIsRunning(false)
    setIsComplete(false)
    setStatus('idle')
    setSteps(makeSteps())
  }, [stopPolling, stopProgressSimulation])

  return {
    run,
    reset,
    steps,
    isRunning,
    isComplete,
    error,
    result,
    status,
    updateSteps,
  }
}
