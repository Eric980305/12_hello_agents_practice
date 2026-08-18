<script setup lang="ts">
import { IconX } from '@tabler/icons-vue'

import { useI18n } from '@/i18n'

defineProps<{
  open: boolean
  title: string
  description?: string
}>()

const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" role="presentation" @mousedown.self="emit('close')">
      <section class="modal" role="dialog" aria-modal="true" :aria-label="title">
        <header>
          <div>
            <h2>{{ title }}</h2>
            <p v-if="description">{{ description }}</p>
          </div>
          <button class="icon-button" type="button" :aria-label="t('common.close')" @click="emit('close')">
            <IconX :size="20" />
          </button>
        </header>
        <slot />
      </section>
    </div>
  </Teleport>
</template>
