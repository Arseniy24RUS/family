/** Small LRU for asynchronous resources. Eviction never cancels an active view. */
export function createAsyncCache({maxEntries = 24} = {}) {
  if (!Number.isInteger(maxEntries) || maxEntries < 1)
    throw RangeError('Cache capacity must be a positive integer.');
  const entries = new Map();
  return {
    get size() { return entries.size; },
    has(key) { return entries.has(key); },
    clear() { entries.clear(); },
    getOrCreate(key, factory) {
      if (entries.has(key)) {
        const existing = entries.get(key);
        entries.delete(key);
        entries.set(key, existing);
        return existing;
      }
      const promise = Promise.resolve().then(factory).catch(error => {
        // An evicted request can fail after a new request has reused its key.
        if (entries.get(key) === promise) entries.delete(key);
        throw error;
      });
      entries.set(key, promise);
      while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
      return promise;
    }
  };
}

// These are shared across project modules, so visiting twelve studies does not
// create twelve independent stores of large observation/text packets.
export const observationCache = createAsyncCache({maxEntries: 3});
// A single text view can compare ten passports concurrently; keep that working
// set together so changing its filter does not repeatedly download the corpus.
export const textPacketCache = createAsyncCache({maxEntries: 12});
