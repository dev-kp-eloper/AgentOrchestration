import time
import pytest
import logging
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware
from src.api.middleware import LoggingMiddleware
from src.common.logging import request_id_var, StructuredFormatter, RequestIDFilter

class TestLoggingMiddleware:
    def setup_method(self):
        self.app = FastAPI()
        self.app.add_middleware(LoggingMiddleware)
        self.client = TestClient(self.app)
        
        # Captured log records
        self.log_records = []
        self.handler = logging.Handler()
        self.handler.emit = lambda record: self.log_records.append(record)
        self.handler.addFilter(RequestIDFilter())
        
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(self.handler)
        
        # StructuredFormatter instance
        self.formatter = StructuredFormatter()

    def teardown_method(self):
        root_logger = logging.getLogger()
        root_logger.removeHandler(self.handler)

    def test_request_id_generated_and_logged(self):
        @self.app.get("/test")
        async def handle():
            logging.getLogger("test").info("Inside request handler")
            return {"status": "ok"}

        response = self.client.get("/test")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        
        req_id = response.headers["X-Request-ID"]
        assert len(req_id) > 0

        # Check logs
        handler_logs = [r for r in self.log_records if r.name == "test"]
        assert len(handler_logs) == 1
        
        formatted = self.formatter.format(handler_logs[0])
        assert req_id in formatted

    def test_custom_request_id_respected(self):
        @self.app.get("/test-custom")
        async def handle():
            logging.getLogger("test").info("Inside custom request handler")
            return {"status": "ok"}

        response = self.client.get("/test-custom", headers={"X-Request-ID": "custom-req-123"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "custom-req-123"

        handler_logs = [r for r in self.log_records if r.name == "test"]
        assert len(handler_logs) == 1
        
        formatted = self.formatter.format(handler_logs[0])
        assert "custom-req-123" in formatted

    def test_background_task_inherits_request_id(self):
        def bg_task():
            # Sync background task log
            logging.getLogger("bg").info("Inside background task")

        @self.app.get("/test-bg")
        async def handle(background_tasks: BackgroundTasks):
            background_tasks.add_task(bg_task)
            return {"status": "ok"}

        response = self.client.get("/test-bg")
        assert response.status_code == 200
        req_id = response.headers["X-Request-ID"]

        # Filter logs for 'bg' logger
        bg_logs = [r for r in self.log_records if r.name == "bg"]
        assert len(bg_logs) == 1
        
        formatted = self.formatter.format(bg_logs[0])
        assert req_id in formatted
