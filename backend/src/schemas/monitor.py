from pydantic import BaseModel,Field,ConfigDict
from datetime import datetime
class MonitorInput(BaseModel):
    name:str=Field(min_length=2,max_length=140)
    study_id:int
    alpha:float=Field(default=.05,gt=0,lt=1,allow_inf_nan=False,strict=True)
    planned_total:int|None=Field(default=None,ge=1,le=2000)
class StopInput(BaseModel):
    note:str=Field(min_length=2,max_length=600)
class MonitorOut(BaseModel):
    id:int
    name:str
    study_id:int
    alpha:float
    status:str
    look_rule:str
    look_count:int
    plan_snapshot:dict
    plan_fingerprint:str
    last_evidence:dict
    started_by:str
    started_at:datetime
    stopped_at:datetime|None
    stopped_by:str
    stop_note:str
    stopped_look_count:int
    stopped_input_fingerprint:str
    stop_evidence:dict
    model_config=ConfigDict(from_attributes=True)
class LookOut(BaseModel):
    id:int
    monitor_id:int
    look_index:int
    evidence:dict
    input_fingerprint:str
    created_by:str
    created_at:datetime
    model_config=ConfigDict(from_attributes=True)
