"""Import four owner-approved established published rankings.

The command is read-only unless ``--apply`` is supplied.  It preserves source
positions (including publisher-defined series/composite entries), resolves
against the existing catalogue before creating anything, and publishes through
the revision-aware external-list importer.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.settings")

import django

django.setup()

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from backend.core.models import Person, Ranking, ResearchSource, Work
from research.import_community_published_rankings import proposed_form, split_authors
from research.import_historical_published_rankings import resolve_work as resolve_latin_work

CHECKED_ON = "2026-09-14"
RUN = ROOT / "research" / "_runs" / CHECKED_ON / "recommended-published-rankings"


DEFINITIONS = {
    "asia-weekly-chinese-fiction-100-1999": {
        "title": "Asia Weekly · 20th-Century 100 Best Chinese Fictions (1999)",
        "publisher": "Asia Weekly (Yazhou Zhoukan)",
        "url": "https://www.mybook285.com/xdwx/20bq.htm",
        "mirror": "https://thegreatestbooks.org/v/table/lists/424",
        "family": "media_expert_poll",
        "method": "All 100 positions in the June 1999 result selected by a 14-member transregional jury from a shortlist of more than 500 Chinese-language works.",
        "limitation": "The original Asia Weekly page is no longer directly available. The exact Chinese ordering comes from a contemporaneous-style transcription and was cross-checked against a separate English-language transcription. The source defines fiction broadly and includes story collections and multi-volume works.",
        "expected": 100,
        "unresolved": 0,
    },
    "booklive-best-100-novels-2018": {
        "title": "BookLive · Readers’ Best 100 Novels (2018)",
        "publisher": "BookLive",
        "url": "https://booklive.jp/feature/index/id/novel100",
        "mirror": "https://www.booklive.co.jp/topics/18490",
        "archive": "https://web.archive.org/web/20200102121444/https://booklive.jp/feature/index/id/novel100",
        "family": "public_poll",
        "method": "Published reader-poll positions from BookLive's 1,835-member survey, conducted 26 April–6 May 2018; series-level entries are retained as published.",
        "limitation": "BookLive suppresses position 92 for signed-out visitors under its content controls, including in all located archived captures. The other 99 positions are verified; position 92 remains explicitly unresolved and is not guessed or renumbered.",
        "expected": 99,
        "unresolved": 1,
    },
    "modern-library-board-100-nonfiction-1999": {
        "title": "Modern Library · Board's 100 Best Nonfiction (1999)",
        "publisher": "Modern Library",
        "url": "https://sites.prh.com/modern-library-top-100",
        "family": "publisher_list",
        "method": "All 100 nonfiction works in the Modern Library board's published order.",
        "limitation": "A publisher-appointed board's twentieth-century English-language canon; source order is not Marginalia's assessment.",
        "expected": 100,
        "unresolved": 0,
    },
    "pbs-great-american-read-2018": {
        "title": "PBS · The Great American Read (2018)",
        "publisher": "PBS",
        "url": "https://www.pbs.org/the-great-american-read/results/",
        "mirror": "https://www.pbs.org/the-great-american-read/books/",
        "family": "public_poll",
        "method": "All 100 final positions from PBS's 2018 nationwide public vote, with author identities cross-checked against PBS's official book metadata feed.",
        "limitation": "US public-popularity poll selected from PBS's programme shortlist. The source deliberately treats several series as single entries.",
        "expected": 100,
        "unresolved": 0,
    },
}


# English display aliases are keyed by the exact Chinese source title.  The
# Chinese source title and credit remain in each reviewed row for provenance.
ASIA_ENGLISH = {
    "呐喊": "Call to Arms", "边城": "Border Town", "骆驼祥子": "Rickshaw Boy",
    "传奇": "Love in a Fallen City", "围城": "Fortress Besieged", "子夜": "Midnight",
    "台北人": "Taipei People", "家": "Family", "呼兰河传": "Tales of Hulan River",
    "老残游记": "The Travels of Lao Can", "寒夜": "Cold Nights", "彷徨": "Wandering",
    "官场现形记": "Officialdom Unmasked", "财主底儿女们": "Children of the Rich",
    "将军族": "A Race of Generals", "沉沦": "Drowning", "死水微澜": "Ripples Across Stagnant Water",
    "红高粱": "Red Sorghum", "小二黑结婚": "The Marriage of Young Blacky", "棋王": "The Chess Master",
    "家变": "Family Catastrophe", "马桥词典": "A Dictionary of Maqiao", "亚细亚的孤儿": "Orphan of Asia",
    "半生缘": "Half a Lifelong Romance", "四世同堂": "Four Generations Under One Roof",
    "胡雪岩": "Hu Xueyan", "啼笑因缘": "Fate in Tears and Laughter", "儿子的大玩偶": "The Sandwich Man",
    "射雕英雄传": "The Legend of the Condor Heroes", "莎菲女士的日记": "Miss Sophie's Diary",
    "鹿鼎记": "The Deer and the Cauldron", "孽海花": "A Flower in a Sinful Sea", "惹事": "Making Trouble",
    "嫁妆一牛车": "An Oxcart for Dowry", "异域": "The Alien Realm", "曾国藩": "Zeng Guofan",
    "原乡人": "My Native Land", "白鹿原": "White Deer Plain", "长恨歌": "The Song of Everlasting Sorrow",
    "吉陵春秋": "The Jiling Chronicles", "黄祸": "Yellow Peril", "狂风沙": "Sandstorm",
    "艳阳天": "The Bright Sunny Day", "公墓": "Cemetery", "旧址": "The Old Site",
    "星星·月亮·太阳": "Stars, Moon, Sun", "台湾人三部曲": "Taiwanese Trilogy", "洗澡": "Baptism",
    "旋风": "The Whirlwind", "荷花淀": "Lotus Creek", "我城": "My City",
    "受戒": "The Love Story of a Young Monk", "铁浆": "Iron Slurry", "世纪末的华丽": "Fin de Siècle Splendor",
    "蜀山剑侠传": "Legend of the Swordsmen of the Mountains of Shu", "又见棕榈，又见棕榈": "Again the Palm Trees",
    "浮躁": "Turbulence", "组织部新来的年轻人": "The Young Newcomer in the Organizational Department",
    "玉梨魂": "The Soul of Jade Pear", "香港三部曲": "Hong Kong Trilogy", "京华烟云": "Moment in Peking",
    "倪焕之": "Ni Huanzhi", "春桃": "Spring Peach", "桑青与桃红": "Mulberry and Peach",
    "蓝与黑": "The Blue and the Black", "二月": "February", "风萧萧": "The Wind Whistles",
    "芙蓉镇": "A Small Town Called Hibiscus", "地之子": "Son of the Earth", "城南旧事": "Memories of Peking",
    "古船": "The Ancient Ship", "酒徒": "The Drunkard", "未央歌": "Song Never to End",
    "沉重的翅膀": "Heavy Wings", "果园城记": "Records of Orchard City", "人啊，人！": "Stones in the Wall",
    "黄金时代": "Golden Age", "狗日的粮食": "Dogshit Food", "赖索": "Lai Suo",
    "妻妾成群": "Raise the Red Lantern", "霸王别姬": "Farewell to My Concubine", "杀夫": "The Butcher's Wife",
    "楚留香": "Chu Liuxiang", "窗外": "Outside the Window", "沉默之岛": "Silent Island",
    "白发魔女传": "The Bride with White Hair", "古都": "The Old Capital", "尹县长": "The Execution of Mayor Yin",
    "四喜忧国": "Lucky Worries About His Country", "喜宝": "The Story of Hay Bo",
    "男人的一半是女人": "Half of Man Is Woman", "将军底头": "The General's Head", "蓝血人": "Blue Blood Being",
    "二十年目睹之怪现状": "Bizarre Happenings Eyewitnessed over Two Decades", "活着": "To Live",
    "冈底斯的诱惑": "The Lure of the Gangdise Mountains", "十年十意": "Ten Years and Ten Cases of Hysteria",
    "北极风情画": "North Pole Landscape Painting", "雍正皇帝": "Yongzheng Emperor",
}

ASIA_AUTHORS = {
    "鲁迅": "Lu Xun", "沈从文": "Shen Congwen", "老舍": "Lao She", "张爱玲": "Eileen Chang",
    "钱锺书": "Qian Zhongshu", "茅盾": "Mao Dun", "白先勇": "Pai Hsien-yung", "巴金": "Ba Jin",
    "萧红": "Xiao Hong", "刘鹗": "Liu E", "李伯元": "Li Baojia", "路翎": "Lu Ling",
    "陈映真": "Chen Yingzhen", "郁达夫": "Yu Dafu", "李劼人": "Li Jieren", "莫言": "Mo Yan",
    "赵树理": "Zhao Shuli", "阿城": "Ah Cheng", "王文兴": "Wang Wen-hsing", "韩少功": "Han Shaogong",
    "吴浊流": "Wu Zhuoliu", "高阳": "Gao Yang", "张恨水": "Zhang Henshui", "黄春明": "Huang Chun-ming",
    "金庸": "Jin Yong", "丁玲": "Ding Ling", "曾朴": "Zeng Pu", "赖和": "Lai Ho",
    "王祯和": "Wang Zhenhe", "柏杨": "Bo Yang", "唐浩明": "Tang Haoming", "锺理和": "Chung Li-ho",
    "陈忠实": "Chen Zhongshi", "王安忆": "Wang Anyi", "李永平": "Li Yongping", "王力雄": "Wang Lixiong",
    "司马中原": "Sima Zhongyuan", "浩然": "Hao Ran", "穆时英": "Mu Shiying", "李锐": "Li Rui",
    "徐速": "Xu Su", "锺肇政": "Chung Chao-cheng", "杨绛": "Yang Jiang", "姜贵": "Chiang Kuei",
    "孙犁": "Sun Li", "西西": "Xi Xi", "汪曾祺": "Wang Zengqi", "朱西宁": "Chu Hsi-ning",
    "朱天文": "Chu Tien-wen", "还珠楼主": "Huanzhulouzhu", "於梨华": "Yu Lihua", "贾平凹": "Jia Pingwa",
    "王蒙": "Wang Meng", "徐枕亚": "Xu Zhenya", "施叔青": "Shi Shuqing", "林语堂": "Lin Yutang",
    "叶圣陶": "Ye Shengtao", "许地山": "Xu Dishan", "聂华苓": "Hualing Nieh", "王蓝": "Wang Lan",
    "柔石": "Rou Shi", "徐吁": "Xu Xu", "古华": "Gu Hua", "台静农": "Tai Jingnong",
    "林海音": "Lin Hai-yin", "张炜": "Zhang Wei", "刘以鬯": "Liu Yichang", "鹿桥": "Luqiao",
    "张洁": "Zhang Jie", "师陀": "Shi Tuo", "戴厚英": "Dai Houying", "王小波": "Wang Xiaobo",
    "刘恒": "Liu Heng", "张系国": "Chang Hsi-kuo", "黄凡": "Huang Fan", "苏童": "Su Tong",
    "李碧华": "Lilian Lee", "李昂": "Li Ang", "古龙": "Gu Long", "琼瑶": "Chiung Yao",
    "苏伟贞": "Su Wei-chen", "梁羽生": "Liang Yusheng", "朱天心": "Chu Tien-hsin", "陈若曦": "Chen Ruoxi",
    "张大春": "Chang Ta-chun", "亦舒": "Yi Shu", "张贤亮": "Zhang Xianliang", "施蛰存": "Shi Zhecun",
    "倪匡": "Ni Kuang", "吴趼人": "Wu Jianren", "余华": "Yu Hua", "马原": "Ma Yuan",
    "林斤澜": "Lin Jinlan", "无名氏": "Anonymous", "二月河": "Eryue He",
}

BOOKLIVE_AUTHORS = {
    "モンゴメリ": "L. M. Montgomery", "田中芳樹": "Yoshiki Tanaka", "司馬遼太郎": "Ryotaro Shiba",
    "有川浩": "Hiro Arikawa", "池波正太郎": "Shotaro Ikenami", "池井戸潤": "Jun Ikeido",
    "上橋菜穂子": "Nahoko Uehashi", "山崎豊子": "Toyoko Yamasaki", "横溝正史": "Seishi Yokomizo",
    "西尾維新": "Nisio Isin", "住野よる": "Yoru Sumino", "北方謙三": "Kenzo Kitakata",
    "香月美夜": "Miya Kazuki", "夢枕獏": "Baku Yumemakura", "新海誠": "Makoto Shinkai",
    "三浦しをん": "Shion Miura", "横山秀夫": "Hideo Yokoyama", "貴志祐介": "Yusuke Kishi",
    "和田竜": "Ryo Wada", "塩野七生": "Nanami Shiono", "カルロ・ゼン": "Carlo Zen",
    "馬場翁": "Okina Baba", "石田衣良": "Ira Ishida", "米澤穂信": "Honobu Yonezawa",
    "東川篤哉": "Tokuya Higashigawa", "恩田陸": "Riku Onda", "松岡圭祐": "Keisuke Matsuoka",
    "冲方丁": "Tow Ubukata", "川村元気": "Genki Kawamura", "神永学": "Manabu Kaminaga",
    "山岡荘八": "Sohachi Yamaoka", "カズオ・イシグロ": "Kazuo Ishiguro", "浅葉なつ": "Natsu Asaba",
    "誉田哲也": "Tetsuya Honda", "今野敏": "Bin Konno", "荻原規子": "Noriko Ogiwara",
    "三上延": "En Mikami", "伊坂幸太郎": "Kotaro Isaka", "ダレン・シャン": "Darren Shan",
    "綾辻行人": "Yukito Ayatsuji", "乾くるみ": "Kurumi Inui", "秋川滝美": "Takimi Akikawa",
    "堂場瞬一": "Shunichi Doba", "菊地秀行": "Hideyuki Kikuchi", "香月日輪": "Hinowa Kozuki",
    "平岩弓枝": "Yumie Hiraiwa", "友麻碧": "Midori Yuma", "栗本薫": "Kaoru Kurimoto",
    "又吉直樹": "Naoki Matayoshi", "渡辺和子": "Kazuko Watanabe", "千月さかき": "Sakaki Sengetsu",
    "宮下奈都": "Natsu Miyashita", "太田紫織": "Shiori Ota", "森博嗣": "Hiroshi Mori",
    "大沢在昌": "Arimasa Osawa", "澪亜": "Reia", "古流望": "Nozomu Koryu", "雪村花菜": "Kana Yukimura",
    "真山仁": "Jin Mayama", "逢坂剛": "Go Osaka", "佐藤大輔": "Daisuke Sato", "辻村深月": "Mizuki Tsujimura",
    "桜庭一樹": "Kazuki Sakuraba", "青柳碧人": "Aito Aoyagi", "ピエール・ルメートル": "Pierre Lemaitre",
    "スティーグラーソン": "Stieg Larsson", "風野真知雄": "Machio Kazeno", "京極夏彦": "Natsuhiko Kyogoku",
    "小路幸也": "Yukiya Shoji", "鷹見一幸": "Kazuyuki Takami", "浅田次郎": "Jiro Asada",
    "コナン・ドイル": "Arthur Conan Doyle", "ジェイムズ・P・ホーガン": "James P. Hogan",
    "百田尚樹": "Naoki Hyakuta", "東野圭吾": "Keigo Higashino",
    "愛七ひろ": "Hiro Ainana",
}

BOOKLIVE_TITLE_ALIASES = {
    "赤毛のアン・シリーズ": "Anne of Green Gables series", "銀河英雄伝説": "Legend of the Galactic Heroes",
    "図書館戦争シリーズ": "Library War series", "アルスラーン戦記": "The Heroic Legend of Arslan novels",
    "シリーズ": "Monogatari series", "本好きの下剋上": "Ascendance of a Bookworm",
    "君の膵臓をたべたい": "I Want to Eat Your Pancreas", "小説 君の名は。": "Your Name",
    "新世界より": "From the New World", "わたしを離さないで": "Never Let Me Go",
    "コンビニ人間": "Convenience Store Woman", "ダレン・シャン": "The Saga of Darren Shan",
    "火花": "Spark", "かがみの孤城": "Lonely Castle in the Mirror", "その女アレックス": "Alex",
    "ミレニアムシリーズ": "Millennium series", "容疑者xの献身": "The Devotion of Suspect X",
    "シャーロック・ホームズシリーズ": "Sherlock Holmes series",
}


def unorm(value: str) -> str:
    """Unicode-aware identity key; unlike the legacy helper, retain CJK."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return "".join(char for char in value if char.isalnum())


def reviewed_path(slug: str) -> Path:
    return ROOT / "research" / slug / f"source-list-reviewed-{CHECKED_ON.replace('-', '')}.json"


def parse_asia() -> list[dict]:
    raw = Path("/private/tmp/asiaweekly-chinese100.html").read_bytes().decode("gb18030", "replace")
    rows = []
    seen_titles = defaultdict(int)
    for match in re.finditer(r"(\d+)\.《([^》]+)》([^<\r\n]+)</td>", raw):
        rank, source_title, source_author = int(match.group(1)), match.group(2).strip(), match.group(3).strip()
        seen_titles[source_title] += 1
        title = ASIA_ENGLISH[source_title]
        # Asia Weekly contains two unrelated works titled Chess Master.
        if source_title == "棋王" and seen_titles[source_title] == 2:
            title = "Chess King"
        rows.append({"source_rank": rank, "title": title, "author": ASIA_AUTHORS[source_author],
                     "source_title": source_title, "source_credits": source_author})
    return rows


def parse_booklive() -> list[dict]:
    raw = Path("/private/tmp/booklive-novel100-wayback-20200102.html").read_text(errors="replace")
    marks = list(re.finditer(r"<a\s+name=[\"']rank_no_(\d+)[\"']", raw, re.I))
    rows = []
    missing_authors = {46: "上橋菜穂子", 82: "百田尚樹", 93: "東野圭吾"}
    reviewed_primary_authors = {89: "スティーグラーソン"}
    for index, match in enumerate(marks):
        rank = int(match.group(1))
        block = raw[match.start(): marks[index + 1].start() if index + 1 < len(marks) else len(raw)]
        title_match = re.search(r"<span[^>]+id=[\"']title[^\"']*[\"'][^>]*>(.*?)</span>", block, re.S | re.I)
        source_title = html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1))).strip()
        source_title = re.sub(r"\s+", " ", source_title).replace(" 【未配信】", "")
        author_match = re.search(r"(?:book_icon_author|著者)[^>]*>(.*?)(?:</div>|</p>)", block, re.S | re.I)
        credits = ""
        if author_match:
            credits = html.unescape(re.sub(r"<[^>]+>", " / ", author_match.group(1))).strip()
            credits = re.sub(r"(\s*/\s*)+", " / ", credits).strip(" /")
        primary = reviewed_primary_authors.get(rank, credits.split(" / ")[0] if credits else missing_authors.get(rank, "")).strip()
        if not primary:
            raise RuntimeError(f"Missing BookLive primary author at rank {rank}")
        rows.append({"source_rank": rank, "title": BOOKLIVE_TITLE_ALIASES.get(source_title, source_title),
                     "author": BOOKLIVE_AUTHORS.get(primary, primary), "source_title": source_title,
                     "source_credits": credits or missing_authors[rank]})
    return rows


def parse_modern_library() -> list[dict]:
    candidates = []
    for path in (ROOT / "research" / "_runs" / "2026-09-13" / "supplied-corpus").glob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict) and "modern-library-top-100" in payload.get("url", ""):
            candidates.append(payload.get("text", ""))
    if not candidates:
        raise RuntimeError("Modern Library official source snapshot not found")
    matches = []
    for match in re.finditer(r"(?m)^(\d+)\.\s+(.+?)\s+by\s+(.+?)\s*$", max(candidates, key=len)):
        if 1 <= int(match.group(1)) <= 100:
            matches.append((int(match.group(1)), match.group(2).strip(), match.group(3).strip()))
    rows = matches[-100:]
    corrections = {
        "IDEAS AND OPINIO NS": ("Ideas and Opinions", "Albert Einstein"),
        "THE AGE OF JACKSON": ("The Age of Jackson", "Arthur M. Schlesinger Jr."),
    }
    return [{"source_rank": rank, "title": corrections.get(title, (title.title(), author))[0],
             "author": corrections.get(title, (title.title(), author))[1],
             "source_title": title, "source_credits": author} for rank, title, author in rows]


def parse_pbs() -> list[dict]:
    payload = json.loads(Path("/private/tmp/pbs-gar-books.json").read_text())
    rows = []
    for row in sorted(payload, key=lambda item: int(item["ranking"])):
        source_title = row["title"]
        match = re.match(r"^(.*), (The|A|An)( \(Series\))?$", source_title)
        title = f"{match.group(2)} {match.group(1)}{match.group(3) or ''}" if match else source_title
        if title == "Doña Bárbára":
            title = "Doña Bárbara"
        rows.append({"source_rank": int(row["ranking"]), "title": title,
                     "author": row["author"].replace(" / ", " and "),
                     "source_title": source_title, "source_credits": row["author"]})
    return rows


def source_lists() -> dict[str, list[dict]]:
    parsers = {
        "asia-weekly-chinese-fiction-100-1999": parse_asia,
        "booklive-best-100-novels-2018": parse_booklive,
        "modern-library-board-100-nonfiction-1999": parse_modern_library,
        "pbs-great-american-read-2018": parse_pbs,
    }
    rows = {}
    for slug, parser in parsers.items():
        path = reviewed_path(slug)
        rows[slug] = json.loads(path.read_text()) if path.exists() else parser()
        definition = DEFINITIONS[slug]
        actual_ranks = [row["source_rank"] for row in rows[slug]]
        if len(rows[slug]) != definition["expected"] or len(set(actual_ranks)) != len(actual_ranks):
            raise RuntimeError(f"{slug}: expected {definition['expected']} unique rows, got {len(rows[slug])}")
    return rows


LATIN_TITLE_ALIASES = {
    "lord of rings": "the lord of the rings", "chronicles of narnia": "the chronicles of narnia",
    "grapes of wrath": "the grapes of wrath", "book thief": "the book thief", "great gatsby": "the great gatsby",
    "stand": "the stand", "color purple": "the color purple", "alice in wonderland": "alice's adventures in wonderland",
    "catcher in the rye": "the catcher in the rye", "outsiders": "the outsiders", "call of the wild": "the call of the wild",
    "dona barbara": "doña bárbara", "the travels of lao can": "the travels of lao ts'an",
}

REVIEWED_WORK_IDS = {
    ("modern-library-board-100-nonfiction-1999", 4): 168,
    ("pbs-great-american-read-2018", 2): 6624,
    ("pbs-great-american-read-2018", 3): 6609,
    ("pbs-great-american-read-2018", 5): 382,
    ("pbs-great-american-read-2018", 9): 6611,
    ("pbs-great-american-read-2018", 39): 723,
    ("pbs-great-american-read-2018", 40): 6618,
    ("pbs-great-american-read-2018", 48): 6639,
    ("pbs-great-american-read-2018", 49): 5085,
    ("pbs-great-american-read-2018", 62): 6642,
    ("pbs-great-american-read-2018", 64): 280,
}


def make_indexes():
    by_title = defaultdict(list)
    latin = defaultdict(list)
    from research.import_community_published_rankings import title_keys
    for work in Work.objects.filter(is_archived=False).prefetch_related("authors"):
        by_title[unorm(work.title)].append(work)
        for key in title_keys(work.title):
            latin[key].append(work)
    return by_title, latin


def resolve_work(slug: str, row: dict, unicode_index, latin_index):
    reviewed_id = REVIEWED_WORK_IDS.get((slug, row["source_rank"]))
    if reviewed_id:
        return Work.objects.get(pk=reviewed_id, is_archived=False), "reviewed_duplicate_choice"
    keys = [unorm(row["title"]), unorm(row.get("source_title", ""))]
    alias = next((value for key, value in LATIN_TITLE_ALIASES.items()
                  if unorm(key) == unorm(row["title"])), None)
    if alias:
        keys.append(unorm(alias))
    matches = {work.pk: work for key in keys if key for work in unicode_index.get(key, [])}
    if matches:
        wanted = {unorm(name) for name in split_authors(row["author"])}
        exact = [work for work in matches.values() if {unorm(person.name) for person in work.authors.all()} == wanted]
        if len(exact) == 1:
            return exact[0], "unicode_title_author"
        if len(matches) == 1:
            return next(iter(matches.values())), "unicode_unique_title"
        return None, "ambiguous_unicode:" + ",".join(str(pk) for pk in sorted(matches))
    if any(ord(char) > 127 for char in row.get("source_title", "")):
        return None, "missing"
    # Reuse the mature Latin-title resolver for punctuation/known alias cases.
    return resolve_latin_work(row, latin_index)


def ensure_rankings():
    for slug, definition in DEFINITIONS.items():
        ranking, created = Ranking.objects.get_or_create(slug=slug, defaults={
            "title": definition["title"], "origin": "external", "presentation": "ranked",
            "domain": "collections", "item_type": "work", "is_public": True,
            "source_url": definition["url"], "publisher": definition["publisher"],
            "status": "pending_import", "description": definition["limitation"],
            "scope": {"external_metadata": definition},
        })
        if created:
            ranking.full_clean()


def prepare(apply: bool):
    lists = source_lists()
    index, latin_index = make_indexes()
    people = defaultdict(list)
    for person in Person.objects.filter(is_archived=False):
        people[unorm(person.name)].append(person)
    mapped, created_works, created_people, problems = {}, [], [], []
    with transaction.atomic():
        if apply:
            ensure_rankings()
        for slug, rows in lists.items():
            mapped[slug], used = [], set()
            for row in rows:
                work, resolution = resolve_work(slug, row, index, latin_index)
                if work is None and resolution.startswith("ambiguous"):
                    problems.append({"target": slug, **row, "reason": resolution})
                    continue
                if work is None and not apply:
                    mapped[slug].append({**row, "work_id": None, "resolution": "would_create"})
                    continue
                if work is None:
                    authors = []
                    for name in split_authors(row["author"] or "Anonymous"):
                        candidates = people[unorm(name)]
                        person = min(candidates, key=lambda item: item.pk) if candidates else None
                        if person is None:
                            person = Person(name=name, source_url=DEFINITIONS[slug]["url"])
                            person.full_clean(); person.save()
                            people[unorm(name)].append(person)
                            created_people.append({"id": person.pk, "name": name})
                        authors.append(person)
                    form = proposed_form(row["title"])
                    if "series" in row["title"].casefold() or "シリーズ" in row.get("source_title", ""):
                        form = "collection"
                    work = Work(title=row["title"], form=form, field="literature",
                                description=f"Source-defined entry in {DEFINITIONS[slug]['title']}; edition and cover metadata pending.")
                    work.full_clean(); work.save(); work.authors.set(authors)
                    index[unorm(work.title)].append(work)
                    from research.import_community_published_rankings import title_keys
                    for key in title_keys(work.title):
                        latin_index[key].append(work)
                    created_works.append({"id": work.pk, "title": work.title,
                                          "authors": [author.name for author in authors], "source": slug})
                    resolution = "created"
                if work.pk in used:
                    problems.append({"target": slug, **row, "reason": f"duplicate_work:{work.pk}"})
                    continue
                used.add(work.pk)
                mapped[slug].append({**row, "work_id": work.pk, "resolution": resolution})
        if problems:
            raise RuntimeError(f"Resolve {len(problems)} rows before import: {problems[:25]}")
        if not apply:
            transaction.set_rollback(True)
    return {"mapped": mapped, "created_works": created_works, "created_people": created_people,
            "would_create": sum(row["resolution"] == "would_create" for rows in mapped.values() for row in rows)}


def source_records(slug: str, definition: dict) -> list[dict]:
    records = [{
        "source_id": "PUBLISHED-LIST-01", "underlying_source_id": "published-list:" + definition["url"],
        "title": definition["title"] + " — result publication", "canonical_url": definition["url"],
        "source_family": definition["family"], "publisher": definition["publisher"],
        "evidence_notes": definition["method"], "limitations": definition["limitation"],
    }]
    for number, key in enumerate(("mirror", "archive"), 2):
        if definition.get(key):
            records.append({
                "source_id": f"PUBLISHED-LIST-{number:02d}",
                "underlying_source_id": "published-list:" + definition[key],
                "title": definition["title"] + (" — official method notice" if key == "mirror" and slug.startswith("booklive") else " — transcription/data cross-check"),
                "canonical_url": definition[key], "source_family": "list_transcription",
                "publisher": definition["publisher"],
                "evidence_notes": "Used to verify methodology, identities, or the complete visible source order.",
                "limitations": "Corroborates the same published list; not independent opinion evidence.",
            })
    return records


def save_and_import(result):
    RUN.mkdir(parents=True, exist_ok=True)
    snapshots = [Path("/private/tmp/asiaweekly-chinese100.html"), Path("/private/tmp/booklive-novel100-wayback-20200102.html"),
                 Path("/private/tmp/booklive-press-20180531.html"), Path("/private/tmp/modern-library-top100.html"),
                 Path("/private/tmp/pbs-great-american-read.html"), Path("/private/tmp/pbs-great-american-read-books.html"),
                 Path("/private/tmp/pbs-gar-books.json")]
    audit = {"checked_on": CHECKED_ON, "targets": {},
             "catalog": {"created_works": result["created_works"], "created_people": result["created_people"]},
             "source_snapshots": {path.name: {"bytes": path.stat().st_size,
                 "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in snapshots if path.exists()}}
    for slug, rows in result["mapped"].items():
        definition = DEFINITIONS[slug]
        directory = ROOT / "research" / slug
        directory.mkdir(parents=True, exist_ok=True)
        source_rows = [{key: row[key] for key in ("source_rank", "title", "author", "source_title", "source_credits")} for row in rows]
        reviewed = reviewed_path(slug)
        reviewed.write_text(json.dumps(source_rows, ensure_ascii=False, indent=2) + "\n")
        records = source_records(slug, definition)
        ledger = {"target_id": slug, "status": "named_external_list_import", "saved_at": CHECKED_ON,
                  "sources": [{**record, "target_ids": [slug],
                               "relevance_by_target": {slug: record["evidence_notes"]},
                               "accessed_at": CHECKED_ON, "eligible": True} for record in records]}
        (directory / "sources.json").write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
        ranking = Ranking.objects.get(slug=slug)
        entries = [{"work_id": row["work_id"], "source_rank": row["source_rank"],
                    "note": f"{row['source_credits']} — source-defined list entry"} for row in rows]
        payload = {"target": slug, "presentation": "ranked", "expected_revision": ranking.revision,
                   "source_checked_on": CHECKED_ON,
                   "status": "imported" if not definition["unresolved"] else "imported_with_source_gap",
                   "unresolved_count": definition["unresolved"], "method_note": definition["method"],
                   "allow_reviewed_replacement": ranking.entries.filter(is_archived=False).exists(), "entries": entries}
        input_path = directory / f"reviewed-contents-{CHECKED_ON.replace('-', '')}.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        call_command("import_external_list", str(input_path))
        ranking.refresh_from_db()
        now = timezone.now()
        ranking.target_size = 100
        ranking.last_researched_at = now
        ranking.last_sources_checked_at = now
        ranking.scope = {**ranking.scope,
                         "entry_semantics": "publisher-defined books, series, collections or composite works",
                         "source_entry_count": len(entries), "source_expected_count": 100,
                         "source_unresolved_count": definition["unresolved"],
                         "source_method": definition["method"], "source_limitations": definition["limitation"]}
        ranking.description = definition["limitation"]
        ranking.full_clean(); ranking.save()
        for record in records:
            source, created = ResearchSource.objects.get_or_create(
                ranking=ranking, underlying_source_id=record["underlying_source_id"],
                defaults={"source_id": record["source_id"], "title": record["title"], "url": record["canonical_url"],
                          "family": record["source_family"], "publisher": record["publisher"],
                          "evidence": record["evidence_notes"], "limitations": record["limitations"],
                          "consulted_on": date.fromisoformat(CHECKED_ON), "eligible": True, "metadata": record})
            if created:
                source.full_clean()
        status_text = (f"fully imported named published ranking ({len(entries)} entries)" if not definition["unresolved"]
                       else f"imported with one publisher-hidden source position ({len(entries)} verified entries; rank 92 unresolved)")
        (directory / "RESEARCH.md").write_text(
            f"# {definition['title']}\n\nStatus: {status_text}, checked {CHECKED_ON}.\n\n"
            f"Primary source: {definition['url']}\n\nMethod: {definition['method']}\n\n"
            "The source ordering and source ranks are stored separately from Marginalia's researched rankings and personal assessments. "
            "No criteria, weights or private scores were assigned. Missing edition/cover enrichment does not alter membership.\n\n"
            f"Limitations: {definition['limitation']}\n\nArtifacts: `{reviewed.name}`, `{input_path.name}`, its import receipt, and `sources.json`.\n")
        audit["targets"][slug] = {"ranking_id": ranking.pk, "entries": len(entries), "revision": ranking.revision,
                                   "source_count": ranking.sources.filter(is_archived=False).count(),
                                   "unresolved": definition["unresolved"],
                                   "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}
    (RUN / "publication-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        result = prepare(False)
        print(json.dumps({"mode": "read_only", "counts": {slug: len(rows) for slug, rows in result["mapped"].items()},
                          "would_create": result["would_create"]}, ensure_ascii=False, indent=2))
        return
    with transaction.atomic():
        result = prepare(True)
        save_and_import(result)
    print(json.dumps({"mode": "applied", "counts": {slug: len(rows) for slug, rows in result["mapped"].items()},
                      "created_works": len(result["created_works"]), "created_people": len(result["created_people"])},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
