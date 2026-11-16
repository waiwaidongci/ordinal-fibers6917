import json
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from src.models import GradeStudy,Treatment,GradeReading,SequentialMonitor,SequentialLook
from src.services.sequential import (ALGORITHM,build_evidence,prefix_trace,readings_fingerprint,
    validate_alpha,look_spending,canonical_json)
from src.constants.enums import MonitorStatus
from datetime import datetime

LOCK_RULE='工艺、alpha与组对方向在开始前锁定；之后新增工艺不进入本监测'


def list_monitors(db):return db.scalars(select(SequentialMonitor).order_by(SequentialMonitor.id.desc())).all()

def get_monitor(db,id):
    m=db.get(SequentialMonitor,id)
    if not m:raise HTTPException(404,'持续监测不存在')
    return m

def list_looks(db,monitor_id):
    get_monitor(db,monitor_id)
    return db.scalars(select(SequentialLook).where(SequentialLook.monitor_id==monitor_id).order_by(SequentialLook.look_index)).all()

def get_look(db,monitor_id,look_index):
    l=db.scalar(select(SequentialLook).where(SequentialLook.monitor_id==monitor_id,SequentialLook.look_index==look_index))
    if not l:raise HTTPException(404,'该次查看没有证据记录')
    return l

def _locked_readings(db,monitor):
    ids=[t['id'] for t in monitor.plan_snapshot['treatments']]
    rows=db.scalars(select(GradeReading).where(GradeReading.study_id==monitor.study_id)).all()
    used=[];excluded=0
    for r in rows:
        if r.treatment_id in ids:used.append(r)
        else:excluded+=1
    payload=[{'id':r.id,'treatment_id':r.treatment_id,'specimen_code':r.specimen_code,'grade':float(r.grade)} for r in used]
    return payload,excluded

def create_monitor(db,data,user):
    study=db.get(GradeStudy,data.study_id)
    if not study:raise HTTPException(404,'等级研究不存在')
    if db.scalar(select(SequentialMonitor).where(SequentialMonitor.name==data.name)):raise HTTPException(409,'监测名称重复')
    if db.scalar(select(SequentialMonitor).where(SequentialMonitor.study_id==study.id,SequentialMonitor.status==MonitorStatus.ACTIVE)):
        raise HTTPException(409,'同一研究已有进行中的监测；继续查看须用同一监测，否则会重置整族α预算。数据更正后如需新证据，请先停看再另立监测')
    prior=[{'id':m.id,'name':m.name,'looks':m.look_count,'status':m.status} for m in db.scalars(select(SequentialMonitor).where(SequentialMonitor.study_id==study.id).order_by(SequentialMonitor.id)).all()]
    treatments=db.scalars(select(Treatment).where(Treatment.study_id==study.id).order_by(Treatment.code)).all()
    if not 2<=len(treatments)<=5:raise HTTPException(422,'持续监测须在研究已登记2–5个预定义工艺后开始')
    counts=db.execute(select(GradeReading.treatment_id,func.count()).where(GradeReading.study_id==study.id).group_by(GradeReading.treatment_id)).all()
    per_group={tid:n for tid,n in counts}
    if any(per_group.get(t.id,0)<1 for t in treatments):raise HTTPException(422,'每个锁定工艺至少要有1份试样，空组无法配齐')
    largest_group=max(per_group.get(t.id,0) for t in treatments)
    planned_total=data.planned_total
    if planned_total is not None:
        if planned_total<1 or planned_total>2000:raise HTTPException(422,'预定总批数须在1–2000之间')
        if planned_total<largest_group:raise HTTPException(422,'预定总批数不能小于单组已到试样数')
    plan={'algorithm':ALGORITHM,'planned_total':planned_total,
          'locked_at':datetime.utcnow().isoformat(timespec='seconds'),
          'study':{'id':study.id,'code':study.code,'name':study.name},
          'treatments':[{'id':t.id,'code':t.code,'name':t.name} for t in treatments],
          'alpha':validate_alpha(data.alpha),'look_rule':'k-spending-6-over-pi2',
          'supersedes':prior,'notes':LOCK_RULE}
    m=SequentialMonitor(name=data.name,study_id=study.id,alpha=plan['alpha'],status=MonitorStatus.ACTIVE,
        plan_snapshot=plan,plan_fingerprint=build_evidence(plan,[],1)['plan_fingerprint'],
        look_rule=plan['look_rule'],look_count=0,last_evidence={},started_by=user.email)
    db.add(m);db.commit();return m

def record_look(db,monitor_id,user,look_index=None):
    m=get_monitor(db,monitor_id)
    if m.status!=MonitorStatus.ACTIVE:raise HTTPException(409,'监测已停看；新证据须新建监测，旧记录保留')
    nxt=m.look_count+1
    if look_index is not None and look_index not in (m.look_count,nxt):
        raise HTTPException(422,f'查看见证须按顺序：下一回为第{nxt}回（当前输入重算），不能跳过')
    readings,excluded=_locked_readings(db,m)
    current_fp=readings_fingerprint(readings)
    existing=db.scalar(select(SequentialLook).where(SequentialLook.monitor_id==m.id,SequentialLook.look_index==nxt))
    if existing:
        # 同一回重试，输入未变则幂等返回；输入已变则不重复计一次查看。
        if existing.input_fingerprint==current_fp:return existing,False
        raise HTTPException(409,'该回已记录且源数据此后有变动；请核对已留档证据，不要覆盖查看记录')
    retried=db.scalar(select(SequentialLook).where(SequentialLook.monitor_id==m.id,SequentialLook.look_index==look_index)) if look_index==m.look_count else None
    if retried:
        if retried.input_fingerprint==current_fp:return retried,False
        raise HTTPException(409,'该回已记录且源数据此后有变动；请核对已留档证据，不要覆盖查看记录')
    try:evidence=build_evidence(m.plan_snapshot,readings,nxt,excluded=excluded,planned_total=(m.plan_snapshot.get('planned_total') or None))
    except ValueError as exc:raise HTTPException(422,str(exc))
    l=SequentialLook(monitor_id=m.id,look_index=nxt,evidence=evidence,
        readings_snapshot=readings,input_fingerprint=evidence['input_fingerprint'],created_by=user.email)
    db.add(l);m.look_count=nxt;m.last_evidence=evidence
    try:db.commit()
    except IntegrityError:
        # 并发的同一回请求：唯一键(monitor_id,look_index)只允许一条，另一条按幂等规则返回。
        db.rollback();winner=get_look(db,m.id,nxt)
        if winner.input_fingerprint==evidence['input_fingerprint']:return winner,False
        raise HTTPException(409,'该回已被并发记录且输入不同；请刷新后核对留档证据')
    return l,True

def stop_monitor(db,monitor_id,data,user):
    m=get_monitor(db,monitor_id)
    if m.status!=MonitorStatus.ACTIVE:raise HTTPException(409,'监测已停看，结论保留且不改写')
    if m.look_count<1:raise HTTPException(409,'请先记录至少一次查看，再停看并保留结论')
    m.status=MonitorStatus.STOPPED;m.stopped_at=datetime.utcnow();m.stopped_by=user.email;m.stop_note=data.note
    m.stopped_look_count=m.look_count;m.stopped_input_fingerprint=readings_fingerprint(_locked_readings(db,m)[0])
    m.stop_evidence=m.last_evidence
    db.commit();return m

def staleness(db,m):
    """源数据是否已改动；旧证据保留但标记失效，下一次查看按当前输入重算。"""
    current,_=_locked_readings(db,m)
    current_fp=readings_fingerprint(current)
    recorded=(m.last_evidence or {}).get('input_fingerprint')
    changed=bool(recorded) and current_fp!=recorded
    stopped=m.status==MonitorStatus.STOPPED
    stopped_stale=stopped and bool(m.stopped_input_fingerprint) and current_fp!=m.stopped_input_fingerprint
    if stopped_stale:note='停看后源数据又被更正：停看时的结论原样保留，但已标为失效，不能代表当前输入；需要新证据请另立监测'
    elif stopped:note='监测已停看；停看时的结论保留，不代表之后的源数据变化'
    elif changed:note='源数据已更新：此前证据仍保留，但不再代表当前输入；记录下一次查看即重算'
    elif not recorded:note='尚无查看记录'
    else:note='当前输入与此前证据一致'
    return {'recorded_input_fingerprint':recorded,'current_input_fingerprint':current_fp,
            'source_changed':changed,'never_viewed':not recorded,
            'stopped':stopped,'stopped_look_count':m.stopped_look_count,
            'stopped_input_fingerprint':m.stopped_input_fingerprint or None,
            'stopped_conclusion_invalidated':stopped_stale,
            'note':note}

def locking_status(db,m):
    """锁定快照与当前登记的一致性：名称/编号改动不改写锁定计划，只如实提示。"""
    study=db.get(GradeStudy,m.study_id)
    problems=[]
    if not study:problems.append('研究已不存在')
    else:
        if study.code!=m.plan_snapshot['study']['code']:problems.append('研究编号已改动')
        if study.name!=m.plan_snapshot['study']['name']:problems.append('研究名称已改动')
        for t in m.plan_snapshot['treatments']:
            row=db.get(Treatment,t['id'])
            if not row:problems.append(f'{t["code"]} 工艺已不存在')
            elif row.code!=t['code'] or row.name!=t['name']:problems.append(f'{t["code"]} 工艺名称/编号已改动')
        extra=db.scalars(select(Treatment).where(Treatment.study_id==m.study_id)).all()
        if len(extra)!=len(m.plan_snapshot['treatments']):
            problems.append('研究登记了锁定之外的工艺，本监测不纳入')
    return {'plan_fingerprint':m.plan_fingerprint,'intact':not problems,'changes':problems,
            'locked_treatments':m.plan_snapshot['treatments'],'alpha':m.alpha,'look_rule':m.look_rule,
            'locked_at':m.plan_snapshot.get('locked_at'),'planned_total':m.plan_snapshot.get('planned_total'),
            'supersedes':m.plan_snapshot.get('supersedes',[])}

def replay(db,monitor_id):
    """从每次查看保存的读数快照完整重放；证据须逐字节一致。"""
    m=get_monitor(db,monitor_id)
    looks=db.scalars(select(SequentialLook).where(SequentialLook.monitor_id==m.id).order_by(SequentialLook.look_index)).all()
    mismatches=[]
    for l in looks:
        stored=json.loads(canonical_json(l.evidence))
        rebuilt=build_evidence(m.plan_snapshot,l.readings_snapshot,l.look_index,
                               excluded=int(stored.get('excluded_reading_count',0)),
                               planned_total=stored.get('planned_total'))
        if canonical_json(rebuilt)!=canonical_json(stored):
            mismatches.append(l.look_index)
    family_size=(m.last_evidence or {}).get('family_size') or (len(m.plan_snapshot['treatments'])*(len(m.plan_snapshot['treatments'])-1)//2)
    per_pair=sum(look_spending(k,family_size) for k in range(1,m.look_count+1)) if m.look_count else 0.0
    return {'monitor_id':m.id,'looks':len(looks),'identical':not mismatches,
            'mismatched_looks':mismatches,'look_rule':m.look_rule,'family_size':family_size,
            'spent_fraction_per_pair':per_pair,'spent_fraction_family':per_pair*family_size,
            'note':('逐次查看按保存的读数快照与锁定计划重算；不含时间戳与随机数，重放结果与首次记录一致。'
                    '已花整族预算为各回各组分摊之和；继续查看最多用满alpha，停看不会退回预算')}

def trace(db,monitor_id,pair_key,step=1):
    """追查证据：只按最近一次已留档查看的读数快照重算，不读取尚未记录的新数据。"""
    m=get_monitor(db,monitor_id)
    if m.look_count<1:raise HTTPException(409,'尚无查看记录；追查只基于已留档的输入，不能替代一次查看')
    look=get_look(db,m.id,m.look_count)
    try:
        result=prefix_trace(m.plan_snapshot,look.readings_snapshot,pair_key,step)
    except ValueError as exc:raise HTTPException(422,str(exc))
    return {**result,'monitor_id':m.id,'look_index':look.look_index,
            'input_fingerprint':look.input_fingerprint,
            'note':'按第%d回留档的读数快照重算；不包含此后新到或更正的试样'%look.look_index}
