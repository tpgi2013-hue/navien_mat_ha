"""기기 목록(REST)과 실시간 상태(MQTT)를 합친다.

폴링 주기가 긴 이유는 게으름이 아니다 — 기기가 상태를 스스로 올리는 것을 실측으로
확인했으므로, 폴링은 **재접속 후 초기 동기화와 기기 목록 변화 감지**만 담당한다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    AwsCredentials,
    NavienSmartApi,
    NavienSmartAuthError,
    NavienSmartError,
)
from .const import (
    DOMAIN,
    MIN_REFRESH_COOLDOWN_SECONDS,
    MODE_HEAT,
    SERVICE_MATE,
    TOPIC_PREFIX,
    UPDATE_INTERVAL_SECONDS,
)
from .models import NavienDevice
from .mqtt import NavienSmartMqtt

_LOGGER = logging.getLogger(__name__)


def _zone_unchanged(device: NavienDevice, zone: str, value: Any) -> bool:
    """이 구역 명령이 기기가 이미 보고한 상태와 똑같은가."""
    if not isinstance(value, dict):
        return False
    axis = value.get("temperature") or value.get("level") or {}
    want = axis.get("set") if isinstance(axis, dict) else None
    current = device.zone_setting(zone)
    return (
        want is not None
        and current is not None
        and float(want) == current
        and value.get("enable") == device.zone_enabled(zone)
    )


def _app_number(value: Any) -> Any:
    """앱처럼 정수 값은 정수로 보낸다 (`35.0` → `35`, `35.5` 는 그대로)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _app_style_heater(heater: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for zone, value in heater.items():
        if not isinstance(value, dict):
            out[zone] = value
            continue
        zone_out = dict(value)
        for axis in ("temperature", "level"):
            inner = value.get(axis)
            if isinstance(inner, dict) and "set" in inner:
                zone_out[axis] = {**inner, "set": _app_number(inner["set"])}
        out[zone] = zone_out
    return out


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class NavienSmartCoordinator(DataUpdateCoordinator[dict[str, NavienDevice]]):
    """`data` 는 `deviceId` → `NavienDevice` 다."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        api: NavienSmartApi,
        home_seq: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
            config_entry=entry,
            # **밖에서 우리를 얼마나 자주 깨울 수 있는지의 하한.**
            #
            # HA 기본값은 10초다(`REQUEST_REFRESH_DEFAULT_COOLDOWN`). 그대로 두면
            # `homeassistant.update_entity` 를 10초마다 부르는 자동화 하나가
            # 계정 하나로 하루 8,640번 나비엔 서버를 두드린다. 비공식 클라이언트가
            # 감당할 수도, 감당해서도 안 되는 양이다.
            #
            # `immediate=True` 는 기본값 그대로 둔다 — 첫 요청은 즉시 처리하고
            # 뒤이어 몰려오는 것만 하나로 묶는다. 「지금 새로고침」은 계속 먹는다.
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=MIN_REFRESH_COOLDOWN_SECONDS,
                immediate=True,
            ),
        )
        self.api = api
        self.home_seq = home_seq
        # 매트가 아닌 기기도 원본은 들고 있는다 (진단용).
        self.raw_devices: list[dict[str, Any]] = []
        self.unsupported: list[dict[str, Any]] = []
        # 「상태가 안 온다」와 「와도 못 붙인다」를 진단만으로 가리기 위한 집계.
        # 개인정보는 없다 — 개수와 키 이름뿐이다.
        self.drop_counts: dict[str, int] = {"mate_no_device": 0}
        self._mqtt: NavienSmartMqtt | None = None
        # **기기마다 명령을 한 줄로 세운다.** 좌·우를 연달아 조작하면 HTTP 요청 두 개가
        # 동시에 나가고, 서버에 도착하는 순서가 바뀌면 먼저 보낸 명령이 나중에 적용돼
        # 뒤 명령을 덮는다 (실측: 좌 31 / 우 30 으로 남음).
        self._send_locks: dict[str, asyncio.Lock] = {}
        self._skipped_logged: set[str] = set()
        # **폴링이 돌기는 하는지**를 남긴다.
        #
        # 이슈 #1 에서 공기질 값이 열 시간 동안 그대로였는데, 조회 실패도 빈 응답도
        # 0 이었다. 「방이 조용했다」와 「우리가 아예 못 읽었다」가 같은 모양으로
        # 보였다 — 폴링 쪽 시각이 없어서다.
        self.poll_stamp: float | None = None
        self.poll_failures = 0
        # **`NavienSmartError` 만 세면 나머지가 통째로 안 보인다.** 이슈 #1 에서
        # 폴링이 설치 직후 한 번만 돌고 멈췄는데 `poll_failures` 가 0 이었다.
        # 우리 예외가 아닌 것(응답 모양이 달라 생긴 `TypeError` 같은)이 나면
        # 카운터에도 진단에도 흔적이 없다. 종류를 가리지 않고 세고, 마지막
        # 것을 남긴다 — **개인정보는 없다. 예외 이름과 메시지뿐이다.**
        self.poll_last_error: str | None = None
        # **「불렀는데 실패」와 「아예 안 부름」을 가른다.**
        #
        # 이슈 #1 에서 폴링이 설치 직후 한 번만 돌고 멈췄다. 실패 횟수는 0 이고,
        # 제보자가 로그를 `navien` 으로 검색해 전부 줬는데 HA 가 갱신 실패 때
        # 반드시 찍는 `Error fetching ... data` 가 **없었다.**
        #
        # 그러면 남는 것은 둘뿐이다 — 우리가 못 잡는 예외로 죽거나,
        # **HA 가 다음 차례를 아예 안 잡거나.** 성공 시각만으로는 못 가린다.
        # 시도 자체를 세면 한 줄로 갈린다.
        #
        #   시도가 늘어난다  → 부르고 있다. 우리가 실패하는 것이다
        #   시도가 멈춰 있다 → HA 가 안 부른다. 예약 쪽 문제다
        self.poll_attempts = 0

    # -- 수집 --------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, NavienDevice]:
        self.poll_attempts += 1
        try:
            return await self._async_collect()
        except (NavienSmartAuthError, ConfigEntryAuthFailed, UpdateFailed):
            raise
        except Exception as err:
            # **여기까지 오면 우리가 예상 못 한 것이다.** 그대로 올려보내면
            # HA 는 다시 잡아주지만 우리 진단에는 아무것도 안 남는다.
            self.poll_failures += 1
            self.poll_last_error = f"{type(err).__name__}: {err}"
            _LOGGER.exception("갱신 중 예상 못 한 오류가 났습니다")
            raise UpdateFailed(self.poll_last_error) from err

    async def _async_collect(self) -> dict[str, NavienDevice]:
        try:
            raw_devices = await self.api.async_get_devices(self.home_seq)
        except NavienSmartAuthError as err:
            self.poll_failures += 1
            self.poll_last_error = f"인증 실패: {err}"
            raise ConfigEntryAuthFailed(str(err)) from err
        except NavienSmartError as err:
            self.poll_failures += 1
            self.poll_last_error = f"기기목록 조회 실패: {err}"
            raise UpdateFailed(str(err)) from err

        previous = self.data or {}
        devices: dict[str, NavienDevice] = {}
        self.raw_devices = raw_devices
        self.unsupported = []

        for raw in raw_devices:
            # **항목이 dict 가 아닐 수 있다.** 그때 `.get` 을 부르면
            # `AttributeError` 가 나고, 우리 예외가 아니라 갱신이 조용히 멈춘다.
            if not isinstance(raw, dict):
                _LOGGER.warning(
                    "기기 목록에 예상 못 한 항목이 있어 건너뜁니다 (%s)",
                    type(raw).__name__,
                )
                continue
            # **이 전용판은 온수매트만 다룬다.** 보일러·환기청정 등은 건너뛴다.
            if _as_int(raw.get("serviceCode")) != SERVICE_MATE:
                self.unsupported.append(raw)
                continue

            device = NavienDevice.parse(raw)
            if device is None:
                self._log_skip(raw, "응답에서 기기를 해석하지 못했습니다")
                continue

            control = device.heat_control
            if control is None:
                self._log_skip(
                    raw, "functions.heatControl 이 없어 난방 제어를 만들지 않습니다"
                )
            elif not control.is_known:
                # 값 체계를 모르는 항목은 추측해서 명령을 보내지 않는다.
                self._log_skip(
                    raw,
                    f"heatControl.unit '{control.unit}' 은 확인된 값이 아닙니다. "
                    "난방 제어 엔티티를 만들지 않고 건너뜁니다",
                )

            # 이미 받아둔 실시간 상태를 잃지 않는다.
            #
            # **기록도 함께 이어받는다.** 기기 객체는 폴링마다 새로 만든다.
            # 이어받을 것을 빠뜨리면 그 값이 조용히 0 으로 돌아간다 — 진단 기록이
            # 그렇게 매번 지워지고 있었다(v0.9.5).
            if (old := previous.get(device.device_id)) is not None:
                device.reported = old.reported
                device.command_log = old.command_log
                device.state_log = old.state_log
                device.pending_zones = old.pending_zones

            if device.is_four_season:
                self._log_four_season(device)
            if device.has_unknown_season:
                self._log_unknown_season(device)

            devices[device.device_id] = device

        self.poll_stamp = time.monotonic()
        self.poll_failures = 0
        self.poll_last_error = None
        return devices

    def _log_four_season(self, device: NavienDevice) -> None:
        """사계절 기기를 만나면 한 번만 알린다.

        난방은 그대로 쓸 수 있다. 냉방은 값 체계가 확인되지 않아 그 구간에서만
        제어를 비활성으로 둔다. 아래 값이 제보로 오면 냉방을 열 수 있다.
        """
        key = f"{device.device_seq}:four_season"
        if key in self._skipped_logged:
            return
        self._skipped_logged.add(key)
        cool = device.cool_control
        _LOGGER.info(
            "사계절 모델을 찾았습니다 (%s, modelCode=%s). 냉방(COOL) 범위는 "
            "%s~%s 입니다. 앱에서 COOL 로 바꾸시면 HA 도 그 범위로 따라갑니다 — "
            "**냉방에서는 좌우가 같은 온도로 동작하므로** 어느 쪽을 조작해도 "
            "양쪽에 같은 값이 갑니다.",
            device.nickname,
            device.model_code,
            cool.range_min if cool else "?",
            cool.range_max if cool else "?",
        )

    def _log_unknown_season(self, device: NavienDevice) -> None:
        """`season` 이 우리가 아는 값이 아닐 때 한 번만 알린다.

        앱 상수는 WARM(0) / COOL(2) 둘뿐인데 규격표에는 `Cool+` 라는 이름도 있다.
        **다른 값이 오면 난방으로 두고 알린다** — 냉방 범위를 잘못 적용하는 것보다
        안전하다.
        """
        key = f"{device.device_seq}:season:{device.season}"
        if key in self._skipped_logged:
            return
        self._skipped_logged.add(key)
        _LOGGER.warning(
            "%s 의 season 값 %s 를 해석하지 못해 난방으로 다룹니다 "
            "(아는 값: 0 난방 / 2 냉방). 냉방 중이신데 이 로그가 보이면 "
            "이 줄과 통계정보를 이슈에 붙여 주세요 — 바로 넓힐 수 있습니다.",
            device.nickname,
            device.season,
        )

    def _log_skip(self, raw: dict[str, Any], reason: str) -> None:
        """건너뛴 내용을 설치 로그에 남긴다. 조용히 버리지 않는다."""
        key = f"{raw.get('deviceSeq')}:{reason}"
        if key in self._skipped_logged:
            return
        self._skipped_logged.add(key)
        _LOGGER.warning(
            "기기 건너뜀 (deviceSeq=%s, modelName=%s): %s",
            raw.get("deviceSeq"),
            raw.get("modelName"),
            reason,
        )

    # -- 실시간 ------------------------------------------------------------

    async def async_start_mqtt(self) -> None:
        prefixes = {
            prefix
            for device in (self.data or {}).values()
            if (prefix := TOPIC_PREFIX.get(device.service_code))
        }
        if not prefixes:
            _LOGGER.debug("구독할 기기가 없어 MQTT 를 시작하지 않습니다")
            return

        session = self.api.session
        self._mqtt = NavienSmartMqtt(
            self.hass,
            home_seq=self.home_seq,
            user_seq=session.user_seq if session else self.home_seq,
            topic_prefixes=prefixes,
            credentials_provider=self._async_aws_credentials,
            on_reported=self._handle_reported,
            on_subscribed=self._async_request_initial_state,
        )
        await self._mqtt.async_start()

    async def _async_request_initial_state(self) -> None:
        """켜져 있는 기기에 상태를 올려달라고 한다.

        shadow 이벤트는 **변화가 있을 때만** 온다. 그래서 구독만 해두면 아무 조작이
        없는 동안 상태가 비어 있다 — 엔티티가 계속 `unknown` 으로 남는다.

        제어 필드 없이 `event.modelCode` 만 담아 보내면 기기가 현재 상태를
        `reported` 로 올린다. 앱도 같은 방식을 쓴다.
        **설정을 바꾸지 않는다** — 보낼 값이 없기 때문이다.

        꺼져 있는 기기에는 보내지 않는다. 응답하지 않고 shadow 에만 쌓인다.

        **그래서 섀도우 조회를 먼저 한다.** 서버에 저장된 마지막 문서를 달라는
        읽기라 **꺼져 있는 기기도 답한다.** 붙인 직후 설정값이 바로 생기고,
        `climate` 가 「보낼 구역 값이 없습니다」로 막히는 일이 없어진다.
        """
        for device in (self.data or {}).values():
            # **먼저 저장된 것을 읽는다.** 온·오프라인을 가리지 않는다 —
            # 기기가 아니라 서버가 답하기 때문이다. 실기기 두 대로 확인했다.
            try:
                await self.api.async_request_shadow(self.home_seq, device.raw)
                _LOGGER.debug("%s 섀도우를 조회했습니다", device.nickname)
            except NavienSmartError as err:
                # 실패해도 아래 요청이 남아 있다. v0.13.x 와 같은 상태가 될 뿐이다.
                _LOGGER.debug("%s 섀도우 조회 실패: %s", device.nickname, err)

            if not device.available:
                _LOGGER.debug("%s 는 오프라인이라 초기 상태를 요청하지 않습니다", device.nickname)
                continue
            try:
                await self.api.async_control(self.home_seq, device.raw, {})
                _LOGGER.debug("%s 에 초기 상태를 요청했습니다", device.nickname)
            except NavienSmartError as err:
                _LOGGER.warning("%s 초기 상태 요청 실패: %s", device.nickname, err)

    async def async_stop_mqtt(self) -> None:
        if self._mqtt is not None:
            await self._mqtt.async_stop()
            self._mqtt = None

    @property
    def mqtt_connected(self) -> bool:
        return self._mqtt is not None and self._mqtt.connected

    @property
    def poll_age(self) -> float | None:
        """마지막으로 **끝까지 성공한** 폴링 뒤 흐른 초."""
        if self.poll_stamp is None:
            return None
        return round(time.monotonic() - self.poll_stamp, 1)

    @property
    def mqtt_stats(self) -> dict[str, Any]:
        """받은 개수·버린 개수. 진단에 담아 로그 없이도 가릴 수 있게 한다."""
        stats: dict[str, Any] = dict(self._mqtt.stats) if self._mqtt else {}
        stats.update(self.drop_counts)
        return stats

    async def _async_aws_credentials(self) -> AwsCredentials | None:
        """접속·재접속 시마다 새 자격증명을 받는다.

        `/auth/token/refresh` 는 AWS 자격증명을 주지 않으므로 `secured-sign-in` 을
        다시 부르는 것이 유일한 경로다.
        """
        try:
            return await self.api.async_refresh_aws_credentials()
        except NavienSmartAuthError:
            session = await self.api.async_login()
            return session.aws

    @callback
    def _handle_reported(self, device_id: str, reported: dict[str, Any]) -> None:
        """MQTT 로 들어온 `reported` 를 반영한다. HA 이벤트 루프에서 불린다."""
        devices = self.data or {}
        device = devices.get(device_id)
        if device is None:
            # 새로 등록된 기기일 수 있다. 다음 폴링에서 잡힌다.
            self.drop_counts["mate_no_device"] += 1
            _LOGGER.debug("모르는 기기의 보고 무시: %s", device_id)
            return
        # **덮어쓰지 않는다.** 사계절 모델이 부분 응답을 보낸다 (`apply_reported`).
        device.apply_reported(reported)
        self._async_push_update(devices)

    @callback
    def _async_push_update(self, data: dict[str, NavienDevice]) -> None:
        """MQTT 로 받은 상태를 엔티티에 알린다. **폴링 예약은 건드리지 않는다.**

        전에는 `async_set_updated_data()` 를 썼는데 그게 폴링을 굶겼다.
        HA 원본을 보면 그 함수가 이렇게 한다.

            def async_set_updated_data(self, data):
                self._async_unsub_refresh()        # 예약된 다음 폴링을 취소
                self._debounced_refresh.async_cancel()
                ...
                if self._listeners:
                    self._schedule_refresh()       # 지금부터 다시 세는 것

        **메시지가 올 때마다 다음 폴링이 뒤로 밀린다.**

        `async_update_listeners()` 는 엔티티에 알리기만 하고 예약을 안 건드린다.
        그것만 쓴다.
        """
        self.data = data
        # MQTT 로 신선한 값이 왔으니 엔티티를 살려둔다. 예약만 안 건드릴 뿐
        # 나머지는 `async_set_updated_data` 와 같게 한다.
        self.last_update_success = True
        self.async_update_listeners()

    async def async_send(self, device: NavienDevice, desired: dict[str, Any]) -> None:
        """명령을 보낸 뒤 낙관적 갱신은 하지 않는다.

        기기가 `reported` 를 올려줄 때까지 기다린다. 명령이 shadow 에 들어간 시점의
        이벤트(`reported` 없는 `/accepted`)를 상태로 쓰면 HA 가 기기보다 앞서 나간다.
        """
        # **앱과 같게 조작음을 요청한다.** 실측(앱 명령 캐처): 앱은 모든 조작에
        # `beep: true` 를 싣는다. 이게 없으면 매트가 설정은 받되 샑 소리도 안 내고
        # 화면도 안 깨운다 — 본체를 눌러봐야 바뀐 온도가 보였다.
        if device.has_beep and "beep" not in desired:
            desired = {"beep": True, **desired}
        # **바뀐 구역만 보낸다 — 앱이 그렇게 한다.** 실측(앱 명령 캐처): 좌측 온도만
        # 바꾸면 `heater` 에 `left` 하나만 실린다. 안 바뀐 구역까지 실어 보내면 매트가
        # 설정은 받되 「○○도로 설정되었습니다」 안내를 띄우지 않았다.
        heater = desired.get("heater")
        if isinstance(heater, dict) and len(heater) > 1:
            changed = {
                zone: value
                for zone, value in heater.items()
                if not _zone_unchanged(device, zone, value)
            }
            if changed:
                desired = {**desired, "heater": changed}
        # **앱 모양에 마저 맞춘다** (앱 명령 캐처와 대조).
        #   - 이미 켜져 있으면 온도 명령에 `operationMode` 를 싣지 않는다. 앱은 온도만
        #     보낸다. 매번 `operationMode: 1` 을 같이 보내면 매트가 「켜기」로 받아
        #     「○○도로 설정되었습니다」 안내를 건너뛰었다
        #   - 정수 온도는 정수로 (`35`, `35.5`). 앱이 그렇게 보낸다
        if isinstance(desired.get("heater"), dict):
            desired = {**desired, "heater": _app_style_heater(desired["heater"])}
            if desired.get("operationMode") == MODE_HEAT and device.is_on:
                desired = {k: v for k, v in desired.items() if k != "operationMode"}
        # 무엇을 보냈는지 남긴다. 냉방은 「보낸 값이 그대로 돌아오는가」를 봐야
        # 닫히는 구간이라 이 기록이 근거가 된다.
        device.note_command(desired)
        lock = self._send_locks.setdefault(device.device_id, asyncio.Lock())
        try:
            async with lock:
                await self.api.async_control(self.home_seq, device.raw, desired)
        except NavienSmartAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
