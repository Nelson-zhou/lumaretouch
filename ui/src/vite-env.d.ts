/// <reference types="vite/client" />

// Vite 的构建期常量（`import.meta.env.DEV`）在这里进类型链：发布态 UI 要靠它把
// 跑靶/解释器这类**开发工具面板**与产品面板分开——`npm run build` 出来的包里
// DEV 为 false，`npm run dev` 与自动跑靶用的都是同一份代码，不另开一条分支。
