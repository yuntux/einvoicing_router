import { ref } from 'vue'

/** Message d'erreur affiché sous forme d'alerte (`role="alert"`) dans les vues IHM :
 * centralise le `error.value = ''` / `try { … } catch (e) { error.value = (e as
 * Error).message }` répété à chaque appel API, plutôt que de le recopier à chaque
 * fonction de formulaire. */
export function useErrorMessage() {
  const error = ref('')

  async function guard(action: () => Promise<void>): Promise<void> {
    error.value = ''
    try {
      await action()
    } catch (e) {
      error.value = (e as Error).message
    }
  }

  return { error, guard }
}
