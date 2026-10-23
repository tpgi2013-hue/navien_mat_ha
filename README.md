# Navien Smart (Mat) — 온수매트 전용판

[ripe-avocado/navien_smart_ha](https://github.com/ripe-avocado/navien_smart_ha) **v0.18.1**에서 **나비엔 WiFi 온수매트(숙면매트) 부분만** 떼어 내 개인 설치용으로 고친 버전입니다. 원본은 MIT 라이선스이고 저작권 표기는 `LICENSE`에 그대로 두었습니다.

## 원본과 다른 점

| 항목 | 내용 |
|---|---|
| **좌우 연속 명령 덮어쓰기 수정** | 좌·우를 연달아 조작하면 두 번째 명령이 반대쪽의 **옛 값**을 실어 보내서 첫 명령을 되돌리던 문제. 보낸 값을 15초 동안 기억했다가 다음 명령을 만들 때 그 값을 씁니다 (`models.py` `pending_zones`) |
| **"좌우 통합" climate 추가** | 좌우 분리 매트에 엔티티 하나를 더 만듭니다. 온도 설정과 켜기는 양쪽을 **명령 1건**으로 보내고, 끄기는 전원을 끕니다 |
| **매트 전용** | 환기청정(에어원)·보일러 코드를 뺐습니다. `number` 플랫폼과 `airone.py`가 없습니다 |

도메인은 원본과 같은 `navien_smarthome`입니다. 원본 위에 덮어쓰면 기존 엔티티와 설정을 그대로 씁니다.

## 설치

`custom_components/navien_smarthome` 폴더를 HA `/config/custom_components/` 아래에 덮어쓰고 재시작하세요.
