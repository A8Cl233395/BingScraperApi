export type PetState = 'idle' | 'thinking' | 'answering' | 'tool_calling';

export const PET_STATES: PetState[] = ['idle', 'thinking', 'answering', 'tool_calling'];

export const CODEX_SPRITE_CONFIG = {
  columns: 8,
  rows: 9,
  states: {
    idle:          { row: 0, frames: 6, delays: [280, 110, 110, 140, 140, 320] as number[] },
    answering:     { row: 6, frames: 6, delays: [150, 150, 150, 150, 150, 260] as number[] },
    tool_calling:  { row: 7, frames: 6, delays: [120, 120, 120, 120, 120, 220] as number[] },
    thinking:      { row: 8, frames: 6, delays: [150, 150, 150, 150, 150, 280] as number[] },
  },
} as const;

interface PetRecord {
  key: string;
  images: Record<PetState, Blob | null>;
}

const DB_NAME = 'pet_db';
const DB_VERSION = 1;
const STORE_NAME = 'pets';
const RECORD_KEY = 'default';

let dbInstance: IDBDatabase | null = null;

function openDB(): Promise<IDBDatabase> {
  if (dbInstance) return Promise.resolve(dbInstance);

  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'key' });
      }
    };

    request.onsuccess = () => {
      dbInstance = request.result;
      resolve(dbInstance);
    };

    request.onerror = () => reject(request.error);
  });
}

function createDefaultRecord(): PetRecord {
  return {
    key: RECORD_KEY,
    images: { idle: null, thinking: null, answering: null, tool_calling: null },
  };
}

export async function getPet(): Promise<PetRecord> {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const request = store.get(RECORD_KEY);

    request.onsuccess = () => {
      resolve(request.result ?? createDefaultRecord());
    };
    request.onerror = () => reject(request.error);
  });
}

export async function savePetImage(state: PetState, blob: Blob): Promise<void> {
  const db = await openDB();
  const record = await getPet();
  record.images[state] = blob;

  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function deletePetImage(state: PetState): Promise<void> {
  const db = await openDB();
  const record = await getPet();
  record.images[state] = null;

  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function clearAllPetImages(): Promise<void> {
  const db = await openDB();
  const record = await getPet();
  record.images = { idle: null, thinking: null, answering: null, tool_calling: null };

  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);
    store.put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}


