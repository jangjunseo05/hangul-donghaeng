# 실제 시연 영상 준비 — Android 라이브 + 90초 백업

상태: PREPARED_ONLY / 실제 p8 녹화·타이밍 입력 대기. 이 디렉터리에는 아직 시연 결과 영상이 없다.

## 1. 발표 순서

1. **Android 라이브가 기본**: https://arrive-relationship-halifax-triple.trycloudflare.com 을 연다. 임시 터널이 유지되는 동안만 유효하다. 실제 카메라 권한·미리보기·선택적 분석·장면 고정·문화 장소↔식당·카드는 root가 확인한 범위만 시연한다.
2. **백업은 실제 브라우저 화면 녹화**: p8의 실제 raw WebM과 실제 단계 시간표를 사용한다. 녹화 파일에는 재촬영/모델 실행 지시가 들어 있지 않다. 이 변환 스크립트는 제품이나 모델 서버를 호출하지 않는다.
3. 백업으로 전환할 때 “앞서 실제 브라우저에서 실행한 화면입니다. 샘플 사진 시연이며, 표시된 대기 구간만 압축했습니다”라고 밝힌다. Android 라이브 성공·현장 카메라 인식의 증거로 소개하지 않는다.
4. 시연 후에도 제품 worker·broker·터널은 유지한다. 이 도구는 자신이 연 임시 재생 서버와 Chrome만 닫는다.

## 2. 설치된 도구 확인

2026-10-07 확인:

- Windows PATH: ffmpeg/ffprobe 없음.
- WSL: `wsl.exe --exec which ffmpeg ffprobe` 결과 없음. 설치하지 않았다.
- Playwright 캐시: `C:\Users\USER\AppData\Local\ms-playwright\ffmpeg-1011\ffmpeg-win64.exe`, 버전 `n7.0.1-playwright-build-1011`.
- 캐시 ffmpeg는 VP8/WebM 녹화용 축소 빌드다. MP4/H.264 인코더·MP4 muxer·drawtext/subtitles 필터가 없어 일반적인 ffmpeg MP4 변환 명령은 사용할 수 없다.
- **기존 Chrome의 MediaRecorder**: H.264 MP4, VP8 WebM, canvas.captureStream 지원을 오프라인으로 확인했다. 설치된 `web/node_modules/playwright`를 사용한다. Chrome은 `--disable-gpu`로 실행하며 별도 패키지 설치가 없다.

따라서 실제 원본 영상을 로컬 브라우저에서 재생하고, 원본 화면 전체와 명시적 편집 자막을 캔버스에 기록한다. 새로운 제품 UI/답변을 만들거나 원본의 글자를 수정하지 않는다. 캡션은 영상 주변 여백에 표시한다. 보간 생성·가짜 화면·가짜 결과·새 추론은 없다.

**현재 검증은 문법과 브라우저 형식 지원뿐이다.** 실제 원본을 통한 디코딩·90초 인코딩·결과 보존 검수는 아직 수행하지 않았다.

## 3. p8 인계 입력

- 실제 서비스에서 녹화한 `raw.webm`의 절대 경로.
- 그 영상에 정확히 맞춘 `step-timing.json`의 절대 경로.
- 원본이 route mock/fixture 결과 영상이 아님을 확인한다. 그런 테스트 영상은 실증 백업으로 사용하지 않는다.
- 영상 시간 0부터 끝까지 순서대로 겹침·누락 없이 구간을 지정한다. 로그의 벽시계 시간을 무조건 영상 타임코드로 간주하지 않고 실제 영상을 대조한다.
- `action`: 클릭·질문·대상 확인. 항상 원속도.
- `result`: 결과·출처·모름·저장 카드가 읽히는 구간. 항상 원속도.
- `wait`: 답변 대기만 해당. 이 구간에만 `compressible: true`를 명시할 수 있다. 유의미한 화면 변화·사용자 조작이 있으면 action/result로 나눈다.
- 각 구간의 caption은 짧은 한 줄로 작성한다. 샘플 타이밍을 실측처럼 사용하지 않는다.
- Playwright recordVideo는 무음 백업으로 취급하고 발표자가 현장에서 설명한다. TTS가 들린다는 주장은 하지 않는다. 원본에 실제 오디오가 있으면 이 무음 변환 경로를 사용하지 않는다.

`step-timing.template.json`을 복사해서 실제 관측값으로 채운다. null/빈 배열 상태에서는 변환이 거부된다. 스키마:

```text
version: 1
source_kind: actual-browser-recording
contains_mock_results: false (실제 원본 확인 후)
sample_photo_demonstration: true 또는 false (실제 촬영 방식)
audio: none (Playwright 무음 녹화)
duration_seconds: 실제 원본 길이
segments: [
  {start: 시작초, end: 종료초, kind: action|result|wait,
   compressible: 대기 압축 허용 여부, caption: 실제 단계의 짧은 설명}
]
```

## 4. 준비된 정확한 실행 명령

PowerShell에서 아래 두 입력 변수만 p8가 전달한 실제 경로로 바꾼다. 출력은 이 demo 폴더에만 생성한다. 기존 출력은 덮어쓰지 않는다.

```powershell
Set-Location C:\Users\USER\Desktop\hangul-donghaeng
$demoTool = '.\docs\presentation\assets\demo\prepare-demo.cjs'
$rawVideo = 'C:\Users\USER\Desktop\hangul-donghaeng\.runtime\presentation-build\p8-demo.webm'
$stepTiming = 'C:\Users\USER\Desktop\hangul-donghaeng\.runtime\presentation-build\p8-step-timing.json'

# 원본 없이 가능: 설치된 Chrome 형식 지원만 재확인
node $demoTool --check-env

# 실제 입력 수령 후: 계획만 검토. 결과 파일명은 아래 최종 출력과 다르게 둔다.
node $demoTool --input $rawVideo --timings $stepTiming --out review-plan.mp4 --plan-only

# 원본 결과와 클릭 원속도 유지, 대기 압축 명시, 단계 설명 자막 포함
node $demoTool --input $rawVideo --timings $stepTiming --out backup-90s.mp4 --captions

# 단계 설명 자막 생략 시 --captions를 빼면 된다. 편집 사실 표시는 항상 남는다.
# MP4 지원이 사라진 환경은 기존 브라우저 WebM으로 명시적 대체
node $demoTool --input $rawVideo --timings $stepTiming --out backup-90s.webm --captions
```

MP4와 WebM을 동시에 돌리지 않는다. 각각 원본 재생을 약 90초 수행한다. 코드/환경 사전 검증만 하고 실제 영상 입력이 오기 전에는 인코딩을 시작하지 않는다.

## 5. 90초 편집 규칙

- 원본이 90초보다 길면 **명시된 대기 구간만** 같은 배속으로 압축한다. 나머지 구간은 자르거나 빠르게 만들지 않는다. 구간 전환에서 다음 구간의 시작 시각으로 돌아가므로 배속 대기 뒤 결과의 첫 부분을 건너뛰지 않는다.
- 원본이 짧으면 마지막 실제 화면을 유지하고 “마지막 실제 화면 유지”라고 표시한다. 이를 추가 실행 결과로 소개하지 않는다.
- 긴 원본은 재생 종료 오차를 고려해 89.5초까지 편집하고 남는 시간을 명시적으로 유지한다. 실제 출력 길이는 90초 ±1초 범위로 검사한다.
- 원속도 보호 구간이 89.5초 이상이거나 필요한 대기 배속이 16배보다 크면 중단한다. 결과를 임의로 잘라 맞추지 않는다. 더 짧은 실제 녹화 또는 정확한 대기 분리가 필요하다.
- 영상 상단에는 실제 화면 녹화/샘플 사진 여부와 대기 압축 여부를 계속 표시한다. 하단에는 현재 대기 배속 또는 원속도/최종 화면 유지 상태를 표시한다.
- 입력 원본 SHA256과 타이밍 SHA256, 출력 SHA256·길이·처리 구간·압축 배속을 sidecar에 남긴다. 원본 파일이 처리 중 바뀌면 결과를 승인하지 않는다.

## 6. 출력과 마지막 확인

- `backup-90s.mp4` 또는 `.webm`: 실제 영상 입력 후에만 생성.
- `.plan.json`: 원본→편집 타임라인 대응·배속·보존 길이.
- `.vtt`: 단계 자막 타임라인. 편집 고지 자체는 영상에 항상 포함.
- `.receipt.json`: 브라우저 디코딩 길이, 구간 끝 도달, 원본 불변 해시 검사 결과.

`READY_FOR_HUMAN_REVIEW`는 인코딩 구조 확인이다. 문화 기능 PASS가 아니다. root는 최종 파일을 처음부터 끝까지 재생해 장소/근거/확인/카드가 원본과 같은지, 기다림 압축 표시가 읽히는지, 마감 시점의 실제 구현 상태와 맞는지 확인한다. 원본과 영수증을 보존하며 샘플·fixture·사전 결과의 성격을 숨기지 않는다.

현재 대기 항목: p8 실제 raw WebM, 실제 단계 타이밍, root의 실측 범위. 이 준비 작업은 어떤 제품/모델 실행도 수행하지 않았다.