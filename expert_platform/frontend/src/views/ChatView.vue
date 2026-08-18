<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { IconSend2, IconSparkles } from '@tabler/icons-vue'

import { api, ApiError } from '@/api'
import StatusNotice from '@/components/StatusNotice.vue'
import { useI18n } from '@/i18n'
import { useSessionStore } from '@/stores/session'
import type { ChatMessage } from '@/types'

const session = useSessionStore()
const { expertName, localeTag, t } = useI18n()
const messages = ref<ChatMessage[]>([])
const question = ref('')
const advanced = ref(false)
const loading = ref(false)
const error = ref('')
const conversation = ref<HTMLElement>()

const selectedExpert = computed(() => session.selectedExpert ?? session.concreteExperts[0])

async function loadHistory() {
  const payload = await api<{ items: ChatMessage[] }>('/chat/history')
  messages.value = payload.items
}

async function sendQuestion() {
  const content = question.value.trim()
  if (!content || loading.value || !selectedExpert.value) return
  error.value = ''
  question.value = ''
  messages.value.push({
    id: `pending-user-${Date.now()}`,
    role: 'user',
    content,
    expertId: selectedExpert.value.id,
    expertName: selectedExpert.value.name,
    createdAt: new Date().toISOString(),
  })
  loading.value = true
  await nextTick()
  conversation.value?.scrollTo({ top: conversation.value.scrollHeight, behavior: 'smooth' })
  try {
    const payload = await api<{ message: ChatMessage }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ expertId: selectedExpert.value.id, question: content, advanced: advanced.value }),
    })
    messages.value.push(payload.message)
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught.message : t('chat.failed')
  } finally {
    loading.value = false
    await nextTick()
    conversation.value?.scrollTo({ top: conversation.value.scrollHeight, behavior: 'smooth' })
  }
}

onMounted(loadHistory)
</script>

<template>
  <div class="view chat-view">
    <header class="view-header chat-header">
      <div>
        <p class="section-label">{{ t('nav.chat') }}</p>
        <h1>{{ t('chat.title') }}</h1>
        <p>{{ t('chat.description') }}</p>
      </div>
      <label class="expert-select">
        <span>{{ t('shell.currentExpert') }}</span>
        <select v-model="session.selectedExpertId" @change="session.selectExpert(session.selectedExpertId)">
          <option v-for="expert in session.concreteExperts" :key="expert.id" :value="expert.id">
            {{ expertName(expert) }}
          </option>
        </select>
      </label>
    </header>

    <section ref="conversation" class="conversation-panel" aria-live="polite">
      <div v-if="messages.length === 0" class="empty-conversation">
        <div class="empty-icon"><IconSparkles :size="28" /></div>
        <h2>{{ t('chat.ready', { expert: selectedExpert ? expertName(selectedExpert) : '' }) }}</h2>
        <p>{{ t('chat.empty') }}</p>
      </div>
      <article v-for="message in messages" :key="message.id" class="message" :data-role="message.role">
        <div class="message-meta">
          <span>{{ message.role === 'user' ? t('chat.you') : expertName({ id: message.expertId, name: message.expertName }) }}</span>
          <time>{{ new Date(message.createdAt).toLocaleTimeString(localeTag, { hour: '2-digit', minute: '2-digit' }) }}</time>
        </div>
        <p>{{ message.content }}</p>
      </article>
      <article v-if="loading" class="message" data-role="assistant">
        <div class="message-meta"><span>{{ selectedExpert ? expertName(selectedExpert) : '' }}</span></div>
        <p class="thinking">{{ t('chat.thinking') }}</p>
      </article>
    </section>

    <StatusNotice :message="error" tone="error" />

    <section class="composer">
      <div class="composer-options">
        <label class="toggle">
          <input v-model="advanced" type="checkbox" />
          <span>{{ t('chat.advanced') }}</span>
          <small>MQE + HyDE</small>
        </label>
        <span>{{ t('chat.answerScope', { expert: selectedExpert ? expertName(selectedExpert) : '' }) }}</span>
      </div>
      <div class="composer-row">
        <textarea v-model="question" rows="2" :placeholder="t('chat.placeholder')" @keydown.meta.enter.prevent="sendQuestion" />
        <button class="send-button" type="button" :disabled="loading || !question.trim()" :aria-label="t('chat.send')" @click="sendQuestion">
          <IconSend2 :size="21" />
        </button>
      </div>
    </section>
  </div>
</template>
