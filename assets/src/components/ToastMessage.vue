<script setup lang="ts">
import { useToast } from '../composables/useToast';

const { toastMessage, toastType, showToastMsg } = useToast();
</script>

<template>
  <div class="toast" :class="[toastType, { show: showToastMsg }]">
    <FontAwesomeIcon v-if="toastType === 'success'" :icon="['fas', 'check']" />
    <FontAwesomeIcon v-else-if="toastType === 'info'" :icon="['fas', 'circle-info']" />
    <FontAwesomeIcon v-else :icon="['fas', 'triangle-exclamation']" />
    {{ toastMessage }}
  </div>
</template>
