import axios from 'axios'

const DEFAULT_API_BASE_URL = 'http://localhost:8000'
const FIVE_MINUTES_MS = 5 * 60 * 1000
const PIPELINE_TIMEOUT_MS = 10 * 60 * 1000
const moleculeImageCache = new Map()

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL,
  timeout: PIPELINE_TIMEOUT_MS,
  headers: {
    'Content-Type': 'application/json',
  },
})

function extractFastApiDetail(detail) {
  if (!detail) {
    return ''
  }

  if (typeof detail === 'string') {
    return detail
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .filter(Boolean)
      .join(', ')
  }

  if (typeof detail === 'object') {
    return detail.message || detail.detail || JSON.stringify(detail)
  }

  return String(detail)
}

export function getApiErrorMessage(error) {
  if (error?.code === 'ECONNABORTED' || /timeout/i.test(error?.message || '')) {
    return 'This request is taking longer than expected. Full pipeline runs can take several minutes.'
  }

  if (!error?.response) {
    return 'Could not connect to the MolGenix backend. Make sure it is running.'
  }

  if (error.response?.status === 404) {
    return 'This resource was not found.'
  }

  if (error.response?.status >= 500) {
    return 'The server encountered an error. Check the backend logs.'
  }

  return (
    extractFastApiDetail(error.response?.data?.detail) ||
    error.message ||
    'An unexpected error occurred'
  )
}

api.interceptors.request.use((config) => {
  if (import.meta.env.DEV) {
    console.log('[API]', (config.method || 'GET').toUpperCase(), config.url)
  }

  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detailMessage = extractFastApiDetail(error.response?.data?.detail)
    const message = detailMessage || getApiErrorMessage(error) || 'An unexpected error occurred'
    const normalizedError = new Error(message)
    normalizedError.status = error.response?.status
    normalizedError.endpoint = error.config?.url
    normalizedError.code = error.code
    normalizedError.response = error.response
    throw normalizedError
  },
)

export function toAbsoluteUrl(path) {
  if (!path) {
    return ''
  }

  if (/^https?:\/\//i.test(path)) {
    return path
  }

  return `${api.defaults.baseURL}${path.startsWith('/') ? path : `/${path}`}`
}

export async function analyzeTarget(query, seedSmiles = null, nMolecules = 10) {
  const response = await api.post('/api/targets/analyze', {
    name: query,
    seed_smiles: seedSmiles,
    n_molecules: nMolecules,
  })

  return response.data
}

export async function getTarget(targetId) {
  const response = await api.get(`/api/targets/${targetId}`)
  return response.data
}

export async function getAllTargets() {
  const response = await api.get('/api/targets/')
  return response.data?.targets || []
}

export async function getMolecules(targetId) {
  const response = await api.get(`/api/molecules/${targetId}`)
  return response.data?.molecules || []
}

export async function getMoleculesBatch(moleculeIds = []) {
  if (!moleculeIds.length) {
    return []
  }

  const query = new URLSearchParams(moleculeIds.map((moleculeId) => ['ids', moleculeId])).toString()
  const response = await api.get(`/api/molecules/batch?${query}`)
  return response.data?.molecules || []
}

export async function getMoleculeImage(moleculeId) {
  if (moleculeImageCache.has(moleculeId)) {
    return moleculeImageCache.get(moleculeId)
  }

  try {
    const response = await api.get(`/api/molecules/${moleculeId}/image`, {
      responseType: 'blob',
    })
    const objectUrl = URL.createObjectURL(response.data)
    moleculeImageCache.set(moleculeId, objectUrl)
    return objectUrl
  } catch {
    return null
  }
}

export async function predictAdmet(moleculeIds) {
  const response = await api.post('/api/admet/predict', {
    molecule_ids: moleculeIds,
  })
  return response.data?.results || []
}

export async function runDocking(moleculeId, pdbFilename) {
  const response = await api.post('/api/docking/run', {
    molecule_id: moleculeId,
    pdb_filename: pdbFilename,
  })
  return response.data
}

export async function getDockingResults(targetId) {
  const response = await api.get(`/api/docking/results/${targetId}`)
  return [...(response.data?.results || [])].sort(
    (left, right) => (left.docking_score ?? Number.POSITIVE_INFINITY) - (right.docking_score ?? Number.POSITIVE_INFINITY),
  )
}

export async function optimizeMolecule(moleculeId) {
  const response = await api.post('/api/optimize/molecule', {
    molecule_id: moleculeId,
  })
  return response.data
}

export async function generateReport(targetId, moleculeIds = []) {
  if (!moleculeIds.length) {
    throw new Error('Cannot generate report: no molecules selected')
  }

  const response = await api.post('/api/reports/generate', {
    target_id: targetId,
    molecule_ids: moleculeIds,
  })
  return response.data
}

export async function downloadReport(reportId, targetName, moleculeIds = []) {
  if (!moleculeIds.length) {
    throw new Error('Cannot download report: no molecules selected')
  }

  const query = `?${new URLSearchParams(moleculeIds.map((moleculeId) => ['molecule_ids', moleculeId])).toString()}`
  const response = await api.get(`/api/reports/${reportId}/download${query}`, {
    responseType: 'blob',
  })
  const url = URL.createObjectURL(response.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${String(targetName || 'molgenix_report').replace(/\s+/g, '_')}_molgenix_report.pdf`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function getReportBlobSize(reportId, moleculeIds = []) {
  if (!moleculeIds.length) {
    throw new Error('Cannot inspect report size: no molecules selected')
  }

  const query = `?${new URLSearchParams(moleculeIds.map((moleculeId) => ['molecule_ids', moleculeId])).toString()}`
  const response = await api.get(`/api/reports/${reportId}/download${query}`, {
    responseType: 'blob',
  })
  return response.data?.size || 0
}

export async function getMoleculeRationale(moleculeId) {
  try {
    const response = await api.get(`/api/molecules/${moleculeId}/rationale`)
    return response.data
  } catch (error) {
    if (error.status === 404) {
      return { rationale: 'Rationale not available for this compound.' }
    }
    throw error
  }
}

export async function runPipeline(query, seedSmiles = null, nMolecules = 10) {
  const response = await api.post('/api/pipeline/run', {
    query,
    seed_smiles: seedSmiles || null,
    n_molecules: nMolecules,
  })
  return response.data
}

export function pollPipelineStatus(targetId, onUpdate, intervalMs = 2000) {
  const startedAt = Date.now()

  const intervalId = window.setInterval(async () => {
    if (Date.now() - startedAt >= FIVE_MINUTES_MS) {
      window.clearInterval(intervalId)
      return
    }

    try {
      const target = await getTarget(targetId)
      onUpdate?.(target)

      if (target?.pipeline_complete === true) {
        window.clearInterval(intervalId)
      }
    } catch (error) {
      console.warn('Pipeline status poll failed:', error.message)
    }
  }, intervalMs)

  return () => window.clearInterval(intervalId)
}

export default api
