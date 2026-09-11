<script setup lang="ts"></script>

<template>
  <nav>
    <RouterLink to="/companies">Entreprises</RouterLink> |
    <RouterLink to="/target-applications">Applications cibles</RouterLink> |
    <RouterLink to="/routing-rules">Règles de routage</RouterLink>
  </nav>
  <RouterView />
</template>
