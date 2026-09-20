import { createApp } from 'vue'
import { createAppRouter } from './router'

import App from './App.vue'
import './assets/theme.css'

const router = createAppRouter()
const app = createApp(App)

app.use(router)
// 首帧等路由解析完再挂：解析没跑完时 route.name 还是空，<router-view> 拿不到组件，
// 先挂就会画一帧「有侧栏、没有面板」的空工作台，深链 /docs 也要闪一下才到位。
router.isReady().then(() => app.mount('#app'))
