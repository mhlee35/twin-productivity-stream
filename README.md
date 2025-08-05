# 실시간 스트리밍 객체 감지 시스템

이 프로젝트는 RTSP 스트림을 받아서 HLS로 변환하고, 동시에 Roboflow를 사용하여 실시간 객체 감지를 수행하는 FastAPI 애플리케이션입니다.

## 기능

- RTSP 스트림을 HLS로 실시간 변환
- Roboflow 기반 실시간 객체 감지
- 감지 결과를 loguru를 통해 실시간 로깅
- 감지된 객체의 좌표, 크기, 신뢰도 정보 출력

## 설치

1. 의존성 설치:
```bash
pip install -r requirements.txt
```

2. FFmpeg 설치 (시스템에 따라):
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# Windows
# https://ffmpeg.org/download.html 에서 다운로드
```

## 설정

1. Roboflow API 키 설정:
   - `server.py` 파일에서 `api_key` 값을 본인의 Roboflow API 키로 변경
   - 프로젝트 이름과 버전을 본인의 모델에 맞게 수정

2. RTSP URL 설정:
   - `server.py` 파일에서 `rtsp_url`을 실제 RTSP 스트림 URL로 변경

## 실행

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

## 로그 출력 예시

```
2024-01-15 14:30:25 | INFO     | server:detect_objects_in_frame:35 - 객체 감지 #1: person - 좌표: (320.45, 180.23), 크기: 45.67x89.12, 신뢰도: 0.85
2024-01-15 14:30:26 | INFO     | server:detect_objects_in_frame:35 - 객체 감지 #1: forklift - 좌표: (450.12, 300.78), 크기: 120.34x80.56, 신뢰도: 0.92
```

## 주요 파일

- `server.py`: 메인 FastAPI 애플리케이션
- `logging_config.py`: loguru 로깅 설정
- `requirements.txt`: Python 의존성 목록
- `public/`: HLS 스트림 파일들이 저장되는 디렉토리

## 객체 감지 설정

- **감지 간격**: 30프레임마다 객체 감지 (약 1초마다)
- **신뢰도 임계값**: 40%
- **오버랩 임계값**: 30%

이 설정들은 `server.py`의 `detection_interval`과 `model.predict()` 파라미터에서 조정할 수 있습니다. 