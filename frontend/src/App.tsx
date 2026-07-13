import { useEffect, useMemo, useState } from 'react'
import type { ChangeEvent, FormEvent, ReactNode } from 'react'
import { Link, Navigate, Route, Routes, useNavigate, useParams } from 'react-router-dom'

type Outcome = 'approved' | 'pending' | 'rejected'
type RunStatus = Outcome | 'running' | 'started' | 'completed' | string
type CheckStatus = 'pass' | 'warn' | 'fail' | 'error' | 'skipped'
type Method = 'deterministic' | 'llm' | 'external_api' | 'simulated_api' | string

type PendingItem = {
  item: string
  detail: string
  action_required: string
  internal_only?: boolean
}

type CheckResult = {
  check_id: string
  gate: number
  category: string
  method: Method
  result: CheckStatus
  severity: string
  evidence: string
  llm_rationale?: string | null
  duration_ms: number
  pending_item?: PendingItem | null
}

type Decision = {
  outcome: Outcome
  hard_fails: string[]
  soft_flags: string[]
  pending_items: PendingItem[]
  summary: string
}

type SubmissionListItem = {
  id: string
  vendor_legal_name: string
  country: string
  status: RunStatus
  hard_fail_count: number
  pending_count: number
  flag_count: number
  received_at: string
  decided_at?: string | null
}

type FixtureInfo = {
  name: string
  title: string
  expected_outcome: Outcome
  description: string
}

type DemoKitInfo = {
  id: string
  fixture: string
  title: string
  expected_outcome: Outcome
  description: string
  has_bank_proof: boolean
  path: string
}

type RunResult = {
  submission_id: string
  country_profile?: string
  vendor_legal_name: string
  status: RunStatus
  checks: CheckResult[]
  decision?: Decision | null
  vendor_email_draft?: string | null
  audit?: Record<string, unknown>
  extracted?: Record<string, unknown>
}

type GateState = {
  gate: number
  title: string
  status: 'idle' | 'running' | 'done'
  checks: CheckResult[]
}

type SubmissionFormState = {
  legal_name: string
  trade_name: string
  tax_id: string
  address: {
    line1: string
    city: string
    state: string
    postal_code: string
  }
  bank: {
    account_number: string
    ifsc: string
    beneficiary_name: string
  }
  contact: {
    email: string
    phone: string
  }
}

const gateDefaults = [
  { gate: 1, title: 'Intake completeness' },
  { gate: 2, title: 'Document reading' },
  { gate: 3, title: 'Identity consistency' },
  { gate: 4, title: 'Bank verification' },
  { gate: 5, title: 'Risk screening' },
]

const emptyForm: SubmissionFormState = {
  legal_name: '',
  trade_name: '',
  tax_id: '',
  address: {
    line1: '',
    city: '',
    state: '',
    postal_code: '',
  },
  bank: {
    account_number: '',
    ifsc: '',
    beneficiary_name: '',
  },
  contact: {
    email: '',
    phone: '',
  },
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: init?.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })

  if (!response.ok) {
    const detail = await response.text().catch(() => '')
    throw new Error(detail || `Request failed: ${response.status}`)
  }

  return response.json() as Promise<T>
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/new" element={<NewSubmission />} />
      <Route path="/run/:id" element={<RunView />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-[var(--surface)] text-[var(--ink)]">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-5 sm:px-6 lg:px-8">
        <header className="flex flex-col gap-4 border-b border-[var(--line)] pb-5 md:flex-row md:items-end md:justify-between">
          <Link to="/" className="group">
            <h1 className="text-3xl font-semibold tracking-[-0.04em] text-[var(--ink)] sm:text-4xl">
              VendorGate
            </h1>
          </Link>
          <Link
            to="/new"
            className="inline-flex w-fit items-center justify-center rounded-full bg-[var(--accent)] px-5 py-3 text-sm font-bold text-white transition hover:bg-[var(--accent-strong)] focus:outline-none focus:ring-4 focus:ring-[var(--accent-soft)]"
          >
            New submission
          </Link>
        </header>
        {children}
      </div>
    </div>
  )
}

function Dashboard() {
  const [runs, setRuns] = useState<SubmissionListItem[]>([])
  const [fixtures, setFixtures] = useState<FixtureInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [fixtureLoading, setFixtureLoading] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError('')
      try {
        const [runList, fixtureList] = await Promise.all([
          apiJson<SubmissionListItem[]>('/api/submissions'),
          apiJson<FixtureInfo[]>('/api/fixtures'),
        ])

        if (!cancelled) {
          setRuns(sortRuns(runList))
          setFixtures(fixtureList)
        }
      } catch (err) {
        if (!cancelled) setError(readError(err, 'Backend is not available yet.'))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  async function runFixture(name: string) {
    setFixtureLoading(name)
    setError('')
    try {
      const result = await apiJson<{ id?: string; submission_id?: string }>(`/api/fixtures/${name}/run`, {
        method: 'POST',
      })
      const id = result.id ?? result.submission_id
      if (!id) throw new Error('Fixture run response did not include an id.')
      navigate(`/run/${id}`)
    } catch (err) {
      setError(readError(err, 'Could not start fixture.'))
    } finally {
      setFixtureLoading('')
    }
  }

  return (
    <AppShell>
      <main className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="rounded-[2rem] border border-[var(--line)] bg-white">
          <div className="flex flex-col gap-2 border-b border-[var(--line)] p-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="eyebrow">Dashboard</p>
              <h2 className="text-2xl font-semibold tracking-[-0.03em]">Submission runs</h2>
            </div>
            <p className="text-sm text-[var(--muted)]">Newest first</p>
          </div>

          {error ? <Notice tone="error">{error}</Notice> : null}

          {loading ? (
            <div className="space-y-3 p-5">
              {[0, 1, 2].map((item) => (
                <div key={item} className="h-16 animate-pulse rounded-2xl bg-[var(--surface-strong)]" />
              ))}
            </div>
          ) : runs.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left">
                <thead className="text-xs uppercase tracking-[0.18em] text-[var(--muted)]">
                  <tr className="border-b border-[var(--line)]">
                    <th className="px-5 py-4 font-semibold">Vendor</th>
                    <th className="px-5 py-4 font-semibold">Status</th>
                    <th className="px-5 py-4 font-semibold">Counts</th>
                    <th className="px-5 py-4 font-semibold">Received</th>
                    <th className="px-5 py-4 font-semibold">Decided</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr
                      key={run.id}
                      onClick={() => navigate(`/run/${run.id}`)}
                      className="cursor-pointer border-b border-[var(--line)] transition last:border-0 hover:bg-[var(--surface)]"
                    >
                      <td className="px-5 py-4">
                        <p className="font-semibold">{run.vendor_legal_name || 'Unnamed vendor'}</p>
                        <p className="font-mono text-xs text-[var(--muted)]">{run.country} · {run.id}</p>
                      </td>
                      <td className="px-5 py-4">
                        <StatusChip status={run.status} />
                      </td>
                      <td className="px-5 py-4">
                        <CountBadges hard={run.hard_fail_count} pending={run.pending_count} flags={run.flag_count} />
                      </td>
                      <td className="px-5 py-4 text-sm text-[var(--muted)]">{formatDate(run.received_at)}</td>
                      <td className="px-5 py-4 text-sm text-[var(--muted)]">{formatDate(run.decided_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No submissions yet"
              body="Start with a new submission or run one of the demo fixtures."
            />
          )}
        </section>

        <aside className="h-fit rounded-[2rem] border border-[var(--line)] bg-white p-5">
          <p className="eyebrow">Demo fixtures</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">Known outcomes</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--muted)]">
            Each fixture creates a run so reviewers can watch the rule gates resolve.
          </p>
          <div className="mt-5 space-y-3">
            {fixtures.length ? fixtures.map((fixture) => (
              <button
                key={fixture.name}
                type="button"
                onClick={() => runFixture(fixture.name)}
                disabled={fixtureLoading === fixture.name}
                className="w-full rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4 text-left transition hover:border-[var(--accent)] disabled:cursor-wait disabled:opacity-60"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold">{fixture.title}</span>
                  <StatusChip status={fixture.expected_outcome} compact />
                </div>
                <p className="mt-2 text-sm text-[var(--muted)]">{fixture.description}</p>
              </button>
            )) : (
              <p className="rounded-2xl bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
                Fixtures will appear here when the backend is running.
              </p>
            )}
          </div>
        </aside>
      </main>
    </AppShell>
  )
}

function NewSubmission() {
  const [form, setForm] = useState<SubmissionFormState>(emptyForm)
  const [taxCertificate, setTaxCertificate] = useState<File | null>(null)
  const [bankProof, setBankProof] = useState<File | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [kits, setKits] = useState<DemoKitInfo[]>([])
  const [selectedKit, setSelectedKit] = useState('')
  const [kitHint, setKitHint] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    let cancelled = false
    apiJson<DemoKitInfo[]>('/api/demo-kits')
      .then((list) => {
        if (!cancelled) setKits(list)
      })
      .catch(() => {
        if (!cancelled) setKits([])
      })
    return () => {
      cancelled = true
    }
  }, [])

  function update(path: string, value: string) {
    const parts = path.split('.')
    setForm((current) => {
      const next = structuredClone(current)
      let target: Record<string, unknown> = next as unknown as Record<string, unknown>
      for (const part of parts.slice(0, -1)) target = target[part] as Record<string, unknown>
      target[parts[parts.length - 1]] = value
      return next
    })
  }

  async function loadDemoKit(kitId: string) {
    setSelectedKit(kitId)
    setError('')
    setTaxCertificate(null)
    setBankProof(null)
    if (!kitId) {
      setKitHint('')
      return
    }
    try {
      const payload = await apiJson<{
        legal_name?: string
        trade_name?: string | null
        tax_id?: string
        address?: SubmissionFormState['address']
        bank?: SubmissionFormState['bank']
        contact?: SubmissionFormState['contact']
      }>(`/api/demo-kits/${kitId}/form`)
      setForm({
        legal_name: payload.legal_name ?? '',
        trade_name: payload.trade_name ?? '',
        tax_id: payload.tax_id ?? '',
        address: {
          line1: payload.address?.line1 ?? '',
          city: payload.address?.city ?? '',
          state: payload.address?.state ?? '',
          postal_code: payload.address?.postal_code ?? '',
        },
        bank: {
          account_number: payload.bank?.account_number ?? '',
          ifsc: payload.bank?.ifsc ?? '',
          beneficiary_name: payload.bank?.beneficiary_name ?? '',
        },
        contact: {
          email: payload.contact?.email ?? '',
          phone: payload.contact?.phone ?? '',
        },
      })
      const meta = kits.find((k) => k.id === kitId)
      setKitHint(
        meta?.has_bank_proof
          ? `Form prefilled from ${kitId}. Drop tax_certificate.pdf and bank_proof.pdf from demo_kits/${kitId}/.`
          : `Form prefilled from ${kitId}. Drop tax_certificate.pdf only — leave bank proof empty (EC-3).`,
      )
    } catch (err) {
      setError(readError(err, 'Could not load demo kit form.'))
      setKitHint('')
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const payload = new FormData()
      payload.append('form', JSON.stringify({ country: 'IN', ...form }))
      if (taxCertificate) payload.append('tax_certificate', taxCertificate)
      if (bankProof) payload.append('bank_proof', bankProof)

      const result = await apiJson<{ id?: string; submission_id?: string }>('/api/submissions', {
        method: 'POST',
        body: payload,
      })
      const id = result.id ?? result.submission_id
      if (!id) throw new Error('Submission response did not include an id.')
      navigate(`/run/${id}`)
    } catch (err) {
      setError(readError(err, 'Could not submit vendor.'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AppShell>
      <main className="rounded-[2rem] border border-[var(--line)] bg-white">
        <div className="border-b border-[var(--line)] p-5">
          <p className="eyebrow">New submission</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.03em]">India vendor intake</h2>
          <p className="mt-2 text-sm text-[var(--muted)]">Country is fixed to IN for this workflow.</p>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-sm">
              <span className="font-medium text-[var(--muted)]">Load demo kit</span>
              <select
                value={selectedKit}
                onChange={(event) => loadDemoKit(event.target.value)}
                className="rounded-xl border border-[var(--line)] bg-[var(--surface)] px-3 py-2 text-[var(--ink)]"
              >
                <option value="">Type manually…</option>
                {kits.map((kit) => (
                  <option key={kit.id} value={kit.id}>
                    {kit.title}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {kitHint ? (
            <p className="mt-3 rounded-xl bg-[var(--surface)] px-3 py-2 text-sm text-[var(--muted)]">{kitHint}</p>
          ) : null}
        </div>
        {error ? <Notice tone="error">{error}</Notice> : null}
        <form onSubmit={submit} className="grid gap-6 p-5 lg:grid-cols-2">
          <FormSection title="Vendor identity">
            <TextField label="Legal name" value={form.legal_name} onChange={(value) => update('legal_name', value)} required />
            <TextField label="Trade name" value={form.trade_name} onChange={(value) => update('trade_name', value)} />
            <TextField label="GSTIN" value={form.tax_id} onChange={(value) => update('tax_id', value.toUpperCase())} required />
          </FormSection>

          <FormSection title="Registered address">
            <TextField label="Address line 1" value={form.address.line1} onChange={(value) => update('address.line1', value)} required />
            <div className="grid gap-4 sm:grid-cols-2">
              <TextField label="City" value={form.address.city} onChange={(value) => update('address.city', value)} required />
              <TextField label="State" value={form.address.state} onChange={(value) => update('address.state', value)} required />
            </div>
            <TextField label="Postal code" value={form.address.postal_code} onChange={(value) => update('address.postal_code', value)} required />
          </FormSection>

          <FormSection title="Bank details">
            <TextField label="Account number" value={form.bank.account_number} onChange={(value) => update('bank.account_number', value)} required />
            <TextField label="IFSC" value={form.bank.ifsc} onChange={(value) => update('bank.ifsc', value.toUpperCase())} required />
            <TextField label="Beneficiary name" value={form.bank.beneficiary_name} onChange={(value) => update('bank.beneficiary_name', value)} required />
          </FormSection>

          <FormSection title="Contact">
            <TextField label="Email" type="email" value={form.contact.email} onChange={(value) => update('contact.email', value)} required />
            <TextField label="Phone" value={form.contact.phone} onChange={(value) => update('contact.phone', value)} required />
          </FormSection>

          <div className="grid gap-4 lg:col-span-2 lg:grid-cols-2">
            <DropZone label="Tax certificate PDF" file={taxCertificate} onFile={setTaxCertificate} />
            <DropZone label="Bank proof PDF" file={bankProof} onFile={setBankProof} />
          </div>

          <div className="flex flex-col gap-3 border-t border-[var(--line)] pt-5 sm:flex-row sm:items-center sm:justify-between lg:col-span-2">
            <p className="text-sm text-[var(--muted)]">Multipart includes `form` JSON plus optional PDF parts.</p>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-full bg-[var(--accent)] px-6 py-3 text-sm font-bold text-white transition hover:bg-[var(--accent-strong)] disabled:cursor-wait disabled:opacity-60"
            >
              {submitting ? 'Submitting...' : 'Submit and run gates'}
            </button>
          </div>
        </form>
      </main>
    </AppShell>
  )
}

function RunView() {
  const { id = '' } = useParams()
  const [vendor, setVendor] = useState('Vendor submission')
  const [country, setCountry] = useState('IN')
  const [rulesetVersion, setRulesetVersion] = useState('ruleset pending')
  const [status, setStatus] = useState<RunStatus>('running')
  const [gates, setGates] = useState<GateState[]>(() => initialGates())
  const [decision, setDecision] = useState<Decision | null>(null)
  const [emailDraft, setEmailDraft] = useState('')
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let cancelled = false
    setError('')

    async function loadSnapshot() {
      try {
        const result = await apiJson<RunResult>(`/api/submissions/${id}`)
        if (cancelled) return
        applySnapshot(result)
      } catch (err) {
        if (!cancelled) setError(readError(err, 'Waiting for run data.'))
      }
    }

    function applySnapshot(result: RunResult) {
      setVendor(result.vendor_legal_name || 'Vendor submission')
      setCountry(result.country_profile || 'IN')
      setStatus(result.status || 'running')
      setDecision(result.decision ?? null)
      setEmailDraft(result.vendor_email_draft ?? '')
      if (result.checks?.length) {
        setGates((current) => mergeChecksIntoGates(current, result.checks).map((gate) => ({
          ...gate,
          status: gate.checks.length ? 'done' : gate.status,
        })))
      }
    }

    loadSnapshot()

    const stream = new EventSource(`/api/submissions/${id}/stream`)
    const listen = <T,>(name: string, handler: (payload: T) => void) => {
      stream.addEventListener(name, (event) => {
        if (cancelled) return
        handler(parseEvent<T>(event as MessageEvent))
      })
    }

    listen<{ submission_id: string; vendor: string; country: string; ruleset_version: string }>('run_started', (payload) => {
      setVendor(payload.vendor || 'Vendor submission')
      setCountry(payload.country || 'IN')
      setRulesetVersion(payload.ruleset_version || 'ruleset active')
      // Don't clobber a completed snapshot when EventSource replays history.
      setStatus((current) => (current === 'approved' || current === 'pending' || current === 'rejected' ? current : 'running'))
    })

    listen<{ gate: number; title: string }>('gate_started', (payload) => {
      setGates((current) => current.map((gate) => (
        gate.gate === Number(payload.gate)
          ? { ...gate, title: payload.title || gate.title, status: 'running' }
          : gate
      )))
    })

    listen<CheckResult>('check_completed', (payload) => {
      setGates((current) => upsertCheck(current, payload))
    })

    listen<{ gate: number }>('gate_completed', (payload) => {
      setGates((current) => current.map((gate) => (
        gate.gate === Number(payload.gate) ? { ...gate, status: 'done' } : gate
      )))
    })

    listen<Decision>('decision', (payload) => {
      setDecision(payload)
      setStatus(payload.outcome)
    })

    listen<{ text: string }>('email_draft', (payload) => {
      setEmailDraft(payload.text || '')
    })

    listen<{ status: RunStatus }>('run_completed', (payload) => {
      setStatus(payload.status || 'completed')
      stream.close()
      loadSnapshot()
    })

    stream.onmessage = (event) => {
      const payload = parseEvent<Record<string, unknown>>(event)
      const type = String(payload.type || payload.event || '')
      if (type === 'check_completed') setGates((current) => upsertCheck(current, payload as CheckResult))
      if (type === 'decision') {
        setDecision(payload as Decision)
        setStatus((payload as Decision).outcome)
      }
    }

    stream.onerror = () => {
      stream.close()
    }

    return () => {
      cancelled = true
      stream.close()
    }
  }, [id])

  const totals = useMemo(() => {
    const checks = gates.flatMap((gate) => gate.checks)
    return {
      hard: decision?.hard_fails.length ?? checks.filter((check) => check.severity === 'hard_fail').length,
      pending: decision?.pending_items.length ?? checks.filter((check) => check.severity === 'pending_item').length,
      flags: decision?.soft_flags.length ?? checks.filter((check) => check.severity === 'soft_flag').length,
    }
  }, [decision, gates])

  const internalOnly = decision?.pending_items.length
    ? decision.pending_items.every((item) => item.internal_only) && !emailDraft
    : false

  async function copyDraft() {
    await navigator.clipboard.writeText(emailDraft)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <AppShell>
      <main className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_390px]">
        <section className="rounded-[2rem] border border-[var(--line)] bg-white">
          <div className="flex flex-col gap-4 border-b border-[var(--line)] p-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="eyebrow">Live run · {country}</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-[-0.04em]">{vendor}</h2>
              <p className="mt-2 font-mono text-xs text-[var(--muted)]">{id} · {rulesetVersion}</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <StatusChip status={status} />
              <CountBadges hard={totals.hard} pending={totals.pending} flags={totals.flags} />
            </div>
          </div>

          {error ? <Notice tone="warn">{error}</Notice> : null}

          <div className="p-5">
            <div className="relative space-y-4 before:absolute before:left-[1.15rem] before:top-6 before:h-[calc(100%-3rem)] before:w-px before:bg-[var(--line)]">
              {gates.map((gate) => (
                <GateCard
                  key={gate.gate}
                  gate={gate}
                  expanded={expanded}
                  onToggle={(checkId) => setExpanded((current) => ({ ...current, [checkId]: !current[checkId] }))}
                />
              ))}
              <DecisionTimelineCard decision={decision} status={status} />
            </div>
          </div>
        </section>

        <aside className="space-y-6">
          <DecisionCard decision={decision} />

          <section className="rounded-[2rem] border border-[var(--line)] bg-white p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="eyebrow">Vendor email</p>
                <h3 className="mt-2 text-xl font-semibold tracking-[-0.03em]">Draft response</h3>
              </div>
              {emailDraft ? (
                <button
                  type="button"
                  onClick={copyDraft}
                  className="rounded-full border border-[var(--line)] px-4 py-2 text-sm font-bold transition hover:border-[var(--accent)]"
                >
                  {copied ? 'Copied' : 'Copy'}
                </button>
              ) : null}
            </div>
            {emailDraft ? (
              <>
                <p className="mt-3 text-sm text-[var(--muted)]">Draft only — not sent (by design)</p>
                <pre className="mt-4 max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-2xl bg-[var(--surface)] p-4 font-mono text-sm leading-6 text-[var(--ink)]">
                  {emailDraft}
                </pre>
              </>
            ) : internalOnly ? (
              <p className="mt-4 rounded-2xl bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
                Internal review only — no vendor email
              </p>
            ) : (
              <p className="mt-4 rounded-2xl bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
                Email draft will appear if the decision requires vendor action.
              </p>
            )}
          </section>
        </aside>
      </main>
    </AppShell>
  )
}

function GateCard({
  gate,
  expanded,
  onToggle,
}: {
  gate: GateState
  expanded: Record<string, boolean>
  onToggle: (checkId: string) => void
}) {
  return (
    <section className="relative pl-14">
      <div className="absolute left-0 top-5 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-[var(--line)] bg-white font-mono text-sm font-bold">
        {gate.status === 'running' ? <span className="h-3 w-3 animate-pulse rounded-full bg-[var(--accent)]" /> : gate.gate}
      </div>
      <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface)] p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Gate {gate.gate}</p>
            <h3 className="mt-1 text-xl font-semibold tracking-[-0.03em]">{gate.title}</h3>
          </div>
          <span className="text-sm font-semibold text-[var(--muted)]">
            {gate.status === 'running' ? 'Running' : gate.status === 'done' ? 'Complete' : 'Waiting'}
          </span>
        </div>

        <div className="mt-4 space-y-3">
          {gate.checks.length ? gate.checks.map((check) => (
            <CheckRow
              key={`${check.gate}-${check.check_id}`}
              check={check}
              expanded={Boolean(expanded[`${check.gate}-${check.check_id}`])}
              onToggle={() => onToggle(`${check.gate}-${check.check_id}`)}
            />
          )) : (
            <p className="rounded-2xl border border-dashed border-[var(--line)] bg-white p-4 text-sm text-[var(--muted)]">
              Checks will stream in as this gate runs.
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

function CheckRow({ check, expanded, onToggle }: { check: CheckResult; expanded: boolean; onToggle: () => void }) {
  const hasMore = Boolean(check.evidence || check.llm_rationale || check.pending_item)

  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={!hasMore}
      className="w-full rounded-2xl border border-[var(--line)] bg-white p-4 text-left transition hover:border-[var(--accent)] disabled:cursor-default disabled:hover:border-[var(--line)]"
    >
      <div className="grid gap-3 lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:items-start">
        <div className={`result-icon result-${check.result}`}>{resultIcon(check.result)}</div>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold">{humanizeCheckId(check.check_id)}</p>
            <MethodBadge method={check.method} />
            <span className="font-mono text-xs text-[var(--muted)]">{check.duration_ms}ms</span>
          </div>
          <p className="mt-2 truncate font-mono text-sm text-[var(--muted)]">{check.evidence || 'No evidence provided'}</p>
        </div>
        <span className="text-sm font-bold text-[var(--accent)]">{hasMore ? (expanded ? 'Collapse' : 'Evidence') : ''}</span>
      </div>

      {expanded ? (
        <div className="mt-4 space-y-3 border-t border-[var(--line)] pt-4">
          <EvidenceBlock label="Evidence" value={check.evidence} />
          {check.llm_rationale ? <EvidenceBlock label="LLM rationale" value={check.llm_rationale} /> : null}
          {check.pending_item ? (
            <div className="rounded-xl bg-[var(--surface)] p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-bold">{check.pending_item.item}</span>
                {check.pending_item.internal_only ? <span className="internal-badge">internal</span> : null}
              </div>
              <p className="mt-1 text-[var(--muted)]">{check.pending_item.detail}</p>
              <p className="mt-2 font-semibold">Action: {check.pending_item.action_required}</p>
            </div>
          ) : null}
        </div>
      ) : null}
    </button>
  )
}

function DecisionTimelineCard({ decision, status }: { decision: Decision | null; status: RunStatus }) {
  return (
    <section className="relative pl-14">
      <div className="absolute left-0 top-5 z-10 flex h-9 w-9 items-center justify-center rounded-full border border-[var(--line)] bg-white font-mono text-sm font-bold">
        {decision ? 'D' : <span className="h-3 w-3 rounded-full bg-[var(--muted)]" />}
      </div>
      <div className="rounded-[1.5rem] border border-[var(--line)] bg-white p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-mono text-xs uppercase tracking-[0.2em] text-[var(--muted)]">Decision</p>
            <h3 className="mt-1 text-xl font-semibold tracking-[-0.03em]">
              {decision ? sentenceCase(decision.outcome) : 'Awaiting final rule decision'}
            </h3>
          </div>
          <StatusChip status={decision?.outcome ?? status} />
        </div>
        <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
          {decision?.summary || 'The LLM can read messy evidence, but only deterministic rules produce the final outcome.'}
        </p>
      </div>
    </section>
  )
}

function DecisionCard({ decision }: { decision: Decision | null }) {
  return (
    <section className="rounded-[2rem] border border-[var(--line)] bg-white p-5">
      <p className="eyebrow">Decision card</p>
      {decision ? (
        <>
          <div className="mt-3 flex items-start justify-between gap-4">
            <h3 className="text-2xl font-semibold tracking-[-0.03em]">{sentenceCase(decision.outcome)}</h3>
            <StatusChip status={decision.outcome} compact />
          </div>
          <p className="mt-3 text-sm leading-6 text-[var(--muted)]">{decision.summary}</p>
          <DecisionList title="Hard fails" items={decision.hard_fails.map(humanizeCheckId)} empty="No hard failures." />
          <DecisionList title="Flags" items={decision.soft_flags.map(humanizeCheckId)} empty="No soft flags." />
          <div className="mt-5">
            <h4 className="text-sm font-bold">Pending items</h4>
            {decision.pending_items.length ? (
              <div className="mt-2 space-y-2">
                {decision.pending_items.map((item) => (
                  <div key={`${item.item}-${item.detail}`} className="rounded-2xl bg-[var(--surface)] p-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold">{item.item}</span>
                      {item.internal_only ? <span className="internal-badge">internal</span> : null}
                    </div>
                    <p className="mt-1 text-[var(--muted)]">{item.detail}</p>
                    <p className="mt-2 font-semibold">{item.action_required}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-sm text-[var(--muted)]">No pending items.</p>
            )}
          </div>
        </>
      ) : (
        <p className="mt-3 rounded-2xl bg-[var(--surface)] p-4 text-sm text-[var(--muted)]">
          Decision appears after all gates complete.
        </p>
      )}
    </section>
  )
}

function DecisionList({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div className="mt-5">
      <h4 className="text-sm font-bold">{title}</h4>
      {items.length ? (
        <ul className="mt-2 space-y-2">
          {items.map((item) => (
            <li key={item} className="rounded-xl bg-[var(--surface)] px-3 py-2 text-sm text-[var(--muted)]">
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-[var(--muted)]">{empty}</p>
      )}
    </div>
  )
}

function TextField({
  label,
  value,
  onChange,
  type = 'text',
  required,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  required?: boolean
}) {
  return (
    <label className="block">
      <span className="text-sm font-bold">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        className="mt-2 w-full rounded-2xl border border-[var(--line)] bg-white px-4 py-3 text-base outline-none transition focus:border-[var(--accent)] focus:ring-4 focus:ring-[var(--accent-soft)]"
      />
    </label>
  )
}

function FormSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface)] p-5">
      <h3 className="text-xl font-semibold tracking-[-0.03em]">{title}</h3>
      <div className="mt-4 space-y-4">{children}</div>
    </section>
  )
}

function DropZone({ label, file, onFile }: { label: string; file: File | null; onFile: (file: File | null) => void }) {
  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    onFile(event.target.files?.[0] ?? null)
  }

  return (
    <label className="flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-[1.5rem] border border-dashed border-[var(--accent)] bg-[var(--accent-soft)] p-6 text-center transition hover:bg-white">
      <span className="font-semibold">{label}</span>
      <span className="mt-2 text-sm text-[var(--muted)]">
        {file ? `${file.name} · ${Math.round(file.size / 1024)} KB` : 'Drop or choose a PDF'}
      </span>
      <input type="file" accept="application/pdf,.pdf" className="sr-only" onChange={handleFile} />
    </label>
  )
}

function StatusChip({ status, compact = false }: { status: RunStatus; compact?: boolean }) {
  const normalized = String(status || '').toLowerCase()
  const tone = normalized.includes('reject')
    ? 'rejected'
    : normalized.includes('approve')
      ? 'approved'
      : normalized.includes('run') || normalized.includes('start')
        ? 'running'
        : 'pending'

  return (
    <span className={`status-chip status-${tone} ${compact ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm'}`}>
      {tone === 'running' ? <span className="h-2 w-2 animate-pulse rounded-full bg-current" /> : null}
      {tone === 'running' ? 'Running' : sentenceCase(tone)}
    </span>
  )
}

function CountBadges({ hard, pending, flags }: { hard: number; pending: number; flags: number }) {
  return (
    <div className="flex flex-wrap gap-2 font-mono text-xs">
      <span className="count-badge">✕ {hard} hard</span>
      <span className="count-badge">! {pending} pending</span>
      <span className="count-badge">⚑ {flags} flags</span>
    </div>
  )
}

function MethodBadge({ method }: { method: Method }) {
  const normalized = String(method)
  const label = normalized === 'deterministic'
    ? 'RULE'
    : normalized === 'llm'
      ? 'LLM'
      : normalized === 'external_api'
        ? 'LIVE API'
        : normalized === 'simulated_api'
          ? 'SIMULATED'
          : normalized.toUpperCase()
  const className = normalized === 'llm'
    ? 'method-llm'
    : normalized === 'external_api'
      ? 'method-api'
      : normalized === 'simulated_api'
        ? 'method-sim'
        : 'method-rule'
  return <span className={`method-badge ${className}`}>{label}</span>
}

function EvidenceBlock({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <p className="font-mono text-xs uppercase tracking-[0.16em] text-[var(--muted)]">{label}</p>
      <pre className="mt-2 whitespace-pre-wrap rounded-xl bg-[var(--surface)] p-3 font-mono text-sm leading-6 text-[var(--ink)]">
        {value || 'No evidence provided'}
      </pre>
    </div>
  )
}

function Notice({ children, tone }: { children: ReactNode; tone: 'error' | 'warn' }) {
  return (
    <div className={`mx-5 mt-5 rounded-2xl border p-4 text-sm ${tone === 'error' ? 'border-red-200 bg-red-50 text-red-900' : 'border-amber-200 bg-amber-50 text-amber-900'}`}>
      {children}
    </div>
  )
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="p-10 text-center">
      <h3 className="text-2xl font-semibold tracking-[-0.03em]">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-[var(--muted)]">{body}</p>
    </div>
  )
}

function initialGates(): GateState[] {
  return gateDefaults.map((gate) => ({ ...gate, status: 'idle', checks: [] }))
}

function upsertCheck(gates: GateState[], check: CheckResult): GateState[] {
  return gates.map((gate) => {
    if (gate.gate !== Number(check.gate)) return gate
    const key = `${check.gate}-${check.check_id}`
    const checks = gate.checks.filter((existing) => `${existing.gate}-${existing.check_id}` !== key)
    return { ...gate, status: 'running', checks: [...checks, check] }
  })
}

function mergeChecksIntoGates(gates: GateState[], checks: CheckResult[]): GateState[] {
  return checks.reduce((current, check) => upsertCheck(current, check), gates)
}

function parseEvent<T>(event: MessageEvent): T {
  try {
    return JSON.parse(event.data) as T
  } catch {
    return {} as T
  }
}

function sortRuns(runs: SubmissionListItem[]) {
  return [...runs].sort((a, b) => parseApiDate(b.received_at).getTime() - parseApiDate(a.received_at).getTime())
}

/** Backend stores UTC; naive ISO strings must be treated as UTC, not local. */
function parseApiDate(value: string): Date {
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
  return new Date(hasTz ? value : `${value}Z`)
}

function readError(err: unknown, fallback: string) {
  return err instanceof Error ? err.message : fallback
}

function humanizeCheckId(checkId: string) {
  const acronyms = new Set(['gstin', 'ifsc', 'pan', 'api', 'llm'])
  const normalized = checkId.replaceAll('__', ': ').replaceAll('_', ' ')
  return normalized.replace(/\b[a-z0-9]+\b/gi, (word) => {
    const lower = word.toLowerCase()
    if (acronyms.has(lower)) return lower.toUpperCase()
    return word.charAt(0).toUpperCase() + word.slice(1)
  })
}

function sentenceCase(value: string) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1).replaceAll('_', ' ') : ''
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = parseApiDate(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hour12: true,
  }).format(date)
}

function resultIcon(result: CheckStatus) {
  if (result === 'pass') return '✓'
  if (result === 'fail' || result === 'error') return '✕'
  if (result === 'warn') return '!'
  return '▸'
}

export default App
