<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  IconAlertTriangle,
  IconDatabase,
  IconFileText,
  IconRefresh,
  IconSearch,
  IconTrash,
  IconUserStar,
  IconUsers,
} from '@tabler/icons-vue'

import { api, ApiError } from '@/api'
import BaseModal from '@/components/BaseModal.vue'
import StatusNotice from '@/components/StatusNotice.vue'
import { useI18n } from '@/i18n'
import type {
  AdminDeletePlan,
  AdminDeleteTarget,
  AdminDocument,
  AdminExpert,
  AdminOverview,
  AdminUser,
} from '@/types'

type AdminTab = 'users' | 'experts' | 'documents'

const PAGE_SIZE = 25
const { localeTag, t } = useI18n()
const activeTab = ref<AdminTab>('users')
const overview = ref<AdminOverview | null>(null)
const users = ref<AdminUser[]>([])
const experts = ref<AdminExpert[]>([])
const documents = ref<AdminDocument[]>([])
const total = ref(0)
const offset = ref(0)
const query = ref('')
const ownerFilter = ref('')
const expertFilter = ref('')
const loading = ref(false)
const status = ref('')
const statusTone = ref<'success' | 'error'>('success')
const deleteOpen = ref(false)
const deleteTarget = ref<AdminDeleteTarget | null>(null)
const deletePlan = ref<AdminDeletePlan | null>(null)
const confirmationText = ref('')
const confirmation = ref('')
const previewing = ref(false)
const deleting = ref(false)

const vectorCount = computed(() => {
  const vectorStore = overview.value?.vectorStore
  if (!vectorStore || vectorStore.status === 'unavailable') return null
  return (vectorStore.ragPoints ?? 0) + (vectorStore.episodicPoints ?? 0)
})

const page = computed(() => Math.floor(offset.value / PAGE_SIZE) + 1)
const canNext = computed(() => offset.value + PAGE_SIZE < total.value)
const modalTitle = computed(() => {
  if (deleteTarget.value?.action === 'user') return t('admin.confirmUser')
  if (deleteTarget.value?.action === 'expert') return t('admin.confirmExpert')
  return t('admin.confirmDocument')
})
const sqliteRows = computed(() => sum(deletePlan.value?.sqliteRows))
const qdrantPoints = computed(() => sum(deletePlan.value?.qdrantPoints))

function sum(values: Record<string, number> | undefined) {
  return Object.values(values ?? {}).reduce((totalValue, value) => totalValue + value, 0)
}

function formatDate(value: string) {
  return value ? new Date(value).toLocaleString(localeTag.value) : '—'
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let size = value
  let unitIndex = -1
  do {
    size /= 1024
    unitIndex += 1
  } while (size >= 1024 && unitIndex < units.length - 1)
  return `${new Intl.NumberFormat(localeTag.value, { maximumFractionDigits: 1 }).format(size)} ${units[unitIndex]}`
}

async function loadOverview() {
  overview.value = await api<AdminOverview>('/admin/overview')
}

async function loadRows() {
  loading.value = true
  status.value = ''
  const parameters = new URLSearchParams({
    query: query.value.trim(),
    limit: String(PAGE_SIZE),
    offset: String(offset.value),
  })
  if (activeTab.value !== 'users' && ownerFilter.value.trim()) {
    parameters.set('user_id', ownerFilter.value.trim())
  }
  if (activeTab.value === 'documents' && expertFilter.value.trim()) {
    parameters.set('expert_id', expertFilter.value.trim())
  }
  try {
    if (activeTab.value === 'users') {
      const payload = await api<{ items: AdminUser[]; total: number }>(`/admin/users?${parameters}`)
      users.value = payload.items
      total.value = payload.total
    } else if (activeTab.value === 'experts') {
      const payload = await api<{ items: AdminExpert[]; total: number }>(`/admin/experts?${parameters}`)
      experts.value = payload.items
      total.value = payload.total
    } else {
      const payload = await api<{ items: AdminDocument[]; total: number }>(`/admin/documents?${parameters}`)
      documents.value = payload.items
      total.value = payload.total
    }
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('common.requestFailed')
    statusTone.value = 'error'
  } finally {
    loading.value = false
  }
}

async function refreshAll() {
  try {
    await Promise.all([loadOverview(), loadRows()])
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('common.requestFailed')
    statusTone.value = 'error'
  }
}

async function previewDelete(target: AdminDeleteTarget) {
  deleteTarget.value = target
  deletePlan.value = null
  confirmation.value = ''
  confirmationText.value = ''
  deleteOpen.value = true
  previewing.value = true
  try {
    const payload = await api<{ plan: AdminDeletePlan; confirmationText: string }>(
      '/admin/deletions/preview',
      { method: 'POST', body: JSON.stringify(target) },
    )
    deletePlan.value = payload.plan
    confirmationText.value = payload.confirmationText
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('admin.previewFailed')
    statusTone.value = 'error'
    deleteOpen.value = false
  } finally {
    previewing.value = false
  }
}

async function executeDelete() {
  if (!deleteTarget.value || confirmation.value !== confirmationText.value) return
  deleting.value = true
  try {
    await api('/admin/deletions/execute', {
      method: 'POST',
      body: JSON.stringify({ ...deleteTarget.value, confirmation: confirmation.value }),
    })
    deleteOpen.value = false
    deleteTarget.value = null
    status.value = t('admin.deleteSucceeded')
    statusTone.value = 'success'
    if (offset.value >= PAGE_SIZE && offset.value >= total.value - 1) offset.value -= PAGE_SIZE
    await refreshAll()
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('admin.deleteFailed')
    statusTone.value = 'error'
  } finally {
    deleting.value = false
  }
}

function closeDelete() {
  if (!deleting.value) deleteOpen.value = false
}

function changePage(direction: -1 | 1) {
  offset.value = Math.max(0, offset.value + direction * PAGE_SIZE)
  void loadRows()
}

watch(activeTab, () => {
  offset.value = 0
  query.value = ''
  ownerFilter.value = ''
  expertFilter.value = ''
  void loadRows()
})

onMounted(refreshAll)
</script>

<template>
  <div class="view admin-view">
    <header class="view-header admin-header">
      <div>
        <h1>{{ t('admin.title') }}</h1>
        <p>{{ t('admin.description') }}</p>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="refreshAll">
        <IconRefresh :size="18" />{{ t('admin.refresh') }}
      </button>
    </header>

    <section class="admin-metrics" aria-label="Platform totals">
      <article>
        <IconUsers :size="27" />
        <span>{{ t('admin.users') }}</span>
        <strong>{{ overview?.counts.users ?? '—' }}</strong>
        <small>{{ t('admin.totalUsers') }}</small>
      </article>
      <article>
        <IconUserStar :size="27" />
        <span>{{ t('admin.experts') }}</span>
        <strong>{{ overview?.counts.experts ?? '—' }}</strong>
        <small>{{ t('admin.totalExperts') }}</small>
      </article>
      <article>
        <IconFileText :size="27" />
        <span>{{ t('admin.documents') }}</span>
        <strong>{{ overview?.counts.documents ?? '—' }}</strong>
        <small>{{ t('admin.totalDocuments') }}</small>
      </article>
      <article>
        <IconDatabase :size="27" />
        <span>{{ t('admin.vectorIndex') }}</span>
        <strong>{{ vectorCount ?? t('admin.unavailable') }}</strong>
        <small>{{ t('admin.totalVectors') }}</small>
      </article>
    </section>

    <StatusNotice :message="status" :tone="statusTone" />

    <section class="admin-workspace">
      <div class="admin-tabs" role="tablist">
        <button type="button" :class="{ active: activeTab === 'users' }" @click="activeTab = 'users'">{{ t('admin.users') }}</button>
        <button type="button" :class="{ active: activeTab === 'experts' }" @click="activeTab = 'experts'">{{ t('admin.experts') }}</button>
        <button type="button" :class="{ active: activeTab === 'documents' }" @click="activeTab = 'documents'">{{ t('admin.documents') }}</button>
      </div>

      <form class="admin-toolbar" @submit.prevent="offset = 0; loadRows()">
        <label class="search-field">
          <IconSearch :size="18" />
          <input
            v-model="query"
            :placeholder="activeTab === 'users' ? t('admin.searchUsers') : activeTab === 'experts' ? t('admin.searchExperts') : t('admin.searchDocuments')"
          />
        </label>
        <input v-if="activeTab !== 'users'" v-model="ownerFilter" :placeholder="t('admin.ownerFilter')" />
        <input v-if="activeTab === 'documents'" v-model="expertFilter" :placeholder="t('admin.expertFilter')" />
        <button class="secondary-button" type="submit">{{ t('experts.search') }}</button>
      </form>

      <div class="admin-table-scroll">
        <table v-if="activeTab === 'users'" class="admin-table">
          <thead><tr><th>{{ t('admin.username') }}</th><th>{{ t('admin.userId') }}</th><th>{{ t('admin.expertCount') }}</th><th>{{ t('admin.documentCount') }}</th><th>{{ t('admin.diskUsage') }}</th><th>{{ t('admin.sessions') }}</th><th>{{ t('admin.registeredAt') }}</th><th>{{ t('admin.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td><strong>{{ user.username }}</strong></td><td class="mono-cell">{{ user.id }}</td><td>{{ user.expertCount }}</td><td>{{ user.documentCount }}</td><td>{{ formatBytes(user.diskBytes) }}</td><td>{{ user.activeSessions }}</td><td>{{ formatDate(user.createdAt) }}</td>
              <td><span v-if="user.isAdmin" class="protected-label">{{ t('admin.protected') }}</span><button v-else class="danger-link" type="button" @click="previewDelete({ action: 'user', userId: user.id })"><IconTrash :size="16" />{{ t('common.delete') }}</button></td>
            </tr>
          </tbody>
        </table>

        <table v-else-if="activeTab === 'experts'" class="admin-table">
          <thead><tr><th>{{ t('admin.expertName') }}</th><th>{{ t('admin.expertId') }}</th><th>{{ t('admin.owner') }}</th><th>{{ t('admin.namespace') }}</th><th>{{ t('admin.documentCount') }}</th><th>{{ t('admin.chunks') }}</th><th>{{ t('admin.diskUsage') }}</th><th>{{ t('admin.createdAt') }}</th><th>{{ t('admin.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="expert in experts" :key="`${expert.ownerId}-${expert.id}`">
              <td><strong>{{ expert.name }}</strong></td><td class="mono-cell">{{ expert.id }}</td><td>{{ expert.ownerName }}<small class="cell-detail">{{ expert.ownerId }}</small></td><td class="mono-cell">{{ expert.namespace }}</td><td>{{ expert.documentCount }}</td><td>{{ expert.chunkCount }}</td><td>{{ formatBytes(expert.diskBytes) }}</td><td>{{ formatDate(expert.createdAt) }}</td>
              <td><button v-if="expert.deletable" class="danger-link" type="button" @click="previewDelete({ action: 'expert', userId: expert.ownerId, expertId: expert.id })"><IconTrash :size="16" />{{ t('common.delete') }}</button><span v-else class="protected-label">{{ t('admin.protected') }}</span></td>
            </tr>
          </tbody>
        </table>

        <table v-else class="admin-table">
          <thead><tr><th>{{ t('admin.fileName') }}</th><th>{{ t('admin.documentId') }}</th><th>{{ t('admin.type') }}</th><th>{{ t('admin.owner') }}</th><th>{{ t('admin.expert') }}</th><th>{{ t('admin.chunks') }}</th><th>{{ t('admin.diskUsage') }}</th><th>{{ t('admin.createdAt') }}</th><th>{{ t('admin.actions') }}</th></tr></thead>
          <tbody>
            <tr v-for="document in documents" :key="`${document.ownerId}-${document.expertId}-${document.id}`">
              <td><strong>{{ document.fileName }}</strong></td><td class="mono-cell">{{ document.id }}</td><td>{{ document.sourceType.toUpperCase() }}</td><td>{{ document.ownerName }}<small class="cell-detail">{{ document.ownerId }}</small></td><td>{{ document.expertName }}<small class="cell-detail">{{ document.expertId }}</small></td><td>{{ document.chunkCount }}</td><td>{{ formatBytes(document.diskBytes) }}</td><td>{{ formatDate(document.createdAt) }}</td>
              <td><button class="danger-link" type="button" @click="previewDelete({ action: 'document', userId: document.ownerId, expertId: document.expertId, documentId: document.id })"><IconTrash :size="16" />{{ t('common.delete') }}</button></td>
            </tr>
          </tbody>
        </table>

        <div v-if="loading" class="admin-empty">{{ t('admin.loading') }}</div>
        <div v-else-if="total === 0" class="admin-empty">{{ t('admin.empty') }}</div>
      </div>

      <footer class="admin-pagination">
        <span>{{ t('admin.total', { count: total }) }}</span>
        <div>
          <button class="secondary-button" type="button" :disabled="offset === 0" @click="changePage(-1)">{{ t('admin.previous') }}</button>
          <span>{{ t('admin.page', { page }) }}</span>
          <button class="secondary-button" type="button" :disabled="!canNext" @click="changePage(1)">{{ t('admin.next') }}</button>
        </div>
      </footer>
    </section>

    <BaseModal :open="deleteOpen" :title="modalTitle" :description="t('admin.irreversible')" @close="closeDelete">
      <div v-if="previewing" class="admin-preview-loading">{{ t('admin.previewing') }}</div>
      <template v-else-if="deletePlan">
        <div class="admin-impact-warning"><IconAlertTriangle :size="20" /><span>{{ confirmationText }}</span></div>
        <div class="admin-impact-grid">
          <article><IconDatabase :size="21" /><span>{{ t('admin.sqlite') }}</span><strong>{{ t('admin.rows', { count: sqliteRows }) }}</strong><small>{{ Object.entries(deletePlan.sqliteRows).filter(([, count]) => count).map(([name, count]) => `${name}: ${count}`).join(' · ') || '—' }}</small></article>
          <article><IconDatabase :size="21" /><span>{{ t('admin.qdrant') }}</span><strong>{{ t('admin.points', { count: qdrantPoints }) }}</strong><small>{{ Object.entries(deletePlan.qdrantPoints).map(([name, count]) => `${name}: ${count}`).join(' · ') }}</small></article>
          <article><IconFileText :size="21" /><span>{{ t('admin.filesystem') }}</span><strong>{{ t('admin.targets', { count: deletePlan.filesystemTargets.length }) }}</strong><small>{{ deletePlan.filesystemTargets.map((target) => target.kind).join(' · ') || '—' }}</small></article>
        </div>
        <label class="admin-confirmation">
          <span>{{ t('admin.confirmInstruction', { target: confirmationText }) }}</span>
          <input v-model="confirmation" :placeholder="t('admin.confirmPlaceholder')" autocomplete="off" />
        </label>
        <div class="confirm-actions">
          <button class="secondary-button" type="button" :disabled="deleting" @click="closeDelete">{{ t('common.cancel') }}</button>
          <button class="danger-button" type="button" :disabled="deleting || confirmation !== confirmationText" @click="executeDelete">{{ deleting ? t('admin.deleting') : t('common.confirmDelete') }}</button>
        </div>
      </template>
    </BaseModal>
  </div>
</template>
