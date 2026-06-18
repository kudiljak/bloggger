import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { useAuth } from './auth-context'
import { ApiError } from './api'
import {
  createConversation,
  listConversations,
  listMessages,
  streamPost,
  streamRefine,
} from './chat'
import type { Brief, Conversation, StreamEvent } from './chat'
import './Chat.css'

type Status = 'idle' | 'writing' | 'reviewing' | 'done'

interface Round {
  iteration: number
  approved: boolean
  feedback: string
}

const LENGTHS = [
  'Short (about 150 words)',
  'Medium (about 400 words)',
  'Long (about 800 words)',
]

export default function Chat() {
  const navigate = useNavigate()
  const { user, signOut } = useAuth()

  const [brief, setBrief] = useState<Brief>({
    topic: '',
    brand: '',
    tone: 'friendly and warm',
    audience: '',
    length: LENGTHS[1],
  })
  const [status, setStatus] = useState<Status>('idle')
  const [iteration, setIteration] = useState(0)
  const [post, setPost] = useState('')
  const [rounds, setRounds] = useState<Round[]>([])
  const [drafts, setDrafts] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [conversationId, setConversationId] = useState<number | null>(null)
  const [instruction, setInstruction] = useState('')
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const targetRef = useRef('')
  const revealedRef = useRef(0)
  const timerRef = useRef<number | null>(null)

  const busy = status === 'writing' || status === 'reviewing'

  useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current)
    }
  }, [])

  async function loadConversations() {
    try {
      setConversations(await listConversations())
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) navigate('/login')
    }
  }

  useEffect(() => {
    loadConversations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function newPost() {
    setConversationId(null)
    setPost('')
    setRounds([])
    setDrafts(0)
    setError(null)
    setStatus('idle')
    setInstruction('')
    setBrief({
      topic: '',
      brand: '',
      tone: 'friendly and warm',
      audience: '',
      length: LENGTHS[1],
    })
  }

  async function openConversation(conversation: Conversation) {
    setError(null)
    setStatus('idle')
    setInstruction('')
    setConversationId(conversation.id)
    if (conversation.brief) setBrief(conversation.brief)
    try {
      const messages = await listMessages(conversation.id)
      const lastPost = [...messages]
        .reverse()
        .find((m) => m.role === 'assistant')
      if (lastPost) {
        setPost(lastPost.content)
        setDrafts(lastPost.iterations ?? 0)
        setRounds(
          lastPost.critique
            ? [
                {
                  iteration: lastPost.iterations ?? 1,
                  approved: lastPost.critique.approved,
                  feedback: lastPost.critique.feedback,
                },
              ]
            : [],
        )
        setStatus('done')
      } else {
        setPost('')
        setRounds([])
        setDrafts(0)
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) navigate('/login')
    }
  }

  function update(field: keyof Brief, value: string) {
    setBrief((b) => ({ ...b, [field]: value }))
  }

  async function handleSignOut() {
    await signOut()
    navigate('/login')
  }

  async function drive(
    run: (onEvent: (event: StreamEvent) => void) => Promise<void>,
  ) {
    setError(null)
    setPost('')
    setRounds([])
    setDrafts(0)
    setIteration(1)
    setStatus('writing')

    targetRef.current = ''
    revealedRef.current = 0
    let streamEnded = false

    if (timerRef.current !== null) window.clearInterval(timerRef.current)
    timerRef.current = window.setInterval(() => {
      const target = targetRef.current
      if (revealedRef.current < target.length) {
        const remaining = target.length - revealedRef.current
        const step = Math.max(2, Math.ceil(remaining / 25))
        revealedRef.current += step
        setPost(target.slice(0, revealedRef.current))
      } else if (streamEnded) {
        window.clearInterval(timerRef.current!)
        timerRef.current = null
      }
    }, 16)

    let currentIteration = 1
    try {
      await run((event) => {
        switch (event.type) {
          case 'writer_start':
            currentIteration = event.iteration
            setIteration(event.iteration)
            setStatus('writing')
            targetRef.current = ''
            revealedRef.current = 0
            setPost('')
            break
          case 'token':
            targetRef.current += event.text
            break
          case 'critic_start':
            setStatus('reviewing')
            break
          case 'critique':
            setRounds((r) => [
              ...r,
              {
                iteration: currentIteration,
                approved: event.approved,
                feedback: event.feedback,
              },
            ])
            break
          case 'done':
            setDrafts(event.iterations)
            setStatus('done')
            break
        }
      })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        navigate('/login')
        return
      }
      setError('Generation failed. Check that the server is running.')
      setStatus('idle')
    } finally {
      streamEnded = true
    }
  }

  async function generate() {
    await drive(async (onEvent) => {
      const conversation = await createConversation(brief.topic || 'Untitled')
      setConversationId(conversation.id)
      await streamPost(conversation.id, brief, onEvent)
    })
    loadConversations()
  }

  function refine() {
    const text = instruction.trim()
    if (conversationId === null || !text) return
    setInstruction('')
    return drive((onEvent) => streamRefine(conversationId, text, onEvent))
  }

  const statusText =
    status === 'writing'
      ? `Writing draft… (round ${iteration})`
      : status === 'reviewing'
        ? 'Quality-checking…'
        : status === 'done'
          ? 'Done'
          : 'Ready'

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header-left">
          <button
            className="icon-btn"
            onClick={() => setSidebarOpen((o) => !o)}
            aria-label="Toggle posts"
            title="Your posts"
          >
            ☰
          </button>
          <div className="app-brand">
            <div className="app-mark">B</div>
            <div className="app-wordmark">Blogger</div>
          </div>
        </div>
        <div className="app-user">
          <span>{user?.email}</span>
          <button className="btn btn-ghost" onClick={handleSignOut}>
            Sign out
          </button>
        </div>
      </header>

      <div className="layout">
        {sidebarOpen && (
          <aside className="sidebar">
            <button className="btn btn-primary sidebar-new" onClick={newPost}>
              + New post
            </button>
            <div className="sidebar-label">Your posts</div>
            {conversations.length === 0 ? (
              <p className="sidebar-empty">No posts yet.</p>
            ) : (
              <ul className="conv-list">
                {conversations.map((c) => (
                  <li
                    key={c.id}
                    className={`conv-item ${
                      c.id === conversationId ? 'active' : ''
                    }`}
                    onClick={() => openConversation(c)}
                  >
                    <span className="conv-title">{c.title}</span>
                    <span className="conv-date">
                      {new Date(c.created_at).toLocaleDateString()}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        )}

        <div className="workspace">
          <section className="card panel">
            <h2 className="panel-title">Brief</h2>
            <p className="panel-hint">Tell Blogger what to write.</p>

            <div className="brief-form">
              <label className="field">
                Topic
                <input
                  value={brief.topic}
                  onChange={(e) => update('topic', e.target.value)}
                  placeholder="Why cold brew tastes smoother"
                />
              </label>
              <label className="field">
                Brand
                <input
                  value={brief.brand}
                  onChange={(e) => update('brand', e.target.value)}
                  placeholder="Brewly"
                />
              </label>
              <label className="field">
                Tone
                <input
                  value={brief.tone}
                  onChange={(e) => update('tone', e.target.value)}
                  placeholder="friendly and warm"
                />
              </label>
              <label className="field">
                Audience
                <input
                  value={brief.audience}
                  onChange={(e) => update('audience', e.target.value)}
                  placeholder="coffee beginners"
                />
              </label>
              <label className="field">
                Length
                <select
                  value={brief.length}
                  onChange={(e) => update('length', e.target.value)}
                >
                  {LENGTHS.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </select>
              </label>

              <button
                className="btn btn-primary generate-btn"
                onClick={generate}
                disabled={busy || !brief.topic || !brief.brand}
              >
                {busy ? 'Generating…' : 'Generate post'}
              </button>
            </div>
          </section>

          <section className="card panel output">
            <div className="status-bar">
              <span className={`status-dot ${busy ? 'live' : ''}`} />
              {statusText}
            </div>

            <div className="post">
              {post && <ReactMarkdown>{post}</ReactMarkdown>}
              {status === 'writing' && <span className="caret" />}
            </div>

            {error && <div className="error-box">{error}</div>}

            {rounds.length > 0 && (
              <div className="qc">
                <div className="qc-title">Quality control</div>
                {drafts > 0 && (
                  <div className="qc-summary">
                    {drafts === 1
                      ? 'Approved on the first draft — no revisions needed.'
                      : `Final after ${drafts} drafts (${drafts - 1} revision${
                          drafts - 1 === 1 ? '' : 's'
                        }).`}
                  </div>
                )}
                {rounds.map((round) => (
                  <div className="qc-round" key={round.iteration}>
                    <span
                      className={`qc-badge ${round.approved ? 'ok' : 'revise'}`}
                    >
                      {round.approved ? 'Approved' : 'Revise'}
                    </span>
                    <span className="qc-feedback">{round.feedback}</span>
                  </div>
                ))}
              </div>
            )}

            {status === 'done' && conversationId !== null && (
              <div className="refine">
                <input
                  value={instruction}
                  onChange={(e) => setInstruction(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') refine()
                  }}
                  placeholder="Ask for a change… e.g. make it funnier, add a section on pricing"
                />
                <button
                  className="btn btn-primary"
                  onClick={refine}
                  disabled={!instruction.trim()}
                >
                  Refine
                </button>
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  )
}
