import {defineStore} from 'pinia';import {ref,computed} from 'vue';import * as api from '../api/monitors';import type {Monitor,MonitorLook,MonitorStatus,MonitorLocking,MonitorReplay,MonitorTrace} from '../types/domain';
export const useMonitors=defineStore('monitors',()=>{
 const items=ref<Monitor[]>([]),selected=ref(Number(localStorage.getItem('ordinal-monitor')||0)),looks=ref<MonitorLook[]>([]),status=ref<MonitorStatus|null>(null),locking=ref<MonitorLocking|null>(null),replayResult=ref<MonitorReplay|null>(null),traceResult=ref<MonitorTrace|null>(null);
 const current=computed(()=>items.value.find(m=>m.id===selected.value));
 async function load(){items.value=await api.list();if(!items.value.some(m=>m.id===selected.value))selected.value=items.value[0]?.id||0;}
 function select(id:number){selected.value=id;localStorage.setItem('ordinal-monitor',String(id));}
 async function open(id:number){select(id);replayResult.value=null;traceResult.value=null;await loadDetail();}
 async function loadDetail(){const id=selected.value;if(!id){looks.value=[];status.value=null;locking.value=null;replayResult.value=null;traceResult.value=null;return;}
  const [l,s,k]=await Promise.all([api.looks(id),api.status(id),api.locking(id)]);looks.value=l;status.value=s;locking.value=k;}
 async function create(data:unknown){const m=await api.create(data);await load();await open(m.id);return m;}
 async function look(lookIndex?:number){const l=await api.look(selected.value,lookIndex);await load();await open(selected.value);return l;}
 async function stop(note:string){const m=await api.stop(selected.value,note);await load();await open(selected.value);return m;}
 async function replay(){replayResult.value=await api.replay(selected.value);return replayResult.value;}
 async function trace(pair:string,step:number){traceResult.value=await api.trace(selected.value,pair,step);return traceResult.value;}
 return {items,selected,current,looks,status,locking,replayResult,traceResult,load,select,open,loadDetail,create,look,stop,replay,trace};});
