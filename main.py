import base64
from io import StringIO
from pathlib import Path
import requests
import yaml


def get_token(region, api_id, api_secret):
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


def locale(region):
    if region == "us":
        return "en_US"
    elif region == "eu":
        return "en_GB"
    elif region == "kr":
        return "ko_KR"
    elif region == "tw":
        return "zh_TW"
    return ""


def bn_request(region, url, access_token=None, namespace=None):
    if not url.startswith('http'):
        url = f"https://{region}.api.blizzard.com:443" + url

    if access_token is not None:
        url += '&' if url.find('?') >= 0 else '?'
        url += "access_token=" + access_token
    if namespace != None:
        url += '&' if url.find('?') >= 0 else '?'
        url += f"region={region}"
        url += f"&namespace={namespace}-{region}"
        url += f"&locale={locale(region)}"

    try:
        res = requests.get(url, timeout=5)
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

        for i in range(10):
            res = bn_request(region,
                             f'/profile/wow/character/{realm}/{name}/mythic-keystone-profile',
                             access_token=access_token,
                             namespace='profile'
                             )
            print(type(res))
            if res is dict:
                continue

            print(res)

            mkdir(f'data/{realm}')
            mkdir(f'data/{realm}/{name}')
            mkdir(f'data/{realm}/{name}/runs')
            current_period_id = res['current_period']['period']['id']
            current_period = yaml.dump(res['current_period'])
            character = yaml.dump(res['character'])
            current_mythic_rating = yaml.dump(res['current_mythic_rating'])
            write_file(f'data/{realm}/{name}/current_period', current_period)
            write_file(f'data/{realm}/{name}/character', character)
            write_file(
                f'data/{realm}/{name}/current_mythic_rating', current_mythic_rating)

            for run in res['current_period']['best_runs']:
                write_file(
                    f'data/{realm}/{name}/runs/{run["completed_timestamp"]}.yml', yaml.dump(run))
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

            for run in res['leading_groups']:
                run['keystone_affixes'] = [affix['keystone_affix']
                                           for affix in res['keystone_affixes']]
                members = [m for m in run['members'] if m['profile']['realm']
                           ['slug'] == realm and m['profile']['name'] == name]
                if len(members) == 0:
                    continue

                for mem in members:
                    mem['character'] = mem['profile']
                    del mem['profile']
                run['dungeon'] = dungeon
                write_file(
                    f'data/{realm}/{name}/runs/{run["completed_timestamp"]}.yml', yaml.dump(run))


if __name__ == '__main__':
    main()
