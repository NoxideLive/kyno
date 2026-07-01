import '@/assets/main.css'
import '@/assets/markdown-content.css'
import 'katex/dist/katex.min.css'

import { clerkPlugin } from '@clerk/vue'
import { convexVue } from 'convex-vue'
import { createApp } from 'vue'
import App from '@/App.vue'
import { clerkPluginOptions, hasClerkPublishableKey } from '@/lib/clerkConfig'
import { resolveConvexClientUrl } from '@/lib/convexClientUrl'
import { initMessageContentRenderer } from '@/lib/renderMessageContent'
import router from '@/router'
import { installAuthGuards } from '@/router/guards'

async function bootstrap(): Promise<void> {
  await initMessageContentRenderer()

  const app = createApp(App)

  if (hasClerkPublishableKey()) {
    app.use(clerkPlugin, clerkPluginOptions())
  }

  const convexUrl = resolveConvexClientUrl(import.meta.env.VITE_CONVEX_URL ?? '')
  app.use(convexVue, {
    url: convexUrl,
    ...(convexUrl
      ? {}
      : { clientOptions: { skipConvexDeploymentUrlCheck: true } }),
  })

  // Register guards before the first navigation; composables need clerkPlugin + runWithContext.
  app.runWithContext(() => {
    installAuthGuards(router)
  })

  app.use(router)
  app.mount('#app')
}

void bootstrap()
