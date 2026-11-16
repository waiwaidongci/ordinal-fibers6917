from fastapi import APIRouter,Depends,Query,Response
from src.config.database import get_db
from src.utils.auth import current_user,editor
from src.schemas.monitor import MonitorInput,MonitorOut,LookOut,StopInput
from src.controllers import monitor_controller as controller
router=APIRouter(prefix='/monitors',tags=['monitors'])
@router.get('',response_model=list[MonitorOut])
def index(db=Depends(get_db),user=Depends(current_user)):return controller.index(db)
@router.post('',response_model=MonitorOut,status_code=201)
def create(data:MonitorInput,db=Depends(get_db),user=Depends(editor)):return controller.create(db,data,user)
@router.get('/{id}',response_model=MonitorOut)
def detail(id:int,db=Depends(get_db),user=Depends(current_user)):return controller.detail(db,id)
@router.post('/{id}/looks',response_model=LookOut,status_code=201)
def look(id:int,response:Response,look_index:int|None=Query(default=None,ge=1),db=Depends(get_db),user=Depends(editor)):
    row,created=controller.look(db,id,user,look_index)
    if not created:response.status_code=200
    return row
@router.get('/{id}/looks',response_model=list[LookOut])
def looks(id:int,db=Depends(get_db),user=Depends(current_user)):return controller.looks(db,id)
@router.get('/{id}/looks/{look_index}',response_model=LookOut)
def look_detail(id:int,look_index:int,db=Depends(get_db),user=Depends(current_user)):return controller.look_detail(db,id,look_index)
@router.post('/{id}/stop',response_model=MonitorOut)
def stop(id:int,data:StopInput,db=Depends(get_db),user=Depends(editor)):return controller.stop(db,id,data,user)
@router.get('/{id}/status')
def status(id:int,db=Depends(get_db),user=Depends(current_user)):return controller.status(db,id)
@router.get('/{id}/locking')
def locking(id:int,db=Depends(get_db),user=Depends(current_user)):return controller.locking(db,id)
@router.get('/{id}/replay')
def replay(id:int,db=Depends(get_db),user=Depends(current_user)):return controller.replay(db,id)
@router.get('/{id}/trace')
def trace(id:int,pair:str,step:int=Query(default=1,ge=1,le=500),db=Depends(get_db),user=Depends(current_user)):return controller.trace(db,id,pair,step)
