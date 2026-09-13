from datetime import datetime
import re

def render_filename(template,title,item_id,platform):
    vals={'title':title or 'media','id':str(item_id),'date':datetime.utcnow().strftime('%Y-%m-%d'),'platform':platform or 'media'}
    out=template
    for k,v in vals.items(): out=out.replace('{'+k+'}',str(v))
    return (re.sub(r'[^A-Za-z0-9._ -]+','_',out).strip(' .') or 'media')[:180]
