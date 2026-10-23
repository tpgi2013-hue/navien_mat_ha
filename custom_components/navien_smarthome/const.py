"""나비엔 스마트 통합 상수.

**추측한 값은 없다.** 전부 앱에서 직접 추출했다. 다만 검증 수준이 다르다.

- 매트(200) 관련 값 — 실기기로 검증했다. 단계형은 직접, 온도형·사계절은 제보로
- 에어원(300) 관련 값 — 앱에서 추출한 뒤 **제보로 확인했다**. 확인된 모델은
  룸콘 분리형(1901)과 올인원 룸콘(1900) 두 계열이다

**확인의 무게가 다르다.** 직접 눌러본 것과 제보로 들은 것을 섞어 적지 않는다.
각 항목에 어느 쪽인지 적어 두었다.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "navien_smarthome"

# --- 엔드포인트 ------------------------------------------------------------

API_URL: Final = "https://nskr.naviensmartcontrol.com/api/v2.0"
LOGIN_URL: Final = "https://member.naviensmartcontrol.com"

# 앱의 `Constants.getIotEndPoint()` 값. AWS IoT 앞단에 나비엔이 세운 자체 도메인이다.
# 기기 응답의 `network.server.endpoint` 는 **기기가 접속하는 쪽**이라 다르다 —
# 그걸로 붙으면 SNI 불일치로 403 이 난다.
IOT_ENDPOINT: Final = "nskr-iot.naviensmartcontrol.com"
IOT_REGION: Final = "ap-northeast-2"
IOT_SERVICE: Final = "iotdevicegateway"

USER_AGENT: Final = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 APP_NAVIENSMART_IOS"
)

# **요청 하나가 폴링 주기를 통째로 먹지 않게 한다.**
#
# `aiohttp` 기본값은 5분이라 에어원 폴링 주기와 똑같다. 서버가 연결만 받아두고
# 응답하지 않으면 그 한 번이 주기 전체를 잡아먹는다.
REQUEST_TIMEOUT_SECONDS: Final = 30

# --- 서버 응답 코드 --------------------------------------------------------

CODE_SUCCESS: Final = 200
CODE_BAD_REQUEST: Final = 400
# 계정당 세션이 하나뿐이다. 사용자가 앱을 열면 이 코드가 온다.
CODE_NOT_AUTHORIZED: Final = 404
CODE_TOKEN_EXPIRED: Final = 407

# --- 기기 종류 ------------------------------------------------------------

# 앱 내부 이름은 `SERVICE_SMARTTOK` 이다 — 보일러용 통신 모듈 브랜드가 스마트톡이다.
SERVICE_BOILER: Final = 100
SERVICE_MATE: Final = 200
SERVICE_AIRONE: Final = 300
SERVICE_SCADA: Final = 400
SERVICE_HOMEAUTO: Final = 500

# **이 전용판은 온수매트(숙면매트)만 다룬다.**
SUPPORTED_SERVICE_CODES: Final = (SERVICE_MATE,)
REPORT_WANTED_SERVICE_CODES: Final = ()

SERVICE_NAMES: Final = {
    SERVICE_BOILER: "보일러",
    SERVICE_MATE: "숙면매트",
    SERVICE_AIRONE: "환기청정",
    SERVICE_SCADA: "상업용 SCADA",
    SERVICE_HOMEAUTO: "스마트홈",
}

# MQTT 구독 토픽 접두사.
TOPIC_PREFIX: Final = {SERVICE_MATE: "mate"}

# --- 제어 축 (heatControl.unit) -------------------------------------------

# dex 전수 검색 결과 값은 이 둘뿐이다. `<간격><축>` 형식.
UNIT_LEVEL: Final = "1.0L"  # heater.*.level.set — 정수 단계
UNIT_CELSIUS: Final = "0.5C"  # heater.*.temperature.set — 0.5도 간격
KNOWN_UNITS: Final = (UNIT_LEVEL, UNIT_CELSIUS)

# --- operationMode (KDMode.WIFI 맵) ---------------------------------------

MODE_POWER_OFF: Final = 0
MODE_HEAT: Final = 1
MODE_RESERVE: Final = 2
MODE_SLEEP: Final = 3
MODE_STERILIZE: Final = 4
MODE_DISCHARGE: Final = 5
MODE_ERROR: Final = 6
MODE_CUSTOM_SLEEP: Final = 7
MODE_AISLEEP: Final = 8
MODE_CHANGE_HEAT: Final = 99
MODE_BED_DRYING: Final = 129
MODE_HYPER: Final = 130

MODE_NAMES: Final = {
    MODE_POWER_OFF: "전원 꺼짐",
    MODE_HEAT: "난방",
    MODE_RESERVE: "예약",
    MODE_SLEEP: "수면모드",
    MODE_STERILIZE: "살균",
    MODE_DISCHARGE: "배수",
    MODE_ERROR: "오류",
    MODE_CUSTOM_SLEEP: "개인맞춤 수면",
    MODE_AISLEEP: "AI 수면",
    MODE_CHANGE_HEAT: "난방 전환",
    MODE_BED_DRYING: "침대 건조",
    MODE_HYPER: "하이퍼",
}

# 매트 오류 코드 이름. **제보자가 기기 설명서에서 옮겨 준 것**이다(2026-07-31).
#
# **온도형(`0.5C`) 에만 붙인다.** 물탱크·순환펌프·UV램프·냉각장치·누수가 나오는
# 것으로 보아 온수·사계절 계열 설명서다. 카본(단계형)에 같은 번호가 같은 뜻이라는
# 근거가 없어서, 단계형에는 숫자만 보여준다.
#
# 상태값은 숫자 그대로 두고 **속성으로만** 보여준다. 상태를 글자로 바꾸면 이 값을
# 쓰던 자동화·템플릿이 깨진다.
MAT_ERROR_NAMES: Final = {
    0: "정상",
    2: "물 부족 (Er 02)",
    5: "물탱크 공급 온도 센서 (Er 05)",
    7: "외기 온도 센서 (Er 07)",
    8: "순환펌프 동작 (Er 08)",
    9: "팬 이상 (Er 09)",
    11: "수위 감지 (Er 11)",
    15: "UV램프 (Er 15)",
    16: "물탱크 과열 (Er 16)",
    17: "난방 이상 (Er 17)",
    18: "온도센서 (Er 18)",
    26: "냉각장치 과냉 (Er 26)",
    27: "냉방 이상 (Er 27)",
    28: "누수 (Er 28)",
}

# 전원이 켜진 것으로 볼 모드. `MODE_ERROR` 는 제외한다.
MODES_ON: Final = frozenset(
    {
        MODE_HEAT,
        MODE_RESERVE,
        MODE_SLEEP,
        MODE_STERILIZE,
        MODE_CUSTOM_SLEEP,
        MODE_AISLEEP,
        MODE_CHANGE_HEAT,
        MODE_BED_DRYING,
        MODE_HYPER,
    }
)

# --- 난방 구역 ------------------------------------------------------------

ZONE_SINGLE: Final = "single"
ZONE_LEFT: Final = "left"
ZONE_RIGHT: Final = "right"

ZONE_NAMES: Final = {ZONE_SINGLE: "난방", ZONE_LEFT: "좌측", ZONE_RIGHT: "우측"}

# `modelType`. 접두사로 추론하면 틀린다 — EMW750 은 EMW 인데 사계절이다.
MODEL_TYPE_LABELS: Final = {"em": "카본", "wm": "온수", "fm": "사계절"}

# --- 계절 (사계절 모델) ---------------------------------------------------

# `Constants.SUMMER_SEASON` / `WINTER_SEASON`. 값 1 의 용도는 미확인.
SEASON_WINTER: Final = 0
SEASON_SUMMER: Final = 2
SEASON_NAMES: Final = {SEASON_WINTER: "난방", SEASON_SUMMER: "냉방"}

# --- 조작음 음량 ----------------------------------------------------------
#
# **앱 음량 화면에 칸이 넷이다** — 음소거 + 3단계.
# `MateDeviceSettingSoundVolumeFragment` 가 `selectedIndex` 를 0·1·2·3 중 하나로
# 정하고 그대로 `setSoundVolume(int)` 에 넘긴다. 읽을 때도 같은 값으로 갈린다
# (`initializeCurrentVolumeLevel`: 0 이면 음소거 아이콘, 1·2 각각, 나머지는 3).
#
# 보내는 필드는 `Desired.volume` (`Integer`), 명령 이름은 `control-volume`.
# 라벨은 앱 화면 문구가 아니라 아이콘 이름(`mute`, `volumeLevel1~3`)을 따랐다.
MAT_VOLUME_NAMES: Final = {0: "음소거", 1: "1단계", 2: "2단계", 3: "3단계"}

# 사계절 모델은 `season` 이 어느 제어 서술자를 쓸지 고른다 —
# 여름이면 `coolControl`, 그 외에는 `heatControl`. 설정값 경로는 `heater` 를 공유한다.
# 냉방 전용 operationMode 는 `KDMode.WIFI` 맵에 없다.
#
# v1 은 사계절 기기에 제어 엔티티를 만들지 않는다. 값 체계가 확인되지 않았고,
# 냉방 중인 기기를 난방 범위로 표시하면 사용자가 오해한다.
# 실기기 제보가 오면 연다.

# `mcu.capacity` 로 싱글/더블을 가른다. `matType` 이 아니다 (실측: 둘 다 1이었다).
CAPACITY_SINGLE: Final = 1
CAPACITY_DOUBLE: Final = 2

# --- 단계형 제어 표기 ---------------------------------------------------

# 0은 숫자가 아니라 상태다. 앱 슬라이더의 맨 왼쪽이 이것이고, 서버가 알려주는
# `heatControl.rangeMin` (실측 1) 보다 낮다. `level 0` + `enable false` 로 함께 온다.
LEVEL_STANDBY: Final = 0
LABEL_STANDBY: Final = "운전 대기"


def level_label(level: int) -> str:
    """단계 값을 앱과 같은 말로 옮긴다."""
    return LABEL_STANDBY if level == LEVEL_STANDBY else f"{level}단계"

# --- 설정 키 --------------------------------------------------------------

CONF_HOME_SEQ: Final = "home_seq"

# 재접속 후 초기 동기화용. 상태는 MQTT 푸시로 오므로 폴링 주기를 짧게 둘 이유가 없다.
UPDATE_INTERVAL_SECONDS: Final = 900

# **밖에서 들어오는 갱신 요청의 하한 — 폴링 주기와 같게 둔다.**
#
# `homeassistant.update_entity` 로 코디네이터를 언제든 깨울 수 있다. HA 기본
# 하한은 10초라, 자동화를 10초마다 걸면 계정 하나가 하루 8,640번 나비엔 서버를
# 두드린다. 우리는 비공식 클라이언트다 — 막히면 그 사람만 막히는 게 아니라
# 통합 전체가 막힌다.
#
# **처음엔 60초로 잡았다. 앱이 1분마다 읽으니 앱을 상한으로 삼자는 생각이었다.**
# 틀렸다. 앱의 1분은 **화면을 보는 동안만**이고 우리는 24시간 돈다. 그 값을
# 하한으로 두면 우리 기본값(5분)보다 5배 빠른 것을 허용하는 셈이라, 하한이
# 기본값보다 헐거워진다.
#
# 그래서 숫자를 고르지 않고 규칙으로 둔다 — **밖에서 깨워도 우리 폴링 주기보다
# 빠르게는 못 간다.**
#
# 첫 요청은 그대로 즉시 처리된다 (`immediate=True`) — 「지금 새로고침」이 먹통이
# 되면 안 된다. 막는 것은 **반복**이지 한 번이 아니다.
MIN_REFRESH_COOLDOWN_SECONDS: Final = UPDATE_INTERVAL_SECONDS
