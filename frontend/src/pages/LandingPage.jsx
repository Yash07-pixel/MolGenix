import { Link, useNavigate } from 'react-router-dom'
import PageWrapper from '../components/layout/PageWrapper'
import Card from '../components/ui/Card'
import Button from '../components/ui/Button'
import Badge from '../components/ui/Badge'
import Divider from '../components/ui/Divider'

const pipelineSteps = [
  {
    number: '01',
    title: 'Target Analysis',
    body: 'Natural language parsing + UniProt + ChEMBL lookup',
  },
  {
    number: '02',
    title: 'Molecule Generation',
    body: 'RDKit fragment-based generation with Lipinski filtering',
  },
  {
    number: '03',
    title: 'ADMET Screening',
    body: 'DeepChem pretrained models — toxicity, BBB, bioavailability',
  },
  {
    number: '04',
    title: 'Molecular Docking',
    body: 'AutoDock Vina binding affinity simulation',
  },
  {
    number: '05',
    title: 'Report Export',
    body: 'Downloadable PDF with all scores and structures',
  },
]

const preloadedTargets = [
  { name: 'BACE1', disease: "Alzheimer's", score: 0.9 },
  { name: 'EGFR', disease: 'Lung Cancer', score: 0.85 },
  { name: 'HIV Protease', disease: 'HIV-AIDS', score: 0.95 },
  { name: 'COX-2', disease: 'Inflammation', score: 0.8 },
]

const previewAdmet = [
  { label: 'BBB Penetration', badge: 'MODERATE', variant: 'warning' },
  { label: 'Hepatotoxicity', badge: 'SAFE', variant: 'success' },
  { label: 'hERG Cardiotoxicity', badge: 'WARNING', variant: 'danger' },
  { label: 'Oral Bioavailability', badge: 'GOOD', variant: 'success' },
]

function LandingPage() {
  const navigate = useNavigate()

  return (
    <PageWrapper className="landing-page">
      <section className="landing-intro">
        <div className="landing-intro__copy">
          <p className="landing-label">Drug Discovery Platform</p>
          <h1 className="landing-headline">
            From target description
            <br />
            to drug candidates.
          </h1>
          <p className="landing-body">
            Describe a protein target or disease in plain English. MolGenix generates and
            screens novel molecular candidates using RDKit, DeepChem, and AutoDock Vina —
            producing ADMET profiles, docking scores, and a downloadable report.
          </p>
          <div className="landing-actions">
            <Link to="/search">
              <Button size="lg">Start a Search</Button>
            </Link>
          </div>
          <p className="landing-cta-note">
            Run a full discovery pass with target enrichment, ADMET screening, docking,
            and a polished report from one prompt.
          </p>
        </div>

        <Card className="preview-card preview-card--hero">
          <p className="landing-section-label landing-section-label--tight">Example Output</p>
          <div className="preview-card__body">
            <div className="preview-visual" aria-hidden="true">
              <div className="preview-visual__halo" />
              <div className="preview-visual__grid" />
              <div className="preview-visual__molecule">
                <span className="preview-visual__node preview-visual__node--a" />
                <span className="preview-visual__node preview-visual__node--b" />
                <span className="preview-visual__node preview-visual__node--c" />
                <span className="preview-visual__node preview-visual__node--d" />
                <span className="preview-visual__bond preview-visual__bond--ab" />
                <span className="preview-visual__bond preview-visual__bond--bc" />
                <span className="preview-visual__bond preview-visual__bond--cd" />
              </div>
              <div className="preview-visual__chips">
                <span>Docking Active</span>
                <span>ADMET Screened</span>
                <span>Lead Ranked</span>
              </div>
            </div>
            <div className="preview-card__top">
              <span className="preview-card__compound">Compound 001</span>
              <Badge variant="success">Lipinski Pass</Badge>
            </div>
            <p className="preview-card__smiles">CCN(CC)CCOC(=O)c1ccc(Nc2ncc3ccccc3n2)cc1</p>

            <Divider />

            <div className="preview-metrics">
              <div>
                <span>MW</span>
                <strong>342.4 Da</strong>
              </div>
              <div>
                <span>LogP</span>
                <strong>2.8</strong>
              </div>
              <div>
                <span>SAS</span>
                <strong>3.2</strong>
              </div>
              <div>
                <span>Docking</span>
                <strong>-7.4 kcal/mol</strong>
              </div>
            </div>

            <Divider />

            <p className="landing-section-label landing-section-label--tight">ADMET</p>
            <div className="preview-admet">
              {previewAdmet.map((item) => (
                <div key={item.label} className="preview-admet__row">
                  <span>{item.label}</span>
                  <Badge variant={item.variant}>{item.badge}</Badge>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </section>

      <section className="landing-overview">
        <p className="landing-section-label">How It Works</p>
        <div className="overview-steps">
          {pipelineSteps.map((step, index) => (
            <div key={step.number} className="overview-step-wrap">
              <div className="overview-step">
                <span className="overview-step__number">{step.number}</span>
                <h2>{step.title}</h2>
                <p>{step.body}</p>
              </div>
              {index < pipelineSteps.length - 1 ? <div className="overview-step__line" aria-hidden="true" /> : null}
            </div>
          ))}
        </div>
      </section>

      <section className="landing-targets">
        <p className="landing-section-label">Preloaded Targets</p>
        <p className="landing-targets__subtitle">
          These targets are pre-analyzed. Results load instantly.
        </p>
        <div className="landing-target-grid">
          {preloadedTargets.map((target) => (
            <Card
              key={target.name}
              className="target-preview-card"
              onClick={() => navigate(`/search?target=${encodeURIComponent(target.name)}`)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault()
                  navigate(`/search?target=${encodeURIComponent(target.name)}`)
                }
              }}
            >
              <div className="target-preview-card__header">
                <h2>{target.name}</h2>
                <p>{target.disease}</p>
              </div>
              <div className="target-preview-card__footer">
                <div className="target-preview-card__row">
                  <span>Druggability</span>
                  <strong>{target.score.toFixed(2)}</strong>
                </div>
                <div className="target-preview-card__bar">
                  <span style={{ width: `${target.score * 100}%` }} />
                </div>
              </div>
            </Card>
          ))}
        </div>
      </section>
    </PageWrapper>
  )
}

export default LandingPage
