import { useCallback, useEffect, useMemo, useState } from 'react'
import { getMolecules } from '../services/api'

export function useMolecules(targetId) {
  const [molecules, setMolecules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refetch = useCallback(async () => {
    if (!targetId) {
      setMolecules([])
      setLoading(false)
      setError('')
      return []
    }

    setLoading(true)
    setError('')

    try {
      const nextMolecules = await getMolecules(targetId)
      setMolecules(nextMolecules)
      return nextMolecules
    } catch (requestError) {
      setMolecules([])
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

    getMolecules(targetId)
      .then((nextMolecules) => {
        if (!cancelled) {
          setMolecules(nextMolecules)
          setError('')
        }
      })
      .catch((requestError) => {
        if (!cancelled) {
          setMolecules([])
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

  const lipinskiPass = useMemo(
    () => molecules.filter((molecule) => molecule.lipinski_pass),
    [molecules],
  )

  const docked = useMemo(
    () => molecules.filter((molecule) => molecule.docking_score !== null && molecule.docking_score !== undefined),
    [molecules],
  )

  const optimized = useMemo(
    () => molecules.filter((molecule) => molecule.is_optimized),
    [molecules],
  )

  return {
    molecules,
    loading,
    error,
    refetch,
    lipinskiPass,
    docked,
    optimized,
  }
}
