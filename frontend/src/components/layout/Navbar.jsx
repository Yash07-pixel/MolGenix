import { useState } from 'react'
import { Link, NavLink } from 'react-router-dom'
import Button from '../ui/Button'

const navItems = [
  { key: 'search', to: '/search', label: 'Search' },
]

function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false)
  const docsUrl = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'}/docs`

  return (
    <header className="navbar-shell">
      <div className="page-wrapper navbar">
        <Link className="navbar__brand" to="/">
          MolGenix
        </Link>

        <nav className="navbar__links" aria-label="Primary">
          {navItems.map((item) => (
            <NavLink
              key={item.key}
              className={({ isActive }) =>
                `navbar__link ${isActive ? 'navbar__link--active' : ''}`.trim()
              }
              to={item.to}
            >
              {item.label}
            </NavLink>
          ))}
          <a
            className="navbar__link"
            href={docsUrl}
            target="_blank"
            rel="noreferrer"
          >
            Docs
          </a>
        </nav>

        <div className="navbar__actions">
          <Link to="/search">
            <Button size="sm">Run Pipeline</Button>
          </Link>
          <button
            type="button"
            className="navbar__menu"
            aria-label="Open navigation menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((value) => !value)}
          >
            <span />
            <span />
            <span />
          </button>
        </div>
      </div>

      {menuOpen ? (
        <div className="navbar__mobile">
          <div className="page-wrapper navbar__mobile-inner">
            {navItems.map((item) => (
              <NavLink
                key={item.key}
                className="navbar__mobile-link"
                to={item.to}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
            <a
              className="navbar__mobile-link"
              href={docsUrl}
              target="_blank"
              rel="noreferrer"
              onClick={() => setMenuOpen(false)}
            >
              Docs
            </a>
          </div>
        </div>
      ) : null}
    </header>
  )
}

export default Navbar
