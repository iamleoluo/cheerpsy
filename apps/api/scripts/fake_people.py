"""假個資產生：台灣姓名、身分證字號、電話、地址。

刻意不依賴 Faker：這支腳本要能在診所那台 Windows 機器上直接跑，少一個
套件就少一個安裝失敗的機會。台灣姓名用姓氏×名字組合就夠真實了。

身分證字號會算出**格式合法（含檢查碼）**的假號——不是為了騙過誰，而是
因為 generate_case_number() 會取末兩碼當病歷號的一部分，而 activate_case()
會擋沒有身分證的個案。號碼本身是隨機的，不對應任何真人。
"""

from __future__ import annotations

import random

SURNAMES = [
    "陳", "林", "黃", "張", "李", "王", "吳", "劉", "蔡", "楊", "許", "鄭", "謝", "郭",
    "洪", "曾", "邱", "廖", "賴", "徐", "周", "葉", "蘇", "莊", "呂", "江", "何", "蕭",
    "羅", "高", "潘", "簡", "朱", "鍾", "彭", "游", "詹", "胡", "施", "沈",
]

GIVEN_M = [
    "俊宏", "志明", "建良", "家豪", "冠廷", "承翰", "宗翰", "柏勳", "宇軒", "彥廷",
    "威霖", "哲瑋", "怡碩", "君豪", "凱翔", "又銘", "書瑋", "定國", "文彬", "世傑",
]
GIVEN_F = [
    "淑芬", "雅婷", "怡君", "美玲", "佳穎", "詩涵", "欣怡", "曉薇", "宜蓁", "映彤",
    "郁婷", "思妤", "筱涵", "品妍", "家瑜", "馨儀", "亭安", "巧薇", "秀琴", "若瑄",
]

CITIES = ["臺南市", "高雄市", "嘉義市", "臺南市", "臺南市"]
DISTRICTS = ["東區", "南區", "北區", "中西區", "安平區", "永康區", "仁德區", "歸仁區", "新營區"]
STREETS = ["中華路", "小東路", "民族路", "健康路", "崇明路", "林森路", "長榮路", "西門路", "文化街"]

# 身分證首碼對應的兩位數字（縣市代碼）
LETTER_CODE = {
    "A": 10, "B": 11, "C": 12, "D": 13, "E": 14, "F": 15, "G": 16, "H": 17,
    "I": 34, "J": 18, "K": 19, "L": 20, "M": 21, "N": 22, "O": 35, "P": 23,
    "Q": 24, "R": 25, "S": 26, "T": 27, "U": 28, "V": 29, "W": 32, "X": 30,
    "Y": 31, "Z": 33,
}
# 台南/高雄/嘉義為主，讓假資料看起來像同一個生活圈的個案
COMMON_LETTERS = ["D", "E", "S", "A", "B", "C", "F", "N", "Q", "T"]


def national_id(rng: random.Random, gender: str) -> str:
    """產生檢查碼正確的假身分證字號。gender: male → 1、其餘 → 2。"""
    letter = rng.choice(COMMON_LETTERS)
    sex_digit = 1 if gender == "male" else 2
    body = [sex_digit] + [rng.randint(0, 9) for _ in range(7)]

    code = LETTER_CODE[letter]
    total = (code // 10) * 1 + (code % 10) * 9
    # body 有 8 碼（含性別碼），權重由 8 遞減至 1
    for i, d in enumerate(body):
        total += d * (8 - i)
    check = (10 - (total % 10)) % 10
    return letter + "".join(str(d) for d in body) + str(check)


def person(rng: random.Random) -> dict:
    gender = rng.choice(["male", "female"])
    given = rng.choice(GIVEN_M if gender == "male" else GIVEN_F)
    name = rng.choice(SURNAMES) + given
    return {
        "name": name,
        "gender": gender,
        "phone": f"09{rng.randint(10, 89)}{rng.randint(100000, 999999)}",
        "phone_home": f"06-{rng.randint(2000000, 2999999)}",
        "address": (
            f"{rng.choice(CITIES)}{rng.choice(DISTRICTS)}{rng.choice(STREETS)}"
            f"{rng.randint(1, 500)}號"
            + (f"{rng.randint(2, 12)}樓" if rng.random() < 0.5 else "")
        ),
        "national_id": national_id(rng, gender),
        "emergency_contact": rng.choice(SURNAMES) + rng.choice(GIVEN_M + GIVEN_F),
        "emergency_phone": f"09{rng.randint(10, 89)}{rng.randint(100000, 999999)}",
    }


ISSUES = [
    "情緒困擾", "焦慮", "憂鬱", "人際關係", "家庭議題", "婚姻/伴侶",
    "職涯壓力", "創傷", "親職教養", "自我探索", "睡眠困擾", "失落與哀傷",
]

SOURCES = ["自行來電", "機構轉介", "親友介紹", "網路查詢", "醫療院所轉介", "學校轉介"]

CLOSURE_REASONS = [
    "目標達成，雙方同意結案", "個案搬遷至外縣市", "轉介至其他專業資源",
    "個案主動終止", "機構額度用罄且未續自費", "長期失聯",
]

NO_SHOW_REASONS = ["case_leave", "last_minute_cancel", "unreachable", "other"]
