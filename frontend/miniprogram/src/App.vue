<!-- src/App.vue -->
<script setup lang="ts">
import { onLaunch } from '@dcloudio/uni-app'

onLaunch(() => {
  // Token is restored from storage by the Pinia auth store on init.
  // We do NOT force-login on launch — let users explore the home page first.
  console.log('[App] launched')
})
</script>

<template>
  <layout />
</template>
