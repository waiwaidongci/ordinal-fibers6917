<script setup lang="ts">import {onMounted,ref,computed,watch} from 'vue';import {useRoute,useRouter} from 'vue-router';import {useStudies} from '../stores/studies';import {useMonitors} from '../stores/monitors';import {useAuth} from '../stores/auth';import {useTask} from '../hooks/useTask';import {usePolling} from '../hooks/usePolling';import {num,pvalue,date} from '../utils/format';import type {MonitorEvidence,MonitorLook} from '../types/domain';import PageHeading from '../components/common/PageHeading.vue';import ErrorNotice from '../components/common/ErrorNotice.vue';import StatusBadge from '../components/common/StatusBadge.vue';import StudySelect from '../components/StudySelect.vue';import MonitorPairTable from '../components/MonitorPairTable.vue';
const route=useRoute(),router=useRouter(),study=useStudies(),monitors=useMonitors(),auth=useAuth(),{error,busy,perform}=useTask();
const name=ref(''),alpha=ref(.05),planned=ref<number|null>(null),tab=ref('pairs'),tracePair=ref(''),traceStep=ref(5),stopNote=ref(''),message=ref(''),selectedLook=ref(0);
const current=computed(()=>monitors.current);
const evidence=computed<MonitorEvidence|null>(()=>{const e=current.value?.last_evidence as MonitorEvidence|undefined;return e&&Array.isArray(e.pairs)?e:null});
const openId=computed(()=>Number(route.params.id||0));
const shownEvidence=computed<MonitorEvidence|null>(()=>{if(!selectedLook.value)return evidence.value;const l=monitors.looks.find((l:MonitorLook)=>l.look_index===selectedLook.value);return l?l.evidence:evidence.value});
const shownLookIndex=computed(()=>shownEvidence.value?.look_index||0);
const spentShown=computed(()=>shownEvidence.value?shownEvidence.value.spending_share*shownEvidence.value.family_size:0);
const pairOptions=computed(()=>evidence.value?evidence.value.pairs.map(p=>({key:p.left_id+'-'+p.right_id,label:p.left_code+' '+p.left_name+' 对 '+p.right_code+' '+p.right_name})):[]);
const stopEvidence=computed<MonitorEvidence|null>(()=>{const e=current.value?.stop_evidence as MonitorEvidence|undefined;return e&&Array.isArray(e.pairs)?e:null});
const prefixInAllPairs=computed(()=>{const e=shownEvidence.value;if(!e||!e.specimen_counts.length)return 0;return Math.min(...e.specimen_counts.map(g=>g.n))});
onMounted(()=>perform(async()=>{await study.load();await monitors.load();const id=openId.value||monitors.selected;if(id)await monitors.open(id);if(!tracePair.value&&pairOptions.value.length)tracePair.value=pairOptions.value[0].key;}));
watch(openId,id=>{if(id&&id!==monitors.selected)perform(()=>monitors.open(id));});
watch(pairOptions,opts=>{if(!opts.some(o=>o.key===tracePair.value))tracePair.value=opts[0]?.key||'';});
usePolling(async()=>{if(current.value?.status==='active')await monitors.loadDetail();});
async function start(){const p=planned.value;const planned_total=typeof p==='number'&&Number.isFinite(p)?p:null;const s=await monitors.create({name:name.value,study_id:study.selected,alpha:alpha.value,planned_total});name.value='';message.value='监测已开始：工艺与α已锁定，查看次数从第1回起计入整族预算。';router.push('/monitor/'+s.id);}
function open(id:number){router.push('/monitor/'+id);}
async function recordLook(){const intended=(current.value?.look_count||0)+1;const l=await monitors.look(intended);selectedLook.value=0;message.value='第'+l.look_index+'回查看已就绪；同一回重试不会重复消耗预算。';}
async function stop(){const s=await monitors.stop(stopNote.value);stopNote.value='';message.value='已在第'+s.look_count+'回停看；结论保留，不再新增查看。';}
async function doReplay(){const r=await monitors.replay();message.value=r.identical?'完整重放一致：'+r.looks+'回证据逐字节相符。':'重放不一致，请核对第'+r.mismatched_looks.join('、')+'回。';}
async function doTrace(){if(!tracePair.value)return;await monitors.trace(tracePair.value,traceStep.value);tab.value='trace';}
const th=(n:number)=>num(n,4);
</script>
<template>
<PageHeading no="07" title="持续监测" sub="盲评陆续到达时反复查看：工艺与α在开始前锁定，全部组对的优胜证据按查看次数分摊整族误报。"/>
<ErrorNotice :error="error"/>
<p v-if="message" class="success" role="status">{{message}}</p>
<div class="monitor-spread">
<section>
<h2 class="ruled-title">已开始的监测 <small>{{monitors.items.length}}项</small></h2>
<article v-for="m in monitors.items" :key="m.id" :class="['monitor-entry',{active:m.id===monitors.selected}]">
<div class="entry-line"><small>MONITOR {{m.id}}</small><StatusBadge :status="m.status"/></div>
<h3>{{m.name}}</h3>
<p>{{(m.plan_snapshot.treatments||[]).length}}工艺 / α {{m.alpha}} / 已查看 {{m.look_count}}回</p>
<small>{{m.started_by}} · {{date(m.started_at)}}<template v-if="m.stopped_at"> · 停看于 {{date(m.stopped_at)}}</template></small>
<button class="text-link" @click="open(m.id)">打开监测 ↗</button>
</article>
<p v-if="!monitors.items.length" class="empty">尚无监测。先核对工艺与独立试样，再在下方锁定计划并开始。</p>
<details v-if="auth.canEdit" class="edit-fold" :open="!monitors.items.length">
<summary>＋ 开始持续监测（锁定工艺与α）</summary>
<StudySelect/>
<form class="run-form" @submit.prevent="perform(start)">
<label>监测名称<input v-model="name" required minLength="2" maxLength="140" placeholder="例如：形成错位 · 盲评到达监测"/></label>
<label>预设整族显著性 α<input v-model.number="alpha" type="number" min="0.000001" max="0.999999" step="any" required/></label>
<label>每组预定份数（可选，不预设总批数）<input v-model.number="planned" type="number" min="1" max="2000" step="1" placeholder="留空表示不设定，只报告已到与待配齐"/></label>
<div class="method-note"><b>开始后即锁定</b><p>锁定当前研究已登记的2–5个工艺、组对方向与α；新增工艺不进入本监测。α是整族、任意停看时刻的误报上限，不是每回查看的独立阈值。</p></div>
<button class="primary" :disabled="busy||!auth.canEdit">冻结计划并开始 →</button>
</form>
</details>
<aside class="margin-note"><b>为什么反复查看不会放大误报</b><p>第k回查看、m个组对中，每个组对只用 α·6/(π²k²m) 的预算；全部查看与组对求和恰为α。因为可以依据已有结果调整后续取样、停看时刻也可能依赖已见数据，这个任意前缀、任意停看的界仍然成立。</p><p>证据是精确符号检验；并列不计方向，只在θ里计半。未拒绝不表示工艺相同或等效。</p></aside>
</section>
<section>
<div v-if="!current" class="empty"><h2>选一项监测</h2><p>没有监测时先在左侧开始；查看次数与每次证据都会留档。</p></div>
<template v-else>
<div class="result-byline"><b>#{{current.id}} {{current.name}}</b><StatusBadge :status="current.status"/></div>
<div class="monitor-plan">
<p><small>锁定计划</small>{{(current.plan_snapshot.treatments||[]).map(t=>t.code+' '+t.name).join(' / ')}}</p>
<p><small>整族α / 已查看</small>{{current.alpha}} / {{current.look_count}} 回</p>
<p><small>计划指纹</small><code>{{current.plan_fingerprint.slice(0,16)}}…</code></p>
<p v-if="monitors.locking?.locked_at"><small>锁定于</small>{{date(monitors.locking.locked_at)}}</p>
<p v-if="monitors.locking?.supersedes.length"><small>延续自</small><span v-for="p in monitors.locking.supersedes" :key="p.id">#{{p.id}} {{p.name}}（{{p.looks}}回 · {{p.status==='stopped'?'已停看':'进行中'}}）</span></p>
</div>
<div v-if="monitors.locking" :class="['monitor-flag',monitors.locking.intact?'ok':'warn']">
<b>{{monitors.locking.intact?'锁定计划与登记一致':'锁定计划外有改动'}}</b>
<span v-for="c in monitors.locking.changes" :key="c">{{c}}；监测仍按锁定计划计算。</span>
</div>
<div v-if="monitors.status" :class="['monitor-flag',(monitors.status.source_changed||monitors.status.stopped_conclusion_invalidated)?'warn':'ok']">
<b>{{monitors.status.never_viewed?'尚无查看':monitors.status.stopped_conclusion_invalidated?'停看结论已失效':monitors.status.source_changed?'旧证据已失效':'当前输入与旧证据一致'}}</b>
<span>{{monitors.status.note}}</span>
<small v-if="monitors.status.recorded_input_fingerprint">记录指纹 {{monitors.status.recorded_input_fingerprint.slice(0,16)}}… → 当前 {{monitors.status.current_input_fingerprint.slice(0,16)}}…</small>
</div>
<div class="button-row">
<button class="primary" :disabled="busy||current.status!=='active'||!auth.canEdit" @click="perform(recordLook)">记录第 {{current.look_count+1}} 回查看 ⇢</button>
<button :disabled="busy||!current.look_count" @click="perform(doReplay)">完整重放校验 ↻</button>
</div>
<p v-if="!auth.canEdit" class="muted">观察员可阅读与追查证据；请分析员记录查看或停看。</p>
<form v-if="current.status==='active'&&auth.canEdit" class="stop-form" @submit.prevent="perform(stop)"><label>停看说明<input v-model="stopNote" required minLength="2" maxLength="600" placeholder="例如：第3回停看；按锁定α阅读整族证据"/></label><button :disabled="busy||current.look_count<1">停看并保留结论</button></form>
<div v-else-if="current.status==='stopped'" class="stop-record">
<b>已停看 · 第{{current.stopped_look_count}}回结论保留</b>
<p>{{current.stop_note}}<template v-if="current.stopped_by">（{{current.stopped_by}}）</template></p>
<p v-if="stopEvidence" class="muted">停看时整族最强证据 p={{pvalue(stopEvidence.family_p)}}；{{stopEvidence.decisive?'在α下拒绝至少一组对':'未达预设α'}}。不再新增查看；需要新证据请另立监测。</p>
<p v-if="monitors.status?.stopped_conclusion_invalidated" class="error-text">停看后源数据又被更正：以上停看结论原样保留，但已标为失效，不能代表当前输入。</p>
<p class="muted">如需按更正后的输入继续，可另立监测；新监测会记录它延续自这一项，但α预算重新起算，不与旧监测合并。</p>
</div>
<template v-if="evidence">
<div v-if="monitors.status?.source_changed&&!selectedLook" class="monitor-flag warn"><b>最新证据已失效</b><span>源数据在记录本次查看后被更正；以下数字是当时输入的原样留档，不代表当前输入。记录下一回查看可按当前输入重算。</span></div>
<div class="result-metrics monitor-metrics">
<div><small>本回序号 k</small><strong>{{shownLookIndex}}</strong><span>预算 6/(π²k²m)</span></div>
<div><small>每组对本次预算</small><strong>{{num(shownEvidence!.spending_share,5)}}</strong><span>占α · 全族合计 {{num(spentShown,5)}}</span></div>
<div><small>全部组对已配齐</small><strong>{{prefixInAllPairs}}<i>份/组</i></strong><span>{{shownEvidence!.total_specimens}}份在锁定工艺内</span></div>
<div><small>整族最强证据 p</small><strong>{{pvalue(shownEvidence!.family_p)}}</strong><span>{{shownEvidence!.decisive?'在α下拒绝至少一组对':'尚未到达预设α'}}</span></div>
</div>
<div class="result-tabs"><button :class="{active:tab==='pairs'}" @click="tab='pairs'">全部组对 / 优胜证据</button><button :class="{active:tab==='waiting'}" @click="tab='waiting'">等待配齐与计数</button><button :class="{active:tab==='looks'}" @click="tab='looks'">查看留档与重放</button><button :class="{active:tab==='trace'}" @click="tab='trace'">追查前缀证据</button></div>
<section v-if="tab==='pairs'">
<p class="muted">θ = (W + T/2)/m 是本组对中左工艺等级更高的份额，并列计半；证据用 W 对 L 的精确符号检验，并列不提供方向。全部组对都列出，未达到α也不隐藏。</p>
<MonitorPairTable :pairs="shownEvidence!.pairs" :alpha="shownEvidence!.alpha"/>
<p class="method-note">整族误报：第k回每组对可分 {{num(shownEvidence!.spending_share,6)}}×α；全部查看与组对求和恰为α，因此无论何时停看，整族至少一次误报的概率不超过α。查看越多，后续每回的预算越小。</p>
</section>
<section v-if="tab==='waiting'">
<h2 class="ruled-title">各工艺到达与待配齐试样 <small>同一组对内每份只用一次</small></h2>
<div class="table-scroll"><table><thead><tr><th>工艺</th><th>已到试样</th><th>已进入全部组对</th><th>等待配齐</th></tr></thead><tbody>
<tr v-for="w in shownEvidence!.waiting_by_group" :key="w.id"><td><b>{{w.code}}</b><small>{{w.name}}</small></td><td>{{w.n}}<small v-if="shownEvidence!.planned_total">预定 {{shownEvidence!.planned_total}} / 还差 {{Math.max(0,shownEvidence!.planned_total-w.n)}}</small><small v-else>未预设总量</small></td><td>{{prefixInAllPairs}}</td><td>{{w.waiting.length}}<small v-if="w.waiting.length">{{w.waiting.join('、')}}</small><small v-else>无</small></td></tr>
</tbody></table></div>
<p class="muted">程序按入库顺序在各工艺内排队，组对只使用两边共同前缀 min(nᵢ,nⱼ) 份：左第r份对右第r份，每份试样在同一组对中只使用一次。多出的试样按编号列出，等其余工艺补齐后自动进入下一次查看；它们不参与当前的组对证据。</p>
</section>
<section v-if="tab==='looks'">
<h2 class="ruled-title">查看留档 <small>{{monitors.looks.length}}回</small></h2>
<label class="inline-select">回看证据<select v-model.number="selectedLook"><option :value="0">最新（第{{evidence.look_index}}回）</option><option v-for="l in monitors.looks" :key="l.id" :value="l.look_index">第{{l.look_index}}回 · {{date(l.created_at)}}</option></select></label>
<div class="table-scroll"><table><thead><tr><th>回</th><th>每组对预算</th><th>整族p</th><th>决定</th><th>输入指纹</th><th>记录</th></tr></thead><tbody>
<tr v-for="l in monitors.looks" :key="l.id"><td>{{l.look_index}}</td><td>{{num(l.evidence.spending_share,5)}}</td><td>{{pvalue(l.evidence.family_p)}}</td><td :class="l.evidence.decisive?'reject':'muted'">{{l.evidence.decisive?'拒绝':'未拒绝'}}</td><td><code>{{l.input_fingerprint.slice(0,12)}}…</code><small v-if="monitors.status&&l.input_fingerprint!==monitors.status.current_input_fingerprint" class="error-text">源数据已变 · 该回失效</small><small v-else>与当前输入一致</small></td><td>{{l.created_by}}<small>{{date(l.created_at)}}</small></td></tr>
</tbody></table></div>
<div v-if="monitors.replayResult" :class="['monitor-flag',monitors.replayResult.identical?'ok':'warn']">
<b>{{monitors.replayResult.identical?'完整重放一致':'重放存在差异'}}</b>
<small>{{monitors.replayResult.looks}}回 / 已花整族预算 {{num(monitors.replayResult.spent_fraction_family,5)}} / {{monitors.replayResult.look_rule}}</small>
<span>{{monitors.replayResult.note}}</span>
</div>
<p class="fingerprint">当前输入 SHA256 <code>{{shownEvidence!.input_fingerprint}}</code></p>
<p class="fingerprint">锁定计划 SHA256 <code>{{shownEvidence!.plan_fingerprint}}</code></p>
</section>
<section v-if="tab==='trace'">
<h2 class="ruled-title">追查一个组对的前缀证据 <small>逐份配齐时的 W/L/T 与 θ</small></h2>
<form class="trace-form" @submit.prevent="perform(doTrace)">
<label>组对<select v-model="tracePair" aria-label="追查组对"><option v-for="o in pairOptions" :key="o.key" :value="o.key">{{o.label}}</option></select></label>
<label>每几步取一行<input v-model.number="traceStep" type="number" min="1" max="500" step="1" required/></label>
<button :disabled="busy||!tracePair">读取前缀证据</button>
</form>
<div v-if="monitors.traceResult" class="trace-result">
<p class="muted">{{monitors.traceResult.left_code}} {{monitors.traceResult.left_name}} 对 {{monitors.traceResult.right_code}} {{monitors.traceResult.right_name}}：已配齐 {{monitors.traceResult.paired}} 份。</p>
<div class="table-scroll"><table><thead><tr><th>第r份</th><th>W / L / 并列</th><th>θ</th><th>ψ</th><th>原始符号p</th></tr></thead><tbody>
<tr v-for="row in monitors.traceResult.prefix" :key="row.r"><td>{{row.r}}</td><td>{{row.win_left}} / {{row.loss_left}} / {{row.ties}}</td><td>{{th(row.theta_left_higher_half_ties)}}</td><td>{{num(row.psi_left_minus_right,4)}}</td><td>{{pvalue(row.p_exact_sign)}}</td></tr>
</tbody></table></div>
<div class="trace-waiting">
<div><b>本组对中等待配齐 · {{monitors.traceResult.left_code}}</b><p v-if="monitors.traceResult.waiting_left.length">{{monitors.traceResult.waiting_left.map(r=>r.specimen_code+'（等级'+r.grade+'）').join('、')}}</p><p v-else class="muted">无；该工艺是当前配对前缀的短板。</p></div>
<div><b>本组对中等待配齐 · {{monitors.traceResult.right_code}}</b><p v-if="monitors.traceResult.waiting_right.length">{{monitors.traceResult.waiting_right.map(r=>r.specimen_code+'（等级'+r.grade+'）').join('、')}}</p><p v-else class="muted">无；该工艺是当前配对前缀的短板。</p></div>
</div>
<p class="fingerprint">追查只按第{{monitors.traceResult.look_index}}回留档的读数快照（指纹 {{(monitors.traceResult.input_fingerprint||'').slice(0,16)}}…）重算，不含此后新到或更正的试样。</p>
</div>
<p v-else class="muted">选择一个组对与步长，读取逐份配齐时的 W/L/T、θ与原始符号p。</p>
</section>
</template>
<div v-else class="empty"><p>监测已建立，尚无查看。记录第一回即产生可重放的证据。</p></div>
<div class="result-boundary"><b>解释边界</b><p>按任意停看控制的是整族误报率，不控制估计偏差；查看次数会消耗预算，越往后越保守。证据是精确符号检验，等级仍非等距，差异也可能来自分布形状；不证明工艺原因或性能概率。</p></div>
</template>
</section>
</div>
</template>
