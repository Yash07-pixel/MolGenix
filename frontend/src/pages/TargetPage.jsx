import { useEffect, useMemo, useRef } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Badge from '../components/ui/Badge'
import Button from '../components/ui/Button'
import Divider from '../components/ui/Divider'
import Skeleton from '../components/ui/Skeleton'
import PipelineProgress from '../components/PipelineProgress'
import ErrorState from '../components/ErrorState'
import { useToast } from '../hooks/useToast'
import { useTarget } from '../hooks/useTarget'
import { useMolecules } from '../hooks/useMolecules'
import { resetPipelineSession, usePipeline, wasPipelineCompletedThisSession } from '../hooks/usePipeline'

const DEFAULT_PIPELINE_MOLECULE_COUNT = 30

function TargetPage() {
  const { targetId } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const completionHandledRef = useRef(false)
  const shouldSkipCachedPipeline = Boolean(location.state?.skipCachedPipeline)
  const freshAnalysis = Boolean(location.state?.freshAnalysis)
  const { target, loading: targetLoading, error: targetError, refetch: refetchTarget } = useTarget(targetId)
  const { molecules, loading: moleculesLoading, error: moleculesError, refetch: refetchMolecules } = useMolecules(targetId)
  const pipeline = usePipeline(targetId, { skipCache: shouldSkipCachedPipeline })
  const pipelineCompletedThisSession = wasPipelineCompletedThisSession(targetId)
  const pipelineResult = pipeline.result
  const pipelineMoleculeIds = pipelineResult?.molecules?.map((molecule) => molecule.id).filter(Boolean) || []
  const isLoading = targetLoading || moleculesLoading
  const pageError = targetError || moleculesError

  const bestDockingScore = useMemo(() => {
    const scores = molecules
      .map((molecule) => molecule.docking_score)
      .filter((score) => score !== null && score !== undefined)
    return scores.length ? Math.min(...scores) : null
  }, [molecules])

  const biologicalContext = useMemo(() => {
    if (!target) {
      return ''
    }

    const parts = [
      target.disease ? `${target.name} is associated with ${target.disease}.` : `${target.name} is the active target in this run.`,
      target.known_inhibitors !== null && target.known_inhibitors !== undefined
        ? `${target.known_inhibitors} known inhibitor records were identified during enrichment.`
        : null,
      target.structure_count !== null && target.structure_count !== undefined
        ? `${target.structure_count} structural entries were linked to this target.`
        : null,
      target.pdb_id ? `Primary receptor structure: ${target.pdb_id}.` : null,
      target.gemini_source ? `Target context source: ${target.gemini_source}.` : null,
    ]

    return parts.filter(Boolean).join(' ')
  }, [target])

  const completedSteps = useMemo(() => {
    if (!pipelineResult) {
      return []
    }

    const bestRunDocking = pipelineResult.docking_results?.length
      ? Math.min(...pipelineResult.docking_results.map((entry) => entry.docking_score))
      : null

    return [
      {
        name: 'Target Analysis',
        detail: pipelineResult.target?.disease || target?.disease || 'Target enriched and resolved',
      },
      {
        name: 'Molecule Generation',
        detail: `${pipelineResult.molecules?.length || molecules.length} candidates prepared`,
      },
      {
        name: 'ADMET Screening',
        detail: `${pipelineResult.admet_results?.length || 0} molecules scored`,
      },
      {
        name: 'Molecular Docking',
        detail: bestRunDocking !== null ? `Best score ${bestRunDocking} kcal/mol` : 'Docking completed',
      },
      {
        name: 'Report Generation',
        detail: pipelineResult.report_url ? 'Fresh PDF generated for this run' : 'Report complete',
      },
    ]
  }, [molecules.length, pipelineResult, target])

  useEffect(() => {
    if (!freshAnalysis) {
      return
    }

    completionHandledRef.current = false
    resetPipelineSession(targetId)
  }, [freshAnalysis, targetId])

  useEffect(() => {
    if (!pipeline.isComplete || !pipelineCompletedThisSession || completionHandledRef.current) {
      return
    }

    completionHandledRef.current = true
    showToast('Pipeline complete.', 'success')
    refetchTarget().catch(() => {})
    refetchMolecules().catch(() => {})

    const timer = window.setTimeout(() => {
      navigate(`/report/${targetId}`, {
        state: {
          moleculeIds: pipelineMoleculeIds,
        },
      })
    }, 2000)

    return () => window.clearTimeout(timer)
  }, [navigate, pipeline.isComplete, pipelineCompletedThisSession, pipelineMoleculeIds, refetchMolecules, refetchTarget, showToast, targetId])

  async function handleRunPipeline() {
    if (!target?.name) {
      return
    }

    completionHandledRef.current = false

    try {
      await pipeline.run(
        `${target.name}${target.disease ? ` ${target.disease}` : ''}`,
        null,
        DEFAULT_PIPELINE_MOLECULE_COUNT,
      )
    } catch (error) {
      showToast(error.message, 'error')
    }
  }

  function getDruggabilityColor(score) {
    if (score > 0.7) return 'var(--green)'
    if (score >= 0.4) return 'var(--yellow)'
    return 'var(--red)'
  }

  function handlePipelineReset() {
    completionHandledRef.current = false
    pipeline.reset()
  }

  if (pageError && !isLoading) {
    return (
      <PageWrapper className="target-page">
        <ErrorState
          title="Could not load target"
          message={pageError}
          retryFn={() => Promise.all([refetchTarget(), refetchMolecules()])}
        />
      </PageWrapper>
    )
  }

  return (
    <PageWrapper className="target-page">
      <div className="target-breadcrumb">
        <Link to="/search">Search</Link>
        <span>/</span>
        <span>{target?.name || targetId}</span>
      </div>

      <section className="target-header">
        <div className="target-header__main">
          <h1>{target?.name || 'Loading target...'}</h1>
          <p>{target?.disease || 'Target context is loading from the backend.'}</p>
          <div className="target-header__ids">
            <Badge variant="neutral" className="target-header__id-badge">
              UniProt: {target?.uniprot_id || '-'}
            </Badge>
            <Badge variant="neutral" className="target-header__id-badge">
              ChEMBL: {target?.chembl_id || '-'}
            </Badge>
          </div>
        </div>

        <div className="target-header__score">
          <strong style={{ color: target ? getDruggabilityColor(target.druggability_score ?? 0) : 'var(--text)' }}>
            {target?.druggability_score?.toFixed?.(2) ?? '-'}
          </strong>
          <span>Druggability Score</span>
          <span>out of 1.0</span>
        </div>
      </section>

      <Divider className="target-divider" />

      <section className="target-stats">
        <div className="target-stat">
          <strong>{isLoading ? <Skeleton width={60} height={20} /> : target?.known_inhibitors ?? '-'}</strong>
          <span>Known Inhibitors</span>
        </div>
        <div className="target-stat__divider" />
        <div className="target-stat">
          <strong>{isLoading ? <Skeleton width={60} height={20} /> : molecules.length}</strong>
          <span>Molecules Generated</span>
        </div>
        <div className="target-stat__divider" />
        <div className="target-stat">
          <strong>{isLoading ? <Skeleton width={60} height={20} /> : bestDockingScore ?? '-'}</strong>
          <span>Best Docking Score</span>
        </div>
      </section>

      <section className="target-section">
        <p className="target-section__label">Biological Context</p>
        <Card className="target-context-card">
          {isLoading ? (
            <div className="target-skeleton">
              <Skeleton width="100%" height={16} borderRadius="3px" />
              <Skeleton width="90%" height={16} borderRadius="3px" />
              <Skeleton width="70%" height={16} borderRadius="3px" />
            </div>
          ) : (
            <p>{biologicalContext || 'No target summary is available for this record yet.'}</p>
          )}
        </Card>
      </section>

      <section className="target-section">
        <p className="target-section__label">Discovery Pipeline</p>
        <Card className="target-pipeline-card">
          {pipeline.status === 'failed' ? (
            <div className="target-pipeline__error">
              <p>
                Pipeline failed: {pipeline.error || 'No molecules generated. Try a different target or check ChEMBL data availability.'}
              </p>
              <Button size="md" variant="secondary" onClick={handlePipelineReset}>
                Try Again
              </Button>
            </div>
          ) : null}

          {!pipeline.isRunning && (!pipeline.isComplete || !pipelineCompletedThisSession) && !pipelineResult ? (
            <div className="target-pipeline__empty">
              <p>No pipeline run for this target yet.</p>
              <Button size="md" onClick={handleRunPipeline} disabled={pipeline.isRunning}>
                Run Full Pipeline
              </Button>
            </div>
          ) : null}

          {pipeline.isRunning ? <PipelineProgress steps={pipeline.steps} isComplete={pipeline.isComplete} /> : null}

          {(pipeline.isComplete && pipelineCompletedThisSession && pipelineResult) && !pipeline.isRunning ? (
            <>
              <div className="target-pipeline__rows">
                {completedSteps.map((step, index) => (
                  <div
                    key={step.name}
                    className={`target-pipeline__row ${index === completedSteps.length - 1 ? 'target-pipeline__row--last' : ''}`}
                  >
                    <span>{step.name}</span>
                    <p>{step.detail}</p>
                    <strong>Complete</strong>
                  </div>
                ))}
              </div>
              <div className="target-pipeline__footer">
                <button type="button" onClick={() => navigate(`/molecules/${targetId}`)}>
                  View molecules -&gt;
                </button>
                <button
                  type="button"
                  onClick={() => navigate(`/report/${targetId}`, { state: { moleculeIds: pipelineMoleculeIds } })}
                >
                  Download report -&gt;
                </button>
              </div>
            </>
          ) : null}
        </Card>
      </section>
    </PageWrapper>
  )
}

export default TargetPage
