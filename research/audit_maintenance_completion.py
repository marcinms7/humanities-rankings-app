"""Read-only preservation and editorial-reference audit; emits no private values."""
import argparse,json,os,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));os.environ.setdefault('DJANGO_SETTINGS_MODULE','backend.config.settings')
import django;django.setup()
from django.conf import settings
from backend.core.models import Ranking

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--backup',default='data/backups/manual-20260928T193031987090Z.sqlite3');args=parser.parse_args()
 old=sqlite3.connect('file:'+str(ROOT/args.backup)+'?mode=ro',uri=True)
 current=sqlite3.connect('file:'+str(settings.DATABASES['default']['NAME'])+'?mode=ro',uri=True)
 report={'private_tables':{},'editorial_orders':{'checked':0,'issues':[]}}
 tables=['core_user','core_classicalstudyprofile','core_rankingpreference','core_libraryitem','core_readinggoal','core_readingattempt','core_planitem','core_readingadjustment']
 clauses={t:'' for t in tables};clauses.update({'core_ranking':" WHERE origin='personal'",'core_rankingentry':" WHERE ranking_id IN (SELECT id FROM core_ranking WHERE origin='personal')",'core_rankingrevision':" WHERE ranking_id IN (SELECT id FROM core_ranking WHERE origin='personal')"})
 for table,where in clauses.items():
  cols=','.join('"'+r[1]+'"' for r in old.execute('PRAGMA table_info('+table+')'))
  a=old.execute('SELECT '+cols+' FROM '+table+where+' ORDER BY id').fetchall();b=current.execute('SELECT '+cols+' FROM '+table+where+' ORDER BY id').fetchall()
  report['private_tables'][table]={'rows_before':len(a),'rows_after':len(b),'unchanged':a==b}
 for ranking in Ranking.objects.filter(is_archived=False).exclude(origin='personal'):
  orders=(ranking.scope.get('editorial') or {}).get('orders',{})
  if not orders:continue
  ids=set(ranking.entries.filter(is_archived=False).values_list('work_id' if ranking.item_type=='work' else 'person_id',flat=True))
  for lens,order in orders.items():
   values=order.get('item_ids',[])
   if len(values)!=len(set(values)) or set(values)!=ids:report['editorial_orders']['issues'].append({'target':ranking.slug,'lens':lens,'missing':sorted(ids-set(values)),'extra':sorted(set(values)-ids),'duplicates':len(values)-len(set(values))})
  report['editorial_orders']['checked']+=1
 report['integrity']=current.execute('PRAGMA integrity_check').fetchall();report['foreign_key_errors']=current.execute('PRAGMA foreign_key_check').fetchall();report['deletion_guards']=[r[0] for r in current.execute("SELECT name FROM sqlite_master WHERE type='trigger'")]
 report['passed']=all(v['unchanged'] for v in report['private_tables'].values()) and not report['editorial_orders']['issues'] and report['integrity']==[('ok',)] and not report['foreign_key_errors'] and len(report['deletion_guards'])==8
 (ROOT/'research/_runs/2026-09-28/completion/final-integrity-audit.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));assert report['passed']
if __name__=='__main__':main()
