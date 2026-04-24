import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Skeleton from '../components/ui/Skeleton'
import ErrorState from '../components/ErrorState'
import { useToast } from '../hooks/useToast'
import { useTarget } from '../hooks/useTarget'
import { useMolecules } from '../hooks/useMolecules'
import { getDockingResults, optimizeMolecule } from '../services/api'
import MoleculeCard from '../components/MoleculeCard'

function MoleculesPage() {
  const { targetId } = useParams()
  const { showToast } = useToast()
  const { target, loading: targetLoading, error: targetError, refetch: refetchTarget } = useTarget(targetId)
  const moleculesState = useMolecules(targetId)
  const { molecules, loading: moleculesLoading, error: moleculesError, refetch, lipinskiPass, optimized } = moleculesState
  const [dockingResults, setDockingResults] = useState([])
  const [dockingError, setDockingError] = useState('')
  const [activeFilter, setActiveFilter] = useState('all')
  const [sortBy, setSortBy] = useState('docking')
  const [optimizingId, setOptimizingId] = useState('')

  useEffect(() => {
    let mounted = true

    getDockingResults(targetId)
      .then((results) => {
        if (mounted) {
          setDockingResults(results)
          setDockingError('')
        }
      })
      .catch((error) => {
        if (mounted) {
          setDockingResults([])
          setDockingError(error.message)
        }
      })

    return () => {
      mounted = false
    }
  }, [targetId])

  const dockingById = useMemo(
    () =>
      dockingResults.reduce((accumulator, result) => {
        accumulator[result.molecule_id] = result.docking_score
        return accumulator
      }, {}),
    [dockingResults],
  )

  const docked = useMemo(
    () =>
      molecules.filter(
        (molecule) =>
          dockingById[molecule.id] !== undefined ||
          (molecule.docking_score !== null && molecule.docking_score !== undefined),
      ),
    [dockingById, molecules],
  )

  const filterTabs = useMemo(
    () => [
      { key: 'all', label: `All (${molecules.length})`, items: molecules },
      { key: 'lipinski', label: `Lipinski Pass (${lipinskiPass.length})`, items: lipinskiPass },
      { key: 'docked', label: `Docked (${docked.length})`, items: docked },
      { key: 'optimized', label: `Optimized (${optimized.length})`, items: optimized },
    ],
    [docked, lipinskiPass, molecules, optimized],
  )

  const visibleMolecules = useMemo(() => {
    const selected = filterTabs.find((tab) => tab.key === activeFilter)?.items || molecules
    const scored = [...selected]

    scored.sort((left, right) => {
      if (sortBy === 'docking') {
        const leftScore = dockingById[left.id] ?? left.docking_score ?? Number.POSITIVE_INFINITY
        const rightScore = dockingById[right.id] ?? right.docking_score ?? Number.POSITIVE_INFINITY
        return leftScore - rightScore
      }

      if (sortBy === 'sas') {
        return (left.sas_score ?? Number.POSITIVE_INFINITY) - (right.sas_score ?? Number.POSITIVE_INFINITY)
      }

      if (sortBy === 'admet') {
        return admetGreenCount(right.admet_scores) - admetGreenCount(left.admet_scores)
      }

      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    })

    return scored
  }, [activeFilter, dockingById, filterTabs, molecules, sortBy])

  const isLoading = targetLoading || moleculesLoading
  const pageError = targetError || moleculesError || dockingError

  async function retryLoad() {
    await Promise.all([
      refetchTarget(),
      refetch(),
      getDockingResults(targetId).then((results) => {
        setDockingResults(results)
        setDockingError('')
      }),
    ])
  }

  async function handleOptimize(molecule) {
    if (molecule.is_optimized) {
      return
    }

    setOptimizingId(molecule.id)

    try {
      await optimizeMolecule(molecule.id)
      await refetch()
      showToast('Compound optimized.', 'success')
    } catch (error) {
      showToast(error.message, 'error')
    } finally {
      setOptimizingId('')
    }
  }

  if (pageError && !isLoading) {
    return (
      <PageWrapper className="molecules-page">
        <ErrorState
          title="Could not load molecules"
          message={pageError}
          retryFn={retryLoad}
        />
      </PageWrapper>
    )
  }

  return (
    <PageWrapper className="molecules-page">
      <div className="molecules-page__header">
        <div>
          <div className="molecules-breadcrumb">
            <Link to="/search">Search</Link>
            <span>/</span>
            <span>{target?.name || targetId}</span>
            <span>/</span>
            <span>Molecules</span>
          </div>
          <h1>Molecular Candidates</h1>
          <p>
            {molecules.length} molecules generated - {lipinskiPass.length} pass Lipinski filters
          </p>
        </div>
      </div>

      <div className="molecules-toolbar">
        <div className="molecules-toolbar__tabs">
          {filterTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              className={`molecules-tab ${activeFilter === tab.key ? 'molecules-tab--active' : ''}`}
              onClick={() => setActiveFilter(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <select
          className="molecules-sort"
          value={sortBy}
          onChange={(event) => setSortBy(event.target.value)}
        >
          <option value="docking">Best Docking Score</option>
          <option value="sas">Best SAS Score</option>
          <option value="admet">Best ADMET</option>
          <option value="newest">Newest</option>
        </select>
      </div>

      <div className="molecule-grid">
        {isLoading
          ? Array.from({ length: 6 }).map((_, index) => (
              <Card key={`ghost-${index}`} className="molecule-card molecule-card--ghost">
                <div className="molecule-card__header">
                  <Skeleton width={88} height={12} />
                </div>
                <div className="molecule-card__structure">
                  <Skeleton width="80%" height={56} />
                </div>
                <div className="molecule-card__metrics">
                  {Array.from({ length: 4 }).map((__, metricIndex) => (
                    <div key={metricIndex}>
                      <Skeleton width={40} height={10} />
                      <Skeleton width={76} height={14} />
                    </div>
                  ))}
                </div>
                <div className="molecule-card__lipinski">
                  <Skeleton width={120} height={12} />
                  <Skeleton width={48} height={20} />
                </div>
                <div className="molecule-card__actions">
                  <Skeleton width={96} height={28} />
                  <Skeleton width={78} height={28} />
                </div>
              </Card>
            ))
          : visibleMolecules.map((molecule, index) => (
              <MoleculeCard
                key={molecule.id}
                molecule={molecule}
                index={index}
                dockingScore={dockingById[molecule.id]}
                isOptimizing={optimizingId === molecule.id}
                onOptimize={handleOptimize}
              />
            ))}
      </div>

      {!isLoading && !molecules.length ? (
        <div className="empty-state-card">
          <p>No molecules have been generated for this target yet.</p>
          <Link to={`/target/${targetId}`}>
            <Button size="md">Run Pipeline</Button>
          </Link>
        </div>
      ) : null}

      {!isLoading && molecules.length > 0 && !visibleMolecules.length ? (
        <div className="empty-state-card">
          <p>No molecules match this filter.</p>
          {activeFilter === 'docked' ? (
            <p>
              Run the pipeline to generate docking scores. <Link to={`/target/${targetId}`}>Run Pipeline</Link>
            </p>
          ) : null}
        </div>
      ) : null}
    </PageWrapper>
  )
}

function admetGreenCount(admetScores) {
  if (!admetScores) {
    return 0
  }

  return [
    admetScores.bbbp_traffic === 'green',
    admetScores.hepatotoxicity_traffic === 'green',
    admetScores.herg_risk === false,
    admetScores.bioavailability_traffic === 'green',
  ].filter(Boolean).length
}

export default MoleculesPage
