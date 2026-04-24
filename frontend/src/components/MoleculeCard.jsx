import { useEffect, useMemo, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import Button from './ui/Button'
import Badge from './ui/Badge'
import Divider from './ui/Divider'
import Spinner from './ui/Spinner'
import Skeleton from './ui/Skeleton'
import { getMoleculeImage, predictAdmet } from '../services/api'
import { useToast } from '../hooks/useToast'

function formatMetric(value, suffix = '') {
  if (value === null || value === undefined || value === '') {
    return `-${suffix ? ` ${suffix}` : ''}`.trim()
  }

  return `${value}${suffix ? ` ${suffix}` : ''}`
}

function getDockingColor(score) {
  if (score === null || score === undefined) {
    return 'var(--text)'
  }
  if (score < -7) {
    return 'var(--green)'
  }
  if (score <= -5) {
    return 'var(--yellow)'
  }
  return 'var(--red)'
}

function getSasColor(score) {
  if (score === null || score === undefined) {
    return 'var(--text)'
  }
  if (score < 3) {
    return 'var(--green)'
  }
  if (score <= 6) {
    return 'var(--yellow)'
  }
  return 'var(--red)'
}

function getScoreVariant(value, direction = 'higher-better') {
  if (value === null || value === undefined) {
    return 'neutral'
  }

  if (direction === 'lower-better') {
    if (value < 0.35) return 'success'
    if (value <= 0.65) return 'warning'
    return 'danger'
  }

  if (value > 0.7) return 'success'
  if (value >= 0.4) return 'warning'
  return 'danger'
}

function getPanelRows(admetScores) {
  return [
    {
      label: 'BBB Penetration',
      value: admetScores?.bbbp_score ?? admetScores?.bbbp ?? null,
      traffic: admetScores?.bbbp_traffic,
      direction: 'higher-better',
    },
    {
      label: 'Hepatotoxicity',
      value: admetScores?.hepatotoxicity_score ?? admetScores?.hepatotoxicity ?? null,
      traffic: admetScores?.hepatotoxicity_traffic,
      direction: 'lower-better',
    },
    {
      label: 'hERG Cardiotoxicity',
      value: admetScores?.herg_confidence ?? admetScores?.herg_inhibition ?? null,
      traffic: admetScores?.herg_risk ? 'red' : admetScores?.herg_risk === false ? 'green' : undefined,
      direction: 'lower-better',
    },
    {
      label: 'Bioavailability',
      value: admetScores?.bioavailability_score ?? admetScores?.oral_bioavailability ?? null,
      traffic: admetScores?.bioavailability_traffic,
      direction: 'higher-better',
    },
  ]
}

function MoleculeCard({ molecule, index, dockingScore, isOptimizing = false, onOptimize }) {
  const { showToast } = useToast()
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const [imgUrl, setImgUrl] = useState(null)
  const [admetScores, setAdmetScores] = useState(molecule.admet_scores || null)
  const [isAdmetLoading, setIsAdmetLoading] = useState(false)
  const resolvedAdmetScores = admetScores || molecule.admet_scores || null
  const admetRows = useMemo(() => getPanelRows(resolvedAdmetScores), [resolvedAdmetScores])
  const MotionDiv = motion.div
  const MotionAside = motion.aside

  useEffect(() => {
    let mounted = true

    getMoleculeImage(molecule.id).then((result) => {
      if (mounted) {
        setImgUrl(result)
      }
    })

    return () => {
      mounted = false
    }
  }, [molecule.id])

  async function handleOpenPanel() {
    setIsPanelOpen(true)

    if (resolvedAdmetScores || isAdmetLoading) {
      return
    }

    setIsAdmetLoading(true)
    try {
      const results = await predictAdmet([molecule.id])
      setAdmetScores(results[0]?.admet || null)
    } catch (error) {
      showToast(error.message, 'error')
    } finally {
      setIsAdmetLoading(false)
    }
  }

  return (
    <>
      <article className="molecule-card">
        <div className="molecule-card__header">
          <span className="molecule-card__eyebrow">Compound {String(index + 1).padStart(3, '0')}</span>
          {molecule.is_optimized ? <Badge variant="info">OPTIMIZED LEAD</Badge> : null}
        </div>

        <div className="molecule-card__structure">
          {imgUrl ? (
            <img src={imgUrl} alt={`Compound ${index + 1}`} />
          ) : (
            <p>{molecule.smiles}</p>
          )}
        </div>

        <div className="molecule-card__metrics">
          <div>
            <span>MW</span>
            <strong>{formatMetric(molecule.molecular_weight, 'Da')}</strong>
          </div>
          <div>
            <span>LogP</span>
            <strong>{formatMetric(molecule.logp)}</strong>
          </div>
          <div>
            <span>SAS</span>
            <strong style={{ color: getSasColor(molecule.sas_score) }}>{formatMetric(molecule.sas_score)}</strong>
          </div>
          <div>
            <span>Docking</span>
            <strong style={{ color: getDockingColor(dockingScore ?? molecule.docking_score) }}>
              {(dockingScore ?? molecule.docking_score) !== null &&
              (dockingScore ?? molecule.docking_score) !== undefined
                ? `${dockingScore ?? molecule.docking_score} kcal/mol`
                : '-'}
            </strong>
          </div>
        </div>

        <div className="molecule-card__lipinski">
          <span>Lipinski Rule of Five</span>
          <Badge variant={molecule.lipinski_pass ? 'success' : 'danger'}>
            {molecule.lipinski_pass ? 'PASS' : 'FAIL'}
          </Badge>
        </div>

        <div className="molecule-card__actions">
          <Button size="sm" variant="ghost" onClick={handleOpenPanel}>
            ADMET Details
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onOptimize?.(molecule)}
            disabled={isOptimizing}
            loading={isOptimizing}
          >
            {isOptimizing ? 'Optimizing...' : molecule.is_optimized ? 'View Optimization' : 'Optimize'}
          </Button>
        </div>
      </article>

      <AnimatePresence>
        {isPanelOpen ? (
          <>
            <MotionDiv
              className="admet-panel-backdrop admet-panel-backdrop--open"
              onClick={() => setIsPanelOpen(false)}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            />
            <MotionAside
              className="admet-panel admet-panel--open"
              initial={{ x: 320 }}
              animate={{ x: 0 }}
              exit={{ x: 320 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
            >
              <div className="admet-panel__header">
                <div>
                  <h3>ADMET Profile</h3>
                  <p>Compound {String(index + 1).padStart(3, '0')}</p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => setIsPanelOpen(false)}>
                  x
                </Button>
              </div>

              <div className="admet-panel__body">
                {resolvedAdmetScores ? (
                  <>
                    <div className="admet-panel__rows">
                      {admetRows.map((row, rowIndex) => {
                        const numericValue =
                          row.value === null || row.value === undefined ? null : Number(row.value)
                        const clampedValue =
                          numericValue === null ? 0 : Math.max(0, Math.min(100, numericValue * 100))
                        const variant = row.traffic
                          ? row.traffic === 'green'
                            ? 'success'
                            : row.traffic === 'yellow'
                              ? 'warning'
                              : row.traffic === 'red'
                                ? 'danger'
                                : 'neutral'
                          : getScoreVariant(numericValue, row.direction)

                        return (
                          <div key={row.label} className="admet-panel__row">
                            <p>{row.label}</p>
                            <div className="admet-panel__track">
                              <span
                                className={`admet-panel__fill admet-panel__fill--${variant}`}
                                style={{
                                  width: `${clampedValue}%`,
                                  transitionDelay: `${rowIndex * 50}ms`,
                                }}
                              />
                            </div>
                            <div className="admet-panel__meta">
                              <span>{numericValue === null ? '-' : numericValue.toFixed(2)}</span>
                              <Badge variant={variant}>
                                {row.traffic ? row.traffic.toUpperCase() : variant.toUpperCase()}
                              </Badge>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <Divider />
                  </>
                ) : isAdmetLoading ? (
                  <>
                    <div className="admet-panel__rows">
                      {Array.from({ length: 4 }).map((_, rowIndex) => (
                        <div key={rowIndex} className="admet-panel__row">
                          <Skeleton width="58%" height={14} />
                          <Skeleton width="100%" height={4} />
                          <div className="admet-panel__meta">
                            <Skeleton width={32} height={12} />
                            <Skeleton width={56} height={20} />
                          </div>
                        </div>
                      ))}
                    </div>
                    <Divider />
                  </>
                ) : (
                  <>
                    <div className="admet-panel__loading">
                      <Spinner size={16} />
                      <span>Fetching ADMET scores...</span>
                    </div>
                    <Divider />
                  </>
                )}
              </div>
            </MotionAside>
          </>
        ) : null}
      </AnimatePresence>
    </>
  )
}

export default MoleculeCard
