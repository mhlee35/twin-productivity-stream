import subprocess
import os
import cv2
import threading
import time
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from roboflow import Roboflow
import supervision as sv
from loguru import logger
import logging_config  # 로깅 설정 import

app = FastAPI()

# CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React 개발 서버
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(__file__)
PUBLIC = os.path.join(BASE_DIR, "public")

# 1️⃣ public 디렉터리를 정적 파일 루트로 마운트 (WebSocket 엔드포인트 이후에 마운트)

# WebSocket 연결 관리
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

# Roboflow 설정
rf = Roboflow(api_key="PIuczZS2mTaeUkmVtGFR")
project = rf.workspace().project("construction-vehicle-detection-pxc7c")
model = project.version(2).model

# 객체 감지 함수
def detect_objects_in_frame(frame):
    """프레임에서 객체를 감지하고 결과를 로깅하고 WebSocket으로 전송합니다."""
    try:
        # 프레임을 임시 파일로 저장
        temp_image_path = os.path.join(PUBLIC, "temp_frame.jpg")
        cv2.imwrite(temp_image_path, frame)
        
        # Roboflow로 객체 감지
        result = model.predict(temp_image_path, confidence=40, overlap=30).json()
        
        # 감지된 객체 정보 로깅 및 WebSocket 전송
        if result["predictions"]:
            detection_data = {
                "type": "object_detection",
                "timestamp": time.time(),
                "objects": []
            }
            
            for i, prediction in enumerate(result["predictions"]):
                x = prediction["x"]
                y = prediction["y"]
                width = prediction["width"]
                height = prediction["height"]
                confidence = prediction["confidence"]
                class_name = prediction["class"]
                
                # 로깅
                logger.info(f"객체 감지 #{i+1}: {class_name} - 좌표: ({x:.2f}, {y:.2f}), 크기: {width:.2f}x{height:.2f}, 신뢰도: {confidence:.2f}")
                
                # WebSocket 전송용 데이터
                detection_data["objects"].append({
                    "id": i + 1,
                    "class": class_name,
                    "confidence": confidence,
                    "bbox": {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height
                    }
                })
            
            # WebSocket으로 실시간 전송
            asyncio.run(manager.broadcast(json.dumps(detection_data)))
        else:
            logger.info("감지된 객체가 없습니다.")
            # 빈 결과도 전송
            empty_data = {
                "type": "object_detection",
                "timestamp": time.time(),
                "objects": []
            }
            asyncio.run(manager.broadcast(json.dumps(empty_data)))
            
        # 임시 파일 삭제
        if os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            
    except Exception as e:
        logger.error(f"객체 감지 중 오류 발생: {str(e)}")

# 실시간 객체 감지 스레드
def object_detection_thread():
    """실시간으로 RTSP 스트림에서 객체를 감지하는 스레드"""
    rtsp_url = "rtsp://localhost:8554/drone_footage"
    
    # RTSP 스트림 연결
    cap = cv2.VideoCapture(rtsp_url)
    
    if not cap.isOpened():
        logger.error("RTSP 스트림에 연결할 수 없습니다.")
        return
    
    logger.info("객체 감지 스레드가 시작되었습니다.")
    
    frame_count = 0
    detection_interval = 90  # 30프레임마다 객체 감지 (약 1초마다)
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.warning("프레임을 읽을 수 없습니다.")
                time.sleep(1)
                continue
            
            frame_count += 1
            
            # 일정 간격으로 객체 감지 수행
            if frame_count % detection_interval == 0:
                detect_objects_in_frame(frame)
            
            # 짧은 대기 시간
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        logger.info("객체 감지 스레드가 중단되었습니다.")
    except Exception as e:
        logger.error(f"객체 감지 스레드에서 오류 발생: {str(e)}")
    finally:
        cap.release()

# 2️⃣ 서버 시작 시 FFmpeg 프로세스 스폰 및 객체 감지 스레드 시작
@app.on_event("startup")
def start_hls():
    rtsp_url = "rtsp://localhost:8554/drone_footage"
    out_m3u8 = os.path.join(PUBLIC, "stream.m3u8")
    cmd = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", rtsp_url,
        "-c", "copy",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "3",
        "-hls_flags", "delete_segments",
        out_m3u8
    ]
    # 백그라운드에서 계속 실행
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    
    # 객체 감지 스레드 시작
    detection_thread = threading.Thread(target=object_detection_thread, daemon=True)
    detection_thread.start()
    logger.info("HLS 스트리밍과 객체 감지가 시작되었습니다.")

# WebSocket 엔드포인트
@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # 클라이언트로부터 메시지 수신 (필요시 처리)
            await manager.send_personal_message(f"Message received: {data}", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# API 엔드포인트들
@app.get("/api/stream-info")
async def get_stream_info():
    """스트림 정보를 반환합니다."""
    return {
        "stream_url": "/stream.m3u8",
        "status": "active",
        "format": "HLS"
    }

@app.get("/api/detection-status")
async def get_detection_status():
    """객체 감지 상태를 반환합니다."""
    return {
        "status": "active",
        "model": "construction-vehicle-detection-pxc7c",
        "confidence_threshold": 40,
        "overlap_threshold": 30
    }

# 정적 파일 마운트 (WebSocket 엔드포인트 이후에 배치)
app.mount("/", StaticFiles(directory=PUBLIC, html=True), name="static")