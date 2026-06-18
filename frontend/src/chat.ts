import { ApiError, BASE, apiJson } from './api'

export interface Brief {
  topic: string
  brand: string
  tone: string
  audience: string
  length: string
}

export interface Conversation {
  id: number
  title: string
  brief: Brief | null
  created_at: string
}

export interface CriterionResult {
  passed: boolean
  comment: string
}

export interface Critique {
  approved: boolean
  feedback: string
  spelling: CriterionResult
  grammar: CriterionResult
  accuracy: CriterionResult
  tone_brand_audience: CriterionResult
  length: CriterionResult
}

export interface Message {
  id: number
  role: 'user' | 'assistant'
  content: string
  critique: Critique | null
  iterations: number | null
  created_at: string
}

export type StreamEvent =
  | { type: 'writer_start'; iteration: number }
  | { type: 'token'; text: string }
  | { type: 'critic_start' }
  | { type: 'critique'; approved: boolean; feedback: string }
  | {
      type: 'done'
      user_message_id: number
      assistant_message_id: number
      iterations: number
    }

export function createConversation(title?: string): Promise<Conversation> {
  return apiJson<Conversation>('/chat/conversations', {
    method: 'POST',
    body: { title },
  })
}

export function listConversations(): Promise<Conversation[]> {
  return apiJson<Conversation[]>('/chat/conversations')
}

export function listMessages(conversationId: number): Promise<Message[]> {
  return apiJson<Message[]>(`/chat/conversations/${conversationId}/messages`)
}

async function postSSE(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!response.ok || response.body === null) {
    throw new ApiError(response.status, 'Stream failed to start')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''

    for (const frame of frames) {
      const line = frame.trim()
      if (!line.startsWith('data:')) continue
      const json = line.slice(5).trim()
      if (json) onEvent(JSON.parse(json) as StreamEvent)
    }
  }
}

export function streamPost(
  conversationId: number,
  brief: Brief,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  return postSSE(`/chat/conversations/${conversationId}/stream`, brief, onEvent)
}

export function streamRefine(
  conversationId: number,
  instruction: string,
  onEvent: (event: StreamEvent) => void,
): Promise<void> {
  return postSSE(
    `/chat/conversations/${conversationId}/refine`,
    { instruction },
    onEvent,
  )
}
