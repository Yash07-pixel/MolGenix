import Button from './ui/Button'

function ErrorState({ title, message, retryFn }) {
  return (
    <div className="error-state">
      <h2>{title}</h2>
      <p>{message}</p>
      {retryFn ? (
        <Button size="md" variant="secondary" onClick={retryFn}>
          Retry
        </Button>
      ) : null}
    </div>
  )
}

export default ErrorState
