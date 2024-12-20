import base64
from io import StringIO
from pathlib import Path
import requests
import urllib.request
import yaml
from ratelimit import limits, sleep_and_retry


def get_token(region, api_id, api_secret) -> str:
    url = f"https://{region}.battle.net/oauth/token"
    auth = base64.b64encode(
        (api_id + ':' + api_secret).encode()).decode('utf-8')

    headers = {
        'Authorization': 'Basic ' + auth,
        'Content-Type': "application/x-www-form-urlencoded"
    }

    res = requests.post(url, headers=headers, data={
                        'grant_type': 'client_credentials'})
    if res.status_code == 200:
        res_obj = res.json()
        if 'access_token' in res_obj:
            return res_obj['access_token']
    return None


def locale(region) -> str:
    if region == "us":
        return "en_US"
    elif region == "eu":
        return "en_GB"
    elif region == "kr":
        return "ko_KR"
    elif region == "tw":
        return "zh_TW"
    return ""


@sleep_and_retry
@limits(calls=600, period=1)
def bn_request(region, url, access_token=None, namespace=None):
    if not url.startswith('http'):
        url = f"https://{region}.api.blizzard.com:443" + url

    if namespace != None:
        url += '&' if url.find('?') >= 0 else '?'
        url += f"region={region}"
        url += f"&namespace={namespace}-{region}"
        url += f"&locale={locale(region)}"

    headers = {
        'Authorization': 'Bearer ' + access_token
    }

    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json()
        elif res.status_code == 401:
            return 401
        else:
            return None
    except requests.exceptions.Timeout as e:
        return e


def mkdir(path) -> None:
    Path(path).mkdir(exist_ok=True)


def exists(path) -> bool:
    return Path(path).exists()


def write_file(path, text) -> None:
    Path(path).write_text(text, 'utf-8')


def read_file(path) -> str:
    return Path(path).read_text('utf-8')


def get_item_media_url(item : int, access_token : str, region : str) -> str:
    res = bn_request(region,
                    f'/data/wow/media/item/{item}',
                    access_token=access_token,
                    namespace='static'
                    )
    return res['assets'][0]['value']

def save_player_equipment(realm : str, name : str, access_token : str, region : str) -> None:
    res = bn_request(region,
                    f'/profile/wow/character/{realm}/{name}/equipment',
                    access_token=access_token,
                    namespace='profile'
                    )
    
    if 'equipped_items' not in res:
        return

    # 내구도 정보 삭제
    for item in res['equipped_items']:
        if 'durability' in item:
            del item['durability']

    write_file(f'data/{realm}/{name}/equipped_items.yml', yaml.dump(res['equipped_items']))

    for item in res['equipped_items']:
        item_id = item['item']['id']
        if exists(f'data/item/{item_id}.jpg'):
            continue

        url = get_item_media_url(item_id, access_token, region)
        mkdir(f'data/item')
        urllib.request.urlretrieve(url, f'data/item/{item_id}.jpg')

def main():
    config = {}
    with open('config.yml') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
        print(config)

    region = config['region']
    api_id = config['client_id']
    api_secret = config['client_secret']
    access_token = get_token(region, api_id, api_secret)
    print(access_token)

    requested_set = {}

    for character in config['characters']:
        realm = character['realm']
        name = character['name']

        current_period_id = 0

        for _ in range(10):
            res = bn_request(region,
                             f'/profile/wow/character/{realm}/{name}/mythic-keystone-profile',
                             access_token=access_token,
                             namespace='profile'
                             )
            # print(type(res))
            if type(res) is not dict:
                continue
            # print(res)

            mkdir(f'data/{realm}')
            mkdir(f'data/{realm}/{name}')
            mkdir(f'data/{realm}/{name}/runs')
            mkdir(f'data/{realm}/{name}/seasons')

            save_player_equipment(realm, name, access_token, region)

            current_period_id = res['current_period']['period']['id']
            character = yaml.dump(res['character'])
            write_file(
                f'data/{realm}/{name}/character.yml', character)
            if 'current_mythic_rating' in res:
                current_mythic_rating = yaml.dump(res['current_mythic_rating'])
                write_file(
                    f'data/{realm}/{name}/current_mythic_rating.yml', current_mythic_rating)

            def save_run(run):
                if 'ranking' in run:
                    del run['ranking']

                write_file(
                    f'data/{realm}/{name}/runs/{run["completed_timestamp"]}.yml', yaml.dump(run))

            def save_runs(obj):
                if 'best_runs' in obj:
                    for run in season_res['best_runs']:
                        save_run(run)

            seasons = res['seasons']
            for season in seasons:
                href = season['key']['href']
                season_res = bn_request(
                    region, href, access_token=access_token)

                if 'best_runs' in season_res:
                    season_res['best_runs'] = sorted(
                        season_res['best_runs'], key=lambda r: r['completed_timestamp'])
                    for run in season_res['best_runs']:
                        run['members'] = sorted(run['members'], key=lambda m: (
                            m['character']['realm']['id'], m['character']['id']))

                if season_res['mythic_rating']['rating'] > 0:
                    write_file(
                        f'data/{realm}/{name}/seasons/{season["id"]}.yml', yaml.dump(season_res))

                save_runs(season_res)

            save_runs(res['current_period'])
            break

        if not exists(f'data/{realm}/connected_realm_id'):
            res = bn_request(region,
                             f'/data/wow/realm/{realm}',
                             access_token=access_token,
                             namespace='dynamic'
                             )
            href = res['connected_realm']['href']
            res_cr = bn_request(region, href, access_token=access_token)
            write_file(f'data/{realm}/connected_realm_id', str(res_cr['id']))

        connected_realm_id = read_file(f'data/{realm}/connected_realm_id')

        dungeons = bn_request(region,
                              f'/data/wow/connected-realm/{connected_realm_id}/mythic-leaderboard/index',
                              access_token=access_token,
                              namespace='dynamic')

        mkdir(f'data/leaderboard')
        mkdir(f'data/leaderboard/{connected_realm_id}')
        mkdir(f'data/leaderboard/{connected_realm_id}/{current_period_id}')

        # write_file('data/dungeons', yaml.dump(dungeons))

        for dungeon in dungeons['current_leaderboards']:
            dungeon_id = dungeon['id']
            mkdir(
                f'data/leaderboard/{connected_realm_id}/{current_period_id}/{dungeon_id}')

            request_key = f'{connected_realm_id}/{current_period_id}/{dungeon_id}'
            if request_key in requested_set:
                continue

            res = bn_request(region,
                             f'/data/wow/connected-realm/{connected_realm_id}/mythic-leaderboard/{dungeon_id}/period/{current_period_id}',
                             access_token=access_token,
                             namespace='dynamic')

            write_file(
                f'data/leaderboard/{connected_realm_id}/{current_period_id}/{dungeon_id}/data.yml', yaml.dump(res))

            requested_set[request_key] = True

            if res is None or 'leading_groups' not in res:
                continue

            for run in res['leading_groups']:
                run['keystone_affixes'] = [affix['keystone_affix']
                                           for affix in res['keystone_affixes']]
                members = [m for m in run['members'] if m['profile']['realm']
                           ['slug'] == realm and m['profile']['name'] == name]
                if len(members) == 0:
                    continue

                for mem in run['members']:
                    mem['character'] = mem['profile']
                    del mem['profile']

                run['members'] = sorted(run['members'], key=lambda m: (
                    m['character']['realm']['id'], m['character']['id']))

                run['dungeon'] = dungeon
                save_run(run)

if __name__ == '__main__':
    main()
