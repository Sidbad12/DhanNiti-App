"""
DhanNiti — WebSocket Manager
Manages active connections and broadcasts LangGraph progress 
to the Next.js frontend in real-time.
"""

import logging
from fastapi import WebSocket
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.running = False
        self.completed_nodes: List[str] = []
        self.current_node = ""

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total active: {len(self.active_connections)}")
        
        # If the recommendation pipeline is already running, sync the state to the new client
        if self.running:
            try:
                await websocket.send_json({"type": "system", "status": "running"})
                for node in self.completed_nodes:
                    await websocket.send_json({"type": "progress", "node": node})
            except Exception as e:
                logger.warning(f"Failed to send initial pipeline state to new connection: {e}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast JSON message to all connected clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to websocket, disconnecting: {e}")
                self.disconnect(connection)

# Global manager instance
manager = ConnectionManager()
