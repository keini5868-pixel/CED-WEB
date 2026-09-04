/** Cierre inmediato de superficies HUD. No depende de clicks ni de Escape. */

type Closer = () => void;

const closers = new Set<Closer>();

export function registerPresenterCloser(fn: Closer): () => void {
  closers.add(fn);
  return () => {
    closers.delete(fn);
  };
}

export function runPresenterClosers(): void {
  for (const fn of Array.from(closers)) {
    try {
      fn();
    } catch {
      /* un panel pudo desmontarse */
    }
  }
}
