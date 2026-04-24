import './ui.css'

function Skeleton({ width = '100%', height = 16, borderRadius = 'var(--radius)' }) {
  return (
    <span
      className="mgx-skeleton"
      style={{ width, height, borderRadius }}
      aria-hidden="true"
    />
  )
}

export default Skeleton
