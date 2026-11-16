from datetime import datetime
from sqlalchemy import String,ForeignKey,UniqueConstraint,DateTime,JSON,Integer
from sqlalchemy.dialects.mysql import DOUBLE
from sqlalchemy.orm import Mapped,mapped_column
from src.config.database import Base
class SequentialMonitor(Base):
    __tablename__='sequential_monitors'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(140),unique=True)
    study_id:Mapped[int]=mapped_column(ForeignKey('grade_studies.id'))
    alpha:Mapped[float]=mapped_column(DOUBLE(asdecimal=False))
    status:Mapped[str]=mapped_column(String(20),default='active')
    plan_snapshot:Mapped[dict]=mapped_column(JSON,default=dict)
    plan_fingerprint:Mapped[str]=mapped_column(String(64),default='')
    look_rule:Mapped[str]=mapped_column(String(60),default='k-spending-6-over-pi2')
    look_count:Mapped[int]=mapped_column(Integer,default=0)
    last_evidence:Mapped[dict]=mapped_column(JSON,default=dict)
    started_by:Mapped[str]=mapped_column(String(140),default='')
    started_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    stopped_at:Mapped[datetime|None]=mapped_column(DateTime,nullable=True)
    stopped_by:Mapped[str]=mapped_column(String(140),default='')
    stop_note:Mapped[str]=mapped_column(String(600),default='')
    stopped_look_count:Mapped[int]=mapped_column(Integer,default=0)
    stopped_input_fingerprint:Mapped[str]=mapped_column(String(64),default='')
    stop_evidence:Mapped[dict]=mapped_column(JSON,default=dict)
class SequentialLook(Base):
    __tablename__='sequential_looks'
    id:Mapped[int]=mapped_column(primary_key=True)
    monitor_id:Mapped[int]=mapped_column(ForeignKey('sequential_monitors.id'))
    look_index:Mapped[int]=mapped_column(Integer)
    evidence:Mapped[dict]=mapped_column(JSON,default=dict)
    readings_snapshot:Mapped[list]=mapped_column(JSON,default=list)
    input_fingerprint:Mapped[str]=mapped_column(String(64),default='')
    created_by:Mapped[str]=mapped_column(String(140),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('monitor_id','look_index'),)
    def __getitem__(self,key):return getattr(self,key)
