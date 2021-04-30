from lcu_driver import Connector
import requests
from bs4 import BeautifulSoup
import re, json
from selenium import webdriver
import chromedriver_autoinstaller
from win10toast_click import ToastNotifier 
import logging
from PIL import Image


logging.basicConfig(
  format = '%(asctime)s %(message)s',
  datefmt = '[%p %I:%M:%S]',
  level = logging.INFO
)

CURRENT_SUMMONER = '/lol-summoner/v1/current-summoner'
CURRNET_RUNE_PAGE = '/lol-perks/v1/currentpage'
RUNE_PAGE = '/lol-perks/v1/pages'
CURRENT_CHAMPION = '/lol-champ-select/v1/current-champion'
CURRENT_STATE = '/lol-gameflow/v1/gameflow-phase'
MATCH_READY = '/lol-matchmaking/v1/ready-check/accept'
SUMMONER_DATA = '/lol-summoner/v1/summoners/'
BANPICK_PHASE_DATA = '/lol-champ-select/v1/session'

lol_current_version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json")
DDRAGON_CHAMPION = requests.get('http://ddragon.leagueoflegends.com/cdn/' + json.loads(lol_current_version.text)[0] + '/data/ko_KR/champion.json').json()
CHAMPION_KEY_DICT = {}

for champ in DDRAGON_CHAMPION['data']:
    CHAMPION_KEY_DICT[DDRAGON_CHAMPION['data'][champ]['key']] = champ

# print(CHAMPION_KEY_DICT)

connector = Connector()

def parsingRune(parsedStr):
    m = re.search('[0-9][0-9][0-9][0-9][.]png', parsedStr)

    return m.group().split('.')[0]


def open_image():
    try:
        image = Image.open("image/out.png")
        image.show()
    except:
        pass


async def fowMultiSearch(connection):
    summonerList = ""
    matching = await connection.request('get', BANPICK_PHASE_DATA)
    matchingData = await matching.json()
    teamCount = len(matchingData["myTeam"])
    for i in range(teamCount):
        summonerId = matchingData["myTeam"][i]["summonerId"]
        if summonerId != 0:
            summoners = await connection.request('get', SUMMONER_DATA + str(summonerId))
            summonerData = await summoners.json()
            summonerName = summonerData["displayName"]
            summonerList = summonerList + summonerName + ","
    # print(summonerList[:-1])

    path = chromedriver_autoinstaller.install(True)
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    options.add_argument('window-size=1920x1080')
    options.add_argument("disable-gpu")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    fowUrl = "http://fow.kr/multi#" + summonerList[:-1].replace(" ", "")
    # print(fowUrl)

    driver = webdriver.Chrome(path, options=options)
        
    driver.get(fowUrl)
    driver.implicitly_wait(time_to_wait=10)
    result = driver.find_element_by_id('multi_result')
    action = webdriver.ActionChains(driver)
    action.move_to_element(result).perform()
    result_png = result.screenshot_as_png
    with open("image/out.png", "wb") as file:
        file.write(result_png)

    driver.close()
    driver.quit()
    logging.info("멀티서치 완료.")
    toast = ToastNotifier()
    toast.show_toast("멀티서치 완료","확인하려면 클릭하세요!", duration=10, threaded=True, icon_path="image/icon.ico", callback_on_click=open_image)


def opggParsing(currentChamp):
    runeNum = []
    opggUrl = "https://www.op.gg/champion/" + currentChamp + "/statistics"
    response = requests.get(opggUrl)
    if response.status_code == 200:
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')
        parsedStyle = soup.findAll("div", {"class": "perk-page__item perk-page__item--mark"})
        count = 0
        for r in parsedStyle:
            runeNum.append(parsingRune(r.find("img")['src']))
            count += 1
            if count == 2: break

        parsedRune = soup.find("div", "perk-page__item perk-page__item--keystone perk-page__item--active").find("img")
        # print(parsedRune['src'])
        runeNum.append(parsingRune(parsedRune['src']))

        parsedRune = soup.findAll("div", attrs={"class": "perk-page__item perk-page__item--active"})
        count = 0
        for r in parsedRune:
            runeNum.append(parsingRune(r.find("img")['src']))
            count += 1
            if count == 5: break

        parsedRune = soup.findAll("img", attrs={"class": "active tip"})
        count = 0
        for r in parsedRune:
            runeNum.append(parsingRune(r['src']))
            count += 1
            if count == 3: break
            
        # print(runeNum)
        return runeNum

# fired when LCU API is ready to be used
@connector.ready
async def connect(connection):
    logging.info('LCU API is ready to be used.')
    summoner = await connection.request('get', CURRENT_SUMMONER)
    if summoner.status == 200:
        summonerData = await summoner.json()
        logging.info(f"환영합니다. [{summonerData['displayName']}] 소환사님.")


async def runeSetting(connection, currentChamp):
    rune = await connection.request('get', CURRNET_RUNE_PAGE)
    currentRuneData = await rune.json()
    currentPageId = currentRuneData['id']
    currentPageName = currentRuneData['name']
    isDeletable = currentRuneData['isDeletable']
    
    # 기본 룬페이지가 아닌 것 삭제
    if isDeletable:
        logging.info(f"Deleted rune page {currentPageName}, {currentPageId}")
        await connection.request('delete', RUNE_PAGE + '/' + str(currentPageId))

    PerkIds = opggParsing(currentChamp)
    newRune = {"primaryStyleId": PerkIds[0], "subStyleId": PerkIds[1], "selectedPerkIds": PerkIds[2:11], "name": currentChamp}
    logging.info(f"Added new rune page {currentChamp}")
    await connection.request('post', RUNE_PAGE, data=newRune)


# fired when League Client is closed (or disconnected from websocket)
@connector.close
async def disconnect(_):
    logging.info('클라이언트가 종료되었습니다.')
    await connector.stop()


# subscribe to '/lol-summoner/v1/current-summoner' endpoint for the UPDATE event
# when an update to the user happen (e.g. name change, profile icon change, level, ...) the function will be called
@connector.ws.register(CURRENT_SUMMONER, event_types=('UPDATE',))
async def summoner_changed(connection, event):
    logging.info(f'Summoner [{event.data["displayName"]}] detected.')


@connector.ws.register(CURRENT_STATE, event_types=('UPDATE',))
async def state_changed(connection, event):
    logging.info(f'Now state updated to {event.data}')

    if event.data == 'ReadyCheck':
        await connection.request('post', MATCH_READY)
        logging.info("매칭 수락 완료.")

    if event.data == 'ChampSelect':
        await fowMultiSearch(connection)
        

@connector.ws.register(CURRENT_CHAMPION, event_types=('UPDATE','CREATE','DELETE',))
async def champion_changed(connection, event):
    if int(event.data) > 0:
        currentChamp = CHAMPION_KEY_DICT[str(event.data)]
        logging.info(f'Current champion updated to {currentChamp} ({str(event.data)})')
        await runeSetting(connection, currentChamp)

'''
@connector.ws.register('/lol-champ-select/v1/session', event_types=('UPDATE',))
async def ch_changed(connection, event):
    print(event.data)
    print()
'''

print("LoL Tools v0.1")
print("Github: https://github.com/romanceformoon/LoL_Tool")
print()
connector.start()
