import { createRouter, createWebHistory } from 'vue-router'
import CompaniesView from './views/CompaniesView.vue'
import RoutingRulesView from './views/RoutingRulesView.vue'
import TargetApplicationsView from './views/TargetApplicationsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/companies' },
    { path: '/companies', name: 'companies', component: CompaniesView },
    { path: '/target-applications', name: 'target-applications', component: TargetApplicationsView },
    { path: '/routing-rules', name: 'routing-rules', component: RoutingRulesView },
  ],
})
