import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Card from './ui/Card'
import Spinner from './ui/Spinner'

const EDUCATIONAL_MESSAGES = [
  'Applying Lipinski Rule of Five to filter drug-like compounds',
  'Predicting blood-brain barrier penetration with DeepChem',
  'Running AutoDock Vina binding affinity simulation',
  'Calculating synthetic accessibility scores with RDKit',
  'Querying UniProt and ChEMBL for target enrichment',
]

function PipelineProgress({ steps = [], isComplete = false }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [messageIndex, setMessageIndex] = useState(0)
  const MotionP = motion.p

  useEffect(() => {
    if (isComplete) {
      return undefined
    }

    const timer = window.setInterval(() => {
      setElapsedSeconds((current) => current + 1)
    }, 1000)

    return () => window.clearInterval(timer)
  }, [isComplete])

  useEffect(() => {
    if (isComplete) {
      return undefined
    }

    const timer = window.setInterval(() => {
      setMessageIndex((current) => (current + 1) % EDUCATIONAL_MESSAGES.length)
    }, 3000)

    return () => window.clearInterval(timer)
  }, [isComplete])

  return (
    <Card className="pipeline-progress-card">
      <div className="pipeline-progress-card__header">
        <strong>Running Pipeline</strong>
        <span>{elapsedSeconds}s</span>
      </div>

      <div className="pipeline-progress-card__steps">
        {steps.map((step, index) => (
          <div
            key={step.name}
            className={`pipeline-progress-card__row ${index === steps.length - 1 ? 'pipeline-progress-card__row--last' : ''}`}
          >
            <div className="pipeline-progress-card__indicator">
              {step.status === 'running' ? (
                <Spinner size={18} />
              ) : step.status === 'complete' ? (
                <span className="pipeline-progress-card__check">
                  <svg viewBox="0 0 18 18" aria-hidden="true">
                    <circle cx="9" cy="9" r="9" />
                    <path d="M5 9.2 7.6 12 13 6.4" />
                  </svg>
                </span>
              ) : (
                <span className="pipeline-progress-card__pending" />
              )}
            </div>
            <div className="pipeline-progress-card__content">
              <p>{step.name}</p>
              <span>{step.detail || ' '}</span>
            </div>
            <div className="pipeline-progress-card__duration">
              {step.status === 'complete' && step.duration !== null ? <span>{step.duration}s</span> : null}
            </div>
          </div>
        ))}
      </div>

      <div className="pipeline-progress-card__footer">
        <AnimatePresence mode="wait">
          <MotionP
            key={isComplete ? 'complete' : EDUCATIONAL_MESSAGES[messageIndex]}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            {isComplete ? 'Pipeline complete.' : EDUCATIONAL_MESSAGES[messageIndex]}
          </MotionP>
        </AnimatePresence>
      </div>
    </Card>
  )
}

export default PipelineProgress
