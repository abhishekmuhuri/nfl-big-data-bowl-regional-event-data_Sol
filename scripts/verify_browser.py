"""Headless browser QA of our own app and report; no personal browser profile is used."""
from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/qa'
OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True,channel='chrome')
    page=browser.new_page(viewport={'width':1440,'height':1080},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8501',wait_until='networkidle')
    page.get_by_text('Who keeps the options open?',exact=True).wait_for(timeout=120000)
    page.locator('[data-testid="stMetric"]').first.wait_for(timeout=120000)
    page.wait_for_function('document.querySelectorAll("[data-testid=stPlotlyChart] .main-svg").length >= 2')
    page.get_by_text('Player contributions',exact=True).wait_for(timeout=120000)
    page.screenshot(path=str(OUT/'overview.png'),full_page=True)
    assert page.locator('[data-testid="stMetric"]').count()==5
    assert page.locator('[data-testid="stException"]').count()==0
    page.get_by_text('Play explorer',exact=True).click()
    page.get_by_text('Take it to film:',exact=False).wait_for()
    page.wait_for_function('Array.from(document.querySelectorAll(".js-plotly-plot")).some(p => p._transitionData && p._transitionData._frames.length > 0)')
    page.screenshot(path=str(OUT/'play_explorer.png'),full_page=True)
    visible_charts=page.locator('[data-testid="stPlotlyChart"]:visible')
    visible_charts.first.screenshot(path=str(OUT/'receiver_timeline.png'))
    visible_charts.last.screenshot(path=str(OUT/'field_replay.png'))
    page.get_by_text('Data & help',exact=True).click()
    page.get_by_text('Bring in the next game',exact=True).wait_for()
    page.screenshot(path=str(OUT/'data_help.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.get_by_text('Team overview',exact=True).click()
    page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
    page.set_viewport_size({'width':1440,'height':1080})
    page.goto((ROOT/'docs/index.html').as_uri(),wait_until='load')
    page.wait_for_function('document.querySelectorAll(".plotly-graph-div .main-svg").length >= 4')
    page.screenshot(path=str(OUT/'report.png'),full_page=True)
    assert page.get_by_text('The finding',exact=True).count()==1
    assert not errors,errors
    print(json.dumps({'browser_errors':errors,'screenshots':str(OUT),'status':'passed'}))
    browser.close()
