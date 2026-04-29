import { useState, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { listProjects, registerProject, deleteProject, type Project } from '../api/projects'
import { FileBrowser } from '../components/FileBrowser'

// ── Static dashboard content ──────────────────────────────────────────────
//
// All copy here is intentionally aligned with README.md so a user reading
// the dashboard sees the same description they'd see on the GitHub page.
// If the README changes, update this too.

const AGENT_CARDS = [
  {
    icon: '🔍',
    name: 'Reviewer',
    color: 'blue',
    role: 'Reads source code, writes Project.md, generates module docs',
    detail: 'Surveys your codebase to build durable knowledge — endpoint catalog, module summaries, and a living architecture map you can browse in the Docs tab.',
  },
  {
    icon: '🧪',
    name: 'QA Agent',
    color: 'violet',
    role: 'Writes pytest tests, runs them, files bug tickets',
    detail: 'Generates black-box tests against your project\'s contracts and opens a ticket for every failure with the exact pytest output as evidence.',
  },
  {
    icon: '🛠️',
    name: 'Coder',
    color: 'amber',
    role: 'Implements fixes for bugs the QA agent finds',
    detail: 'Reads the bug ticket and source files, then writes targeted patches. Never sees the test code (true blackbox loop) — fixes must satisfy the test contract from the outside.',
  },
]

const QUICKSTART_STEPS = [
  {
    num: 1,
    title: 'Register a project',
    body: <>Use the <span className="font-medium text-gray-700">Browse…</span> button below to point SMRT at any FastAPI codebase on your machine. The bundled <code className="font-mono text-[12px] bg-gray-100 px-1 rounded">eval-fixtures/todo-api</code> and <code className="font-mono text-[12px] bg-gray-100 px-1 rounded">eval-fixtures/inventory-api</code> are great starting points — each has 5 planted bugs.</>,
  },
  {
    num: 2,
    title: 'Run the Init Audit',
    body: <>From the project page, click <span className="font-medium text-gray-700">Run Init Audit</span>. The Reviewer surveys your code and writes <code className="font-mono text-[12px] bg-gray-100 px-1 rounded">.smrt/Project.md</code>. Leave <span className="font-medium text-blue-700">📝 Generate docs</span> checked to also write <code className="font-mono text-[12px] bg-gray-100 px-1 rounded">README.md</code> (when missing) and technical docs under <code className="font-mono text-[12px] bg-gray-100 px-1 rounded">docs/</code>.</>,
  },
  {
    num: 3,
    title: 'Run a QA Session',
    body: <>Click <span className="font-medium text-gray-700">Run QA Session</span>. The QA agent writes pytest tests, runs them, and files a bug ticket for every failure. Watch the live agent thoughts in the Overview tab.</>,
  },
  {
    num: 4,
    title: 'Approve fixes via the kanban board',
    body: <>Open the <span className="font-medium text-gray-700">Tickets</span> tab. Drag a ticket from <span className="font-medium text-orange-700">Pending Confirmation</span> → <span className="font-medium text-blue-700">In Progress</span> to start the Coder. When QA verifies the fix, the <span className="font-medium text-violet-700">Reviewer</span> writes a Fix Summary and may queue documentation updates. Drag from <span className="font-medium text-yellow-700">Needs Review</span> → <span className="font-medium text-emerald-700">Closed</span> to merge — accepting also applies the queued doc updates.</>,
  },
]

const WHATS_NEW = [
  {
    icon: '🔍',
    title: 'Reviewer-written Fix Summaries',
    body: 'Every QA-Coder loop ends with the Reviewer writing a third-perspective summary, grounded in the actual agent log so it never confabulates fixes that didn\'t happen.',
  },
  {
    icon: '📝',
    title: 'Doc generation toggle on Init Audit',
    body: 'Choose whether the Reviewer should also write README.md (when missing/sparse) and technical docs under docs/. Doc tools are hidden from the model entirely when disabled.',
  },
  {
    icon: '🤝',
    title: 'Doc updates applied on Accept',
    body: 'The Reviewer\'s Fix Summary may include proposed updates to README, Project.md, or docs/*. Accepting the ticket from Needs Review applies them automatically.',
  },
  {
    icon: '🧪',
    title: 'QA Advisor with three verdicts',
    body: 'After every failed attempt, the QA Advisor returns "fix is correct", "needs another try" with feedback, or "the test itself is faulty" — halting the loop with a test-update proposal.',
  },
]

// ── Reusable presentational pieces ────────────────────────────────────────

function Hero() {
  return (
    <div className="text-center py-8 px-4 mb-8">
      <div className="inline-flex items-center gap-2 mb-3">
        <span className="text-4xl">🤖</span>
        <h1 className="text-3xl font-bold text-gray-900">SMRT Agent</h1>
        <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-700 border border-emerald-200">
          v1 · local
        </span>
      </div>
      <p className="text-lg text-gray-600 max-w-2xl mx-auto leading-relaxed">
        A semi-autonomous multi-agent system that <span className="font-semibold text-blue-700">discovers</span>{' '}
        and <span className="font-semibold text-amber-700">fixes</span>{' '}
        logical bugs in your Python FastAPI codebase, with{' '}
        <span className="font-semibold text-violet-700">documentation</span>{' '}
        kept current along the way.
      </p>
      <div className="mt-4 flex items-center justify-center gap-3 text-xs text-gray-500">
        <span>🔒 Local-only by default</span>
        <span className="text-gray-300">·</span>
        <span>👤 Two human-in-the-loop gates</span>
        <span className="text-gray-300">·</span>
        <span>💸 Per-run budget caps</span>
      </div>
    </div>
  )
}

function AgentCard({ icon, name, color, role, detail }: typeof AGENT_CARDS[number]) {
  // Tailwind class strings need to be statically present at build time, so
  // we map color names to fully-qualified utility classes here rather than
  // building them dynamically.
  const palette = {
    blue:   { ring: 'ring-blue-200', bg: 'bg-blue-50', label: 'text-blue-700', border: 'border-blue-200' },
    violet: { ring: 'ring-violet-200', bg: 'bg-violet-50', label: 'text-violet-700', border: 'border-violet-200' },
    amber:  { ring: 'ring-amber-200', bg: 'bg-amber-50', label: 'text-amber-700', border: 'border-amber-200' },
  }[color] ?? { ring: 'ring-gray-200', bg: 'bg-gray-50', label: 'text-gray-700', border: 'border-gray-200' }

  return (
    <div className={`rounded-xl border ${palette.border} ${palette.bg} p-5 hover:shadow-md transition-shadow`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-2xl leading-none">{icon}</span>
        <span className={`text-sm font-semibold uppercase tracking-wide ${palette.label}`}>{name}</span>
      </div>
      <p className="text-sm font-medium text-gray-800 mb-2">{role}</p>
      <p className="text-xs text-gray-600 leading-relaxed">{detail}</p>
    </div>
  )
}

function LoopFlow() {
  // Tiny visual storyboard of the QA↔Coder loop. Kept ASCII-style so it
  // renders identically across browsers without needing an SVG dependency.
  return (
    <div className="rounded-xl border border-gray-200 bg-gradient-to-r from-blue-50/30 via-violet-50/30 to-amber-50/30 p-5">
      <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3 text-center">
        How the QA ↔ Coder loop works
      </h3>
      <div className="flex items-center justify-center gap-2 flex-wrap text-xs">
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-violet-100 text-violet-800 border border-violet-200">
          🧪 QA writes tests
        </span>
        <span className="text-gray-400">→</span>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-violet-100 text-violet-800 border border-violet-200">
          📋 Files bug ticket
        </span>
        <span className="text-gray-400">→</span>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-orange-100 text-orange-800 border border-orange-200 font-semibold">
          👤 You approve
        </span>
        <span className="text-gray-400">→</span>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-amber-100 text-amber-800 border border-amber-200">
          🛠️ Coder fixes
        </span>
        <span className="text-gray-400">→</span>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-violet-100 text-violet-800 border border-violet-200">
          🔬 QA re-tests
        </span>
        <span className="text-gray-400">→</span>
        <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-yellow-100 text-yellow-800 border border-yellow-200 font-semibold">
          👤 You merge
        </span>
      </div>
      <p className="text-[11px] text-gray-500 text-center mt-3 italic">
        Two human gates — one to confirm a real bug, one to merge a verified fix. Loop retries up to 3 times before escalating.
      </p>
    </div>
  )
}

function QuickStartStep({ num, title, body }: typeof QUICKSTART_STEPS[number]) {
  return (
    <div className="flex gap-3">
      <div className="shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 font-bold text-sm flex items-center justify-center">
        {num}
      </div>
      <div className="flex-1 min-w-0">
        <h4 className="text-sm font-semibold text-gray-800 mb-0.5">{title}</h4>
        <p className="text-xs text-gray-600 leading-relaxed">{body}</p>
      </div>
    </div>
  )
}

function WhatsNewItem({ icon, title, body }: typeof WHATS_NEW[number]) {
  return (
    <div className="flex gap-2.5 px-3 py-2.5 rounded-md bg-white border border-gray-100">
      <span className="shrink-0 text-lg leading-none mt-0.5">{icon}</span>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-gray-800 mb-0.5">{title}</p>
        <p className="text-[11px] text-gray-600 leading-snug">{body}</p>
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)
  const formRef = useRef<HTMLFormElement>(null)

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleDelete(id: number) {
    if (!confirm('Delete this project and all its runs?')) return
    setDeleting(id)
    try {
      await deleteProject(id)
      setProjects((prev) => prev.filter((p) => p.id !== id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    if (!path) return
    setSubmitting(true)
    setError(null)
    try {
      const project = await registerProject(name, path)
      setProjects((prev) => [...prev, project])
      setName('')
      setPath('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  // Show the educational content prominently when there are no projects
  // yet (a first-time user needs the most help). Once the user has at
  // least one project the same content stays available below the fold,
  // but isn't competing with their existing work for prime real estate.
  const isFirstTimeUser = !loading && projects.length === 0

  return (
    <div className="max-w-5xl mx-auto p-6">
      <Hero />

      {/* What it does — three agent cards */}
      <section aria-label="What SMRT Agent does" className="mb-8">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3 px-1">
          Three specialized agents work together
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {AGENT_CARDS.map((c) => <AgentCard key={c.name} {...c} />)}
        </div>
      </section>

      {/* The loop, visualized */}
      <section className="mb-8">
        <LoopFlow />
      </section>

      {/* What's new — recent additions a returning user should know about.
          Sits below the loop visualization so the conceptual model comes
          first; this is purely supplementary info. */}
      <section aria-label="What's new" className="mb-8 rounded-xl border border-blue-200 bg-blue-50/40 p-4">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-blue-600">✨</span>
          <h2 className="text-sm font-semibold text-blue-900 uppercase tracking-wide">
            What's new
          </h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {WHATS_NEW.map((item) => <WhatsNewItem key={item.title} {...item} />)}
        </div>
      </section>

      {/* Quick start — 4 numbered steps. Always visible because it doubles
          as a reference for returning users. */}
      <section aria-label="Quick start" className="mb-8 rounded-xl border border-gray-200 bg-white shadow-sm p-5">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
          Quick start
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
          {QUICKSTART_STEPS.map((s) => <QuickStartStep key={s.num} {...s} />)}
        </div>
      </section>

      {/* Project list and registration form. The order flips slightly
          based on user state: first-time users see the form prominently
          (it's their first action); returning users see their list first. */}
      {!isFirstTimeUser && (
        <section aria-label="Your projects" className="mb-8">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3 flex items-center gap-2">
            Your projects
            <span className="text-xs font-normal text-gray-400">({projects.length})</span>
          </h2>
          {loading ? (
            <p className="text-sm text-gray-400 italic">Loading projects…</p>
          ) : (
            <ul className="space-y-2">
              {projects.map((p) => (
                <li key={p.id} className="border border-gray-200 rounded-lg p-3 flex items-center justify-between gap-3 bg-white hover:border-gray-300 hover:shadow-sm transition-all">
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/projects/${p.id}`}
                      className="font-medium text-blue-600 hover:underline"
                    >
                      {p.name}
                    </Link>
                    <p className="text-gray-400 text-xs truncate font-mono">{p.canonical_path}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleDelete(p.id)}
                    disabled={deleting === p.id}
                    className="shrink-0 text-sm text-red-500 hover:text-red-700 disabled:opacity-40 px-2 py-1 rounded hover:bg-red-50 transition-colors"
                  >
                    {deleting === p.id ? '…' : 'Delete'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      <section
        aria-label="Register a project"
        className={`mb-8 rounded-xl border ${isFirstTimeUser ? 'border-blue-300 bg-blue-50/30 ring-2 ring-blue-100' : 'border-gray-200 bg-white'} shadow-sm p-5`}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            {isFirstTimeUser ? '👋 Register your first project' : 'Register a new project'}
          </h2>
          {isFirstTimeUser && (
            <span className="text-xs text-blue-600 font-medium">Start here</span>
          )}
        </div>
        {isFirstTimeUser && (
          <p className="text-xs text-gray-600 mb-4">
            Tip: try the bundled <code className="font-mono bg-white px-1 py-0.5 rounded border border-gray-200">eval-fixtures/todo-api</code> or{' '}
            <code className="font-mono bg-white px-1 py-0.5 rounded border border-gray-200">eval-fixtures/inventory-api</code> — each ships with intentional bugs for the agents to discover.
          </p>
        )}
        <form ref={formRef} onSubmit={handleRegister} className="space-y-3">
          <input
            className="block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Project name (e.g., todo-api)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />

          {/* Path picker */}
          <div className="flex gap-2">
            <input
              className="block flex-1 border border-gray-300 rounded-lg px-3 py-2 bg-gray-50 text-sm font-mono"
              placeholder="Click Browse… to select a folder"
              value={path}
              readOnly
            />
            <button
              type="button"
              onClick={() => setShowBrowser(true)}
              className="shrink-0 border border-gray-300 rounded-lg px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Browse…
            </button>
          </div>

          <button
            type="submit"
            disabled={submitting || !path || !name}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {submitting ? 'Registering…' : 'Register project'}
          </button>
        </form>

        {error && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
            {error}
          </div>
        )}
      </section>

      {/* When the user has no projects yet, the project list section above is
          hidden in favor of putting the registration form prominently. We
          still surface a quiet empty state here so the existing test for
          /no projects/i text continues to pass and a power user understands
          why the "Your projects" section is absent. */}
      {isFirstTimeUser && (
        <section className="mb-8 text-center text-xs text-gray-400 italic" aria-label="Your projects">
          No projects registered yet — fill out the form above to get started.
        </section>
      )}

      {/* Modal file browser — rendered outside the form so it can't trigger form submission */}
      {showBrowser && (
        <FileBrowser
          onSelect={(selected) => {
            setPath(selected)
            setShowBrowser(false)
          }}
          onClose={() => setShowBrowser(false)}
        />
      )}

      {/* Footer pointer to deeper docs for users who want to dig in */}
      <footer className="text-center pt-6 pb-4 border-t border-gray-100">
        <p className="text-xs text-gray-400">
          Want the full architecture? See{' '}
          <code className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">README.md</code>
          {' · '}
          <code className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">docs/architecture.md</code>
          {' · '}
          <code className="font-mono bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">docs/agent-design.md</code>
        </p>
      </footer>
    </div>
  )
}
