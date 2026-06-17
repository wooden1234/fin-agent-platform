import { useRef } from 'react'
import { SSEClient } from '@/services/sse/SSEClient'
import { getToken } from '@/services/api/client'
import { useChatStore } from '@/stores/useChatStore'
import type { AgentSSEEvent } from '@/types/events'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

function buildAgentForm(fields: Record<string, string>): FormData {
  const form = new FormData()
  Object.entries(fields).forEach(([key, value]) => {
    if (value) form.append(key, value)
  })
  return form
}

function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export function useAgentChat() {
  const clientRef = useRef<SSEClient | null>(null)
  const {
    activeConversationId,
    setActiveConversationId,
    addMessage,
    updateMessage,
    setGenerating,
    setHitlPending,
  } = useChatStore()

  const runStream = async (
    endpoint: '/api/agent/query' | '/api/agent/resume',
    fields: Record<string, string>,
  ) => {
    let contentBuffer = ''
    let assistantMessageId = ''

    const handleEvent = (event: AgentSSEEvent) => {
      if (event.type === 'token') {
        contentBuffer += event.content

        if (!assistantMessageId) {
          assistantMessageId = `assistant-${Date.now()}`
          addMessage({
            id: assistantMessageId,
            role: 'assistant',
            content: contentBuffer,
            timestamp: Date.now(),
          })
        } else {
          updateMessage(assistantMessageId, { content: contentBuffer })
        }
      }

      if (event.type === 'meta') {
        if (assistantMessageId) {
          updateMessage(assistantMessageId, {
            route: event.route,
            riskLevel: event.risk_level,
          })
        }
      }

      if (event.type === 'done') {
        if (assistantMessageId) {
          updateMessage(assistantMessageId, {
            content: contentBuffer,
            citations: event.citations,
            route: event.route,
            riskLevel: event.risk_level,
          })
        }
        setGenerating(false)
        setHitlPending(false)
      }

      if (event.type === 'interrupt') {
        setHitlPending(true, event.message ?? '该问题已升级人工处理，请稍候或输入补充说明后恢复。')
        if (assistantMessageId) {
          updateMessage(assistantMessageId, {
            content: contentBuffer || event.message || '已转人工客服，请稍候…',
            interrupted: true,
          })
        } else {
          addMessage({
            id: `assistant-hitl-${Date.now()}`,
            role: 'assistant',
            content: event.message || '已转人工客服，请稍候…',
            interrupted: true,
            timestamp: Date.now(),
          })
        }
        setGenerating(false)
      }

      if (event.type === 'error') {
        if (!assistantMessageId) {
          addMessage({
            id: `assistant-error-${Date.now()}`,
            role: 'assistant',
            content: `抱歉，服务暂时不可用：${event.message}`,
            timestamp: Date.now(),
          })
        } else {
          updateMessage(assistantMessageId, {
            content: contentBuffer || `抱歉，服务暂时不可用：${event.message}`,
          })
        }
        setGenerating(false)
        setHitlPending(false)
      }
    }

    const client = new SSEClient({
      url: `${API_BASE_URL}${endpoint}`,
      headers: authHeaders(),
      body: buildAgentForm(fields),
      onConversationId: (conversationId) => {
        if (!activeConversationId) {
          setActiveConversationId(conversationId)
        }
      },
      onEvent: handleEvent,
      onError: (error) => {
        addMessage({
          id: `assistant-error-${Date.now()}`,
          role: 'assistant',
          content: `网络错误：${error.message}`,
          timestamp: Date.now(),
        })
        setGenerating(false)
        setHitlPending(false)
      },
      onComplete: () => {
        const stillGenerating = useChatStore.getState().isGenerating
        if (stillGenerating) {
          setGenerating(false)
        }
      },
    })

    clientRef.current = client
    await client.start()
    clientRef.current = null
  }

  const sendQuery = async (query: string) => {
    const trimmed = query.trim()
    if (!trimmed) return

    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    })

    setGenerating(true)
    setHitlPending(false)

    const fields: Record<string, string> = { query: trimmed }
    if (activeConversationId) {
      fields.conversation_id = activeConversationId
    }

    await runStream('/api/agent/query', fields)
  }

  const resumeAgent = async (humanInput: string) => {
    if (!activeConversationId) return

    const trimmed = humanInput.trim()
    if (!trimmed) return

    addMessage({
      id: `user-${Date.now()}`,
      role: 'user',
      content: `[人工补充] ${trimmed}`,
      timestamp: Date.now(),
    })

    setGenerating(true)
    setHitlPending(false)

    await runStream('/api/agent/resume', {
      conversation_id: activeConversationId,
      query: trimmed,
    })
  }

  const cancelStream = () => {
    clientRef.current?.cancel()
    clientRef.current = null
    setGenerating(false)
  }

  return { sendQuery, resumeAgent, cancelStream }
}
