import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Divider from '../components/ui/Divider'
import Tooltip from '../components/ui/Tooltip'
import Skeleton from '../components/ui/Skeleton'
import ErrorState from '../components/ErrorState'
import { getPipelineSessionResult } from '../hooks/usePipeline'
import { useToast } from '../hooks/useToast'
import {
  downloadReport,
  generateReport,
  getDockingResults,
  getMoleculesBatch,
  getMoleculeRationale,
  getMolecules,
  getReportBlobSize,
  getTarget,
} from '../services/api'

function ReportPage() {
  const { targetId } = useParams()
  const location = useLocation()
  const { showToast } = useToast()
  const spotlightRef = useRef(null)
  const hasGeneratedRef = useRef(false)
  const [target, setTarget] = useState(null)
  const [molecules, setMolecules] = useState([])
  const [dockingResults, setDockingResults] = useState([])
  const [reportMeta, setReportMeta] = useState({
    reportId: '',
    pdfUrl: '',
    sizeKb: null,
    generatedAt: '',
  })
  const [rationale, setRationale] = useState('')
  const [isRationaleLoading, setIsRationaleLoading] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [isDownloading, setIsDownloading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const sessionPipelineResult = getPipelineSessionResult(targetId)
  const latestRunMoleculeIds = useMemo(() => {
    const locationIds = location.state?.moleculeIds
    if (Array.isArray(locationIds) && locationIds.length) {
      return locationIds.filter(Boolean)
    }

    return sessionPipelineResult?.molecules?.map((molecule) => molecule.id).filter(Boolean) || []
  }, [location.state, sessionPipelineResult])

  useEffect(() => {
    hasGeneratedRef.current = false
  }, [targetId])

  useEffect(() => {
    if (hasGeneratedRef.current) {
      return
    }
    hasGeneratedRef.current = true

    let mounted = true

    async function loadReport() {
      try {
        const [nextTarget, nextDockingResults] = await Promise.all([
          getTarget(targetId),
          getDockingResults(targetId),
        ])

        if (!mounted) {
          return
        }

        let effectiveMoleculeIds = latestRunMoleculeIds
        if (!effectiveMoleculeIds.length) {
          const fallbackMolecules = await getMolecules(targetId)
          effectiveMoleculeIds = fallbackMolecules.map((molecule) => molecule.id).filter(Boolean)
        }

        if (!effectiveMoleculeIds.length) {
          throw new Error('No molecules available for this report.')
        }

        const scopedMolecules = await getMoleculesBatch(effectiveMoleculeIds)
        if (!scopedMolecules.length) {
          throw new Error('Molecule data unavailable for this run. Please rerun the pipeline.')
        }
        const scopedDockingResults = nextDockingResults.filter((result) => effectiveMoleculeIds.includes(result.molecule_id))
        const report = await generateReport(targetId, effectiveMoleculeIds)

        let sizeKb = null

        try {
          const size = await getReportBlobSize(report.report_id, effectiveMoleculeIds)
          sizeKb = Math.round(size / 1024)
        } catch {
          sizeKb = null
        }

        if (!mounted) {
          return
        }

        setTarget(nextTarget)
        setMolecules(scopedMolecules)
        setDockingResults(scopedDockingResults)
        setReportMeta({
          reportId: report.report_id,
          pdfUrl: report.pdf_url,
          sizeKb,
          generatedAt: new Date().toISOString(),
        })
      } catch (error) {
        if (mounted) {
          setErrorMessage(error.message)
          showToast(error.message, 'error')
        }
      } finally {
        if (mounted) {
          setIsLoading(false)
        }
      }
    }

    loadReport()

    return () => {
      mounted = false
    }
  }, [latestRunMoleculeIds, showToast, targetId])

  const runMolecules = molecules

  const rankedLeads = useMemo(() => {
    const admetById = runMolecules.reduce((accumulator, molecule) => {
      accumulator[molecule.id] = molecule.admet_scores
      return accumulator
    }, {})

    return dockingResults
      .map((result) => {
        const matchingMolecule = runMolecules.find((molecule) => molecule.id === result.molecule_id)
        return {
          id: matchingMolecule?.id ?? result.molecule_id,
          ...matchingMolecule,
          ...result,
          admet_scores: matchingMolecule?.admet_scores || admetById[result.molecule_id] || null,
        }
      })
      .filter((lead) => Boolean(lead?.id))
      .slice(0, 5)
  }, [dockingResults, runMolecules])

  const topLead = rankedLeads[0] || null
  const optimizedLead = runMolecules.find((molecule) => molecule.is_optimized) || null
  const originalLead =
    (optimizedLead && runMolecules.find((molecule) => molecule.id !== optimizedLead.id && !molecule.is_optimized)) ||
    topLead
  const lipinskiPassRate = runMolecules.length
    ? Math.round((runMolecules.filter((molecule) => molecule.lipinski_pass).length / runMolecules.length) * 100)
    : 0
  const hasMockDocking = runMolecules.some((molecule) => molecule.admet_scores?._docking?.is_mock)

  useEffect(() => {
    if (!topLead?.id || !spotlightRef.current) {
      return undefined
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0]
        if (!entry?.isIntersecting || rationale || isRationaleLoading) {
          return
        }

        setIsRationaleLoading(true)
        getMoleculeRationale(topLead.id)
          .then((response) => {
            setRationale(response.rationale)
          })
          .catch((error) => {
            setRationale(error.message)
          })
          .finally(() => {
            setIsRationaleLoading(false)
          })
      },
      { threshold: 0.2 },
    )

    observer.observe(spotlightRef.current)
    return () => observer.disconnect()
  }, [isRationaleLoading, rationale, topLead])

  useEffect(() => {
    if (!optimizedLead?.id || (Array.isArray(optimizedLead.changes) && optimizedLead.changes.length > 0)) {
      return
    }

    let cancelled = false

    async function loadOptimizationChanges() {
      try {
        const response = await fetch(
          `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/api/molecules/${optimizedLead.id}/optimization`,
        )

        if (!response.ok) {
          if (response.status === 404) {
            return
          }
          throw new Error('Could not load optimization changes.')
        }

        const payload = await response.json()
        if (cancelled || !Array.isArray(payload?.changes)) {
          return
        }

        setMolecules((current) =>
          current.map((molecule) =>
            molecule.id === optimizedLead.id
              ? { ...molecule, changes: payload.changes, is_optimized: payload.is_optimized ?? molecule.is_optimized }
              : molecule,
          ),
        )
      } catch (error) {
        if (!cancelled) {
          console.warn('Optimization changes fetch failed:', error.message)
        }
      }
    }

    loadOptimizationChanges()

    return () => {
      cancelled = true
    }
  }, [optimizedLead])

  async function handleDownload() {
    if (!reportMeta.reportId || isDownloading) {
      return
    }

    const moleculeIds = runMolecules.map((molecule) => molecule.id).filter(Boolean)
    if (!moleculeIds.length) {
      showToast('Cannot download report: no molecules selected', 'error')
      return
    }

    setIsDownloading(true)
    try {
      await downloadReport(
        reportMeta.reportId,
        target?.name || 'MolGenix',
        moleculeIds,
      )
      showToast('Report downloaded.', 'success')
    } catch (error) {
      showToast(error.message, 'error')
    } finally {
      setIsDownloading(false)
    }
  }

  if (errorMessage && !isLoading) {
    return (
      <PageWrapper className="report-page">
        <ErrorState
          title="Could not load report"
          message={errorMessage}
          retryFn={() => window.location.reload()}
        />
      </PageWrapper>
    )
  }

  return (
    <PageWrapper className="report-page">
      <div className="report-breadcrumb">
        <Link to="/search">Search</Link>
        <span>/</span>
        <span>{target?.name || targetId}</span>
        <span>/</span>
        <span>Report</span>
      </div>

      <div className="report-header">
        <div>
          <h1>Discovery Report</h1>
          <p>{target?.name || 'Loading target report...'}</p>
          <span>Generated {reportMeta.generatedAt ? formatDateTime(reportMeta.generatedAt) : '-'}</span>
        </div>
        <div className="report-header__actions">
          <Button
            size="md"
            loading={isDownloading}
            disabled={isLoading || !reportMeta.reportId}
            onClick={handleDownload}
          >
            Download PDF
          </Button>
          <span>{reportMeta.sizeKb ? `${reportMeta.sizeKb} KB` : '-'}</span>
        </div>
      </div>

      <Divider className="report-divider" />

      <section className="report-stats">
        <div className="report-stat">
          <strong>{runMolecules.length}</strong>
          <span>Candidates Generated</span>
        </div>
        <div className="report-stat__divider" />
        <div className="report-stat">
          <strong>{lipinskiPassRate}%</strong>
          <span>Lipinski Pass Rate</span>
        </div>
        <div className="report-stat__divider" />
        <div className="report-stat">
          <strong>{topLead?.docking_score !== undefined && topLead?.docking_score !== null ? `${topLead.docking_score} kcal/mol` : '-'}</strong>
          <span>Best Docking Score</span>
        </div>
        <div className="report-stat__divider" />
        <div className="report-stat">
          <strong>{countGreenFlags(topLead?.admet_scores)}/4</strong>
          <span>ADMET Green Flags</span>
        </div>
      </section>

      <section className="report-section">
        <p className="report-section__label">Top Ranked Molecular Leads</p>
        <p className="report-rationale report-rationale--visible">
          This table shows the highest-ranked compounds from the generated candidate pool, not every molecule produced during the run.
        </p>
        <div className="report-table-wrap">
          <table className="report-table">
            <thead>
              <tr>
                <th>Rank</th>
                <th>Compound</th>
                <th>SMILES</th>
                <th>SAS</th>
                <th>Docking</th>
                <th>ADMET</th>
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 5 }).map((_, index) => (
                    <tr key={`report-skeleton-${index}`}>
                      <td><Skeleton width={24} height={12} /></td>
                      <td><Skeleton width={96} height={12} /></td>
                      <td><Skeleton width={140} height={12} /></td>
                      <td><Skeleton width={40} height={12} /></td>
                      <td><Skeleton width={60} height={12} /></td>
                      <td><Skeleton width={56} height={12} /></td>
                    </tr>
                  ))
                : rankedLeads.map((lead, index) => (
                    <tr key={lead.id}>
                      <td className="report-rank">#{index + 1}</td>
                      <td>
                        <span className="report-compound-name">Compound {index + 1}</span>
                        {lead.is_optimized ? <span className="report-compound-tag">(Optimized)</span> : null}
                      </td>
                      <td>
                        <Tooltip content={lead.smiles}>
                          <span className="report-smiles">{truncateSmiles(lead.smiles)}</span>
                        </Tooltip>
                      </td>
                      <td style={{ color: sasColor(lead.sas_score) }}>{lead.sas_score ?? '-'}</td>
                      <td className="report-docking" style={{ color: dockingColor(lead.docking_score) }}>
                        {lead.docking_score ?? '-'}
                      </td>
                      <td>
                        <div className="report-admet-squares">
                          {admetSquares(lead.admet_scores).map((square, squareIndex) => (
                            <span
                              key={`${lead.id}-${squareIndex}`}
                              className={`report-admet-square report-admet-square--${square}`}
                            />
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="report-section" ref={spotlightRef}>
        <p className="report-section__label">Lead Compound</p>
        <Card className="report-spotlight-card">
          <div className="report-spotlight__structure">
            <div className="report-spotlight__image">
              <span>{topLead?.smiles || 'No structure available'}</span>
            </div>
            <p>{topLead?.smiles || '-'}</p>
          </div>
          <div className="report-spotlight__details">
            <p className="report-sub-label">ADMET Profile</p>
            <div className="report-spotlight__admet">
              {leadProfileRows(topLead?.admet_scores).map((row) => (
                <div key={row.label} className="report-profile-row">
                  <span>{row.label}</span>
                  <div className="report-profile-row__track">
                    <span
                      className={`report-profile-row__fill report-profile-row__fill--${row.variant}`}
                      style={{ width: `${row.width}%` }}
                    />
                  </div>
                  <Badge variant={row.variant}>{row.badge}</Badge>
                </div>
              ))}
            </div>

            <Divider />

            <p className="report-sub-label">Docking Performance</p>
            <div className="report-docking-block">
              <div>
                <span>Reference compound</span>
                <strong>-6.2 kcal/mol</strong>
              </div>
              <div className="report-docking-block__current">
                <span>This compound</span>
                <strong>{topLead?.docking_score ?? '-'} kcal/mol</strong>
              </div>
              <p>{dockingDeltaText(topLead?.docking_score)}</p>
            </div>

            <Divider />

            <p className="report-sub-label">Lead Rationale</p>
            {isRationaleLoading ? (
              <div className="report-rationale report-rationale--loading">
                <Skeleton width="100%" height={16} />
                <Skeleton width="92%" height={16} />
                <Skeleton width="78%" height={16} />
              </div>
            ) : (
              <p className={`report-rationale ${rationale ? 'report-rationale--visible' : ''}`}>
                {rationale || 'Scroll to load the lead rationale.'}
              </p>
            )}
          </div>
        </Card>
      </section>

      {optimizedLead ? (
        <section className="report-section">
          <p className="report-section__label">Lead Optimization</p>
          <div className="report-optimization">
            <Card className="report-optimization__card">
              <p className="report-sub-label">Original</p>
              <p className="report-optimization__smiles">{originalLead?.smiles || '-'}</p>
              <div className="report-optimization__metrics">
                <div><span>SAS</span><strong>{originalLead?.sas_score ?? '-'}</strong></div>
                <div><span>MW</span><strong>{originalLead?.molecular_weight ?? '-'}</strong></div>
                <div><span>Bioavailability</span><strong>{scoreValue(originalLead?.admet_scores?.bioavailability_score)}</strong></div>
                <div><span>Docking</span><strong>{originalLead?.docking_score ?? '-'}</strong></div>
              </div>
            </Card>

            <div className="report-optimization__changes">
              <span>-&gt;</span>
              {(optimizedLead?.changes || ['Lead refinement persisted by backend optimization workflow']).map((change) => (
                <p key={change}>{change}</p>
              ))}
            </div>

            <Card className="report-optimization__card report-optimization__card--accent">
              <p className="report-sub-label report-sub-label--accent">Optimized</p>
              <p className="report-optimization__smiles">{optimizedLead.smiles}</p>
              <div className="report-optimization__metrics">
                <div>
                  <span>SAS</span>
                  <strong>{deltaMetric(originalLead?.sas_score, optimizedLead.sas_score, true)}</strong>
                </div>
                <div>
                  <span>MW</span>
                  <strong>{optimizedLead.molecular_weight ?? '-'}</strong>
                </div>
                <div>
                  <span>Bioavailability</span>
                  <strong>{deltaMetric(originalLead?.admet_scores?.bioavailability_score, optimizedLead.admet_scores?.bioavailability_score, false)}</strong>
                </div>
                <div>
                  <span>Docking</span>
                  <strong>{deltaMetric(originalLead?.docking_score, optimizedLead.docking_score, false)}</strong>
                </div>
              </div>
            </Card>
          </div>
        </section>
      ) : null}

      <section className="report-section">
        <p className="report-section__label">Methodology</p>
        <Card className="report-methodology-card">
          {[
            ['RDKit 2024.03', 'Fragment-based molecule generation, Lipinski filtering, SAS scoring'],
            ['DeepChem 2.7', 'Pretrained BBBP and Tox21 models for ADMET prediction'],
            ['AutoDock Vina 1.2', 'Empirical force-field molecular docking simulation'],
            ['Gemini 1.5 Flash', 'Natural language target parsing and summary generation'],
          ].map(([tool, description]) => (
            <div key={tool} className="report-methodology-row">
              <strong>{tool}</strong>
              <p>{description}</p>
            </div>
          ))}
          {hasMockDocking ? (
            <p className="report-methodology-footnote">
              * Docking scores marked (est.) were computed using an RDKit descriptor model. AutoDock Vina was not available in this environment.
            </p>
          ) : null}
        </Card>
      </section>

      <section className="report-cta">
        <h2>Export this report</h2>
        <p>Includes the top-ranked compounds, their scores, structures, and the generated target review.</p>
        <Button size="lg" loading={isDownloading} onClick={handleDownload}>
          Download PDF
        </Button>
      </section>
    </PageWrapper>
  )
}

function truncateSmiles(smiles) {
  if (!smiles) return '-'
  return smiles.length > 22 ? `${smiles.slice(0, 22)}...` : smiles
}

function sasColor(score) {
  if (score === null || score === undefined) return 'var(--text)'
  if (score < 3) return 'var(--green)'
  if (score <= 6) return 'var(--yellow)'
  return 'var(--red)'
}

function dockingColor(score) {
  if (score === null || score === undefined) return 'var(--text)'
  if (score < -7) return 'var(--green)'
  if (score <= -5) return 'var(--yellow)'
  return 'var(--red)'
}

function admetSquares(admetScores) {
  return [
    admetScores?.bbbp_traffic === 'green' ? 'success' : admetScores?.bbbp_traffic === 'yellow' ? 'warning' : admetScores?.bbbp_traffic === 'red' ? 'danger' : 'neutral',
    admetScores?.hepatotoxicity_traffic === 'green' ? 'success' : admetScores?.hepatotoxicity_traffic === 'yellow' ? 'warning' : admetScores?.hepatotoxicity_traffic === 'red' ? 'danger' : 'neutral',
    admetScores?.herg_risk === false ? 'success' : admetScores?.herg_risk === true ? 'danger' : 'neutral',
    admetScores?.bioavailability_traffic === 'green' ? 'success' : admetScores?.bioavailability_traffic === 'yellow' ? 'warning' : admetScores?.bioavailability_traffic === 'red' ? 'danger' : 'neutral',
  ]
}

function countGreenFlags(admetScores) {
  return admetSquares(admetScores).filter((square) => square === 'success').length
}

function leadProfileRows(admetScores) {
  return [
    makeProfileRow('BBB Penetration', admetScores?.bbbp_score, admetScores?.bbbp_traffic),
    makeProfileRow('Hepatotoxicity', admetScores?.hepatotoxicity_score, admetScores?.hepatotoxicity_traffic),
    makeProfileRow('hERG Cardiotoxicity', admetScores?.herg_confidence, admetScores?.herg_risk === true ? 'red' : admetScores?.herg_risk === false ? 'green' : undefined),
    makeProfileRow('Bioavailability', admetScores?.bioavailability_score, admetScores?.bioavailability_traffic),
  ]
}

function makeProfileRow(label, score, traffic) {
  const numericScore = score === null || score === undefined ? null : Number(score)
  const variant = traffic === 'green' ? 'success' : traffic === 'yellow' ? 'warning' : traffic === 'red' ? 'danger' : 'neutral'

  return {
    label,
    width: numericScore === null ? 0 : Math.max(0, Math.min(100, numericScore * 100)),
    variant,
    badge: traffic ? traffic.toUpperCase() : 'N/A',
  }
}

function dockingDeltaText(score) {
  if (score === null || score === undefined) {
    return 'Docking delta unavailable'
  }
  const delta = Math.abs(score - -6.2).toFixed(1)
  return `+${delta} kcal/mol stronger binding`
}

function deltaMetric(original, optimized, lowerIsBetter) {
  if (optimized === null || optimized === undefined) {
    return '-'
  }
  if (original === null || original === undefined) {
    return `${optimized}`
  }

  const delta = Number(optimized) - Number(original)
  const directionGood = lowerIsBetter ? delta < 0 : delta > 0
  const sign = delta > 0 ? '+' : ''

  return (
    <>
      {optimized}
      <span className={`report-delta ${directionGood ? 'report-delta--good' : ''}`}>
        ({sign}{delta.toFixed(1)})
      </span>
    </>
  )
}

function scoreValue(value) {
  if (value === null || value === undefined) {
    return '-'
  }
  return Number(value).toFixed(2)
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value))
}

export default ReportPage
