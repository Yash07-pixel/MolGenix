import { Link } from 'react-router-dom'
import PageWrapper from '../components/layout/PageWrapper'

function NotFoundPage() {
  return (
    <PageWrapper className="not-found-page">
      <p className="not-found-page__code">404</p>
      <h1>Page not found.</h1>
      <Link to="/search">Back to search</Link>
    </PageWrapper>
  )
}

export default NotFoundPage
