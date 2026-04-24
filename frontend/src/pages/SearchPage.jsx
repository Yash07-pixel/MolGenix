import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Textarea from '../components/ui/Textarea'
import Divider from '../components/ui/Divider'
import { resetPipelineSession } from '../hooks/usePipeline'
import { analyzeTarget, getAllTargets } from '../services/api'

const DEFAULT_QUERY = ''
const DEMO_QUERY = "BACE1 beta-secretase enzyme involved in Alzheimer's disease"
const MAX_QUERY_LENGTH = 300
const EXAMPLE_QUERIES = [
  "BACE1 in Alzheimer's",
  'EGFR kinase in lung cancer',
  'HIV-1 protease',
  'COX-2 in inflammation',
]

function SearchPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [query, setQuery] = useState(DEFAULT_QUERY)
  const [error, setError] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const hasAutoSubmitted = useRef(false)

  const submitAnalysis = useCallback(async (queryValue, seedValue, moleculeCount) => {
    setError('')
    setIsRunning(true)

    try {
      const target = await analyzeTarget(queryValue.trim(), seedValue.trim() || null, moleculeCount)
      resetPipelineSession(target.id)
      navigate(`/target/${target.id}`, {
        state: {
          target,
          skipCachedPipeline: true,
          freshAnalysis: true,
        },
      })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setIsRunning(false)
    }
  }, [navigate])

  async function handleSubmit(event) {
    event.preventDefault()
    const normalizedQuery = query.trim()

    if (!normalizedQuery) {
      setError('Please describe a target before starting the analysis.')
      return
    }

    await submitAnalysis(normalizedQuery, '', 10)
  }

  useEffect(() => {
    const targetValue = searchParams.get('target')
    const isDemo = searchParams.get('demo') === 'true'

    if (targetValue) {
      const timer = window.setTimeout(() => setQuery(targetValue), 0)
      return () => window.clearTimeout(timer)
    }

    if (!isDemo) {
      const timer = window.setTimeout(() => setQuery(DEFAULT_QUERY), 0)
      hasAutoSubmitted.current = false
      return () => window.clearTimeout(timer)
    }

    let cancelled = false

    async function bootDemo() {
      window.setTimeout(() => {
        if (!cancelled) {
          setQuery(DEMO_QUERY)
        }
      }, 0)

      try {
        const targets = await getAllTargets()
        if (cancelled) {
          return
        }

        const existingBace1 = targets.find((target) =>
          `${target.name || ''} ${target.disease || ''}`.toLowerCase().includes('bace1'),
        )

        if (existingBace1) {
          navigate(`/target/${existingBace1.id}?demo=true`)
          return
        }

        if (!hasAutoSubmitted.current) {
          hasAutoSubmitted.current = true
          window.setTimeout(() => {
            if (!cancelled) {
              submitAnalysis(DEMO_QUERY, '', 10)
            }
          }, 800)
        }
      } catch (requestError) {
        if (!cancelled) {
          setError(requestError.message)
        }
      }
    }

    bootDemo()

    return () => {
      cancelled = true
    }
  }, [navigate, searchParams, submitAnalysis])

  return (
    <PageWrapper className="search-page">
      <div className="search-page__header">
        <div>
          <h1>Search for a Target</h1>
          <p>Describe a protein, gene, or disease. The more specific, the better.</p>
        </div>
      </div>

      <Card className="search-form-card">
        <form className="search-form" onSubmit={handleSubmit}>
          <label className="field">
            <span>Target description</span>
            <Textarea
              rows={6}
              maxLength={MAX_QUERY_LENGTH}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="e.g. BACE1 beta-secretase enzyme involved in Alzheimer's disease"
            />
            <span className="search-counter">
              {query.length} / {MAX_QUERY_LENGTH}
            </span>
          </label>

          <Divider className="search-divider" />

          {error ? <div className="search-error-banner">{error}</div> : null}

          <Button type="submit" size="lg" className="search-submit" loading={isRunning}>
            {isRunning ? 'Analyzing...' : 'Analyze Target'}
          </Button>
        </form>
      </Card>

      <div className="search-examples">
        <p className="search-examples__label">Try an example</p>
        <div className="search-examples__chips">
          {EXAMPLE_QUERIES.map((example) => (
            <Button
              key={example}
              size="sm"
              variant="secondary"
              type="button"
              onClick={() => setQuery(example)}
            >
              {example}
            </Button>
          ))}
        </div>
      </div>
    </PageWrapper>
  )
}

export default SearchPage
