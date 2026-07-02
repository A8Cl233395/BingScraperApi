<script setup lang="ts">
import { useToast } from '../composables/useToast';

const { toastMessage, toastType, showToastMsg } = useToast();
</script>

<template>
  <div class="toast" :class="[toastType, { show: showToastMsg }]">
    {{ toastMessage }}
  </div>
</template>
