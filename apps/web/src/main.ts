import { createApp } from 'vue'
import App from './App.vue'
import { createAppRouter } from './app/router'
import { i18n } from './core/i18n/i18n'
import '@fontsource-variable/inter'
import './style.css'

createApp(App).use(i18n).use(createAppRouter()).mount('#app')
