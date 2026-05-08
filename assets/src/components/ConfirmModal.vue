<script setup lang="ts">
defineProps<{
  show: boolean;
  title?: string;
  message?: string;
  confirmText?: string;
  cancelText?: string;
  isDanger?: boolean;
}>();

const emit = defineEmits(['confirm', 'cancel']);
</script>

<template>
  <Transition name="modal">
    <div v-if="show" class="fixed inset-0 z-1000 flex items-center justify-center p-4 sm:p-6">
      <!-- Backdrop -->
      <div 
        class="absolute inset-0 bg-black/40 transition-opacity" 
        @click="emit('cancel')"
      ></div>

      <!-- Modal Content -->
      <div 
        class="relative bg-bg-main rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden transform transition-all border border-border-main"
        @click.stop
      >
        <div class="p-6">
          <div class="flex items-center justify-center w-12 h-12 rounded-full mb-4 mx-auto" :class="isDanger ? 'bg-danger-main/10' : 'bg-primary-main/10'">
            <i 
              class="fas" 
              :class="[
                isDanger ? 'fa-exclamation-triangle text-danger-main' : 'fa-info-circle text-primary-main',
                'text-xl'
              ]"
            ></i>
          </div>
          
          <h3 class="text-lg font-semibold text-text-main text-center mb-2">
            {{ title || '确认操作' }}
          </h3>
          <p class="text-sm text-text-muted text-center">
            {{ message || '您确定要执行此操作吗？' }}
          </p>
        </div>

        <div class="flex border-t border-border-main">
          <button 
            @click="emit('cancel')"
            class="flex-1 px-4 py-4 text-sm font-medium text-text-muted hover:bg-bg-hover transition-colors border-r border-border-main"
          >
            {{ cancelText || '取消' }}
          </button>
          <button 
            @click="emit('confirm')"
            class="flex-1 px-4 py-4 text-sm font-semibold transition-colors"
            :class="isDanger ? 'text-danger-main hover:bg-danger-main/10' : 'text-primary-main hover:bg-primary-main/10'"
          >
            {{ confirmText || '确认' }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .relative {
  transition: transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.modal-leave-active .relative {
  transition: transform 0.2s ease-in;
}

.modal-enter-from .relative {
  transform: scale(0.9) translateY(10px);
}

.modal-leave-to .relative {
  transform: scale(0.95) translateY(5px);
}
</style>
