<script setup lang="ts">
import { computed, ref } from 'vue'
import { IconArrowRight, IconLock, IconUser } from '@tabler/icons-vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api'
import LanguageSwitcher from '@/components/LanguageSwitcher.vue'
import StatusNotice from '@/components/StatusNotice.vue'
import { useI18n } from '@/i18n'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{ mode: 'login' | 'register' }>()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const { t } = useI18n()
const username = ref('')
const password = ref('')
const confirmation = ref('')
const status = ref('')
const loading = ref(false)
const isRegister = computed(() => props.mode === 'register')
const registrationNotice = computed(() =>
  route.query.registered === '1' ? t('auth.registered') : '',
)

async function submit() {
  status.value = ''
  if (isRegister.value && password.value !== confirmation.value) {
    status.value = t('auth.passwordMismatch')
    return
  }
  loading.value = true
  try {
    if (isRegister.value) {
      await session.register(username.value, password.value)
      await router.push({ name: 'login', query: { registered: '1' } })
      return
    }
    await session.login(username.value, password.value)
    await router.push({ name: 'chat' })
  } catch (error) {
    status.value = error instanceof ApiError ? error.message : t('common.requestFailed')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="auth-page">
    <LanguageSwitcher />
    <section class="auth-intro">
      <div class="auth-logo">J</div>
      <p class="auth-product">{{ t('common.productName') }}</p>
      <h1>{{ t('auth.productPitchLine1') }}<br />{{ t('auth.productPitchLine2') }}</h1>
      <p>{{ t('auth.productDescription') }}</p>
      <div class="auth-proof">
        <span>{{ t('auth.proofIsolation') }}</span>
        <span>{{ t('auth.proofSources') }}</span>
        <span>{{ t('auth.proofExperts') }}</span>
      </div>
      <p class="auth-author">{{ t('common.author') }}</p>
    </section>

    <section class="auth-panel">
      <div class="auth-card">
        <p class="auth-card-label">{{ isRegister ? t('auth.createAccount') : t('auth.welcomeBack') }}</p>
        <h2>{{ isRegister ? t('auth.registerTitle') : t('auth.loginTitle') }}</h2>
        <p>{{ isRegister ? t('auth.registerDescription') : t('auth.loginDescription') }}</p>
        <StatusNotice :message="registrationNotice" tone="success" />

        <form @submit.prevent="submit">
          <label>
            <span>{{ t('auth.username') }}</span>
            <div class="input-shell">
              <IconUser :size="19" />
              <input v-model="username" autocomplete="username" :placeholder="t('auth.usernamePlaceholder')" required />
            </div>
          </label>
          <label>
            <span>{{ t('auth.password') }}</span>
            <div class="input-shell">
              <IconLock :size="19" />
              <input
                v-model="password"
                :autocomplete="isRegister ? 'new-password' : 'current-password'"
                type="password"
                :placeholder="t('auth.passwordPlaceholder')"
                required
              />
            </div>
          </label>
          <label v-if="isRegister">
            <span>{{ t('auth.confirmPassword') }}</span>
            <div class="input-shell">
              <IconLock :size="19" />
              <input v-model="confirmation" autocomplete="new-password" type="password" :placeholder="t('auth.confirmPasswordPlaceholder')" required />
            </div>
          </label>
          <StatusNotice :message="status" tone="error" />
          <button class="primary-button auth-submit" :disabled="loading" type="submit">
            {{ loading ? t('auth.processing') : isRegister ? t('auth.createAccount') : t('auth.login') }}
            <IconArrowRight :size="19" />
          </button>
        </form>

        <p class="auth-switch">
          {{ isRegister ? t('auth.haveAccount') : t('auth.noAccount') }}
          <RouterLink :to="isRegister ? '/login' : '/register'">
            {{ isRegister ? t('auth.backToLogin') : t('auth.registerNow') }}
          </RouterLink>
        </p>
      </div>
    </section>
  </main>
</template>
