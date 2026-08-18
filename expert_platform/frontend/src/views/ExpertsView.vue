<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  IconFile,
  IconFileUpload,
  IconPlus,
  IconSearch,
  IconTrash,
  IconUsersGroup,
} from '@tabler/icons-vue'

import { api, ApiError } from '@/api'
import BaseModal from '@/components/BaseModal.vue'
import StatusNotice from '@/components/StatusNotice.vue'
import { useI18n } from '@/i18n'
import { useSessionStore } from '@/stores/session'
import type { DocumentItem, Expert } from '@/types'

const session = useSessionStore()
const { expertName, localeTag, t } = useI18n()
const PAGE_SIZE = 10
const browseExpertId = ref('__all__')
const query = ref('')
const documents = ref<DocumentItem[]>([])
const total = ref(0)
const offset = ref(0)
const status = ref('')
const statusTone = ref<'success' | 'error'>('success')
const loading = ref(false)
const managerOpen = ref(false)
const createOpen = ref(false)
const newExpertName = ref('')
const pendingDelete = ref<Expert | null>(null)
const pendingDocument = ref<DocumentItem | null>(null)
const fileInput = ref<HTMLInputElement>()

const writeExpert = computed(() =>
  session.concreteExperts.find((expert) => expert.id === browseExpertId.value),
)
const page = computed(() => Math.floor(offset.value / PAGE_SIZE) + 1)
const canNext = computed(() => offset.value + PAGE_SIZE < total.value)

async function loadContent() {
  loading.value = true
  status.value = ''
  try {
    const parameters = new URLSearchParams({
      expert_id: browseExpertId.value,
      query: query.value,
      limit: String(PAGE_SIZE),
      offset: String(offset.value),
    })
    const payload = await api<{ items: DocumentItem[]; total: number }>(`/documents?${parameters}`)
    documents.value = payload.items
    total.value = payload.total
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('experts.readFailed')
    statusTone.value = 'error'
  } finally {
    loading.value = false
  }
}

async function createExpert() {
  if (!newExpertName.value.trim()) return
  try {
    const payload = await api<{ item: Expert }>('/experts', {
      method: 'POST',
      body: JSON.stringify({ name: newExpertName.value }),
    })
    await session.refreshExperts()
    session.selectExpert(payload.item.id)
    newExpertName.value = ''
    createOpen.value = false
    status.value = t('experts.created', { expert: payload.item.name })
    statusTone.value = 'success'
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('experts.createFailed')
    statusTone.value = 'error'
  }
}

async function deleteExpert() {
  if (!pendingDelete.value) return
  try {
    await api(`/experts/${pendingDelete.value.id}`, {
      method: 'DELETE',
      body: JSON.stringify({ confirmed: true }),
    })
    pendingDelete.value = null
    await session.refreshExperts()
    offset.value = 0
    await loadContent()
    status.value = t('experts.expertDeleted')
    statusTone.value = 'success'
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('experts.deleteFailed')
    statusTone.value = 'error'
  }
}

async function upload(file: File) {
  if (!writeExpert.value) return
  const form = new FormData()
  form.append('expert_id', writeExpert.value.id)
  form.append('file', file)
  loading.value = true
  try {
    const payload = await api<{ result: { message: string } }>('/documents', { method: 'POST', body: form })
    status.value = payload.result.message
    statusTone.value = 'success'
    browseExpertId.value = writeExpert.value.id
    await loadContent()
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('experts.uploadFailed')
    statusTone.value = 'error'
  } finally {
    loading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

async function deleteDocument() {
  if (!pendingDocument.value) return
  try {
    await api(
      `/documents/${encodeURIComponent(pendingDocument.value.id)}?expert_id=${encodeURIComponent(pendingDocument.value.expertId)}&confirmed=true`,
      { method: 'DELETE' },
    )
    pendingDocument.value = null
    status.value = t('experts.documentDeleted')
    statusTone.value = 'success'
    if (offset.value >= PAGE_SIZE && offset.value >= total.value - 1) offset.value -= PAGE_SIZE
    await loadContent()
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('experts.deleteFailed')
    statusTone.value = 'error'
  }
}

function searchDocuments() {
  offset.value = 0
  void loadContent()
}

function changePage(direction: -1 | 1) {
  offset.value = Math.max(0, offset.value + direction * PAGE_SIZE)
  void loadContent()
}

watch(browseExpertId, () => {
  offset.value = 0
  void loadContent()
})
onMounted(loadContent)
</script>

<template>
  <div class="view experts-view">
    <header class="view-header">
      <div>
        <p class="section-label">{{ t('nav.experts') }}</p>
        <h1>{{ t('experts.title') }}</h1>
        <p>{{ t('experts.description') }}</p>
      </div>
      <button class="secondary-button" type="button" @click="managerOpen = true">
        <IconUsersGroup :size="19" />{{ t('experts.manage') }}
      </button>
    </header>

    <section class="expert-toolbar">
      <label>
        <span>{{ t('experts.browseScope') }}</span>
        <select v-model="browseExpertId">
          <option v-for="expert in session.experts" :key="expert.id" :value="expert.id">{{ expertName(expert) }}</option>
        </select>
      </label>
      <label class="search-field">
        <IconSearch :size="19" />
        <input v-model="query" :placeholder="t('experts.searchPlaceholder')" @keyup.enter="searchDocuments" />
      </label>
      <button class="secondary-button" type="button" @click="searchDocuments">{{ t('experts.search') }}</button>
    </section>

    <StatusNotice :message="status" :tone="statusTone" />

    <section class="data-panel">
      <div class="data-panel-header">
        <div>
          <h2>{{ t('experts.documents') }}</h2>
          <p>{{ loading ? t('experts.loading') : t('experts.documentCount', { count: total }) }}</p>
        </div>
        <button class="primary-button" type="button" :disabled="!writeExpert" @click="fileInput?.click()">
          <IconFileUpload :size="19" />{{ writeExpert ? t('experts.uploadTo', { expert: expertName(writeExpert) }) : t('experts.selectToUpload') }}
        </button>
        <input ref="fileInput" class="visually-hidden" type="file" @change="($event.target as HTMLInputElement).files?.[0] && upload(($event.target as HTMLInputElement).files![0])" />
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>{{ t('experts.fileName') }}</th><th>{{ t('experts.type') }}</th><th>{{ t('experts.owner') }}</th><th>{{ t('experts.createdAt') }}</th><th>{{ t('experts.action') }}</th></tr></thead>
          <tbody>
            <tr v-for="document in documents" :key="`${document.expertId}-${document.id}`">
              <td><IconFile :size="18" /><strong>{{ document.fileName }}</strong></td>
              <td>{{ document.sourceType.toUpperCase() }}</td>
              <td>{{ expertName({ id: document.expertId, name: document.expertName }) }}</td>
              <td>{{ document.createdAt ? new Date(document.createdAt).toLocaleString(localeTag) : '—' }}</td>
              <td><button class="danger-link" type="button" @click="pendingDocument = document"><IconTrash :size="17" />{{ t('common.delete') }}</button></td>
            </tr>
            <tr v-if="!loading && documents.length === 0"><td class="empty-cell" colspan="5">{{ t('experts.empty') }}</td></tr>
          </tbody>
        </table>
      </div>
      <footer class="document-pagination">
        <span>{{ t('experts.documentCount', { count: total }) }}</span>
        <div>
          <button class="secondary-button" type="button" :disabled="loading || offset === 0" @click="changePage(-1)">{{ t('admin.previous') }}</button>
          <span>{{ t('admin.page', { page }) }}</span>
          <button class="secondary-button" type="button" :disabled="loading || !canNext" @click="changePage(1)">{{ t('admin.next') }}</button>
        </div>
      </footer>
    </section>

    <BaseModal :open="managerOpen" :title="t('experts.manage')" :description="t('experts.manageDescription')" @close="managerOpen = false">
      <div class="modal-actions"><button class="primary-button" type="button" @click="createOpen = true"><IconPlus :size="18" />{{ t('experts.new') }}</button></div>
      <div class="expert-list">
        <div v-for="expert in session.concreteExperts" :key="expert.id">
          <span><strong>{{ expertName(expert) }}</strong><small>{{ expert.kind === 'shared' ? t('experts.sharedAccess') : t('experts.privateAccess') }}</small></span>
          <button v-if="expert.deletable" class="danger-link" type="button" @click="pendingDelete = expert"><IconTrash :size="17" />{{ t('common.delete') }}</button>
          <span v-else class="protected-label">{{ t('experts.protected') }}</span>
        </div>
      </div>
    </BaseModal>

    <BaseModal :open="createOpen" :title="t('experts.new')" :description="t('experts.newDescription')" @close="createOpen = false">
      <form class="modal-form" @submit.prevent="createExpert">
        <label><span>{{ t('experts.name') }}</span><input v-model="newExpertName" :placeholder="t('experts.namePlaceholder')" autofocus /></label>
        <button class="primary-button" type="submit">{{ t('experts.create') }}</button>
      </form>
    </BaseModal>

    <BaseModal :open="Boolean(pendingDelete)" :title="t('experts.confirmExpertDelete')" :description="t('experts.confirmExpertDeleteDescription', { expert: pendingDelete?.name ?? '' })" @close="pendingDelete = null">
      <div class="confirm-actions"><button class="secondary-button" type="button" @click="pendingDelete = null">{{ t('common.cancel') }}</button><button class="danger-button" type="button" @click="deleteExpert">{{ t('common.confirmDelete') }}</button></div>
    </BaseModal>

    <BaseModal :open="Boolean(pendingDocument)" :title="t('experts.confirmDocumentDelete')" :description="t('experts.confirmDocumentDeleteDescription', { file: pendingDocument?.fileName ?? '' })" @close="pendingDocument = null">
      <div class="confirm-actions"><button class="secondary-button" type="button" @click="pendingDocument = null">{{ t('common.cancel') }}</button><button class="danger-button" type="button" @click="deleteDocument">{{ t('common.confirmDelete') }}</button></div>
    </BaseModal>
  </div>
</template>
