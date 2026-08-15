import sys, json
sys.path.append(r'c:\Users\donth\Downloads\Drak web')
from health import check_tor_proxy, check_llm_health, check_search_engines
from llm_utils import get_model_choices

print('TOR_CHECK:')
print(check_tor_proxy())

print('\nMODEL_CHOICES:')
models = get_model_choices()
print(models)

print('\nLLM_CHECKS:')
for m in models[:5]:
    try:
        r = check_llm_health(m)
    except Exception as e:
        r = {'status':'error','error':str(e),'provider':None}
    print(m, r)

print('\nSEARCH_ENGINES:')
eng = check_search_engines()
print('total', len(eng))
for e in eng[:8]:
    print(e)
