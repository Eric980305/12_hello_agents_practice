<script setup lang="ts">
import {
  IconBooks,
  IconCalendarMonth,
  IconMessageCircle,
  IconSettings,
  IconUserCircle,
} from '@tabler/icons-vue'
import { computed } from 'vue'
import { RouterLink, RouterView } from 'vue-router'

import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import { useI18n } from '@/i18n'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const { expertName, t } = useI18n()

const navigation = computed(() => [
  { to: '/chat', label: 'nav.chat' as const, icon: IconMessageCircle },
  { to: '/experts', label: 'nav.experts' as const, icon: IconBooks },
  { to: '/reports', label: 'nav.reports' as const, icon: IconCalendarMonth },
  ...(session.user?.isAdmin
    ? [{ to: '/admin', label: 'nav.admin' as const, icon: IconSettings }]
    : []),
])
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/chat" :aria-label="t('shell.home')">
        <span class="brand-mark">J</span>
        <span>
          <strong>{{ t('common.productName') }}</strong>
          <small>{{ t('common.productTagline') }}</small>
        </span>
      </RouterLink>
      <span class="topbar-author">{{ t('common.author') }}</span>
      <LanguageSwitcher />
      <RouterLink class="profile-link" to="/profile">
        <IconUserCircle :size="22" stroke-width="1.8" />
        <span>{{ session.user?.username }}</span>
      </RouterLink>
    </header>

    <main class="workspace">
      <aside class="sidebar" :aria-label="t('nav.main')">
        <nav>
          <RouterLink v-for="item in navigation" :key="item.to" :to="item.to">
            <component :is="item.icon" :size="21" stroke-width="1.8" />
            <span>{{ t(item.label) }}</span>
          </RouterLink>
        </nav>
        <div class="sidebar-expert">
          <span>{{ t('shell.currentExpert') }}</span>
          <strong>{{ session.selectedExpert ? expertName(session.selectedExpert) : t('experts.shared') }}</strong>
          <small>{{ t('shell.expertScope') }}</small>
        </div>
      </aside>
      <section class="content-canvas">
        <RouterView />
      </section>
    </main>

    <nav class="mobile-nav" :class="{ 'has-admin': session.user?.isAdmin }" :aria-label="t('nav.mobile')">
      <RouterLink v-for="item in navigation" :key="item.to" :to="item.to">
        <component :is="item.icon" :size="21" stroke-width="1.9" />
        <span>{{ t(item.label) }}</span>
      </RouterLink>
    </nav>
  </div>
</template>
