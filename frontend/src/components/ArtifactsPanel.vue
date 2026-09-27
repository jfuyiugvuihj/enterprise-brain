<!--
  R315 · 「交成果」屏壳：给一枚早就在树里的组件一个页面位置，其余一件事都不做

  病（docs/handoff/2026-09-26-frontend-gap-recheck.md:288-292 · G11）：ArtifactList.vue 不是半成品，
  它自己分页、自己刷新、自己删、自己重试，四张脸齐全；可本单之前它唯一的挂载点是 DataPanel.vue:454。
  于是员工问「我上周生成的那份报告呢」，今天只有一条路：进「喂料」的数据标签往下滚。
  路由表里没有它 —— 一件已经做好的东西没有自己的位置，这就是业主点名的那一格。

  屏名「交成果」不是这枚壳造的词，出处有两处：
    · docs/frontend-plan-2026-09-14.md:132 工作区映射表：（新增）「交成果」，后端依赖 B-1 / R2 —— 那两条今天都已交付；
    · docs/handoff/2026-09-15-backend-followup-requests.md:2099「说人话」硬规矩③：入口的名字要跟员工的话一致，
      那句话点名的词是「问一句、交成果、报销自查、异常与告警」（本格只复核了这句原文，没去评测集里逐题数）。
      顶栏与页内同源由 R136 判据① 那枚用例真渲染比对，本单的页级 <h3> 就归它管。

  这一枚壳的边界（判据②③⑤，钉在 src/components/__tests__/r315-artifacts-screen.test.js）：
    · 它不取数：GET /artifacts 那一发、页大小、读取更多、刷新、删除、打开、失败与空态全在 ArtifactList 里，
      这里连一次 api.get / fetch 都没有，也不数「这一页几件」——数出来的那一格会被读成全集（R316 判据③同一条）。
    · 它不改 ArtifactList：那枚文件本单一个字节没动（对基点 d609165 逐字节对账），壳也不给它加 prop、
      不加标题、不改它取数的时机。
    · 它不摘 DataPanel 那一处：两屏共用同一枚组件就是同一份账，正在用「数据」那一屏的人不该忽然找不到东西。
-->
<script>
export default { name: 'ArtifactsPanel' }
</script>

<script setup>
// 只 import 默认导出：这一枚组件的公开面（列表、分页、删除、打开、四张脸）一格都不由壳重新组装。
import ArtifactList from './ArtifactList.vue'
</script>

<template>
  <div class="panel-shell" data-testid="artifacts-panel">
    <header class="panel-head">
      <div>
        <div class="eyebrow">从对话与数据析出的成果</div>
        <h3>交成果</h3>
        <p>
          这一屏列的是你这个账号现在打得开的分析产物，按时间从新到旧。
          打开、删除、往下多读几页都在下面这一处；「喂料」的数据标签里看到的也是同一批成果。
        </p>
      </div>
    </header>

    <ArtifactList />
  </div>
</template>
