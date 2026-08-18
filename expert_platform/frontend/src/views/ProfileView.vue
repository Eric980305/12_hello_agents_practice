<script setup lang="ts">
import { IconLogout, IconShieldCheck, IconUserCircle } from '@tabler/icons-vue'
import { useRouter } from 'vue-router'

import { useI18n } from '@/i18n'
import { useSessionStore } from '@/stores/session'

const session = useSessionStore()
const router = useRouter()
const { t } = useI18n()

async function logout() {
  await session.logout()
  await router.push('/login')
}
</script>

<template>
  <div class="view profile-view">
    <header class="view-header">
      <div>
        <p class="section-label">{{ t('profile.section') }}</p>
        <h1>{{ t('profile.title') }}</h1>
        <p>{{ t('profile.description') }}</p>
      </div>
    </header>

    <section class="profile-card">
      <div class="profile-avatar"><IconUserCircle :size="48" stroke-width="1.5" /></div>
      <div><span>{{ t('profile.username') }}</span><h2>{{ session.user?.username }}</h2><p>{{ t('profile.accountType') }}</p></div>
      <div class="profile-meta"><span>{{ session.user?.vipLevel }}</span><strong>{{ t('profile.balance', { amount: session.user?.balance.toFixed(2) ?? '0.00' }) }}</strong></div>
    </section>

    <section class="security-note">
      <IconShieldCheck :size="23" />
      <div><h2>{{ t('profile.security') }}</h2><p>{{ t('profile.securityDescription') }}</p></div>
    </section>

    <button class="danger-button profile-logout" type="button" @click="logout"><IconLogout :size="19" />{{ t('profile.logout') }}</button>
  </div>
</template>
