<script setup>
/**
 * R48 路线甲 · 首屏那张卡。
 *
 * 读的是后端 `answer.headline` 事件（app/api/v1/chat.py::_answer_headline_frame），
 * 载荷里只有「本轮命中了哪些资料」那一类读数：来源行、两枚计数、发卡耗时。🔴 它不是结论，
 * 也不承载结论 —— 判据④ 的机测地板是「只吐 1 枚 token 也要 11.0 s」，所以 1 s 之内压根
 * 没有可显示的模型产出，这张卡一个字都不从正文来。
 *
 * 三张脸（各一枚用例，见 components/__tests__/r48-headline-card.test.js）：
 *   pending   卡片在场、正文还在路上
 *   filled    卡片在场、正文已到
 *   unfilled  卡片在场、正文最终没到 —— 「首屏卡片未获补齐」是新脸，
 *             🔴 不许复用 done-no-result 那句「后端说这一轮跑完了，但读数里没带回答案」，
 *             两句话说的是不同的事：那一句说的是「跑完而没答案」，这一句说的是
 *             「首屏先给了线索、线索后面没接上回答」。
 *   （第四态「本轮不该有卡」= 后端压根没发这枚事件：整条不渲染，
 *     「没检索到」与「检索到了但不给你看」两张脸归收尾的 sources 事件。）
 *
 * 措辞形状沿用 lib/provenance.js 那几张脸的 kind / tone / headline / detail 四键：同一套
 * 词汇，将来收进字典是搬一行，不是再判一次语义。
 */
import { computed } from 'vue'
import { classificationLabel, formatMoment } from '../lib/provenance.js'

const props = defineProps({
  headline: { type: Object, required: true },
  // 屏上此刻有没有正文：卡片不许替正文说话，所以只读它有没有。
  hasAnswer: { type: Boolean, default: false },
  // 这一轮还在流吗（面板的 loading 落在最后一条回答上）。
  streaming: { type: Boolean, default: false },
})

const rows = computed(() => (Array.isArray(props.headline?.rows) ? props.headline.rows : []))

const hitCount = computed(() => Number(props.headline?.hitCount) || 0)
const hiddenCount = computed(() => Number(props.headline?.hiddenCount) || 0)
// 「画了几条」与「命中几条」的差：截断要说成截断，不许说成全部。
const moreCount = computed(() => Math.max(0, hitCount.value - rows.value.length))

/**
 * 「发卡这一刻」的读数出自后端（data.elapsed_ms），界面不自己掐表：
 * 自己掐的表把网络与解析的账算进了首屏，读出来的数也就不能和外面对照。
 */
const cardAge = computed(() => {
  const ms = Number(props.headline?.elapsedMs)
  if (!Number.isFinite(ms) || ms < 0) return ''
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`
})

const face = computed(() => {
  const named = `${rows.value.length ? rows.value.length : hitCount.value} 处资料`
  if (props.hasAnswer) {
    return {
      kind: 'filled',
      tone: 'muted',
      headline: `本轮命中的资料 · ${named}（不是结论）`,
      detail: '回答正文已到。这张卡只说本轮翻到了哪些文件，要引用请指向正文。',
    }
  }
  if (props.streaming) {
    return {
      kind: 'pending',
      tone: 'info',
      headline: `先翻到 ${named}（不是结论）`,
      detail: '正文还在生成。这张卡不含任何模型结论，也别把它当答案引用。',
    }
  }
  return {
    kind: 'unfilled',
    tone: 'warn',
    headline: '首屏卡片未获补齐',
    detail: '这张卡只说明本轮翻到过哪些文件，它不是结论，本轮也没有在它后面接出可引用的回答。请重新提问；每次都停在这里请让管理员查模型服务。',
  }
})
</script>

<template>
  <section
    class="headline-card"
    :class="`headline-card--${face.tone}`"
    role="status"
    data-testid="r48-headline-card"
    :data-kind="face.kind"
  >
    <p class="headline-title" data-testid="r48-headline-title">{{ face.headline }}</p>
    <ul v-if="rows.length" class="headline-rows" data-testid="r48-headline-rows">
      <li v-for="row in rows" :key="row.sourceId || row.filename" class="headline-row">
        <span class="headline-file">{{ row.filename }}</span>
        <span v-if="classificationLabel(row.classification)" class="headline-tag">{{ classificationLabel(row.classification) }}</span>
        <span v-if="row.department" class="headline-tag">{{ row.department }}</span>
        <span v-if="row.versionId" class="headline-tag">版本 {{ row.versionId }}</span>
        <span v-if="row.effectiveDate" class="headline-tag">生效 {{ formatMoment(row.effectiveDate) || '（读数缺格式）' }}</span>
      </li>
    </ul>
    <p v-if="moreCount" class="headline-more" data-testid="r48-headline-more">另有 {{ moreCount }} 处命中未在这张卡上列出。</p>
    <p v-if="hiddenCount" class="headline-more" data-testid="r48-headline-hidden">另有 {{ hiddenCount }} 处命中不在你的可见范围内。</p>
    <p class="headline-detail" data-testid="r48-headline-detail">
      {{ face.detail }}<span v-if="cardAge" class="headline-age">（发卡读数：本轮开始后 {{ cardAge }}）</span>
    </p>
  </section>
</template>

<style scoped>
.headline-card {
  margin: 0 0 var(--s-2);
  padding: var(--s-2);
  border: 1px solid var(--border-1);
  border-left: 2px solid var(--border-2);
  border-radius: var(--r-sm);
  background: var(--surface-1);
  font-size: var(--t-xs);
  color: var(--text-2);
}

.headline-title {
  margin: 0;
  font-size: var(--t-sm);
  color: var(--text-1);
}

.headline-rows {
  margin: var(--s-1) 0 0;
  padding-left: var(--s-3);
  display: grid;
  gap: var(--s-1);
}

.headline-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: var(--s-1);
}

.headline-file {
  color: var(--text-1);
}

.headline-tag {
  padding: 0 var(--s-1);
  border: 1px solid var(--border-1);
  border-radius: var(--r-sm);
  font-size: var(--t-xs);
  color: var(--text-3);
}

.headline-more {
  margin: var(--s-1) 0 0;
  color: var(--text-3);
}

.headline-detail {
  margin: var(--s-1) 0 0;
  color: var(--text-3);
}

.headline-age {
  color: var(--text-3);
}

.headline-card--info {
  border-left-color: var(--accent);
}

.headline-card--warn {
  border-left-color: var(--warning);
}

.headline-card--warn .headline-title {
  color: var(--warning);
}
</style>