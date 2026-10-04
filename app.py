from flask import Flask, jsonify, request, render_template, session, redirect, url_for
from urllib.parse import urlparse, urljoin
from functools import wraps
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

# app.py はプロジェクト直下に置く。
# 実体（templates / static / data）は bousai_app/ 配下にあるので、そこを参照する。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, 'bousai_app')

app = Flask(
    __name__,
    template_folder=os.path.join(APP_DIR, 'templates'),
    static_folder=os.path.join(APP_DIR, 'static'),
)
app.secret_key = 'your-secret-key-here'

# 管理者認証情報
ADMIN_CREDENTIALS = {
    'admin': '123'
}

# ────────────────────────────────
# 気象警報・注意報設定
PREFECTURE_CODE = "020000"  # 青森県
AREA_NAME = "青森市"

# 気象庁の市区町村コード（青森市）
AREA_CODE = "0220100"

WARNING_URL = (
    f"https://www.jma.go.jp/bosai/warning/data/r8/{PREFECTURE_CODE}.json"
)

DISASTER_TYPES = (
    "地震",
    "津波",
    "洪水",
    "土砂災害",
    "高潮",
    "大規模な火事",
)

JST = timezone(timedelta(hours=9))

# 警報・注意報のコード一覧
WARNING_CODES = {
    "00": "解除",
    "02": "暴風雪警報",
    "03": "レベル3大雨警報",
    "04": "洪水警報",
    "05": "暴風警報",
    "06": "大雪警報",
    "07": "波浪警報",
    "08": "レベル3高潮警報",
    "09": "レベル3土砂災害警報",
    "10": "レベル2大雨注意報",
    "12": "大雪注意報",
    "13": "風雪注意報",
    "14": "雷注意報",
    "15": "強風注意報",
    "16": "波浪注意報",
    "17": "融雪注意報",
    "18": "洪水注意報",
    "19": "レベル2高潮注意報",
    "20": "濃霧注意報",
    "21": "乾燥注意報",
    "22": "なだれ注意報",
    "23": "低温注意報",
    "24": "霜注意報",
    "25": "着氷注意報",
    "26": "着雪注意報",
    "27": "その他の注意報",
    "29": "レベル2土砂災害注意報",
    "32": "暴風雪特別警報",
    "33": "レベル5大雨特別警報",
    "35": "暴風特別警報",
    "36": "大雪特別警報",
    "37": "波浪特別警報",
    "38": "レベル5高潮特別警報",
    "39": "レベル5土砂災害特別警報",
    "43": "レベル4大雨危険警報",
    "48": "レベル4高潮危険警報",
    "49": "レベル4土砂災害危険警報"
}

# ────────────────────────────────
# サンプルデータの読み込み
DATA_FILE = os.path.join(APP_DIR, 'data', 'shelters.json')
INSTRUCTIONS_FILE = os.path.join(APP_DIR, 'data', 'instructions.json')

def load_json(path, default):
    """JSONファイルを読み込む（存在しない・壊れている場合は default を返す）"""
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default

shelters = load_json(DATA_FILE, [])
instructions = load_json(INSTRUCTIONS_FILE, [])

def save_instructions():
    """指示ボードのデータをファイルに保存する"""
    try:
        with open(INSTRUCTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(instructions, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_shelters():
    """避難所データをファイルに保存する"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(shelters, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
# ────────────────────────────────

# ────────────────────────────────
# 認証関連の設定とヘルパー関数
def is_safe_url(target):
    """リダイレクト先URLが安全かどうかチェック"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def login_required(f):
    """認証が必要なページに付けるデコレータ"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            # 現在のURLをnextパラメータとしてログイン画面にリダイレクト
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def get_japan_time():
    """日本時間（JST）の現在時刻を取得する"""
    return datetime.now(JST).strftime("%Y年%m月%d日 %H:%M")


def format_report_time(iso_str):
    """気象庁の発表時刻（ISO形式）をJSTの表示用文字列に変換する"""
    if not iso_str:
        return "不明"
    try:
        parsed = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        if parsed.tzinfo:
            parsed = parsed.astimezone(JST)
        return parsed.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        return iso_str


def filter_shelters(
    district=None,
    disaster_type=None,
    pets_allowed=False,
    barrier_free=False,
    keyword=None,
):
    """指定された地区・災害種別・設備条件に一致する避難所を返す"""
    normalized_keyword = keyword.strip().casefold() if keyword else ''
    return [
        shelter for shelter in shelters
        if (not district or shelter.get('district') == district)
        and (
            not normalized_keyword
            or normalized_keyword in str(shelter.get('name', '')).casefold()
        )
        and (
            not disaster_type
            or (
                isinstance(shelter.get('disaster_types'), list)
                and disaster_type in shelter['disaster_types']
            )
        )
        and (not pets_allowed or shelter.get('pets_allowed') is True)
        and (not barrier_free or shelter.get('barrier_free') is True)
    ]


def get_shelter_districts():
    """登録済み避難所の地区名を重複なく返す"""
    districts = set()
    for shelter in shelters:
        district = shelter.get('district')
        if isinstance(district, str) and district.strip():
            districts.add(district.strip())
    return sorted(districts, key=str.casefold)


def parse_area_warnings(warning_data):
    """気象庁の新形式JSONから対象市区町村の発表・継続中の情報を抽出する"""
    if not isinstance(warning_data, list):
        raise ValueError("気象庁の警報・注意報データが新形式の配列ではありません")

    warnings = []
    seen_codes = set()
    report_datetimes = []

    for report in warning_data:
        if not isinstance(report, dict):
            continue

        report_datetime = report.get("reportDatetime")
        if isinstance(report_datetime, str) and report_datetime:
            report_datetimes.append(report_datetime)

        warning = report.get("warning")
        if not isinstance(warning, dict):
            continue

        class20_items = warning.get("class20Items", [])
        if not isinstance(class20_items, list):
            continue

        area = next(
            (
                item for item in class20_items
                if isinstance(item, dict)
                and item.get("areaCode") == AREA_CODE
            ),
            None
        )
        if not area:
            continue

        kinds = area.get("kinds", [])
        if not isinstance(kinds, list):
            continue

        for kind in kinds:
            if not isinstance(kind, dict):
                continue

            status = kind.get("status", "")
            code = kind.get("code", "")
            if status not in ("発表", "継続") or not code or code in seen_codes:
                continue

            warnings.append({
                "name": WARNING_CODES.get(
                    code,
                    f"不明な警報・注意報 (コード: {code})"
                ),
                "code": code,
                "status": status
            })
            seen_codes.add(code)

    latest_report_datetime = max(report_datetimes, default="")
    return warnings, latest_report_datetime


def get_weather_warnings():
    """対象市区町村の警報・注意報を取得する"""
    try:
        # 青森県の新形式（令和8年～）警報・注意報データを取得
        with urllib.request.urlopen(url=WARNING_URL, timeout=10) as res:
            warning_data = json.loads(res.read())

        warnings, report_datetime = parse_area_warnings(warning_data)

        return {
            "area_name": AREA_NAME,
            "warnings": warnings,
            "report_time": format_report_time(report_datetime),
            "last_fetch_time": get_japan_time()
        }

    except Exception:
        return {
            "area_name": AREA_NAME,
            "warnings": [],
            "report_time": "取得失敗",
            "last_fetch_time": get_japan_time(),
            "error": True
        }


# トップページ：templates/index.html を返す（住民向け指示も表示する）
@app.route('/')
def index():
    resident_notices = [i for i in instructions if i.get('target') == '住民']
    return render_template('index.html', resident_notices=resident_notices)

# ログインページ
@app.route('/login', methods=['GET', 'POST'])
def login():
    # リダイレクト先を取得（デフォルトは避難所登録画面）
    next_url = request.args.get('next') or request.form.get('next')

    # 安全でないURLの場合はデフォルトページにリダイレクト
    if not next_url or not is_safe_url(next_url):
        next_url = url_for('shelter_register')

    if request.method == 'POST':
        password = request.form.get('password', '').strip()

        # 認証チェック
        username = next(
            (name for name, registered_password in ADMIN_CREDENTIALS.items()
             if registered_password == password),
            None
        )
        if username:
            session['logged_in'] = True
            session['username'] = username
            # ログイン成功後は指定されたページにリダイレクト
            return redirect(next_url)
        return render_template('login.html', error=True, message="パスワードが正しくありません。", next=next_url)

    # ログイン済みの場合は指定されたページにリダイレクト
    if session.get('logged_in'):
        return redirect(next_url)

    return render_template('login.html', next=next_url)

# ログアウト
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# 避難所登録ページ
@app.route('/shelter_register', methods=['GET', 'POST'])
@login_required
def shelter_register():
    if request.method == 'POST':
        action = request.form.get('action', 'register')
        disaster_types = [
            disaster_type for disaster_type in request.form.getlist('disaster_types')
            if disaster_type in DISASTER_TYPES
        ]

        if action == 'update':
            try:
                shelter_id = int(request.form.get('shelter_id', ''))
            except ValueError:
                shelter_id = None

            shelter = next(
                (item for item in shelters if item.get('id') == shelter_id),
                None,
            )
            if shelter is None:
                return render_template(
                    'shelter_register.html',
                    shelters=shelters,
                    disaster_types=DISASTER_TYPES,
                    error=True,
                    message='避難所が見つかりません。',
                )

            shelter['disaster_types'] = disaster_types
            if 'district' in request.form:
                district = request.form.get('district', '').strip()
                if district:
                    shelter['district'] = district
                else:
                    shelter.pop('district', None)
            save_shelters()
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                disaster_types=DISASTER_TYPES,
                success=True,
                message=f'「{shelter.get("name", "避難所")}」の対応災害種別を更新しました。',
            )

        if action != 'register':
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                disaster_types=DISASTER_TYPES,
                error=True,
                message='不正な操作です。',
            )

        name = request.form.get('name', '').strip()
        district = request.form.get('district', '').strip()
        if not name:
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                disaster_types=DISASTER_TYPES,
                error=True,
                message='避難所名を入力してください。',
            )

        # 重複防止のため、既存名を確認
        if not any(s.get('name') == name for s in shelters):
            shelters.append({
                'id': (max((s.get('id', 0) for s in shelters), default=0) + 1),
                'name': name,
                'disaster_types': disaster_types,
                **({'district': district} if district else {}),
            })
            save_shelters()
            return render_template(
                'shelter_register.html',
                shelters=shelters,
                disaster_types=DISASTER_TYPES,
                success=True,
                message=f'避難所「{name}」を登録しました。',
            )

        return render_template(
            'shelter_register.html',
            shelters=shelters,
            disaster_types=DISASTER_TYPES,
            error=True,
            message=f'避難所「{name}」はすでに登録されています。',
        )

    return render_template(
        'shelter_register.html',
        shelters=shelters,
        disaster_types=DISASTER_TYPES,
    )

# 避難所検索ページ
@app.route('/shelter_search')
def shelter_search():
    disaster_type = request.args.get('disaster_type', '')
    if disaster_type not in DISASTER_TYPES:
        disaster_type = ''

    districts = get_shelter_districts()
    district = request.args.get('district', '')
    if district not in districts:
        district = ''

    return render_template(
        'shelter_search.html',
        disaster_types=DISASTER_TYPES,
        districts=districts,
        selected_district=district,
        keyword=request.args.get('keyword', '').strip(),
        selected_disaster_type=disaster_type,
        pets_allowed=request.args.get('pets_allowed') == 'true',
        barrier_free=request.args.get('barrier_free') == 'true',
    )

# 全施設一覧ページ
@app.route('/all_shelters')
def all_shelters():
    return render_template('search_results.html', results=shelters)


# 指示ボード：住民向けの指示を一覧で確認する
@app.route('/board')
@login_required
def board():
    resident_instructions = [i for i in instructions if i.get('target') == '住民']
    return render_template('board.html', instructions=resident_instructions)

# 検索結果ページ：templates/search_results.html を返す
@app.route('/search_results')
def search_results():
    district = request.args.get('district') or None
    keyword = request.args.get('keyword', '').strip()
    disaster_type = request.args.get('disaster_type')
    valid_districts = get_shelter_districts()
    invalid_district = district is not None and district not in valid_districts
    invalid_disaster_type = (
        disaster_type is not None
        and disaster_type not in DISASTER_TYPES
    )
    pets_allowed = request.args.get('pets_allowed') == 'true'
    barrier_free = request.args.get('barrier_free') == 'true'
    invalid_equipment_filter = any(
        value not in (None, 'true')
        for value in (
            request.args.get('pets_allowed'),
            request.args.get('barrier_free'),
        )
    )
    results = (
        []
        if invalid_district or invalid_disaster_type or invalid_equipment_filter
        else filter_shelters(
            district,
            disaster_type,
            pets_allowed,
            barrier_free,
            keyword,
        )
    )
    return render_template(
        'search_results.html',
        results=results,
        district=district if not invalid_district else None,
        keyword=keyword,
        disaster_type=disaster_type if not invalid_disaster_type else None,
        invalid_district=invalid_district,
        invalid_disaster_type=invalid_disaster_type,
        pets_allowed=pets_allowed,
        barrier_free=barrier_free,
        invalid_equipment_filter=invalid_equipment_filter,
    )

# JSON API：地区・災害種別・設備条件・避難所名キーワードで絞り込む
@app.route('/shelters', methods=['GET'])
def get_shelters():
    disaster_type = request.args.get('disaster_type')
    if disaster_type is not None and disaster_type not in DISASTER_TYPES:
        return jsonify({'error': 'Invalid disaster type'}), 400

    district = request.args.get('district') or None
    if district is not None and district not in get_shelter_districts():
        return jsonify({'error': 'Invalid district'}), 400

    equipment_filters = {}
    for parameter in ('pets_allowed', 'barrier_free'):
        value = request.args.get(parameter)
        if value not in (None, 'true'):
            return jsonify({'error': f'Invalid {parameter} filter'}), 400
        equipment_filters[parameter] = value == 'true'

    results = filter_shelters(
        district,
        disaster_type,
        **equipment_filters,
        keyword=request.args.get('keyword'),
    )

    if not results:
        # 見つからなければエラー JSON を返す
        return jsonify({'error': 'No shelters found'}), 404

    # 見つかったらリストを JSON で返す
    return jsonify(results)

# 気象警報・注意報API
@app.route('/api/weather_warnings')
def api_weather_warnings():
    """気象警報・注意報をJSON形式で返すAPI"""
    return jsonify(get_weather_warnings())

if __name__ == '__main__':
    app.run(debug=True, port=5000)
