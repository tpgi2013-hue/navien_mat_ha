"""진단 정보 내보내기.

설정 → 기기 및 서비스 → 나비엔 스마트 → ⋮ → `통계정보 다운로드` 로 받는다 (한국어 번역이 「통계」다. 원문 Download diagnostics).
사용자가 무엇을 붙여야 할지 몰라도 되게 하는 것이 목적이다.

범위 밖 기기(보일러·상업용·월패드)는 요약만 남긴다. 쓰지 않을 데이터를
내보낼 이유가 없다.

식별자는 전부 가린다. 별칭도 가린다 — 사람 이름이 들어가는 경우가 많다.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from . import NavienSmartConfigEntry
from .const import (
    IOT_ENDPOINT,
    KNOWN_UNITS,
    REPORT_WANTED_SERVICE_CODES,
    SERVICE_NAMES,
    SUPPORTED_SERVICE_CODES,
)

# 키 이름으로 지운다. `heater.left` / `right` 는 구조라서 건드리면 안 되므로
# 별칭은 상위 키(`nickName`, `userInfo`)를 통째로 가린다.
TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    "accessToken",
    "refreshToken",
    "accountId",
    "clientId",
    "defaultClientId",
    "deviceId",
    "eventId",
    "localIp",
    "mac",
    "mqttTopicKey",
    "nickName",
    "regionCode",
    "sessionId",
    "ssid",
    "thingArn",
    "thingId",
    "thingName",
    "userId",
    "userInfo",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: NavienSmartConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data

    supported: list[dict[str, Any]] = []
    report_wanted: list[dict[str, Any]] = []
    out_of_scope: list[dict[str, Any]] = []

    for raw in coordinator.raw_devices:
        service_code = raw.get("serviceCode")
        if service_code in SUPPORTED_SERVICE_CODES:
            supported.append(async_redact_data(raw, TO_REDACT))
        elif service_code in REPORT_WANTED_SERVICE_CODES:
            # 지원을 넓힐 대상. 구조를 봐야 하므로 원본을 담는다.
            report_wanted.append(async_redact_data(raw, TO_REDACT))
        else:
            out_of_scope.append(
                {
                    "serviceCode": service_code,
                    "service": SERVICE_NAMES.get(service_code),
                    "modelName": raw.get("modelName"),
                    "modelCode": raw.get("modelCode"),
                }
            )

    payload = {
        "integration": {
            "iot_endpoint": IOT_ENDPOINT,
            "mqtt_connected": coordinator.mqtt_connected,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds()
                if coordinator.update_interval
                else None
            ),
            # **폴링이 도는지 먼저 본다.** 이 값이 주기보다 훨씬 크면 값이 옛것인
            # 이유는 기기도 서버도 아니고 우리다.
            # **`poll_attempts` 를 먼저 본다.** 성공 시각만으로는 「우리가
            # 실패하는 것」과 「HA 가 안 부르는 것」이 같은 모양으로 보인다.
            "poll_attempts": coordinator.poll_attempts,
            "last_poll_seconds_ago": coordinator.poll_age,
            "poll_failures": coordinator.poll_failures,
            # 마지막 실패가 무엇이었나. 예외 이름과 메시지뿐이다.
            "poll_last_error": coordinator.poll_last_error,
            # **HA 쪽에서 폴링을 꺼둘 수 있다.**
            #
            #   설정 → 기기 및 서비스 → 나비엔 스마트 → ⋮ → 시스템 옵션
            #   → 「변경 사항에 대한 폴링 활성화」
            #
            # 끄면 HA 가 주기 갱신을 통째로 멈춘다. 그런데 MQTT 는 우리가 직접
            # 붙으므로 계속 살아 있다 — **모드·전원은 멀쩡한데 공기질만 멈춘다.**
            # 그때 `last_poll_seconds_ago` 만 커지고 `poll_failures` 는 0 이라,
            # 이 값이 없으면 「왜 안 도는지」를 물어봐야만 알 수 있다.
            "polling_disabled_in_ha": bool(
                getattr(entry, "pref_disable_polling", False)
            ),
            "known_control_units": list(KNOWN_UNITS),
            # **「상태가 안 온다」의 원인을 로그 없이 가리는 값.**
            # 받은 개수가 0 이면 안 오는 것이고, 버린 개수가 있으면 와도 못 쓰는
            # 것이다. 후자면 어느 모양인지
            # 알려준다. 개수와 키 이름뿐이라 개인정보는 없다.
            "mqtt_messages": coordinator.mqtt_stats,
        },
        "counts": {
            "total": len(coordinator.raw_devices),
            "supported": len(supported),
            "report_wanted": len(report_wanted),
            "out_of_scope": len(out_of_scope),
        },
        "entities": [_entity_view(device) for device in (coordinator.data or {}).values()],
        "supported_devices": supported,
        # 이 항목이 비어 있지 않으면 이슈에 그대로 붙여 주세요.
        "report_wanted_devices": report_wanted,
        "out_of_scope_devices": out_of_scope,
    }
    # **키 이름으로 가리는 것만으로는 부족하다.** 값 안에 식별자가 박혀 있는
    # 경우가 있다 — `requestTopic: "dt/rc/7/1097BD3F5CACB84E/did"` 가 그것이다.
    # `requestTopic` 은 가릴 키 목록에 없었고, 제보자가 이 줄을 공개로 올렸다.
    #
    # 그 키를 목록에 더하는 것으로 끝내지 않는다. **다음에 또 새는 것을 막는다.**
    # 식별자 값을 먼저 모아 두고, 결과 전체에서 그 문자열을 지운다.
    # 토픽 모양(`dt/rc/7/**REDACTED**/did`)은 남으므로 지원을 넓힐 근거는 잃지 않는다.
    return _scrub(payload, _identifiers(coordinator.raw_devices))


def _identifiers(raw_devices: list[dict[str, Any]]) -> list[str]:
    """가려야 할 식별자 **값**을 모은다.

    `TO_REDACT` 의 키에 실린 문자열이 대상이다. 8자 미만은 버린다 — 짧은 값은
    다른 문자열에 우연히 들어 있을 수 있고, 그걸 지우면 멀쩡한 값이 망가진다.
    """
    found: set[str] = set()

    def walk(value: Any, key: str | None) -> None:
        if isinstance(value, dict):
            for inner_key, inner in value.items():
                walk(inner, inner_key)
        elif isinstance(value, list):
            for inner in value:
                walk(inner, key)
        elif isinstance(value, str) and key in TO_REDACT:
            text = value.strip()
            if len(text) >= 8:
                found.add(text)

    walk(raw_devices, None)
    # 긴 것부터 지운다. 짧은 값이 긴 값의 일부일 때 순서가 뒤바뀌면 조각이 남는다.
    return sorted(found, key=len, reverse=True)


def _scrub(value: Any, secrets: list[str]) -> Any:
    """결과 전체를 훑어 식별자 문자열을 지운다."""
    if not secrets:
        return value
    if isinstance(value, dict):
        return {key: _scrub(inner, secrets) for key, inner in value.items()}
    if isinstance(value, list):
        return [_scrub(inner, secrets) for inner in value]
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, "**REDACTED**")
        return value
    return value


def _entity_view(device: Any) -> dict[str, Any]:
    """통합이 기기를 어떻게 해석했는지. 오해가 어디서 생겼는지 찾을 때 쓴다."""
    heat = device.heat_control
    cool = device.cool_control
    return {
        "service_code": device.service_code,
        "model_code": device.model_code,
        "model_name": device.model_name,
        "model_type": device.model_type,
        "capacity": device.capacity,
        "zones": list(device.zones),
        "is_double": device.is_double,
        "is_four_season": device.is_four_season,
        "season": device.season,
        "is_cooling": device.is_cooling,
        "has_unknown_season": device.has_unknown_season,
        # 앱이 기기 설정 화면에 두는 값들. 잠금은 읽기만 되고 음량은 쓸 수 있다.
        "child_lock": device.child_lock,
        "volume": device.volume,
        # 상태가 어느 묶음까지 왔는지. 사계절 모델이 부분 응답을 보내서
        # `season`·`operationMode` 가 빠지는 일이 있었다 (v0.9.0).
        "reported_keys": sorted(device.reported or {}),
        "reported_heater_zones": sorted((device.reported or {}).get("heater") or {}),
        # **냉방을 닫으려면 순서를 봐야 한다.** 「26.0 을 보냈는데 기기가 26.0 을
        # 돌려주는가」, 「한쪽만 보냈는데 양쪽이 따라오는가」, 「`season` 이 실제로
        # 무엇으로 바뀌는가」는 그 순간의 값만으로 알 수 없다.
        # `at` 은 절대 시각이 아니라 **간격을 보기 위한 초 단위 눈금**이다
        # (기기 부팅 이후 흐른 초). 값 자체는 뜻이 없고 줄 사이의 차이만 쓴다.
        # 온도·단계 값뿐이라 개인정보는 없다.
        "command_log": list(device.command_log),
        "state_log": list(device.state_log),
        "available": device.available,
        "operation_mode": device.operation_mode,
        "error_code": device.error_code,
        "heat_control": heat.as_diagnostics() if heat else None,
        "cool_control": cool.as_diagnostics() if cool else None,
        "control_unit_known": bool(heat and heat.is_known),
        "functions": {
            "power_ctrl": device.has_power_ctrl,
            "beep": device.has_beep,
            "lock_mode": device.has_lock_mode,
            "power_saving": device.has_power_saving,
            "sleep_mode": device.has_sleep_mode,
            "sleep_durations_minutes": device.sleep_durations,
            "schedule_kinds": list(device.schedule_kinds),
        },
        "zone_state": {
            zone: {
                "setting": device.zone_setting(zone),
                "current": device.zone_current(zone),
                "enabled": device.zone_enabled(zone),
            }
            for zone in device.zones
        },
    }


def _numbers_only(raw: Any) -> dict[str, Any]:
    """딕셔너리에서 **숫자와 참·거짓만** 남긴다.

    이름을 몰라도 값을 볼 수 있게 하는 그물이다. 목표 습도가 어느 키로 오는지
    모르는 상태라 키를 지정할 수 없다.

    문자열을 통째로 빼는 것이 가림 장치다 — 기기ID·SSID·별칭·MAC 은 모두
    문자열이므로 여기 걸리지 않는다. **가릴 키를 나열하는 방식은 새 키가
    생기면 새는데**, 이 방식은 새 문자열 키가 생겨도 안 나간다.
    """
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if isinstance(value, (int, float, bool)) and key not in TO_REDACT
    }
