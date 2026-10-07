# 경복궁·광화문 한정 문화 자료 인계

확인: 2026-10-07 KST. 상태: pN 통합 전 제안. 신규 `heritage-proposal.json`과 이 문서만 작성했다. 기존 catalog/evidence·메뉴·가상 자료는 변경하지 않았다.

## 직접 연 공식 출처

| 자료 | URL | 출처 시점과 확인 범위 |
|---|---|---|
| S1 Visit Seoul 경복궁 | [공식 소개](https://english.visitseoul.net/PalaceArea/Gyeongbokgung-Palace/ENP000072) | 본문·영문명·주소·운영 안내를 열어 확인. 표시 수정일 2026-10-07. 검색 요약에는 2026-09-11이 보였으나 연 페이지의 표시를 기록했다. 수정일이 방문일 운영 보장은 아니다. |
| S2 한국관광공사 광화문 | [공식 소개](https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=110592&menuSn=351) | 한영명·주소·문화 설명·운영 안내를 열어 확인. 원래 cmsCid=264329에서 이 URL로 연결됨. 발행·수정일 미표기로 as_of=null. |

역사·문화 사실은 각 장소당 3문장으로 JSON culture evidence에 요약했다. 긴 본문·사진을 복제하지 않았다. 광화문의 초창기 건립연도와 궁궐 중건연도는 검색 자료 간 표현이 달라 이번 요약에서 제외했다. 확인한 사실을 근거 없는 정밀 연도로 확장하지 않는다.

## 좌표 출처와 충돌

- **경복궁:** S1 HTML의 `f_open_route_map`, `var lat/lng`, `data-map-y/x`는 **37.57590409118165, 126.97684292625048**. 같은 페이지 JSON-LD는 **37.583307, 126.977286**로 다르다. 사용자에게 보이는 지도·길찾기 지점을 채택하고 충돌을 JSON에 보존했다. 궁궐 중심·실측 입구라고 부르지 않는다.
- **광화문:** S2의 JSON-LD와 지도 변수 `lat/lot`가 모두 **37.5760179589004, 126.976788008924**로 일치했다. 현장 GPS 실측은 아니다.
- 좌표는 정직한 User-Agent를 사용한 공개 HTML 읽기로 확인했다. 네트워크 제한으로 최초 로컬 읽기는 실패했고 승인된 재조회에서 필드를 확보했다. 계정·API 키·지도 유료 호출은 사용하지 않았다.
- 두 지도 지점이 가까운 이유는 경복궁 지도 지점이 남쪽 정문 부근이기 때문이다. 광화문을 별도 궁궐·광장·역으로 바꾸지 않는다. 같은 `visit_complex_id`를 사용하고 이중 입장·방문시간을 더하지 않는다.

## pN 통합 계약

- 기존 `data/catalog.json`의 `place_id/name/address_ko/lat/lng/source_id/food_ids`를 유지하며 `kind=heritage`, 한영명·관련 장소·근거 참조를 추가 제안했다.
- 기존 `data/evidence.json`은 `text`, `dataset_id`를 사용한다. 제안의 `evidence[]`는 같은 필드와 `observed_at/valid_from/valid_to/source_locator`를 유지한다. 요청한 `content`는 `text`와 같은 요약이며, 통합 때 중복 저장을 없애도 된다. `dataset_id=real_place`, `type=document`, `scope=culture|operation`이다.
- `places[].source_id`는 해당 좌표·장소 근거 ID를 가리킨다. `links[]` 두 항목의 `bidirectional=true`는 기존 `local:tosokchon`과 양방향 후보 검색을 연결하기 위한 제안이다. 식당-궁궐의 역사적 연관성이나 공식 추천을 주장하지 않는다.
- 문화장소의 `food_ids=[]`를 유지한다. 토속촌의 음식 목록·영업 여부를 문화장소에 복사하지 않는다. 음식에서 근처 문화로, 문화에서 근처 식사 후보로 이어가는 데만 사용한다.
- 경복궁·광화문 두 곳만 신규이며 전국 검색·경로 서비스 확장은 없다. 도보 시간·유효 출입문·무장애 경로는 미검증, 직선거리만 계산 가능하다.

## 운영·품질 한계

두 출처의 정기 휴무 안내와 방문일 실제 통제를 분리했다. 오래된 시간·요금을 실행 가능한 일정으로 고정하지 않도록 `currently_open=null`, `admission_fee=null`을 둔다. 날씨·특별 개방·공휴일 예외·행사·매표·토속촌 영업/재고는 별도 확인 대상이다.

궁능유적본부 khs 페이지는 본문 추출이 불완전했고 구 cha URL 재조회는 시간 초과, 국가유산포털은 403이었다. 이 페이지들의 검색 요약을 검증된 추가 사실로 넣지 않았다. 충분한 Visit Seoul·한국관광공사 1차 자료를 확보해 범위를 넓히지 않았다. 서비스 통합·실행·모델 응답·사용자 효용은 미검증이다.
