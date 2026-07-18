import { ref, watch, onMounted } from 'vue';
import { state } from '../store';
import {
  type PetState,
  PET_STATES,
  CODEX_SPRITE_CONFIG,
  getPet,
  savePetImage,
  deletePetImage as dbDeleteImage,
  clearAllPetImages as dbClearAll,
} from '../utils/pet-db';

export function usePet() {
  const currentImageUrl = ref('');
  const petImages = ref<Record<PetState, string | null>>({
    idle: null,
    thinking: null,
    answering: null,
    tool_calling: null,
  });
  const objectUrls: Record<PetState, string | null> = {
    idle: null,
    thinking: null,
    answering: null,
    tool_calling: null,
  };
  const isLoading = ref(false);

  function revokeUrl(s: PetState) {
    if (objectUrls[s]) {
      URL.revokeObjectURL(objectUrls[s]!);
      objectUrls[s] = null;
    }
  }

  function revokeAll() {
    PET_STATES.forEach(revokeUrl);
  }

  function updateDisplay(signal: PetState) {
    const url = petImages.value[signal];
    currentImageUrl.value = url ?? '';
  }

  async function loadImages(): Promise<void> {
    isLoading.value = true;
    try {
      const record = await getPet();

      for (const s of PET_STATES) {
        revokeUrl(s);
        const blob = record.images[s];
        if (blob) {
          const url = URL.createObjectURL(blob);
          objectUrls[s] = url;
          petImages.value[s] = url;
        } else {
          petImages.value[s] = null;
        }
      }
      updateDisplay(state.aiSignal as PetState);
    } finally {
      isLoading.value = false;
    }
  }

  async function importSprite(file: File): Promise<void> {
    const { default: UPNG } = await import('upng-js');
    const img = await createImageBitmap(file);
    const frameW = img.width / CODEX_SPRITE_CONFIG.columns;
    const frameH = img.height / CODEX_SPRITE_CONFIG.rows;

    const canvas = document.createElement('canvas');
    canvas.width = frameW;
    canvas.height = frameH;
    const ctx = canvas.getContext('2d')!;

    const states = CODEX_SPRITE_CONFIG.states;
    for (const stateKey of PET_STATES) {
      const cfg = states[stateKey as keyof typeof states];
      if (!cfg) continue;
      const buffers: ArrayBuffer[] = [];
      for (let col = 0; col < cfg.frames; col++) {
        ctx.clearRect(0, 0, frameW, frameH);
        ctx.drawImage(img, col * frameW, cfg.row * frameH, frameW, frameH, 0, 0, frameW, frameH);
        const imageData = ctx.getImageData(0, 0, frameW, frameH);
        buffers.push(imageData.data.buffer as ArrayBuffer);
      }
      const apng = UPNG.encode(buffers, frameW, frameH, 0, [...cfg.delays]);
      const blob = new Blob([apng], { type: 'image/apng' });
      await savePetImage(stateKey, blob);
    }

    img.close();
    await loadImages();
  }

  async function removeImage(s: PetState): Promise<void> {
    await dbDeleteImage(s);
    revokeUrl(s);
    petImages.value[s] = null;
    if (state.aiSignal === s) {
      currentImageUrl.value = '';
    }
  }

  async function clearAll(): Promise<void> {
    await dbClearAll();
    revokeAll();
    for (const s of PET_STATES) {
      petImages.value[s] = null;
    }
    currentImageUrl.value = '';
  }

  async function setEnabled(v: boolean): Promise<void> {
    localStorage.setItem('pet_enabled', String(v));
    state.petEnabled = v;
  }

  watch(() => state.aiSignal, (signal) => {
    updateDisplay(signal as PetState);
  });

  onMounted(() => {
    loadImages();
  });

  return {
    currentImageUrl,
    petImages,
    isLoading,
    importSprite,
    removeImage,
    clearAll,
    setEnabled,
  };
}
