"""Exercise real dashboard controls with Streamlit's supported AppTest runner."""
from pathlib import Path
import sys
from streamlit.testing.v1 import AppTest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
app=AppTest.from_file(str(ROOT/'app.py')).run(timeout=180)
assert not app.exception, str(app.exception)
assert not app.error, str(app.error)
assert len(app.metric)==5
print('Initial dashboard:',[(m.label,m.value) for m in app.metric])
controls={x.label:x for x in app.slider}
controls['Separation threshold (yards)'].set_value(3.0)
app.run(timeout=120)
assert not app.exception, str(app.exception)
assert len(app.metric)==5
print('Changed separation threshold:',app.metric[0].value)
teams={x.label:x for x in app.selectbox}
teams['Offensive team'].select('TB')
app.run(timeout=120)
assert not app.exception, str(app.exception)
print('Changed team: TB')
weeks=next(x for x in app.multiselect if x.label=='Weeks')
weeks.set_value([])
app.run(timeout=120)
assert not app.exception, str(app.exception)
assert any('No analyzable plays' in i.value for i in app.info)
print('Empty filters handled. App checks passed.')
