def backoff(attempt:int,base:float=15,max_delay:float=900)->float:
    return min(max_delay,base*(2**max(0,attempt-1)))

def should_retry(error_text:str)->bool:
    e=(error_text or '').lower()
    transient=('timeout','temporarily','connection reset','429','502','503','504','network','incomplete read')
    permanent=('private','unsupported','invalid url','copyright')
    return any(x in e for x in transient) and not any(x in e for x in permanent)
