<script setup lang="ts"></script>

<template>
  <nav>
    <RouterLink to="/invoices">Factures</RouterLink> |
    <RouterLink to="/companies">Entreprises</RouterLink> |
    <RouterLink to="/target-applications">Applications cibles</RouterLink> |
    <RouterLink to="/routing-rules">Règles de routage</RouterLink> |
    <RouterLink to="/failed-routings">Échecs de routage</RouterLink> |
    <RouterLink to="/settings">Configuration</RouterLink>
  </nav>
  <RouterView />
</template>
