<script setup lang="ts">
defineProps<{
  message: string
  tone?: 'info' | 'success' | 'error'
}>()
</script>

<template>
  <p v-if="message" class="status-notice" :data-tone="tone ?? 'info'" role="status">
    {{ message }}
  </p>
</template>
