import { create } from 'zustand'
import type { AgentRoute, Citation, Conversation, RiskLevel } from '@/types/api'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  citations?: Citation[]
  route?: AgentRoute
  riskLevel?: RiskLevel
  interrupted?: boolean
  timestamp: number
}

interface ChatState {
  conversations: Conversation[]
  activeConversationId: string | null
  messages: Message[]
  isGenerating: boolean
  hitlPending: boolean
  hitlMessage: string | null
  setConversations: (conversations: Conversation[]) => void
  setActiveConversationId: (id: string | null) => void
  setMessages: (messages: Message[]) => void
  addMessage: (message: Message) => void
  updateMessage: (id: string, patch: Partial<Message>) => void
  setGenerating: (value: boolean) => void
  setHitlPending: (value: boolean, message?: string | null) => void
  resetChat: () => void
}

export const useChatStore = create<ChatState>((set) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  isGenerating: false,
  hitlPending: false,
  hitlMessage: null,

  setConversations: (conversations) => set({ conversations }),
  setActiveConversationId: (id) => set({ activeConversationId: id }),
  setMessages: (messages) => set({ messages }),
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  updateMessage: (id, patch) =>
    set((state) => ({
      messages: state.messages.map((msg) => (msg.id === id ? { ...msg, ...patch } : msg)),
    })),
  setGenerating: (value) => set({ isGenerating: value }),
  setHitlPending: (value, message = null) => set({ hitlPending: value, hitlMessage: message }),
  resetChat: () =>
    set({
      messages: [],
      activeConversationId: null,
      isGenerating: false,
      hitlPending: false,
      hitlMessage: null,
    }),
}))
