# app/websocket_manager.py
import logging
from typing import Dict, List
from fastapi.websockets import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, user: str = "anonymous"):
        await websocket.accept()
        self.active_connections.append(websocket)
        
        if user not in self.user_connections:
            self.user_connections[user] = []
        self.user_connections[user].append(websocket)
        
        logger.info(f"WebSocket connection established for user '{user}'. Total: {len(self.active_connections)}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        
        for user, connections in self.user_connections.items():
            if websocket in connections:
                connections.remove(websocket)
                if not connections:
                    del self.user_connections[user]
                break
        
        logger.info(f"WebSocket connection closed. Total: {len(self.active_connections)}")
    
    async def send_personal_message(self, message: str, websocket: WebSocket):
        try:
            await websocket.send_text(message)
        except Exception:
            self.disconnect(websocket)
    
    async def send_to_user(self, message: str, user: str):
        if user in self.user_connections:
            disconnected = []
            for connection in self.user_connections[user]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)
            
            for connection in disconnected:
                self.disconnect(connection)
    
    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)
            
            for connection in disconnected:
                self.disconnect(connection)