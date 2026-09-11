import { createRouter, createWebHistory } from 'vue-router'
import { ensureAuthStatus, loginUrl } from './api/auth'
import CompaniesView from './views/CompaniesView.vue'
import FailedRoutingsView from './views/FailedRoutingsView.vue'
import InvoicesView from './views/InvoicesView.vue'
import RoutingRulesView from './views/RoutingRulesView.vue'
import SettingsView from './views/SettingsView.vue'
import TargetApplicationsView from './views/TargetApplicationsView.vue'
import UsersView from './views/UsersView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/invoices' },
    { path: '/companies', name: 'companies', component: CompaniesView },
    { path: '/target-applications', name: 'target-applications', component: TargetApplicationsView },
    { path: '/routing-rules', name: 'routing-rules', component: RoutingRulesView },
    { path: '/invoices', name: 'invoices', component: InvoicesView },
    { path: '/failed-routings', name: 'failed-routings', component: FailedRoutingsView },
    { path: '/settings', name: 'settings', component: SettingsView },
    { path: '/users', name: 'users', component: UsersView },
  ],
})

// Redirige automatiquement vers le login (§ NF3) si l'authentification est activée
// et qu'aucune session n'est présente — puis, une fois connecté, ramène l'utilisateur
// sur la page initialement demandée (paramètre `next`, cf. app/api/ihm/auth.py).
router.beforeEach(async (to) => {
  const status = await ensureAuthStatus()
  if (status.oidc_mode !== 'disabled' && !status.authenticated) {
    window.location.href = loginUrl(to.fullPath)
    return false
  }
  return true
})
