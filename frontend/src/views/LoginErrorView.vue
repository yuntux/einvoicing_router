<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { loginUrl } from '../api/auth'

const route = useRoute()

const reason = computed(() => (Array.isArray(route.query.reason) ? route.query.reason[0] : route.query.reason))

const message = computed(() => {
  if (reason.value === 'inactive') {
    return 'Votre compte a été désactivé. Contactez un administrateur du routeur pour le réactiver.'
  }
  return "Aucun compte n'est pré-provisionné pour votre adresse email. Contactez un administrateur du routeur pour qu'il crée votre accès."
})
</script>

<template>
  <main>
    <h1>Connexion refusée</h1>
    <p role="alert" data-testid="login-error-message">{{ message }}</p>
    <p><a :href="loginUrl()">Réessayer</a></p>
  </main>
</template>
