<script setup lang="ts">import type {MonitorPair} from '../types/domain';import {num,pvalue} from '../utils/format';defineProps<{pairs:MonitorPair[];alpha:number}>()</script>
<template>
<div class="table-scroll">
<table class="pair-table monitor-pair-table">
<thead><tr><th>全部锁定组对</th><th>已配齐<br/>m份</th><th>W / L / 并列</th><th>θ<br/>左更高+并列/2</th><th>原始符号p<br/>精确双侧</th><th>随时可停看 p</th><th>α={{alpha}}</th></tr></thead>
<tbody><tr v-for="p in pairs" :key="p.left_id+'-'+p.right_id">
<td><b>{{p.left_code}} {{p.left_name}}</b><small>对 {{p.right_code}} {{p.right_name}}</small></td>
<td>{{p.paired}}<small v-if="p.waiting_left_count||p.waiting_right_count">待 {{p.waiting_left_count}} / {{p.waiting_right_count}}</small></td>
<td>{{p.win_left}} / {{p.loss_left}} / {{p.ties}}</td>
<td>{{p.theta_left_higher_half_ties==null?'—':num(p.theta_left_higher_half_ties,4)}}<small>{{p.direction==='none'?'无方向':p.direction==='left'?'左侧等级更高':'右侧等级更高'}}</small></td>
<td>{{pvalue(p.p_exact_sign)}}</td>
<td>{{pvalue(p.p_anytime)}}</td>
<td :class="p.reject?'reject':'muted'">{{p.reject?'拒绝该组对零假设':'证据不足'}}</td>
</tr></tbody>
</table>
</div>
</template>
