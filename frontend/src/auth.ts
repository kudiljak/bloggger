import { apiForm, apiJson } from './api'

export interface User {
  id: number
  email: string
  created_at: string
}

interface MessageResponse {
  message: string
}

export function register(email: string, password: string): Promise<User> {
  return apiJson<User>('/auth/register', {
    method: 'POST',
    body: { email, password },
  })
}

export function login(email: string, password: string): Promise<MessageResponse> {
  return apiForm<MessageResponse>('/auth/login', {
    username: email,
    password,
  })
}

export function logout(): Promise<MessageResponse> {
  return apiJson<MessageResponse>('/auth/logout', { method: 'POST' })
}

export function me(): Promise<User> {
  return apiJson<User>('/auth/me')
}
