from datetime import datetime,timedelta

def next_run(now:datetime,cadence:str,hour:int,minute:int,weekday:int=0):
    base=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if cadence=='daily': return base if base>now else base+timedelta(days=1)
    days=(weekday-now.weekday())%7; target=base+timedelta(days=days)
    if target<=now: target+=timedelta(days=7)
    return target
