<script setup lang="ts">
import { ref } from 'vue'
import { IconCalendarMonth, IconMessages, IconSparkles, IconUsers } from '@tabler/icons-vue'

import { api, ApiError } from '@/api'
import StatusNotice from '@/components/StatusNotice.vue'
import { useI18n } from '@/i18n'
import type { MonthlyPersonalReport } from '@/types'

const report = ref<MonthlyPersonalReport | null>(null)
const status = ref('')
const loading = ref(false)
const statusTone = ref<'success' | 'error'>('success')
const { t } = useI18n()

async function generateReport() {
  loading.value = true
  status.value = ''
  try {
    const payload = await api<{ report: MonthlyPersonalReport }>('/reports/monthly', { method: 'POST' })
    report.value = payload.report
    status.value = t('reports.generated')
    statusTone.value = 'success'
  } catch (caught) {
    status.value = caught instanceof ApiError ? caught.message : t('reports.failed')
    statusTone.value = 'error'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="view stats-view">
    <header class="view-header">
      <div>
        <p class="section-label">{{ t('nav.reports') }}</p>
        <h1>{{ t('reports.title') }}</h1>
        <p>{{ t('reports.description') }}</p>
      </div>
      <button class="primary-button" type="button" :disabled="loading" @click="generateReport">
        <IconSparkles :size="19" />{{ loading ? t('reports.generating') : t('reports.generate') }}
      </button>
    </header>

    <section v-if="report" class="metrics-grid">
      <article><IconCalendarMonth :size="22" /><span>{{ t('reports.period') }}</span><strong>{{ t('reports.days', { count: report.period.days }) }}</strong></article>
      <article><IconMessages :size="22" /><span>{{ t('reports.conversations') }}</span><strong>{{ report.metrics.conversationCount }}</strong></article>
      <article><IconUsers :size="22" /><span>{{ t('reports.expertsUsed') }}</span><strong>{{ report.metrics.expertsUsed }}</strong></article>
      <article><IconSparkles :size="22" /><span>{{ t('reports.month') }}</span><strong>{{ report.reportMonth }}</strong></article>
    </section>

    <StatusNotice :message="status" :tone="statusTone" />

    <section class="report-panel">
      <div class="report-panel-header">
        <IconSparkles :size="21" />
        <div><h2>{{ t('reports.panelTitle') }}</h2><p>{{ t('reports.panelDescription') }}</p></div>
      </div>
      <div v-if="report" class="report-content">{{ report.summary }}</div>
      <div v-else class="empty-report">{{ t('reports.empty') }}</div>
    </section>
  </div>
</template>
