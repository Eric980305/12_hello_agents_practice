<script setup lang="ts">
import { IconLanguage } from '@tabler/icons-vue'

import { useI18n, type Locale } from '@/i18n'

const { locale, setLocale, t } = useI18n()
</script>

<template>
  <label class="language-switcher">
    <IconLanguage :size="19" stroke-width="1.8" aria-hidden="true" />
    <span class="visually-hidden">{{ t('language.label') }}</span>
    <select :value="locale" :aria-label="t('language.label')" @change="setLocale(($event.target as HTMLSelectElement).value as Locale)">
      <option value="zh-CN">{{ t('language.zhCN') }}</option>
      <option value="en-US">{{ t('language.enUS') }}</option>
    </select>
  </label>
</template>
