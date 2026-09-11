import { createRouter, createWebHistory } from 'vue-router'
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
