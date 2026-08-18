export interface User {
  id: string
  username: string
  vipLevel: string
  balance: number
  isAdmin: boolean
}

export interface AdminOverview {
  counts: {
    users: number
    experts: number
    documents: number
    chunks: number
  }
  vectorStore: {
    status: 'available' | 'unavailable'
    ragPoints: number | null
    episodicPoints: number | null
  }
}

export interface AdminUser {
  id: string
  username: string
  expertCount: number
  documentCount: number
  activeSessions: number
  diskBytes: number
  createdAt: string
  isAdmin: boolean
}

export interface AdminExpert {
  id: string
  name: string
  ownerId: string
  ownerName: string
  namespace: string
  documentCount: number
  chunkCount: number
  diskBytes: number
  createdAt: string
  deletable: boolean
}

export interface AdminDocument {
  id: string
  fileName: string
  sourceType: string
  ownerId: string
  ownerName: string
  expertId: string
  expertName: string
  chunkCount: number
  diskBytes: number
  createdAt: string
}

export type AdminDeleteAction = 'user' | 'expert' | 'document'

export interface AdminDeleteTarget {
  action: AdminDeleteAction
  userId: string
  expertId?: string
  documentId?: string
}

export interface AdminDeletePlan {
  action: AdminDeleteAction
  userId: string
  username: string
  expertId: string | null
  expertName: string | null
  documentId: string | null
  namespaces: string[]
  sqliteRows: Record<string, number>
  qdrantPoints: Record<string, number>
  filesystemTargets: Array<{ path: string; kind: string }>
}

export type ExpertKind = 'aggregate' | 'shared' | 'private'

export interface Expert {
  id: string
  name: string
  kind: ExpertKind
  deletable: boolean
}

export interface DocumentItem {
  id: string
  fileName: string
  sourceType: string
  expertId: string
  expertName: string
  createdAt: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  expertId: string
  expertName: string
  createdAt: string
}

export interface MonthlyPersonalReport {
  period: {
    startTime: string
    endTime: string
    days: number
  }
  generatedAt: string
  reportMonth: string
  metrics: {
    conversationCount: number
    conversationsUsed: number
    expertsUsed: number
  }
  summary: string
  expertSummaries: Array<{
    expert: { id: string; name: string }
    conversationCount: number
    conversationsUsed: number
    summary: string
  }>
}
